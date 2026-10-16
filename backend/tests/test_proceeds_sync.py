"""Proventos automaticos (026): posicao na data com x valor da StatusInvest.

O que estes testes fixam:

- so entra evento com data com em que havia posicao; a quantidade e a da data
  com (compra posterior nao conta, venda anterior tira);
- uma compra lancada com data no passado traz os proventos desde entao, e
  apagar a operacao tira os automaticos dela;
- a segunda sincronizacao nao grava nada (sync_key + indice unico); eventos
  iguais no mesmo dia viram duas linhas;
- imposto: JCP 15% ate 2025, 17,5% com data com em 2026; rendimento
  tributavel 22,5%; dividendo isento;
- o que o dono decidiu fica: provento digitado nunca e tocado, automatico
  editado nao e recalculado, automatico excluido nao volta;
- falha na fonte nao apaga nada;
- nada de outro usuario.
"""

import importlib

import pytest

import statusinvest_client
from statusinvest_client import ProceedEvent


def event(ticker, record, payment, value, *, kind="DIVIDEND", label="Dividendo"):
    proceeds_type = {"DIVIDEND": "DIVIDEND", "JCP": "JCP", "TAXABLE_INCOME": "JCP"}[kind]
    return ProceedEvent(ticker, proceeds_type, kind, record, payment, value, label)


@pytest.fixture()
def source(app_module, monkeypatch):
    """Historico falso por ticker; `source["fail"] = True` simula a fonte fora."""
    state = {"events": {}, "fail": False, "calls": []}

    def fake(ticker, asset_class, *, force=False, timeout=None, now=None):
        state["calls"].append(ticker)
        if state["fail"]:
            raise statusinvest_client.StatusInvestError("fora do ar")
        return list(state["events"].get(ticker, []))

    statusinvest_client.clear_cache()
    monkeypatch.setattr(statusinvest_client, "get_proceed_events", fake)
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
    return state


def trade(client, auth, ticker, quantity, price, when, asset_class="STOCKS"):
    sale = quantity < 0
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": when, "sale_price": price} if sale else {"purchase_date": when},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def sync(client, auth):
    response = client.post("/api/investment-proceeds/sync", headers=auth, json={})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def proceeds(client, auth):
    response = client.get("/api/investment-proceeds", headers=auth, query_string={"ascending": "true"})
    assert response.status_code == 200
    return response.get_json()


def test_quantity_is_the_position_on_the_record_date(client, auth, source):
    trade(client, auth, "BBSE3", 100, 30.0, "2025-01-10")
    trade(client, auth, "BBSE3", 50, 32.0, "2025-06-10")
    trade(client, auth, "BBSE3", -150, 35.0, "2025-12-01")
    source["events"]["BBSE3"] = [
        event("BBSE3", "2024-12-20", "2025-01-15", 1.0),   # antes da compra
        event("BBSE3", "2025-01-10", "2025-02-01", 1.0),   # data com = dia da compra: conta
        event("BBSE3", "2025-08-01", "2025-08-20", 2.0),   # 150 cotas
        event("BBSE3", "2025-12-05", "2025-12-20", 3.0),   # tudo vendido
    ]

    result = sync(client, auth)
    assert result["status"] == "ok"
    assert result["created"] == 2

    items = proceeds(client, auth)
    assert [(i["record_date"], i["eligible_quantity"], i["gross_amount"]) for i in items] == [
        ("2025-01-10", 100, 100.0),
        ("2025-08-01", 150, 300.0),
    ]
    assert all(i["source"] == "statusinvest" for i in items)
    assert all(i["tax_amount"] == 0 for i in items)


def test_second_sync_writes_nothing_and_same_day_twins_are_two_rows(client, auth, source):
    trade(client, auth, "KLBN4", 10, 4.0, "2025-01-10")
    source["events"]["KLBN4"] = [
        event("KLBN4", "2025-12-15", "2026-05-20", 0.05),
        event("KLBN4", "2025-12-15", "2026-05-20", 0.05),
    ]
    assert sync(client, auth)["created"] == 2
    again = sync(client, auth)
    assert (again["created"], again["updated"], again["removed"]) == (0, 0, 0)
    assert len(proceeds(client, auth)) == 2


def test_backdated_purchase_brings_past_proceeds_and_delete_takes_them(client, auth, source):
    trade(client, auth, "VALE3", 10, 60.0, "2026-03-01")
    source["events"]["VALE3"] = [
        event("VALE3", "2025-08-11", "2025-09-02", 2.0),
        event("VALE3", "2026-08-11", "2026-09-02", 2.0),
    ]
    sync(client, auth)
    assert [i["record_date"] for i in proceeds(client, auth)] == ["2026-08-11"]

    old = trade(client, auth, "VALE3", 5, 50.0, "2025-01-02")
    result = sync(client, auth)
    assert (result["created"], result["updated"]) == (1, 1)
    items = proceeds(client, auth)
    assert [(i["record_date"], i["eligible_quantity"]) for i in items] == [
        ("2025-08-11", 5),
        ("2026-08-11", 15),
    ]

    response = client.delete(f"/api/investments/{old['id']}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    result = sync(client, auth)
    assert (result["removed"], result["updated"]) == (1, 1)
    assert [(i["record_date"], i["eligible_quantity"]) for i in proceeds(client, auth)] == [("2026-08-11", 10)]


def test_tax_by_kind_and_year(client, auth, source):
    trade(client, auth, "BBAS3", 100, 20.0, "2025-01-02")
    source["events"]["BBAS3"] = [
        event("BBAS3", "2025-06-01", "2025-06-11", 1.0, kind="JCP", label="JCP"),
        event("BBAS3", "2026-06-01", "2026-06-11", 1.0, kind="JCP", label="JCP"),
        event("BBAS3", "2026-06-01", "2026-06-11", 0.1, kind="TAXABLE_INCOME", label="Rend. Tributado"),
    ]
    sync(client, auth)
    taxes = {(i["record_date"], i["metadata"]["kind"]): (i["gross_amount"], i["tax_amount"], i["net_amount"])
             for i in proceeds(client, auth)}
    assert taxes[("2025-06-01", "JCP")] == (100.0, 15.0, 85.0)
    assert taxes[("2026-06-01", "JCP")] == (100.0, 17.5, 82.5)
    assert taxes[("2026-06-01", "TAXABLE_INCOME")] == (10.0, 2.25, 7.75)


def test_manual_proceed_is_left_alone(client, auth, source):
    asset_id = trade(client, auth, "TAEE11", 10, 35.0, "2025-01-02")["asset_id"]
    response = client.post("/api/investment-proceeds", headers=auth, json={
        "asset_id": asset_id, "proceeds_type": "DIVIDEND",
        "record_date": "2025-03-01", "payment_date": "2025-03-10", "gross_amount": 7.0,
    })
    assert response.status_code == 201
    source["events"]["TAEE11"] = []
    result = sync(client, auth)
    assert result["removed"] == 0
    assert [i["gross_amount"] for i in proceeds(client, auth)] == [7.0]


def test_edited_proceed_is_locked_and_deleted_one_stays_gone(client, auth, source):
    trade(client, auth, "ITSA4", 100, 10.0, "2025-01-02")
    source["events"]["ITSA4"] = [
        event("ITSA4", "2025-03-01", "2025-04-01", 0.1),
        event("ITSA4", "2025-06-01", "2025-07-01", 0.2),
    ]
    sync(client, auth)
    first, second = proceeds(client, auth)

    response = client.patch(f"/api/investment-proceeds/{first['id']}", headers=auth, json={"gross_amount": 9.0})
    assert response.status_code == 200
    response = client.delete(f"/api/investment-proceeds/{second['id']}", headers=auth)
    assert response.status_code == 200

    trade(client, auth, "ITSA4", 100, 10.0, "2025-01-03")  # mudaria a quantidade das duas
    result = sync(client, auth)
    assert (result["created"], result["updated"], result["removed"]) == (0, 0, 0)
    items = proceeds(client, auth)
    assert [(i["record_date"], i["gross_amount"]) for i in items] == [("2025-03-01", 9.0)]


def test_source_failure_keeps_what_is_recorded(client, auth, source):
    trade(client, auth, "GOAU4", 100, 10.0, "2025-01-02")
    source["events"]["GOAU4"] = [event("GOAU4", "2025-03-01", "2025-03-20", 0.05)]
    sync(client, auth)
    source["fail"] = True
    result = sync(client, auth)
    assert result["status"] == "error"
    assert result["failed"] == ["GOAU4"]
    assert len(proceeds(client, auth)) == 1


def test_other_user_is_untouched(client, auth, other_user, source):
    trade(client, other_user["headers"], "PETR4", 100, 5.0, "2025-01-02")
    trade(client, auth, "PETR4", 10, 5.0, "2025-01-02")
    source["events"]["PETR4"] = [event("PETR4", "2025-06-30", "2025-07-10", 1.0)]
    sync(client, auth)
    assert [i["eligible_quantity"] for i in proceeds(client, auth)] == [10]
    assert proceeds(client, other_user["headers"]) == []


def test_fixed_income_and_foreign_assets_are_not_fetched(client, auth, source):
    trade(client, auth, "TESOURO SELIC 2029", 1, 1000.0, "2025-01-02", asset_class="FIXED_INCOME")
    sync(client, auth)
    assert source["calls"] == []


def test_parse_events_maps_types_and_skips_incomplete_rows():
    payload = {"assetEarningsModels": [
        {"ed": "01/09/2026", "pd": "11/09/2026", "et": "JCP", "v": 0.1},
        {"ed": "01/09/2026", "pd": "11/09/2026", "et": "Rend. Tributado", "v": 0.002},
        {"ed": "30/09/2026", "pd": "15/10/2026", "et": "Rendimento", "v": 0.1},
        {"ed": "30/09/2026", "pd": "-", "et": "Dividendo", "v": 0.5},
        {"ed": "30/09/2026", "pd": "15/10/2026", "et": "Subscricao", "v": 0.5},
        {"ed": "30/09/2026", "pd": "15/10/2026", "et": "Dividendo", "v": 0},
        {"ed": "30/05/2025", "pd": "01/07/2024", "et": "JCP", "v": 0.02},
    ]}
    events = statusinvest_client.parse_events("BBAS3", payload)
    assert [(e.proceeds_type, e.kind, e.record_date, e.payment_date) for e in events] == [
        ("JCP", "JCP", "2026-09-01", "2026-09-11"),
        ("JCP", "TAXABLE_INCOME", "2026-09-01", "2026-09-11"),
        ("DIVIDEND", "DIVIDEND", "2026-09-30", "2026-10-15"),
    ]
    assert statusinvest_client.parse_events("X", None) == []


def test_manual_jcp_uses_the_rate_of_its_record_date(client, auth, source):
    asset_id = trade(client, auth, "BBAS3", 100, 20.0, "2025-01-02")["asset_id"]
    for record, expected in (("2025-12-01", 15.0), ("2026-03-02", 17.5)):
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": asset_id, "proceeds_type": "JCP",
            "record_date": record, "payment_date": record, "amount_per_unit": 1.0,
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["tax_amount"] == expected


def test_renamed_ticker_is_asked_by_its_new_code(monkeypatch):
    asked = []

    def fake_request(path, ticker, timeout):
        asked.append(ticker)
        return {"assetEarningsModels": [{"ed": "31/01/2024", "pd": "16/02/2024", "et": "Rendimento", "v": 0.92}]}

    statusinvest_client.clear_cache()
    monkeypatch.setattr(statusinvest_client, "_request", fake_request)
    events = statusinvest_client.get_proceed_events("MALL11", "REIT")
    assert asked == ["PMLL11"]
    assert [(e.ticker, e.record_date, e.amount_per_unit) for e in events] == [("MALL11", "2024-01-31", 0.92)]
    statusinvest_client.clear_cache()


def test_typed_proceed_stands_in_for_the_same_event(client, auth, source):
    asset_id = trade(client, auth, "TAEE11", 10, 35.0, "2025-01-02")["asset_id"]
    response = client.post("/api/investment-proceeds", headers=auth, json={
        "asset_id": asset_id, "proceeds_type": "DIVIDEND",
        "record_date": "2025-03-01", "payment_date": "2025-03-10", "gross_amount": 7.0,
    })
    assert response.status_code == 201
    source["events"]["TAEE11"] = [
        event("TAEE11", "2025-03-01", "2025-03-12", 0.7),   # o mesmo dividendo, ja digitado
        event("TAEE11", "2025-06-01", "2025-06-12", 0.5),
    ]
    result = sync(client, auth)
    assert result["created"] == 1
    assert [(i["record_date"], i["gross_amount"], i["source"]) for i in proceeds(client, auth)] == [
        ("2025-03-01", 7.0, "manual"),
        ("2025-06-01", 5.0, "statusinvest"),
    ]


def test_row_removed_for_no_position_comes_back_when_the_position_does(client, auth, source):
    trade(client, auth, "BBSE3", 10, 30.0, "2025-01-02")
    trade(client, auth, "BBSE3", -10, 30.0, "2025-02-01")
    source["events"]["BBSE3"] = [event("BBSE3", "2025-03-01", "2025-03-20", 1.0)]
    assert sync(client, auth)["created"] == 0          # sem posicao na data com
    trade(client, auth, "BBSE3", 4, 30.0, "2025-02-15")  # compra lancada depois, com data antiga
    assert sync(client, auth)["created"] == 1
    assert [i["eligible_quantity"] for i in proceeds(client, auth)] == [4]
