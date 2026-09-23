"""Exportacao do extrato e da carteira em CSV — secao "Smaller gaps".

O formato tem que abrir no Excel em pt-BR com um duplo clique: BOM UTF-8,
ponto e virgula e virgula decimal. E a coluna assinada tem que respeitar a
regra das transferencias (uma linha so, sem efeito no saldo consolidado).
"""

import export_csv


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 100,
        "date": "2026-03-01",
        "category": "Lazer",
        "description": "Cinema",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_account(client, headers, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def export(client, headers, path="/api/transactions/export", **params):
    return client.get(path, headers=headers, query_string=params)


def csv_lines(response):
    text = response.get_data(as_text=True)
    assert text.startswith("﻿"), "o Excel pt-BR precisa do BOM para ler UTF-8"
    return text[1:].strip("\r\n").split("\r\n")


# --- formatacao pura ---------------------------------------------------------

def test_format_decimal_uses_comma_and_two_places():
    assert export_csv.format_decimal(1234.5) == "1234,50"
    assert export_csv.format_decimal(0) == "0,00"
    assert export_csv.format_decimal(None) == ""
    assert export_csv.format_decimal("nao e numero") == ""


def test_format_decimal_keeps_share_quantity_precision():
    assert export_csv.format_decimal(0.123456, 6) == "0,123456"


def test_signed_amount_follows_the_type():
    assert export_csv.signed_amount(100, "INCOME") == "100,00"
    assert export_csv.signed_amount(100, "EXPENSE") == "-100,00"


def test_signed_amount_is_empty_for_transfers():
    """Transferencia e uma linha so; somar a coluna nao pode virar despesa."""
    assert export_csv.signed_amount(100, "TRANSFER") == ""


def test_source_label_defaults_to_manual():
    assert export_csv.source_label(None) == "Manual"
    assert export_csv.source_label("STATEMENT_IMPORT") == "Importacao de extrato"
    assert export_csv.source_label("ALGO_NOVO") == "ALGO_NOVO"


def test_build_csv_escapes_the_delimiter():
    text = export_csv.build_csv(["A"], [["mercado; feira"]])
    assert '"mercado; feira"' in text


# --- extrato -----------------------------------------------------------------

def test_export_returns_a_csv_attachment(client, auth):
    create_transaction(client, auth)
    response = export(client, auth)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["Content-Disposition"]
    assert ".csv" in response.headers["Content-Disposition"]


def test_export_has_header_and_one_line_per_transaction(client, auth):
    create_transaction(client, auth, description="Cinema")
    create_transaction(client, auth, description="Padaria")
    lines = csv_lines(export(client, auth))
    assert lines[0] == ";".join(export_csv.TRANSACTIONS_HEADER)
    assert len(lines) == 3


def test_export_writes_the_account_name(client, auth):
    account = create_account(client, auth, "Conta Corrente")
    create_transaction(client, auth, account_id=account["id"])
    body = export(client, auth).get_data(as_text=True)
    assert "Conta Corrente" in body


def test_export_signs_expenses_and_incomes(client, auth):
    create_transaction(client, auth, amount=50, description="Saida")
    create_transaction(client, auth, amount=80, type="INCOME", category="Salario", description="Entrada")
    rows = {line.split(";")[2]: line.split(";") for line in csv_lines(export(client, auth))[1:]}
    assert rows["Saida"][7] == "-50,00"
    assert rows["Entrada"][7] == "80,00"


def test_export_leaves_the_transfer_column_empty(client, auth):
    origin = create_account(client, auth, "Origem")
    destination = create_account(client, auth, "Destino")
    response = client.post(
        "/api/transfers",
        json={
            "amount": 250,
            "date": "2026-03-02",
            "account_id": origin["id"],
            "transfer_account_id": destination["id"],
            "description": "Entre contas",
        },
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)

    line = [row for row in csv_lines(export(client, auth))[1:] if "Entre contas" in row][0].split(";")
    assert line[1] == "Transferencia"
    assert line[4] == "Origem"
    assert line[5] == "Destino"
    assert line[6] == "250,00"
    assert line[7] == ""


def test_export_honours_the_statement_filters(client, auth):
    create_transaction(client, auth, description="Cinema", date="2026-03-01")
    create_transaction(client, auth, description="Padaria", date="2026-05-01")
    lines = csv_lines(export(client, auth, **{"from": "2026-04-01"}))
    assert len(lines) == 2
    assert "Padaria" in lines[1]


def test_export_rejects_an_invalid_filter(client, auth):
    response = export(client, auth, type="NAO_EXISTE")
    assert response.status_code == 400


def test_export_requires_authentication(client):
    assert client.get("/api/transactions/export").status_code == 401


def test_export_does_not_leak_another_user(client, user, other_user):
    create_transaction(client, user["headers"], description="Minha")
    create_transaction(client, other_user["headers"], description="Dela")
    body = export(client, user["headers"]).get_data(as_text=True)
    assert "Minha" in body
    assert "Dela" not in body


# --- carteira ----------------------------------------------------------------

def test_portfolio_row_computes_the_invested_value():
    row = export_csv.portfolio_row({
        "ticker": "PETR4",
        "class": "STOCKS",
        "quantity": 100,
        "average_price": 30,
        "current_price": 35,
        "current_value": 3500,
        "net_value": 3400,
        "taxes": 100,
        "profitability_percent": 13.33,
        "is_tax_free": False,
        "quote": {"quoted_at": "2026-09-22T10:00:00Z"},
    })
    assert row[0] == "PETR4"
    assert row[1] == "Acoes"
    assert row[5] == "3000,00"
    assert row[10] == "Nao"
    assert row[11] == "2026-09-22"


def test_portfolio_export_is_a_csv_with_the_header(client, auth):
    response = client.get("/api/investments/portfolio/export", headers=auth)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    lines = csv_lines(response)
    assert lines[0] == ";".join(export_csv.PORTFOLIO_HEADER)


def test_portfolio_export_requires_authentication(client):
    assert client.get("/api/investments/portfolio/export").status_code == 401
