"""Axis 4: an investment movement reaches the cash statement only when asked.

A movement that carries `metadata.cash_account_id` has exactly one lançamento
in that account — a buy is an EXPENSE, a sale or redemption an INCOME — linked
by `source_type = 'INVESTMENT_TRANSACTION'` + `source_id`. Without the key the
portfolio changes and no account balance moves. Deleting the movement has to
take the linked row with it, otherwise the balance silently drifts.

Every "nothing changed" assertion below links first and checks that the row
exists, so it cannot pass by comparing two empty lists.
"""

import importlib
import io

import pytest

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def list_accounts(client, auth, **params):
    response = client.get("/api/accounts", headers=auth, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def default_account_id(client, auth):
    return next(item["id"] for item in list_accounts(client, auth) if item["is_default"])


def create_account(client, auth, name="Corretora", **fields):
    response = client.post(
        "/api/accounts", headers=auth, json={"name": name, "type": "CHECKING", **fields},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def archive_account(client, auth, account_id):
    response = client.delete(f"/api/accounts/{account_id}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)


def balance_of(client, auth, account_id):
    accounts = list_accounts(client, auth, include_archived=1)
    return next(item["balance"] for item in accounts if item["id"] == account_id)


def buy_payload(*, ticker="PETR4", quantity=100, price=10.0, date="2026-02-10", **metadata):
    return {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": date, **metadata},
    }


def sale_payload(*, ticker="PETR4", quantity=40, price=15.0, date="2026-03-10", **metadata):
    return {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": -quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price, **metadata},
    }


def post_movement(client, auth, payload):
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def post_buy(client, auth, *, account_id=None, **kwargs):
    """A buy; `account_id` is what puts it in the statement."""
    if account_id is not None:
        kwargs["cash_account_id"] = account_id
    return post_movement(client, auth, buy_payload(**kwargs))


def patch_movement(client, auth, investment_id, payload):
    return client.patch(f"/api/investments/{investment_id}", headers=auth, json=payload)


def movements(client, auth):
    response = client.get("/api/investments", headers=auth)
    assert response.status_code == 200
    return response.get_json()


def transactions(client, auth):
    response = client.get("/api/transactions", headers=auth)
    assert response.status_code == 200
    return response.get_json()


def cash_entries(client, auth):
    return [
        item for item in transactions(client, auth)
        if item.get("source_type") == "INVESTMENT_TRANSACTION"
    ]


def linked_to(client, auth, investment):
    return [entry for entry in cash_entries(client, auth) if entry["source_id"] == investment["id"]]


def the_linked_row(client, auth, investment):
    linked = linked_to(client, auth, investment)
    assert len(linked) == 1, linked
    return linked[0]


def upload_receipt(client, auth, transaction_id):
    response = client.post(
        f"/api/transactions/{transaction_id}/attachments",
        data={"file": (io.BytesIO(PDF), "nota.pdf")},
        headers=auth,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def receipts_of(client, auth, transaction_id):
    response = client.get(f"/api/transactions/{transaction_id}/attachments", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


class TestAPlainMovementStaysOutOfTheStatement:
    def test_a_plain_buy_writes_no_lancamento(self, client, auth):
        investment = post_buy(client, auth, ticker="PETR4", quantity=100, price=10.0)

        assert transactions(client, auth) == []
        assert "cash_account_id" not in investment["metadata"]
        assert any(item["id"] == investment["id"] for item in movements(client, auth))

    def test_a_plain_buy_leaves_every_balance_alone(self, client, auth):
        post_buy(client, auth, quantity=50, price=20.0)
        assert [account["balance"] for account in list_accounts(client, auth)] == [0]

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_a_blank_account_is_the_same_as_no_account(self, client, auth, blank):
        investment = post_movement(client, auth, buy_payload(cash_account_id=blank))

        assert transactions(client, auth) == []
        # The stored metadata is clean: the key is gone, not kept empty.
        stored = next(item for item in movements(client, auth) if item["id"] == investment["id"])
        assert "cash_account_id" not in stored["metadata"]

    def test_each_movement_decides_for_itself(self, client, auth):
        account_id = default_account_id(client, auth)
        purchase = post_buy(client, auth, ticker="ABEV3", date="2026-01-10", account_id=account_id)
        sale = post_movement(client, auth, sale_payload(ticker="ABEV3"))

        # The buy was linked; that does not make its sale linked.
        assert [entry["source_id"] for entry in cash_entries(client, auth)] == [purchase["id"]]
        assert linked_to(client, auth, sale) == []
        assert balance_of(client, auth, account_id) == pytest.approx(-1000.0)


class TestALinkedBuyIsAnOutflowInTheChosenAccount:
    def test_a_linked_buy_creates_one_expense_in_that_account(self, client, auth):
        main_id = default_account_id(client, auth)
        broker = create_account(client, auth, "Corretora")

        investment = post_buy(client, auth, ticker="PETR4", quantity=100, price=10.0, account_id=broker["id"])

        entry = the_linked_row(client, auth, investment)
        assert entry["id"] == f"cash:{investment['id']}"
        assert entry["type"] == "EXPENSE"
        assert entry["amount"] == pytest.approx(1000.0)
        assert entry["date"] == "2026-02-10"
        assert entry["category"] == "Investimento"
        assert entry["account_id"] == broker["id"]
        assert investment["metadata"]["cash_account_id"] == broker["id"]
        # The chosen account paid; the default one was not touched.
        assert balance_of(client, auth, broker["id"]) == pytest.approx(-1000.0)
        assert balance_of(client, auth, main_id) == 0

    def test_the_outflow_amount_follows_quantity_times_price(self, client, auth):
        investment = post_buy(
            client, auth, ticker="VALE3", quantity=7, price=33.33,
            account_id=default_account_id(client, auth),
        )
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(233.31)

    def test_two_linked_buys_create_two_independent_entries(self, client, auth):
        account_id = default_account_id(client, auth)
        first = post_buy(client, auth, ticker="ITUB4", quantity=10, price=5.0, account_id=account_id)
        second = post_buy(client, auth, ticker="ITUB4", quantity=20, price=5.0, account_id=account_id)

        assert the_linked_row(client, auth, first)["amount"] == pytest.approx(50.0)
        assert the_linked_row(client, auth, second)["amount"] == pytest.approx(100.0)
        assert len(cash_entries(client, auth)) == 2


class TestALinkedSaleIsAnInflow:
    def test_a_linked_sale_is_an_income_net_of_costs(self, client, auth):
        account_id = default_account_id(client, auth)
        post_buy(client, auth, ticker="ABEV3", quantity=100, price=10.0, date="2026-01-10")

        sale = post_movement(
            client, auth,
            sale_payload(ticker="ABEV3", quantity=40, price=15.0, other_costs=12.5, cash_account_id=account_id),
        )

        entry = the_linked_row(client, auth, sale)
        assert entry["type"] == "INCOME"
        # 40 x 15,00 - 12,50 de custos.
        assert entry["amount"] == pytest.approx(587.5)
        assert entry["date"] == "2026-03-10"
        assert entry["account_id"] == account_id
        # The buy was not linked, so the sale is the only thing the account saw.
        assert balance_of(client, auth, account_id) == pytest.approx(587.5)

    def test_a_linked_redemption_brings_in_the_redeemed_value(self, client, auth):
        account_id = default_account_id(client, auth)
        title = post_movement(client, auth, {
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB BANCO X",
            "quantity": 1,
            "average_price": 1000.0,
            "current_price": 1000.0,
            "metadata": {"purchase_date": "2026-02-02"},
        })
        redemption = post_movement(client, auth, {
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB BANCO X",
            "quantity": -1,
            "average_price": 400.0,     # base de custo resgatada
            "current_price": 450.0,     # valor resgatado
            "metadata": {
                "is_redemption": True, "affects_position": True,
                "related_id": title["id"], "redemption_date": "2026-08-03",
                "other_costs": 4.25, "cash_account_id": account_id,
            },
        })

        entry = the_linked_row(client, auth, redemption)
        assert entry["type"] == "INCOME"
        assert entry["amount"] == pytest.approx(445.75)
        assert entry["date"] == "2026-08-03"
        assert linked_to(client, auth, title) == []

    def test_selling_more_than_owned_is_rejected(self, client, auth):
        post_buy(client, auth, ticker="MGLU3", quantity=10, price=10.0)

        response = client.post(
            "/api/investments",
            headers=auth,
            json=sale_payload(
                ticker="MGLU3", quantity=50, price=12.0,
                cash_account_id=default_account_id(client, auth),
            ),
        )
        assert response.status_code == 400, response.get_data(as_text=True)
        assert transactions(client, auth) == []


class TestEditingTheMovement:
    def test_changing_the_account_moves_the_same_row(self, client, auth):
        main_id = default_account_id(client, auth)
        broker = create_account(client, auth, "Corretora")
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=main_id)
        before = the_linked_row(client, auth, investment)
        assert before["account_id"] == main_id

        response = patch_movement(client, auth, investment["id"], {
            "metadata": {**investment["metadata"], "cash_account_id": broker["id"]},
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["metadata"]["cash_account_id"] == broker["id"]

        after = the_linked_row(client, auth, investment)
        assert after["id"] == before["id"]
        assert after["account_id"] == broker["id"]
        assert after["amount"] == pytest.approx(500.0)
        assert len(cash_entries(client, auth)) == 1
        assert balance_of(client, auth, main_id) == 0
        assert balance_of(client, auth, broker["id"]) == pytest.approx(-500.0)

    def test_a_patch_that_omits_the_account_keeps_the_link(self, client, auth):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=account_id)
        before = the_linked_row(client, auth, investment)

        # A form that rebuilds the metadata without knowing about the account.
        response = patch_movement(client, auth, investment["id"], {
            "quantity": 20, "metadata": {"purchase_date": "2026-02-11"},
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["metadata"]["cash_account_id"] == account_id

        after = the_linked_row(client, auth, investment)
        assert after["id"] == before["id"]
        assert after["account_id"] == account_id
        assert after["amount"] == pytest.approx(1000.0)
        assert after["date"] == "2026-02-11"

    def test_a_patch_without_metadata_keeps_the_link(self, client, auth):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=account_id)
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(500.0)

        response = patch_movement(client, auth, investment["id"], {"average_price": 60.0})
        assert response.status_code == 200, response.get_data(as_text=True)

        after = the_linked_row(client, auth, investment)
        assert after["amount"] == pytest.approx(600.0)
        assert after["account_id"] == account_id

    @pytest.mark.parametrize("blank", [None, ""])
    def test_an_empty_account_takes_the_movement_out_of_the_statement(self, client, auth, blank):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=account_id)
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(500.0)
        assert balance_of(client, auth, account_id) == pytest.approx(-500.0)

        response = patch_movement(client, auth, investment["id"], {
            "metadata": {**investment["metadata"], "cash_account_id": blank},
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        assert "cash_account_id" not in response.get_json()["metadata"]

        assert transactions(client, auth) == []
        assert balance_of(client, auth, account_id) == 0
        # The movement itself is untouched.
        stored = next(item for item in movements(client, auth) if item["id"] == investment["id"])
        assert stored["quantity"] == pytest.approx(10)
        assert "cash_account_id" not in stored["metadata"]

    def test_an_edit_can_put_a_plain_movement_into_the_statement(self, client, auth):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0)
        assert transactions(client, auth) == []

        response = patch_movement(client, auth, investment["id"], {
            "metadata": {**investment["metadata"], "cash_account_id": account_id},
        })
        assert response.status_code == 200, response.get_data(as_text=True)

        entry = the_linked_row(client, auth, investment)
        assert entry["type"] == "EXPENSE"
        assert entry["amount"] == pytest.approx(500.0)
        assert entry["account_id"] == account_id

    def test_a_refused_account_on_an_edit_changes_nothing(self, client, auth, other_user):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=account_id)
        before = the_linked_row(client, auth, investment)
        theirs = default_account_id(client, other_user["headers"])

        response = patch_movement(client, auth, investment["id"], {
            "quantity": 99, "metadata": {**investment["metadata"], "cash_account_id": theirs},
        })
        assert response.status_code == 400, response.get_data(as_text=True)

        assert the_linked_row(client, auth, investment) == before
        stored = next(item for item in movements(client, auth) if item["id"] == investment["id"])
        assert stored["quantity"] == pytest.approx(10)
        assert stored["metadata"]["cash_account_id"] == account_id
        assert transactions(client, other_user["headers"]) == []


class TestReceiptsOnTheLinkedRow:
    def test_leaving_the_statement_is_refused_while_the_row_has_a_receipt(self, client, auth):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="BBAS3", quantity=50, price=8.0, account_id=account_id)
        entry = the_linked_row(client, auth, investment)
        receipt = upload_receipt(client, auth, entry["id"])
        unlink = {"metadata": {**investment["metadata"], "cash_account_id": None}}

        response = patch_movement(client, auth, investment["id"], {"quantity": 60, **unlink})
        assert response.status_code == 409, response.get_data(as_text=True)
        assert "comprovante" in response.get_json()["error"]

        # Nothing moved: the row, its receipt and the movement are as they were.
        survivor = the_linked_row(client, auth, investment)
        assert survivor["id"] == entry["id"]
        assert survivor["amount"] == pytest.approx(400.0)
        assert [item["id"] for item in receipts_of(client, auth, entry["id"])] == [receipt["id"]]
        stored = next(item for item in movements(client, auth) if item["id"] == investment["id"])
        assert stored["quantity"] == pytest.approx(50)
        assert stored["metadata"]["cash_account_id"] == account_id

        # With the receipt removed, the same request goes through.
        removed = client.delete(
            f"/api/transactions/{entry['id']}/attachments/{receipt['id']}", headers=auth,
        )
        assert removed.status_code == 200, removed.get_data(as_text=True)
        assert patch_movement(client, auth, investment["id"], unlink).status_code == 200
        assert transactions(client, auth) == []

    def test_an_edit_that_zeroes_the_amount_cannot_take_the_receipt_with_it(self, client, auth):
        # Found by the audit: a price of zero left nothing to write, so the sync
        # deleted the linked row (and its receipt) without passing the guard.
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="BBAS3", quantity=50, price=8.0, account_id=account_id)
        entry = the_linked_row(client, auth, investment)
        receipt = upload_receipt(client, auth, entry["id"])

        response = patch_movement(client, auth, investment["id"], {"average_price": 0})
        assert response.status_code == 400, response.get_data(as_text=True)
        assert "extrato" in response.get_json()["error"]

        survivor = the_linked_row(client, auth, investment)
        assert survivor["id"] == entry["id"]
        assert survivor["amount"] == pytest.approx(400.0)
        assert [item["id"] for item in receipts_of(client, auth, entry["id"])] == [receipt["id"]]
        stored = next(item for item in movements(client, auth) if item["id"] == investment["id"])
        assert stored["average_price"] == pytest.approx(8.0)

    def test_moving_to_another_account_keeps_the_receipt(self, client, auth):
        account_id = default_account_id(client, auth)
        broker = create_account(client, auth, "Corretora")
        investment = post_buy(client, auth, ticker="BBAS3", quantity=50, price=8.0, account_id=account_id)
        entry = the_linked_row(client, auth, investment)
        receipt = upload_receipt(client, auth, entry["id"])

        response = patch_movement(client, auth, investment["id"], {
            "metadata": {**investment["metadata"], "cash_account_id": broker["id"]},
        })
        assert response.status_code == 200, response.get_data(as_text=True)

        moved = the_linked_row(client, auth, investment)
        assert moved["id"] == entry["id"]
        assert moved["account_id"] == broker["id"]
        assert [item["id"] for item in receipts_of(client, auth, moved["id"])] == [receipt["id"]]


class TestTheAccountMustBeTheOwnersActiveAndInReais:
    def assert_nothing_was_written(self, client, auth):
        assert movements(client, auth) == []
        assert transactions(client, auth) == []
        assert client.get("/api/assets", headers=auth).get_json() == []

    def test_another_users_account_is_refused_and_nothing_is_written(self, client, auth, other_user):
        theirs = default_account_id(client, other_user["headers"])

        response = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id=theirs))
        assert response.status_code == 400, response.get_data(as_text=True)

        self.assert_nothing_was_written(client, auth)
        assert transactions(client, other_user["headers"]) == []
        assert balance_of(client, other_user["headers"], theirs) == 0

    def test_another_users_account_reads_exactly_like_an_unknown_one(self, client, auth, other_user):
        theirs = default_account_id(client, other_user["headers"])
        foreign = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id=theirs))
        unknown = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id="nao-existe"))

        assert foreign.status_code == unknown.status_code == 400
        assert foreign.get_json() == unknown.get_json()

    def test_a_bad_account_in_a_batch_writes_none_of_it(self, client, auth):
        account_id = default_account_id(client, auth)
        response = client.post("/api/investments", headers=auth, json=[
            buy_payload(ticker="PETR4", cash_account_id=account_id),
            buy_payload(ticker="VALE3", cash_account_id="nao-existe"),
        ])
        assert response.status_code == 400, response.get_data(as_text=True)
        self.assert_nothing_was_written(client, auth)

    def test_an_archived_account_is_refused_on_a_new_movement(self, client, auth):
        broker = create_account(client, auth, "Corretora")
        archive_account(client, auth, broker["id"])

        response = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id=broker["id"]))
        assert response.status_code == 400, response.get_data(as_text=True)
        assert "arquivada" in response.get_json()["error"]
        self.assert_nothing_was_written(client, auth)

    def test_an_edit_still_works_after_the_linked_account_is_archived(self, client, auth):
        broker = create_account(client, auth, "Corretora")
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, account_id=broker["id"])
        other = post_buy(client, auth, ticker="ITUB4", quantity=10, price=5.0)
        assert the_linked_row(client, auth, investment)["account_id"] == broker["id"]
        archive_account(client, auth, broker["id"])

        # Sending the account back, as the edit form does, is not a new choice.
        response = patch_movement(client, auth, investment["id"], {
            "quantity": 20, "metadata": {**investment["metadata"], "purchase_date": "2026-02-12"},
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        entry = the_linked_row(client, auth, investment)
        assert entry["account_id"] == broker["id"]
        assert entry["amount"] == pytest.approx(1000.0)
        assert balance_of(client, auth, broker["id"]) == pytest.approx(-1000.0)

        # But another movement cannot start using the archived account.
        response = patch_movement(client, auth, other["id"], {
            "metadata": {**other["metadata"], "cash_account_id": broker["id"]},
        })
        assert response.status_code == 400, response.get_data(as_text=True)
        assert linked_to(client, auth, other) == []

    def test_a_foreign_currency_account_is_refused(self, client, auth, monkeypatch):
        # Uma conta em dolar pede a PTAX ao ser listada: aqui, sem rede.
        fx = importlib.import_module("services.fx")
        fx.reset_fetch_throttle()
        monkeypatch.setattr(fx, "fetch_bcb_window", lambda series, start, end: [])
        usd = create_account(client, auth, "Conta EUA", currency="USD")

        response = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id=usd["id"]))
        assert response.status_code == 400, response.get_data(as_text=True)
        assert "reais" in response.get_json()["error"]
        self.assert_nothing_was_written(client, auth)

    @pytest.mark.parametrize("value", [123, True, {"id": "conta"}, ["conta"]])
    def test_a_value_that_is_not_an_account_id_is_refused(self, client, auth, value):
        response = client.post("/api/investments", headers=auth, json=buy_payload(cash_account_id=value))
        assert response.status_code == 400, response.get_data(as_text=True)
        self.assert_nothing_was_written(client, auth)


class TestALinkedMovementAlwaysHasItsRow:
    """An operation with nothing to write cannot ask for the statement: the key
    never says "no extrato" while the Extrato has no row for it."""

    def test_a_linked_buy_without_value_is_refused_and_nothing_is_written(self, client, auth):
        account_id = default_account_id(client, auth)
        response = client.post(
            "/api/investments", headers=auth,
            json=buy_payload(ticker="ITUB4", price=0, cash_account_id=account_id),
        )
        assert response.status_code == 400, response.get_data(as_text=True)
        assert "extrato" in response.get_json()["error"]
        assert movements(client, auth) == []
        assert transactions(client, auth) == []

    def test_the_same_buy_without_the_account_is_accepted(self, client, auth):
        investment = post_buy(client, auth, ticker="ITUB4", price=0)
        assert [item["id"] for item in movements(client, auth)] == [investment["id"]]
        assert transactions(client, auth) == []

    def test_costs_above_the_sale_cannot_empty_a_linked_sale(self, client, auth):
        account_id = default_account_id(client, auth)
        post_buy(client, auth, ticker="ABEV3", quantity=100, price=10.0, date="2026-01-10")
        sale = post_movement(client, auth, sale_payload(ticker="ABEV3", cash_account_id=account_id))
        entry = the_linked_row(client, auth, sale)
        assert entry["amount"] == pytest.approx(600.0)

        response = patch_movement(client, auth, sale["id"], {
            "metadata": {**sale["metadata"], "other_costs": 900},
        })
        assert response.status_code == 400, response.get_data(as_text=True)

        survivor = the_linked_row(client, auth, sale)
        assert survivor["id"] == entry["id"]
        assert survivor["amount"] == pytest.approx(600.0)
        stored = next(item for item in movements(client, auth) if item["id"] == sale["id"])
        assert stored["metadata"].get("other_costs") != 900


class TestDeletingTheMovementRemovesTheCashEntry:
    def test_deleting_a_linked_buy_removes_its_expense(self, client, auth):
        account_id = default_account_id(client, auth)
        investment = post_buy(client, auth, ticker="BBAS3", quantity=50, price=8.0, account_id=account_id)
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(400.0)

        response = client.delete(f"/api/investments/{investment['id']}", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)

        assert transactions(client, auth) == []
        assert balance_of(client, auth, account_id) == 0

    def test_deleting_every_movement_of_an_asset_clears_its_cash_entries(self, client, auth):
        account_id = default_account_id(client, auth)
        first = post_buy(client, auth, ticker="WEGE3", quantity=10, price=10.0, account_id=account_id)
        second = post_buy(client, auth, ticker="WEGE3", quantity=10, price=12.0, account_id=account_id)
        kept = post_buy(client, auth, ticker="ITUB4", quantity=10, price=5.0, account_id=account_id)
        assert len(cash_entries(client, auth)) == 3

        # The endpoint demands the asset class as a confirmation guard, so a
        # stale id from the UI cannot wipe the wrong asset.
        response = client.delete(
            f"/api/investments/by-asset/{first['asset_id']}?asset_class=STOCKS",
            headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)

        assert linked_to(client, auth, first) == []
        assert linked_to(client, auth, second) == []
        # Another asset's lançamento is not swept along.
        assert [entry["source_id"] for entry in cash_entries(client, auth)] == [kept["id"]]


class TestDestructiveGuards:
    def test_deleting_an_asset_without_its_class_is_refused(self, client, auth):
        investment = post_buy(client, auth, ticker="B3SA3", quantity=10, price=10.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}",
            headers=auth,
        )
        assert response.status_code == 400

    def test_deleting_an_asset_with_the_wrong_class_is_refused(self, client, auth):
        investment = post_buy(
            client, auth, ticker="TOTS3", quantity=10, price=10.0,
            account_id=default_account_id(client, auth),
        )
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(100.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}?asset_class=REIT",
            headers=auth,
        )
        assert response.status_code == 409
        # The movement and its cash entry survive the refused delete.
        assert any(item["id"] == investment["id"] for item in movements(client, auth))
        assert the_linked_row(client, auth, investment)["amount"] == pytest.approx(100.0)
