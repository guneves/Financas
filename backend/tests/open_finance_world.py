"""Um Pluggy de mentira para os testes de Open Finance (043).

`FakePluggy` tem os metodos do `pluggy_client.PluggyClient` que o servico usa,
com itens, contas e transacoes em dicionarios; registra cada chamada. Os
formatos das transacoes seguem o sandbox (Pluggy Bank, 2026-10-27): na conta,
DEBIT negativo e CREDIT positivo; no cartao, as compras negativas com type
CREDIT (o contrario do que a doc diz — `card_tx(..., docs_sign=True)` da o da doc).
"""

import importlib
import uuid

import pytest

import pluggy_client


def pluggy_id():
    return str(uuid.uuid4())


def day_iso(day, hour_utc=3):
    """Uma data da Pluggy: T03:00:00.000Z e a meia-noite em -03:00 (sandbox)."""
    return f"{day}T{hour_utc:02d}:00:00.000Z"


def bank_tx(amount, day, description="COMPRA PADARIA", category_id=None, category=None, tx_id=None, status="POSTED",
            payment_method=None, counterparty=None, doc=None, operation_type=None):
    payment = None
    if payment_method or counterparty or doc:
        side = {"name": counterparty, "documentNumber": {"type": "CPF", "value": doc} if doc else None}
        payment = {"paymentMethod": payment_method, "payer": side, "receiver": side}
    return {
        "id": tx_id or pluggy_id(),
        "description": description,
        "amount": amount,
        "currencyCode": "BRL",
        "date": day_iso(day),
        "type": "DEBIT" if amount < 0 else "CREDIT",
        "status": status,
        "category": category,
        "categoryId": category_id,
        "operationType": operation_type,
        "paymentData": payment,
        "creditCardMetadata": None,
    }


def card_tx(amount, day, description="LOJA", category_id=None, tx_id=None, installment=None, total_installments=None,
            total_amount=None, purchase_date=None, docs_sign=False, status="POSTED"):
    """`amount` positivo = uma compra. Sandbox: chega negativo com type CREDIT;
    docs_sign: positivo, type DEBIT."""
    signed = amount if docs_sign else -amount
    metadata = None
    if installment or purchase_date:
        metadata = {
            "installmentNumber": installment,
            "totalInstallments": total_installments,
            "totalAmount": (None if total_amount is None else (total_amount if docs_sign else -total_amount)),
            "purchaseDate": purchase_date,
        }
    return {
        "id": tx_id or pluggy_id(),
        "description": description,
        "amount": signed,
        "currencyCode": "BRL",
        "date": day_iso(day),
        "type": ("DEBIT" if signed > 0 else "CREDIT") if docs_sign else "CREDIT",
        "status": status,
        "category": None,
        "categoryId": category_id,
        "creditCardMetadata": metadata,
        "paymentData": None,
    }


class FakePluggy:
    configured = True

    def __init__(self):
        self.items = {}
        self.accounts = {}
        self.transactions = {}
        self.investments = {}
        self.investment_transactions = {}
        self.calls = []

    # -- montar o mundo --------------------------------------------------

    def add_item(self, connector_name="Itaú", status="UPDATED", execution_status="SUCCESS", error=None):
        item_id = pluggy_id()
        self.items[item_id] = {
            "id": item_id,
            "status": status,
            "executionStatus": execution_status,
            "error": error,
            # Longe no passado: nenhum teste depende do relogio de verdade para
            # o intervalo de 1 h entre pedidos de atualizacao.
            "lastUpdatedAt": "2026-01-01T12:00:00.000Z",
            "connector": {"id": 201, "name": connector_name},
        }
        self.accounts[item_id] = []
        return item_id

    def add_account(self, item_id, kind="BANK", name="Conta Corrente", number="0001/12345-0", balance=1000.0,
                    subtype=None):
        account_id = pluggy_id()
        self.accounts[item_id].append({
            "id": account_id, "type": kind,
            "subtype": subtype or ("CHECKING_ACCOUNT" if kind == "BANK" else "CREDIT_CARD"),
            "name": name, "number": number, "balance": balance, "currencyCode": "BRL",
        })
        self.transactions[account_id] = []
        return account_id

    def add_tx(self, account_id, *txs):
        self.transactions[account_id].extend(txs)
        return txs[0]["id"] if len(txs) == 1 else [tx["id"] for tx in txs]

    def add_position(self, item_id, code, quantity, kind="EQUITY", subtype="STOCK", value=10.0, day="2026-10-26",
                     name=None):
        """Uma posicao da corretora (`GET /investments`), como o MeuPluggy manda
        a do BTG (2026-10-27): renda variavel e EQUITY/STOCK, a data e D-1."""
        investment_id = pluggy_id()
        self.investments.setdefault(item_id, []).append({
            "id": investment_id, "code": code, "name": name or code, "type": kind, "subtype": subtype,
            "quantity": quantity, "value": value, "balance": round(quantity * value, 2), "status": "ACTIVE",
            "date": day_iso(day), "currencyCode": "BRL",
        })
        self.investment_transactions[investment_id] = []
        return investment_id

    def add_operation(self, investment_id, kind, quantity, price, trade_day, op_id=None, expenses=None):
        amount = round(quantity * price, 2)
        fee = sum(expenses.values()) if isinstance(expenses, dict) else (expenses or 0)
        row = {
            "type": kind, "quantity": quantity, "value": price, "amount": amount,
            "netAmount": amount + fee if kind == "BUY" else amount - fee,
            "tradeDate": day_iso(trade_day), "date": day_iso(trade_day), "expenses": expenses,
        }
        if op_id is not False:
            row["id"] = op_id or pluggy_id()
        self.investment_transactions[investment_id].append(row)
        return row.get("id")

    def drop_tx(self, account_id, tx_id):
        self.transactions[account_id] = [tx for tx in self.transactions[account_id] if tx["id"] != tx_id]

    # -- a API que o servico usa -----------------------------------------

    def create_connect_token(self, item_id=None, client_user_id=None):
        self.calls.append(("connect_token", item_id, client_user_id))
        return "connect-token-de-teste"

    def get_item(self, item_id):
        self.calls.append(("get_item", item_id))
        if getattr(self, "fail_with", None):
            raise self.fail_with
        if item_id not in self.items:
            raise pluggy_client.PluggyError("Item nao encontrado.", status=404)
        return dict(self.items[item_id])

    def delete_item(self, item_id):
        self.calls.append(("delete_item", item_id))
        return self.items.pop(item_id, None) is not None

    def list_accounts(self, item_id):
        self.calls.append(("list_accounts", item_id))
        return [dict(account) for account in self.accounts.get(item_id, [])]

    def list_transactions(self, account_id, date_from, date_to=None):
        self.calls.append(("list_transactions", account_id, date_from))
        return [dict(tx) for tx in self.transactions.get(account_id, []) if tx["date"][:10] >= date_from]

    def list_investments(self, item_id):
        self.calls.append(("list_investments", item_id))
        return [dict(row) for row in self.investments.get(item_id, [])]

    def list_investment_transactions(self, investment_id):
        self.calls.append(("list_investment_transactions", investment_id))
        return [dict(row) for row in self.investment_transactions.get(investment_id, [])]

    def windows(self, account_id):
        return [call[2] for call in self.calls if call[0] == "list_transactions" and call[1] == account_id]


@pytest.fixture()
def open_finance_module(app_module):
    return importlib.import_module("services.open_finance")


@pytest.fixture()
def fake_pluggy(open_finance_module, invoices_module, monkeypatch):
    fake = FakePluggy()
    open_finance_module.set_client(fake)
    # Hoje e 27/10/2026: a primeira busca (30 dias) comeca em 27/09.
    monkeypatch.setattr(invoices_module, "local_today", lambda: __import__("datetime").date(2026, 10, 27))
    yield fake
    open_finance_module.set_client(None)


class World:
    def __init__(self, client, auth, fake):
        self.client = client
        self.auth = auth
        self.fake = fake

    def call(self, method, path, expected=(200, 201), **kwargs):
        response = getattr(self.client, method)(path, headers=self.auth, **kwargs)
        codes = expected if isinstance(expected, tuple) else (expected,)
        assert response.status_code in codes, (response.status_code, response.get_data(as_text=True))
        return response.get_json()

    def account(self, name="Itaú", type_="CHECKING", institution=None, **extra):
        body = {"name": name, "type": type_, **extra}
        if institution:
            body["institution"] = institution
        return self.call("post", "/api/accounts", json=body)["id"]

    def card(self, name="Itaú Visa", **extra):
        body = {"name": name, "due_day": 10, "closing_day": 3, **extra}
        return self.call("post", "/api/credit-cards", json=body)["id"]

    def overview(self):
        return self.call("get", "/api/open-finance")

    def connect(self, pluggy_item_id, expected=201):
        return self.call("post", "/api/open-finance/items", expected=expected, json={"pluggy_item_id": pluggy_item_id})

    def map(self, of_account_id, expected=200, **target):
        return self.call("put", f"/api/open-finance/accounts/{of_account_id}", expected=expected, json=target)

    def sync(self, item_id, expected=200):
        return self.call("post", f"/api/open-finance/items/{item_id}/sync", expected=expected)

    def pending(self):
        return self.call("get", "/api/inbox")["items"]

    def decided(self):
        return self.call("get", "/api/inbox?view=decided")["items"]

    def approve(self, item, expected=200, **payload):
        return self.call(
            "post", f"/api/inbox/{item['id']}/approve", expected=expected, json={"version": item["version"], **payload},
        )

    def transactions(self, account_id=None):
        rows = self.call("get", "/api/transactions")
        return [row for row in rows if account_id is None or row["account_id"] == account_id]

    def card_rows(self, card_id):
        return [row for row in self.call("get", "/api/cc-expenses") if row["card_id"] == card_id]


def connected(world, *, connector_name="Itaú", bank=True, card=False):
    """Um item da Pluggy com uma conta (e/ou um cartao), conectado e mapeado.
    Devolve (item_id nosso, {"bank": (pluggy_id, of_id, account_id), "card": (...)})."""
    fake = world.fake
    pluggy_item = fake.add_item(connector_name)
    made = {}
    if bank:
        made["bank"] = [fake.add_account(pluggy_item, "BANK", number="0001/12345-0")]
    if card:
        made["card"] = [fake.add_account(pluggy_item, "CREDIT", name="Mastercard Black", number="9437", balance=-838.5)]
    body = world.connect(pluggy_item)
    item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
    accounts = {entry["number"]: entry for entry in item["accounts"]}
    if bank:
        account_id = world.account(f"{connector_name} conta {uuid.uuid4().hex[:4]}")
        of_id = accounts["0001/12345-0"]["id"]
        world.map(of_id, account_id=account_id)
        made["bank"] += [of_id, account_id]
    if card:
        card_id = world.card(f"{connector_name} Black {uuid.uuid4().hex[:4]}")
        of_id = accounts["9437"]["id"]
        world.map(of_id, card_id=card_id)
        made["card"] += [of_id, card_id]
    return body["item_id"], pluggy_item, made
