"""Aplicar regras de importacao a lancamentos ja gravados.

O que estes testes fixam:

- a previa lista so o que mudaria de categoria e nao grava nada;
- /apply so mexe nos ids confirmados, e confere cada um de novo contra a regra
  (um id que a regra ja nao muda e pulado, nao forcado);
- com `rule_id`, so aquela regra; sem, a ordem de prioridade da importacao;
- transferencias, dinheiro de investimento e pagamento de fatura ficam fora;
- `category` e `category_id` mudam juntos, e `hits` conta o que mudou;
- nada de outro usuario entra na previa nem no /apply.
"""


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 27.9,
        "date": "2026-09-03",
        "category": "Outros",
        "description": "UBER * TRIP",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_rule(client, headers, **overrides):
    payload = {"pattern": "uber", "category": "Transporte"}
    payload.update(overrides)
    response = client.post("/api/import-rules", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def apply_preview(client, headers, **payload):
    return client.post("/api/import-rules/apply/preview", json=payload, headers=headers)


def apply(client, headers, ids, **payload):
    return client.post(
        "/api/import-rules/apply", json={"transaction_ids": ids, **payload}, headers=headers
    )


def get_transaction(client, headers, item_id):
    return next(
        item for item in client.get("/api/transactions", headers=headers).get_json()
        if item["id"] == item_id
    )


def category_id(client, headers, name):
    return next(
        item["id"] for item in client.get("/api/categories", headers=headers).get_json()
        if item["name"] == name
    )


def test_preview_lists_what_would_change_and_writes_nothing(client, auth):
    create_rule(client, auth)
    uber = create_transaction(client, auth)
    create_transaction(client, auth, description="Padaria", category="Alimentação")

    body = apply_preview(client, auth).get_json()
    assert [item["id"] for item in body["items"]] == [uber["id"]]
    assert body["items"][0]["category"] == "Outros"
    assert body["items"][0]["new_category"] == "Transporte"
    assert body["total"] == 1
    assert get_transaction(client, auth, uber["id"])["category"] == "Outros"


def test_a_row_already_in_the_rule_category_is_not_a_candidate(client, auth):
    create_rule(client, auth)
    create_transaction(client, auth, category="Transporte")
    assert apply_preview(client, auth).get_json()["items"] == []


def test_apply_rewrites_name_and_id_and_counts_hits(client, auth):
    rule = create_rule(client, auth)
    uber = create_transaction(client, auth)

    response = apply(client, auth, [uber["id"]])
    assert response.status_code == 200
    assert response.get_json() == {"updated": 1, "skipped": 0}

    item = get_transaction(client, auth, uber["id"])
    assert item["category"] == "Transporte"
    assert item["category_id"] == category_id(client, auth, "Transporte")
    rules = client.get("/api/import-rules", headers=auth).get_json()["items"]
    assert next(r for r in rules if r["id"] == rule["id"])["hits"] == 1


def test_apply_touches_only_the_confirmed_ids(client, auth):
    create_rule(client, auth)
    chosen = create_transaction(client, auth)
    left_alone = create_transaction(client, auth, date="2026-09-04")

    apply(client, auth, [chosen["id"]])
    assert get_transaction(client, auth, chosen["id"])["category"] == "Transporte"
    assert get_transaction(client, auth, left_alone["id"])["category"] == "Outros"


def test_apply_skips_an_id_the_rule_no_longer_changes(client, auth):
    create_rule(client, auth)
    uber = create_transaction(client, auth)
    other = create_transaction(client, auth, description="Padaria")
    # Editado depois da previa: a descricao ja nao casa com a regra.
    client.patch(f"/api/transactions/{uber['id']}", json={"description": "Taxi"}, headers=auth)

    body = apply(client, auth, [uber["id"], other["id"]]).get_json()
    assert body == {"updated": 0, "skipped": 2}
    assert get_transaction(client, auth, uber["id"])["category"] == "Outros"


def test_apply_requires_a_list_of_ids(client, auth):
    create_rule(client, auth)
    create_transaction(client, auth)
    assert client.post("/api/import-rules/apply", json={}, headers=auth).status_code == 400
    assert apply(client, auth, []).status_code == 400
    assert apply(client, auth, [123]).status_code == 400


def test_one_rule_only_uses_that_rule(client, auth):
    create_rule(client, auth)
    padaria = create_rule(client, auth, pattern="padaria", category="Alimentação")
    create_transaction(client, auth)
    bread = create_transaction(client, auth, description="Padaria do Ze")

    body = apply_preview(client, auth, rule_id=padaria["id"]).get_json()
    assert [item["id"] for item in body["items"]] == [bread["id"]]


def test_one_rule_applies_even_when_inactive(client, auth):
    rule = create_rule(client, auth)
    client.patch(f"/api/import-rules/{rule['id']}", json={"active": False}, headers=auth)
    uber = create_transaction(client, auth)

    assert apply_preview(client, auth).get_json()["items"] == []
    items = apply_preview(client, auth, rule_id=rule["id"]).get_json()["items"]
    assert [item["id"] for item in items] == [uber["id"]]


def test_all_rules_follow_import_priority(client, auth):
    create_rule(client, auth)
    create_rule(client, auth, pattern="uber * trip", category="Lazer", priority=10)
    create_transaction(client, auth)
    items = apply_preview(client, auth).get_json()["items"]
    assert items[0]["new_category"] == "Lazer"


def test_rule_direction_is_respected(client, auth):
    create_rule(client, auth, pattern="salario", category="Lazer", applies_to="EXPENSE")
    create_transaction(client, auth, description="Salario", type="INCOME", category="Receita")
    assert apply_preview(client, auth).get_json()["items"] == []


def test_transfers_and_investment_cash_are_never_recategorized(client, auth):
    savings = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()
    client.post(
        "/api/transactions",
        json={
            "amount": 50, "date": "2026-09-01", "type": "TRANSFER",
            "description": "uber reserva", "transfer_account_id": savings["id"],
        },
        headers=auth,
    )
    client.post(
        "/api/investments",
        json={
            "asset_class": "STOCKS", "ticker_or_name": "VALE3", "quantity": 5,
            "average_price": 60, "metadata": {"purchase_date": "2026-09-01"},
        },
        headers=auth,
    )
    cash = next(
        item for item in client.get("/api/transactions", headers=auth).get_json()
        if item["source_type"] == "INVESTMENT_TRANSACTION"
    )
    create_rule(client, auth)
    create_rule(client, auth, pattern=cash["description"], category="Lazer")

    assert apply_preview(client, auth).get_json()["items"] == []
    assert apply(client, auth, [cash["id"]]).get_json() == {"updated": 0, "skipped": 1}
    assert get_transaction(client, auth, cash["id"])["category"] == cash["category"]


def test_invoice_payments_are_never_recategorized(client, auth):
    """O pagamento de fatura nasce junto com o PAID dos itens; a regra nao mexe nele."""
    card = client.post(
        "/api/credit-cards", json={"name": "Cartao", "due_day": 10, "closing_day": 3}, headers=auth
    ).get_json()
    client.post(
        "/api/cc-expenses",
        json={
            "card_id": card["id"], "category": "Lazer", "description": "Compra",
            "amount": 80, "purchase_date": "2026-07-01", "invoice_month": 8,
            "invoice_year": 2026, "installment_info": "1/1",
        },
        headers=auth,
    )
    paid = client.post(
        "/api/cc-expenses/pay-invoice",
        json={"card_id": card["id"], "invoice_month": 8, "invoice_year": 2026},
        headers=auth,
    )
    assert paid.status_code in (200, 201), paid.get_data(as_text=True)
    payment = next(
        item for item in client.get("/api/transactions", headers=auth).get_json()
        if item["source_type"] == "CC_INVOICE_PAYMENT"
    )
    assert payment["description"] and payment["category"] != "Lazer"
    create_rule(client, auth, pattern=payment["description"], category="Lazer")

    assert apply_preview(client, auth).get_json()["items"] == []
    assert apply(client, auth, [payment["id"]]).get_json() == {"updated": 0, "skipped": 1}


def test_unknown_rule_is_404(client, auth):
    assert apply_preview(client, auth, rule_id="nao-existe").status_code == 404


def test_other_users_rows_and_rules_stay_out(client, auth, other_user):
    other = other_user["headers"]
    theirs = create_transaction(client, other)
    their_rule = create_rule(client, other)
    create_rule(client, auth)

    assert apply_preview(client, auth).get_json()["items"] == []
    assert apply_preview(client, auth, rule_id=their_rule["id"]).status_code == 404
    assert apply(client, auth, [theirs["id"]]).get_json() == {"updated": 0, "skipped": 1}
    assert get_transaction(client, other, theirs["id"])["category"] == "Outros"
