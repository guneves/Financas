"""Exportacao em .xlsx, seletor de colunas, Operacoes e Proventos.

O que estes testes fixam:

- `?format=xlsx` devolve uma planilha de verdade (zip OOXML) com numero como
  numero, data como data do Excel e o cabecalho das colunas escolhidas;
- `?columns=` escolhe e ordena as colunas, e uma coluna desconhecida e 400;
- Operacoes sai com o resultado realizado (FIFO) da venda, e Proventos com os
  mesmos filtros da tela;
- nada de outro usuario entra em nenhuma exportacao.
"""

import io
import re
import zipfile

import pytest

import export_csv
import export_xlsx


def csv_rows(response):
    text = response.get_data(as_text=True)
    assert text.startswith("﻿")
    return [line.split(";") for line in text[1:].strip("\r\n").split("\r\n")]


def sheet_xml(response):
    archive = zipfile.ZipFile(io.BytesIO(response.get_data()))
    assert "xl/workbook.xml" in archive.namelist()
    return archive.read("xl/worksheets/sheet1.xml").decode("utf-8")


def post_buy(client, auth, *, ticker="PETR4", quantity=100, price=10.0, date="2026-01-10"):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": quantity,
            "average_price": price,
            "current_price": price,
            "metadata": {"purchase_date": date},
        },
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def post_sell(client, auth, *, ticker="PETR4", quantity=40, price=15.0, date="2026-03-10"):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": -quantity,
            "average_price": 10.0,
            "current_price": price,
            "metadata": {"sale_date": date, "sale_price": price},
        },
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)


# --- modulo puro ---------------------------------------------------------------

def test_column_letters_go_past_z():
    assert export_xlsx.column_letter(0) == "A"
    assert export_xlsx.column_letter(25) == "Z"
    assert export_xlsx.column_letter(26) == "AA"


def test_excel_serial_matches_excel():
    # 1900-01-01 e o dia 1 do Excel (com o bug do 29/02/1900, 01/03/1900 e 61).
    assert export_xlsx.excel_serial("1900-03-01") == 61
    assert export_xlsx.excel_serial("2026-09-23") == 46288
    assert export_xlsx.excel_serial("nao e data") is None


def test_select_columns_keeps_the_requested_order():
    columns = export_csv.select_columns(export_csv.TRANSACTION_COLUMNS, "valor,data")
    assert [column.key for column in columns] == ["valor", "data"]


def test_select_columns_refuses_an_unknown_key():
    with pytest.raises(export_csv.ColumnError):
        export_csv.select_columns(export_csv.TRANSACTION_COLUMNS, "data,inventada")


def test_xlsx_cells_are_typed_and_text_is_escaped():
    columns = export_csv.select_columns(export_csv.TRANSACTION_COLUMNS, "data,descricao,valor_com_sinal")
    body = export_xlsx.table_xlsx(
        "Extrato", columns,
        [{"date": "2026-03-01", "description": "Pão & <leite>", "amount": 12.5, "type": "EXPENSE"}],
    )
    xml = zipfile.ZipFile(io.BytesIO(body)).read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert '<c r="A2" s="3"><v>46082.0</v></c>' in xml
    assert "Pão &amp; &lt;leite&gt;" in xml
    assert '<c r="C2" s="2"><v>-12.5</v></c>' in xml


def test_xlsx_whole_quantity_has_no_trailing_separator():
    # "#,##0.######" sai "3.024," no Excel; quantidade inteira usa "#,##0".
    columns = export_csv.select_columns(export_csv.PORTFOLIO_COLUMNS, "quantidade")
    body = export_xlsx.table_xlsx(
        "Carteira", columns, [{"quantity": 3024}, {"quantity": 0.5}, {"quantity": 1.0000000001}],
    )
    package = zipfile.ZipFile(io.BytesIO(body))
    xml = package.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert f'<c r="A2" s="{export_xlsx.STYLE_QUANTITY_WHOLE}"><v>3024.0</v></c>' in xml
    assert f'<c r="A3" s="{export_xlsx.STYLE_QUANTITY}"><v>0.5</v></c>' in xml
    assert f'<c r="A4" s="{export_xlsx.STYLE_QUANTITY_WHOLE}">' in xml
    styles = package.read("xl/styles.xml").decode("utf-8")
    cell_xfs = styles.split("<cellXfs")[1].split("</cellXfs>")[0]
    xfs = cell_xfs.split("<xf ")[1:]
    assert f'count="{len(xfs)}"' in cell_xfs
    assert 'numFmtId="3"' in xfs[export_xlsx.STYLE_QUANTITY_WHOLE]


def test_quantity_in_csv_drops_trailing_zeros():
    assert export_csv.format_cell(100, "quantity") == "100"
    assert export_csv.format_cell(0.123456, "quantity") == "0,123456"


# --- extrato -------------------------------------------------------------------

def test_statement_export_as_xlsx(client, auth):
    client.post(
        "/api/transactions",
        json={"amount": 80, "date": "2026-03-01", "category": "Lazer", "description": "Cinema", "type": "EXPENSE"},
        headers=auth,
    )
    response = client.get("/api/transactions/export", headers=auth, query_string={"format": "xlsx"})
    assert response.status_code == 200
    assert response.mimetype == export_xlsx_mimetype()
    assert re.search(r'filename="extrato-\d{4}-\d{2}-\d{2}\.xlsx"', response.headers["Content-Disposition"])
    xml = sheet_xml(response)
    assert "Cinema" in xml
    assert "<v>-80.0</v>" in xml


def export_xlsx_mimetype():
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_statement_export_honours_the_column_picker(client, auth):
    client.post(
        "/api/transactions",
        json={"amount": 80, "date": "2026-03-01", "category": "Lazer", "description": "Cinema", "type": "EXPENSE"},
        headers=auth,
    )
    response = client.get(
        "/api/transactions/export", headers=auth, query_string={"columns": "descricao,valor"},
    )
    rows = csv_rows(response)
    assert rows[0] == ["Descrição", "Valor"]
    assert rows[1] == ["Cinema", "80,00"]


@pytest.mark.parametrize("params", [{"columns": "data,nada"}, {"format": "pdf"}])
def test_statement_export_rejects_bad_options(client, auth, params):
    response = client.get("/api/transactions/export", headers=auth, query_string=params)
    assert response.status_code == 400


# --- operacoes -------------------------------------------------------------------

def test_movements_export_carries_the_realized_result(client, auth):
    post_buy(client, auth)
    post_sell(client, auth)
    response = client.get(
        "/api/investments/export", headers=auth,
        query_string={"columns": "data,tipo,ativo,quantidade,preco,valor_bruto,resultado"},
    )
    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0] == ["Data", "Tipo", "Ativo", "Quantidade", "Preço", "Valor bruto", "Resultado"]
    # Mais recente primeiro: a venda, com lucro de 40 x (15 - 10).
    assert rows[1] == ["2026-03-10", "Venda", "PETR4", "40", "15,00", "600,00", "200,00"]
    assert rows[2] == ["2026-01-10", "Compra", "PETR4", "100", "10,00", "1000,00", ""]


def test_movements_export_as_xlsx(client, auth):
    post_buy(client, auth)
    response = client.get("/api/investments/export", headers=auth, query_string={"format": "xlsx"})
    assert response.status_code == 200
    assert "PETR4" in sheet_xml(response)


def test_movements_export_requires_authentication(client):
    assert client.get("/api/investments/export").status_code == 401


# --- proventos -------------------------------------------------------------------

def create_dividend(client, auth, asset_id, payment_date="2026-02-15"):
    response = client.post(
        "/api/investment-proceeds",
        json={
            "asset_id": asset_id,
            "proceeds_type": "DIVIDEND",
            "record_date": "2026-02-01",
            "payment_date": payment_date,
            "amount_per_unit": 0.5,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def test_proceeds_export_lists_the_dividends(client, auth):
    buy = post_buy(client, auth)
    create_dividend(client, auth, buy["asset_id"])
    response = client.get(
        "/api/investment-proceeds/export", headers=auth,
        query_string={"columns": "pagamento,ativo,tipo,quantidade,liquido"},
    )
    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0] == ["Pagamento", "Ativo", "Tipo", "Quantidade", "Líquido"]
    assert rows[1] == ["2026-02-15", "PETR4", "Dividendos", "100", "50,00"]


def test_proceeds_export_honours_the_page_filters(client, auth):
    buy = post_buy(client, auth)
    create_dividend(client, auth, buy["asset_id"], payment_date="2026-02-15")
    create_dividend(client, auth, buy["asset_id"], payment_date="2026-05-15")
    response = client.get(
        "/api/investment-proceeds/export", headers=auth,
        query_string={"date_from": "2026-04-01", "columns": "pagamento"},
    )
    assert csv_rows(response)[1:] == [["2026-05-15"]]


# --- carteira ---------------------------------------------------------------------

def dividend_on(client, auth, asset_id, day):
    response = client.post(
        "/api/investment-proceeds",
        json={
            "asset_id": asset_id,
            "proceeds_type": "DIVIDEND",
            "record_date": day,
            "payment_date": day,
            "amount_per_unit": 0.5,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)


def portfolio_with_proceeds(client, auth):
    """100 cotas a 10 (custo 1000), um dividendo de 50 ha mais de um ano e
    outro de 50 ha 30 dias: proventos 100, 12m 50, DY 5% e rentabilidade com
    proventos de 10% (preco parado)."""
    from datetime import date, timedelta

    buy = post_buy(client, auth, date="2024-01-10")
    dividend_on(client, auth, buy["asset_id"], "2024-06-14")
    dividend_on(client, auth, buy["asset_id"], (date.today() - timedelta(days=30)).isoformat())


PROCEEDS_COLUMN_KEYS = "ativo,quantidade,proventos,proventos_12m,dy_12m,rentabilidade_com_proventos"


def test_portfolio_export_carries_proceeds_and_total_return(client, auth):
    portfolio_with_proceeds(client, auth)
    response = client.get(
        "/api/investments/portfolio/export", headers=auth,
        query_string={"columns": PROCEEDS_COLUMN_KEYS},
    )
    assert response.status_code == 200
    rows = csv_rows(response)
    assert rows[0] == ["Ativo", "Quantidade", "Proventos", "Proventos 12m", "DY 12m (%)", "Rentab. c/ proventos (%)"]
    assert rows[1] == ["PETR4", "100", "100,00", "50,00", "5,00", "10,00"]


def test_portfolio_export_proceeds_columns_are_numbers_in_xlsx(client, auth):
    portfolio_with_proceeds(client, auth)
    response = client.get(
        "/api/investments/portfolio/export", headers=auth,
        query_string={"format": "xlsx", "columns": PROCEEDS_COLUMN_KEYS},
    )
    assert response.status_code == 200
    xml = sheet_xml(response)
    assert "Rentab. c/ proventos (%)" in xml
    # Quantidade inteira segue sem casa decimal (conferido pelo dono em 2026-09-26).
    assert f'<c r="B2" s="{export_xlsx.STYLE_QUANTITY_WHOLE}"><v>100' in xml
    assert f'<c r="C2" s="{export_xlsx.STYLE_MONEY}"><v>100' in xml
    assert f'<c r="D2" s="{export_xlsx.STYLE_MONEY}"><v>50' in xml
    assert re.search(rf'<c r="E2" s="{export_xlsx.STYLE_PERCENT}"><v>0\.05\d*</v>', xml)
    assert re.search(rf'<c r="F2" s="{export_xlsx.STYLE_PERCENT}"><v>0\.1\d*</v>', xml)


def test_column_catalog_offers_the_portfolio_proceeds_columns(client, auth):
    body = client.get("/api/exports/columns", headers=auth).get_json()
    keys = [column["key"] for column in body["portfolio"]]
    assert keys.index("rentabilidade") < keys.index("proventos") < keys.index("rentabilidade_com_proventos")
    assert {"key": "proventos_12m", "label": "Proventos 12m"} in body["portfolio"]


# --- catalogo e isolamento ---------------------------------------------------------

def test_column_catalog_lists_every_export(client, auth):
    body = client.get("/api/exports/columns", headers=auth).get_json()
    assert set(body) == {"transactions", "portfolio", "movements", "proceeds"}
    assert body["transactions"][0] == {"key": "data", "label": "Data"}


@pytest.mark.parametrize("path", [
    "/api/transactions/export",
    "/api/investments/export",
    "/api/investment-proceeds/export",
    "/api/investments/portfolio/export",
])
def test_exports_do_not_leak_another_user(client, user, other_user, path):
    other = other_user["headers"]
    buy = post_buy(client, other, ticker="VALE3")
    create_dividend(client, other, buy["asset_id"])
    response = client.get(path, headers=user["headers"], query_string={"format": "xlsx"})
    assert response.status_code == 200
    xml = sheet_xml(response)
    assert "VALE3" not in xml
    assert "<row r=\"2\">" not in xml
