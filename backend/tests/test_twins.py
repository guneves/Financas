"""Gemeos: "2× igual" (design §3.5, decisao 4; services/twins.py).

Duas compras iguais de verdade ficam duas (I2) e ganham um selo neutro no
Extrato e no Revisar: mesma conta (ou cartao), mesmos centavos, mesma descricao
normalizada, ate 60 min (mesma data sem hora). Sem cartao de atencao, sem acao.
"""

import importlib

import pytest

from test_auto_record import notifications_on
from test_inbox import ITAU, create_account, create_card, detection, ms, send

pytestmark = pytest.mark.usefixtures("any_bank_notifications")


@pytest.fixture()
def itau(client, auth):
    notifications_on(client, auth)
    return create_account(client, auth, "Itaú")


def coffee(client, auth, hour, minute, merchant="CAFE DO PONTO", cents=800, day=21):
    send(client, auth, detection("DEBIT_PURCHASE", cents, at=ms(2026, 10, day, hour, minute), app=ITAU,
                                 merchant=merchant))


def flags(client, auth, query=""):
    body = client.get(f"/api/transactions{query}", headers=auth).get_json()
    items = body["items"] if isinstance(body, dict) else body
    return sorted((row["amount"], row["twin"]) for row in items)


def review_flags(client, auth):
    items = client.get("/api/review", headers=auth).get_json()["items"]
    return sorted((item["amount"], item["twin"]) for item in items)


class TestTransactions:
    def test_two_coffees_four_minutes_apart(self, client, auth, itau):
        coffee(client, auth, 8, 0)
        coffee(client, auth, 8, 4)
        assert flags(client, auth) == [(8.0, True), (8.0, True)]
        assert flags(client, auth, "?limit=50") == [(8.0, True), (8.0, True)]
        assert review_flags(client, auth) == [(8.0, True), (8.0, True)]

    def test_two_hours_apart_are_not_twins(self, client, auth, itau):
        coffee(client, auth, 8, 0)
        coffee(client, auth, 10, 0)
        assert flags(client, auth) == [(8.0, False), (8.0, False)]
        assert review_flags(client, auth) == [(8.0, False), (8.0, False)]

    def test_another_merchant_is_not_a_twin(self, client, auth, itau):
        coffee(client, auth, 8, 0)
        coffee(client, auth, 8, 4, merchant="PADARIA BOM PAO")
        assert flags(client, auth) == [(8.0, False), (8.0, False)]

    def test_other_cents_are_not_twins(self, client, auth, itau):
        coffee(client, auth, 8, 0)
        coffee(client, auth, 8, 4, cents=850)
        assert flags(client, auth) == [(8.0, False), (8.5, False)]

    def test_another_account_is_not_a_twin(self, client, auth, itau):
        other = create_account(client, auth, "Outra")
        for account in (itau, other):
            response = client.post("/api/transactions", headers=auth, json={
                "amount": 8, "date": "2026-10-21", "type": "EXPENSE", "description": "Cafe", "account_id": account,
                "category": "Alimentação",
            })
            assert response.status_code == 201
        assert flags(client, auth) == [(8.0, False), (8.0, False)]

    def test_typed_without_time_same_day_are_twins(self, client, auth, itau):
        for _ in range(2):
            response = client.post("/api/transactions", headers=auth, json={
                "amount": 8, "date": "2026-10-21", "type": "EXPENSE", "description": "Cafe", "account_id": itau,
                "category": "Alimentação",
            })
            assert response.status_code == 201
        assert flags(client, auth) == [(8.0, True), (8.0, True)]

    def test_income_is_never_a_twin(self, client, auth, itau):
        for _ in range(2):
            client.post("/api/transactions", headers=auth, json={
                "amount": 8, "date": "2026-10-21", "type": "INCOME", "description": "Pix", "account_id": itau,
                "category": "Receita",
            })
        assert flags(client, auth) == [(8.0, False), (8.0, False)]

    def test_a_twin_on_the_next_page_still_counts(self, client, auth, itau):
        coffee(client, auth, 8, 0)
        coffee(client, auth, 8, 4)
        body = client.get("/api/transactions?limit=1", headers=auth).get_json()
        assert [row["twin"] for row in body["items"]] == [True]

    def test_another_users_coffee_is_not_a_twin(self, client, auth, itau, other_user):
        coffee(client, auth, 8, 0)
        notifications_on(client, other_user["headers"])
        create_account(client, other_user["headers"], "Itaú")
        coffee(client, other_user["headers"], 8, 4)
        assert flags(client, auth) == [(8.0, False)]


class TestCards:
    def purchase(self, client, auth, card, description="LOJA BOA", total=90, installments=3):
        response = client.post("/api/cc-expenses/purchases", headers=auth, json={
            "card_id": card, "total_amount": total, "purchase_date": "2026-10-21", "description": description,
            "installments": installments, "category": "Compras",
        })
        assert response.status_code == 201, response.get_data(as_text=True)

    def statement(self, client, auth):
        return sorted(
            (row["amount"], row["twin"])
            for row in client.get("/api/cc-expenses/statement", headers=auth).get_json()
        )

    def test_two_identical_card_purchases_are_twins(self, client, auth):
        card = create_card(client, auth)
        self.purchase(client, auth, card)
        self.purchase(client, auth, card)
        assert self.statement(client, auth) == [(90.0, True), (90.0, True)]

    def test_another_description_is_not_a_twin(self, client, auth):
        card = create_card(client, auth)
        self.purchase(client, auth, card)
        self.purchase(client, auth, card, description="OUTRA LOJA")
        assert self.statement(client, auth) == [(90.0, False), (90.0, False)]

    def test_another_card_is_not_a_twin(self, client, auth):
        self.purchase(client, auth, create_card(client, auth, "Um"))
        self.purchase(client, auth, create_card(client, auth, "Dois"))
        assert self.statement(client, auth) == [(90.0, False), (90.0, False)]

    def test_card_twins_in_review(self, client, auth, itau):
        card = create_card(client, auth)
        send(client, auth, detection("CREDIT_PURCHASE", 4590, at=ms(2026, 10, 21, 14, 0), app=ITAU, merchant="LOJA"))
        send(client, auth, detection("CREDIT_PURCHASE", 4590, at=ms(2026, 10, 21, 14, 20), app=ITAU, merchant="LOJA"))
        rows = client.get("/api/cc-expenses/statement", headers=auth).get_json()
        assert [(row["card_id"], row["twin"]) for row in rows] == [(card, True), (card, True)]
        assert review_flags(client, auth) == [(45.9, True), (45.9, True)]


def _twins():
    return importlib.import_module("services.twins")


class TestPure:
    @pytest.mark.parametrize("a, b, expected", [
        ("2026-10-21T08:00:00-03:00", "2026-10-21T08:59:00-03:00", True),
        ("2026-10-21T08:00:00-03:00", "2026-10-21T09:01:00-03:00", False),
        ("2026-10-21T08:00:00-03:00", "2026-10-21T11:30:00Z", True),
        ("2026-10-21", "2026-10-21T08:00:00-03:00", True),
        ("2026-10-21", "2026-10-22", False),
        (None, None, True),
    ])
    def test_close_in_time(self, a, b, expected):
        day_a, day_b = (a or "2026-10-21")[:10], (b or "2026-10-21")[:10]
        assert _twins().close_in_time(day_a, a, day_b, b) is expected

    def test_twin_keys_groups_by_target_cents_and_text(self):
        base = {"target": "acc", "cents": 800, "description": "Café do Ponto", "date": "2026-10-21", "occurred_at": None}
        entries = [
            {**base, "key": 1}, {**base, "key": 2, "description": "CAFE DO PONTO"},
            {**base, "key": 3, "cents": 801}, {**base, "key": 4, "target": "other"},
        ]
        assert _twins().twin_keys(entries) == {1, 2}
