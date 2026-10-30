"""Aprovar x Recorrentes (034): a notificacao da assinatura ou do salario faz a
ocorrencia da recorrencia.

O que estes testes protegem:

- um item de Aprovar mostra a ocorrencia de recorrencia que ele parece ser
  (mesmo tipo, ate RECURRING_MATCH_DAYS dias, valor exato ou o nome batendo com
  o valor perto; numa receita, o valor perto basta), e nada e gravado antes de
  aprovar;
- aprovar grava o lancamento da notificacao e da a ocorrencia como feita: ela
  nao e pendente, sai da previsao e o /run nao grava outra (nada contado duas
  vezes);
- "nao e esta recorrencia" vale tambem para o "Aprovar todos";
- uma ocorrencia feita nao e sugerida de novo, uma pausada nem a de outro
  usuario nunca.
"""

import importlib

import pytest

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

from test_inbox import (
    approve,
    card_rows,
    create_account,
    create_card,
    decided,
    detection,
    ms,
    patch,
    pending,
    rows,
    send,
)


def create_recurring(client, auth, **overrides):
    payload = {
        "amount": 55.90,
        "type": "EXPENSE",
        "category": "Assinaturas",
        "description": "Netflix",
        "frequency": "MONTHLY",
        "start_date": "2026-10-05",
    }
    payload.update(overrides)
    response = client.post("/api/recurring", json=payload, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def recurring_item(client, auth, recurring_id):
    items = client.get("/api/recurring", headers=auth).get_json()["items"]
    return next(item for item in items if item["id"] == recurring_id)


def run(client, auth, through):
    response = client.post("/api/recurring/run", json={"through": through}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def recurring_rows_of(client, auth, recurring_id):
    return [
        item for item in rows(client, auth)
        if item.get("source_type") == "RECURRING_TRANSACTION"
        and str(item.get("source_id") or "").startswith(f"{recurring_id}:")
    ]


def netflix(at=None, amount_cents=5590, **extra):
    return detection("CREDIT_PURCHASE", amount_cents, at or ms(2026, 10, 5, 3), merchant="NETFLIX.COM", **extra)


def salary(at=None, amount_cents=852340):
    return detection(
        "PIX_IN", amount_cents, at or ms(2026, 10, 6, 9), app="com.itau",
        counterparty="EMPRESA EXEMPLO LTDA", counterparty_doc="12345678",
    )


@pytest.fixture()
def card(client, auth):
    return create_card(client, auth, "Itaú Visa")


@pytest.fixture()
def account(client, auth):
    return create_account(client, auth, "Itaú")


class TestSuggestion:
    def test_a_subscription_purchase_shows_the_occurrence_it_settles(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        assert item["recurring"]["recurring_id"] == rec["id"]
        assert item["recurring"]["date"] == "2026-10-05"
        assert item["recurring"]["exact_amount"] is True
        assert item["recurring"]["settled"] is False
        assert item["recurring_off"] is False
        # Mostrar nao grava: a ocorrencia continua devendo.
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-10-05"

    def test_the_salary_matches_by_amount_even_in_the_employers_name(self, client, auth, account):
        rec = create_recurring(
            client, auth, type="INCOME", amount=8500, category="Salário", description="Salário",
            account_id=account,
        )
        send(client, auth, salary())
        [item] = pending(client, auth)
        assert item["recurring"]["recurring_id"] == rec["id"]
        assert item["recurring"]["exact_amount"] is False

    def test_a_price_increase_still_matches_by_name(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix(amount_cents=5990))
        [item] = pending(client, auth)
        assert item["recurring"]["recurring_id"] == rec["id"]
        assert item["recurring"]["exact_amount"] is False

    def test_the_same_amount_matches_without_the_name(self, client, auth, card):
        rec = create_recurring(client, auth, description="Academia", amount=99.90, category="Saúde")
        send(client, auth, detection("CREDIT_PURCHASE", 9990, ms(2026, 10, 6), merchant="SMARTFIT"))
        [item] = pending(client, auth)
        assert item["recurring"]["recurring_id"] == rec["id"]

    @pytest.mark.parametrize("payload, notice", [
        # Despesa de outro valor sem o nome bater: nao e a assinatura.
        ({"description": "Academia", "amount": 99.90}, {"merchant": "PADARIA", "amount_cents": 9000}),
        # O nome bate, mas o valor esta longe demais.
        ({}, {"amount_cents": 9990}),
        # Longe demais da data.
        ({}, {"at": ms(2026, 10, 20)}),
    ])
    def test_no_suggestion_when_amount_name_or_date_do_not_fit(self, client, auth, card, payload, notice):
        create_recurring(client, auth, **payload)
        send(client, auth, detection(
            "CREDIT_PURCHASE", notice.get("amount_cents", 5590), notice.get("at", ms(2026, 10, 5)),
            merchant=notice.get("merchant", "NETFLIX.COM"),
        ))
        [item] = pending(client, auth)
        assert item["recurring"] is None

    def test_an_income_never_settles_an_expense(self, client, auth, account):
        create_recurring(client, auth, amount=8523.40, description="Aluguel", category="Moradia")
        send(client, auth, salary())
        [item] = pending(client, auth)
        assert item["recurring"] is None

    def test_a_paused_recurrence_is_never_suggested(self, client, auth, card):
        rec = create_recurring(client, auth)
        client.patch(f"/api/recurring/{rec['id']}", json={"active": False}, headers=auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        assert item["recurring"] is None

    def test_another_users_recurrence_is_never_suggested(self, client, auth, other_user, card):
        create_recurring(client, other_user["headers"])
        send(client, auth, netflix())
        [item] = pending(client, auth)
        assert item["recurring"] is None


class TestApproving:
    def test_approving_settles_the_occurrence_and_run_writes_nothing(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        body = approve(client, auth, item)
        assert body["state"] == "APPROVED"
        assert body["recurring"]["settled"] is True and body["recurring"]["date"] == "2026-10-05"

        assert len(card_rows(client, auth, card)) == 1
        after = recurring_item(client, auth, rec["id"])
        assert after["next_run_date"] == "2026-11-05"
        assert after["last_occurrence_date"] == "2026-10-05"

        result = run(client, auth, "2026-10-31")
        assert result["created"] == 0
        assert recurring_rows_of(client, auth, rec["id"]) == []

        forecast = client.get("/api/recurring/forecast?days=365", headers=auth).get_json()
        assert all(entry["date"] != "2026-10-05" for entry in forecast["occurrences"] if entry["recurring_id"] == rec["id"])

        [done] = decided(client, auth)
        assert done["recurring"]["recurring_id"] == rec["id"]

    def test_the_lancamento_takes_the_recurrences_category_when_no_rule_named_one(self, client, auth, card):
        create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        assert item["category"] == "Outros"
        approve(client, auth, item)
        [purchase] = card_rows(client, auth, card)
        assert purchase["category"] == "Assinaturas"
        assert purchase["amount"] == 55.90

    def test_an_edited_category_stays(self, client, auth, card):
        create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        approve(client, auth, item, category="Lazer")
        [purchase] = card_rows(client, auth, card)
        assert purchase["category"] == "Lazer"

    def test_the_salary_settles_with_the_real_amount(self, client, auth, account):
        rec = create_recurring(
            client, auth, type="INCOME", amount=8500, category="Salário", description="Salário",
            start_date="2026-10-05", account_id=account,
        )
        send(client, auth, salary())
        [item] = pending(client, auth)
        approve(client, auth, item, account_id=account)
        incomes = [row for row in rows(client, auth, account) if row["type"] == "INCOME"]
        assert [row["amount"] for row in incomes] == [8523.40]
        assert incomes[0]["category"] == "Salário"
        assert run(client, auth, "2026-10-31")["created"] == 0
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-11-05"

    def test_a_settled_occurrence_after_a_pending_one_is_skipped_by_run(self, client, auth, card):
        rec = create_recurring(client, auth, start_date="2026-09-05")
        send(client, auth, netflix())
        [item] = pending(client, auth)
        assert item["recurring"]["date"] == "2026-10-05"
        approve(client, auth, item)
        # Setembro continua devendo: o cursor nao pula ele.
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-09-05"
        result = run(client, auth, "2026-10-31")
        assert result["created"] == 1 and result["already_existed"] == 1
        assert [row["date"] for row in recurring_rows_of(client, auth, rec["id"])] == ["2026-09-05"]
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-11-05"

    def test_a_settled_occurrence_is_not_suggested_again(self, client, auth, card):
        create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        approve(client, auth, item)
        send(client, auth, netflix(at=ms(2026, 10, 7)))
        [second] = pending(client, auth)
        assert second["recurring"] is None

    def test_not_this_recurrence_holds_for_approve_all(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        item = patch(client, auth, item, card_id=card, recurring=False)
        assert item["recurring_off"] is True
        assert item["recurring"]["recurring_id"] == rec["id"]  # ainda mostrado, para desfazer
        response = client.post("/api/inbox/approve-ready", json={"ids": [item["id"]]}, headers=auth)
        assert response.get_json()["approved"] == [item["id"]]
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-10-05"
        [done] = decided(client, auth)
        assert done["recurring"] is None

    def test_undoing_not_this_recurrence(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        item = patch(client, auth, item, recurring=False)
        item = patch(client, auth, item, recurring=True)
        assert item["recurring_off"] is False
        approve(client, auth, item)
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-11-05"

    def test_approve_with_recurring_false_settles_nothing(self, client, auth, card):
        rec = create_recurring(client, auth)
        send(client, auth, netflix())
        [item] = pending(client, auth)
        approve(client, auth, item, recurring=False)
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-10-05"

    def test_a_stale_choice_is_refused_and_nothing_is_written(self, client, auth, card):
        rec = create_recurring(client, auth)
        run(client, auth, "2026-10-05")  # o /run ja gravou a ocorrencia
        send(client, auth, netflix(amount_cents=5990))
        [item] = pending(client, auth)
        assert item["recurring"] is None
        approve(client, auth, item, expected=400, recurring={"recurring_id": rec["id"], "date": "2026-10-05"})
        assert card_rows(client, auth, card) == []
        assert pending(client, auth)[0]["state"] == "PENDING"

    def test_a_transfer_never_settles(self, app_module):
        services_recurring = importlib.import_module("services.recurring")
        assert services_recurring.recurring_type_of_item({"entry_type": "TRANSFER", "direction": "OUT"}) is None

    def test_its_this_one_settles_the_occurrence_too(self, client, auth, account):
        rec = create_recurring(client, auth, description="Academia", amount=99.90, category="Saúde", account_id=account)
        typed = client.post(
            "/api/transactions",
            json={"account_id": account, "amount": 99.90, "date": "2026-10-05", "type": "EXPENSE",
                  "category": "Saúde", "description": "Academia"},
            headers=auth,
        )
        assert typed.status_code in (200, 201), typed.get_data(as_text=True)
        send(client, auth, detection("DEBIT_PURCHASE", 9990, ms(2026, 10, 5), merchant="SMARTFIT"))
        [item] = pending(client, auth)
        assert item["candidates"] and item["recurring"]["recurring_id"] == rec["id"]
        candidate = item["candidates"][0]
        approve(client, auth, item, candidate={"table": candidate["table"], "id": candidate["id"]})
        assert recurring_item(client, auth, rec["id"])["next_run_date"] == "2026-11-05"
