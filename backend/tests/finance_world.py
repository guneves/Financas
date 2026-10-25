"""Montagem comum de test_home.py, test_attention.py, test_cc_invoices.py e
test_cc_purchase_delete.py: contas, lancamentos, cartoes e o relogio.

Nao importa nenhum modulo do app no topo (conftest.py): o `World` recebe o
client e importa `db` e os servicos dentro dos metodos, depois do `app_module`.

O relogio e `local_today()`, congelado em cada modulo que o le (CLAUDE.md,
"patch where the name is read").
"""

import importlib
import uuid
from datetime import date

CLOCK_MODULES = (
    "services.invoices",
    "routes.cards",
    "services.card_invoices",
    "services.home",
    "services.home_panels",
    "services.attention",
    "routes.home",
)


class Clock:
    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value if isinstance(value, date) else date.fromisoformat(value)


def freeze(monkeypatch, value):
    clock = Clock(value)
    for name in CLOCK_MODULES:
        monkeypatch.setattr(importlib.import_module(name), "local_today", lambda: clock.value)
    return clock


class World:
    def __init__(self, client, user):
        self.client = client
        self.user = user
        self.auth = user["headers"]
        self.categories = None

    # -- API -----------------------------------------------------------------
    def call(self, method, path, expected=(200, 201), **kwargs):
        response = getattr(self.client, method)(path, headers=self.auth, **kwargs)
        if expected is not None:
            codes = expected if isinstance(expected, tuple) else (expected,)
            assert response.status_code in codes, f"{method} {path}: {response.status_code} {response.get_data(as_text=True)}"
        return response

    def get(self, path, **kwargs):
        return self.call("get", path, **kwargs).get_json()

    def home(self, months=None):
        query = {"months": months} if months is not None else {}
        return self.get("/api/home", query_string=query)

    def panels(self):
        return self.get("/api/home/panels")

    def attention(self):
        return self.get("/api/attention")["items"]

    def invoices(self):
        return self.get("/api/cc-invoices")

    def account(self, name, type_="CHECKING", initial=0, **extra):
        return self.call("post", "/api/accounts", json={
            "name": name, "type": type_, "initial_balance": initial, **extra,
        }).get_json()

    def archive_account(self, account):
        self.call("delete", f"/api/accounts/{account['id']}")

    def category_id(self, name):
        if self.categories is None:
            self.categories = {row["name"]: row["id"] for row in self.get("/api/categories") if not row.get("parent_id")}
        return self.categories[name]

    def tx(self, type_, amount, day, account, category="Outros", description="", **share):
        row = self.call("post", "/api/transactions", json={
            "type": type_, "amount": amount, "date": day, "account_id": account["id"],
            "category": category, "description": description,
        }).get_json()
        if share:
            row = self.call("patch", f"/api/transactions/{row['id']}", json=share).get_json()
        return row

    def transfer(self, amount, day, origin, target):
        return self.call("post", "/api/transfers", json={
            "amount": amount, "date": day, "account_id": origin["id"], "transfer_account_id": target["id"],
        }).get_json()

    def card(self, name="Nubank", due_day=10, closing_day=3, **extra):
        return self.call("post", "/api/credit-cards", json={
            "name": name, "due_day": due_day, "closing_day": closing_day, **extra,
        }).get_json()

    def purchase(self, card, total, day, description="Loja", installments=1, category="Alimentação"):
        return self.call("post", "/api/cc-expenses/purchases", json={
            "card_id": card["id"], "total_amount": total, "purchase_date": day,
            "description": description, "installments": installments, "category": category,
        }).get_json()

    def refund(self, card, amount, day, description="Estorno"):
        return self.call("post", "/api/cc-expenses/refunds", json={
            "card_id": card["id"], "amount": amount, "purchase_date": day, "description": description,
        }).get_json()

    def pay(self, card, month, year, account):
        return self.call("post", "/api/cc-expenses/pay-invoice", json={
            "card_id": card["id"], "invoice_month": month, "invoice_year": year, "account_id": account["id"],
        }).get_json()

    # -- linhas que a API so grava por outro caminho ---------------------------
    def insert_tx(self, type_, amount, day, account, *, source_type=None, category="Outros", target=None):
        db = importlib.import_module("db")
        row_id = f"t-{uuid.uuid4().hex[:12]}"
        with db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO transactions (id, user_id, account_id, transfer_account_id, amount, date,
                                          category, type, source_type, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row_id, self.user["id"], account["id"], target["id"] if target else None, amount, day,
                 category, type_, source_type, row_id if source_type else None),
            )
        return row_id

    def set_rows(self, sql, params=()):
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(sql, params)
