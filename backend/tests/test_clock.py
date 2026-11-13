"""O relogio do app (dates.local_now / local_today) e um so, e congela num ponto.

Antes, cerca de 50 lugares liam `datetime.now()` / `date.today()` direto, ao lado
do `invoices.local_today()` que os testes congelavam modulo a modulo: um teste
com datas fixas mudava de resultado quando o calendario passava delas (tres
falharam em 2026-11-11 e pararam o deploy). Estes testes fixam que cada area
segue `dates.now_source`.
"""

import importlib
from datetime import date, datetime

import pytest


@pytest.fixture()
def dates(app_module):
    return importlib.import_module("dates")


@pytest.fixture()
def at(dates, monkeypatch):
    def freeze(moment):
        monkeypatch.setattr(dates, "now_source", lambda: moment)
    return freeze


def test_unfrozen_it_is_the_system_clock(dates):
    before = datetime.now()
    now = dates.local_now()
    assert before <= now <= datetime.now()
    assert now.tzinfo is None
    assert dates.local_today() == now.date()


def test_names_imported_from_dates_follow_the_frozen_clock(dates, at):
    at(datetime(2031, 3, 4, 23, 59))
    assert dates.local_now() == datetime(2031, 3, 4, 23, 59)
    assert dates.local_today() == date(2031, 3, 4)
    # Quem importou pelo nome le o mesmo relogio.
    assert importlib.import_module("services.invoices").local_today() == date(2031, 3, 4)
    assert importlib.import_module("services.fx")._as_date(None) == date(2031, 3, 4)


@pytest.mark.parametrize("today, status", [(datetime(2030, 5, 9, 12), "SCHEDULED"), (datetime(2030, 5, 10, 0, 1), "PAID")])
def test_a_provento_is_paid_from_its_payment_day(at, today, status):
    at(today)
    assert importlib.import_module("services.proceeds").proceed_status("2030-05-10") == status


def test_the_tax_report_defaults_to_last_year(client, auth, at):
    at(datetime(2030, 2, 1, 9))
    response = client.get("/api/tax-report", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["year"] == 2029
    assert client.get("/api/tax-report?year=2031", headers=auth).status_code == 400


def test_recurrences_are_pending_against_the_frozen_day(client, auth, at):
    created = client.post("/api/recurring", headers=auth, json={
        "amount": 100, "type": "EXPENSE", "category": "Outros", "description": "Aluguel",
        "frequency": "MONTHLY", "start_date": "2030-01-10",
    })
    assert created.status_code == 201, created.get_data(as_text=True)
    at(datetime(2030, 1, 9, 8))
    assert client.get("/api/recurring", headers=auth).get_json()["items"][0]["pending_count"] == 0
    at(datetime(2030, 3, 15, 8))
    assert client.get("/api/recurring", headers=auth).get_json()["items"][0]["pending_count"] == 3
