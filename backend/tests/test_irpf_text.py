"""Texto para colar no programa do IRPF (irpf_text.py sobre o relatorio de IR).

O que estes testes fixam:

- o texto so reescreve os numeros do relatorio (nenhuma regra nova): custo
  em 31/12, rendimentos por fonte pagadora, meses da renda variavel;
- dinheiro em pt-BR (1.234,56), CNPJ nunca inventado ("(preencher)");
- mes de venda isenta aponta para o codigo 20; mes de prejuizo entra
  negativo em "Mercado a vista - acoes"; o saldo de prejuizo do ano anterior
  aparece para janeiro;
- nada de outro usuario entra.
"""

import importlib
from datetime import timedelta

import pytest

from irpf_text import br_money, br_quantity


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()

    def ptax(series, start, end):
        rows, day = [], start.date()
        while day <= end.date():
            if day.weekday() < 5:
                rows.append({"data": day.strftime("%d/%m/%Y"), "valor": "5.0000"})
            day += timedelta(days=1)
        return rows

    monkeypatch.setattr(fx, "fetch_bcb_window", ptax)


def trade(client, headers, ticker, quantity, price, date, *, asset_class="STOCKS"):
    sale = quantity < 0
    response = client.post("/api/investments", headers=headers, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def proceed(client, headers, asset_id, payment_date, gross, *, kind="DIVIDEND", tax=0):
    response = client.post(
        "/api/investment-proceeds", headers=headers,
        json={"asset_id": asset_id, "proceeds_type": kind, "record_date": payment_date,
              "payment_date": payment_date, "gross_amount": gross, "tax_amount": tax},
    )
    assert response.status_code == 201, response.get_data(as_text=True)


def report(client, headers, year=2025):
    response = client.get(f"/api/tax-report?year={year}", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def section(body, key):
    return next(item for item in body["irpf_text"]["sections"] if item["key"] == key)


def block(sec, title_start):
    return next(item for item in sec["blocks"] if item["title"].startswith(title_start))


@pytest.mark.parametrize("value, text", [
    (1234.5, "1.234,50"), (0.125, "0,13"), (-1000, "-1.000,00"), (-0.001, "0,00"), (None, "0,00"),
])
def test_br_money_is_pt_br_and_half_up(value, text):
    assert br_money(value) == text


def test_br_quantity_keeps_fractions():
    assert br_quantity(1000) == "1.000"
    assert br_quantity(12.5) == "12,5"
    assert br_quantity(0.123456) == "0,123456"


@pytest.fixture
def seeded(client, auth):
    # 2024: prejuizo em acoes que chega a 2025.
    trade(client, auth, "ITUB4", 1000, 30.0, "2024-04-10")
    trade(client, auth, "ITUB4", -1000, 25.0, "2024-05-10")        # vendas 25.000, prejuizo 5.000
    petr = trade(client, auth, "PETR4", 1000, 10.0, "2024-06-10")
    hglg = trade(client, auth, "HGLG11", 20, 100.0, "2025-01-10", asset_class="REIT")
    trade(client, auth, "PETR4", -500, 12.0, "2025-02-10")         # vendas 6.000, ganho isento 1.000
    trade(client, auth, "VALE3", 1000, 30.0, "2025-03-03")
    trade(client, auth, "VALE3", -1000, 22.0, "2025-04-10")        # vendas 22.000, prejuizo 8.000
    trade(client, auth, "HGLG11", -10, 110.0, "2025-05-10", asset_class="REIT")  # FII ganho 100
    proceed(client, auth, petr["asset_id"], "2025-03-20", 50)
    proceed(client, auth, petr["asset_id"], "2025-06-20", 100, kind="JCP", tax=15)
    proceed(client, auth, hglg["asset_id"], "2025-07-15", 12.34)
    return report(client, auth)


def test_bens_e_direitos_text(seeded):
    bens = section(seeded, "bens")
    petr = block(bens, "PETR4")["text"]
    assert "Grupo: 03 - Participações Societárias" in petr
    assert "Código: 01 - Ações (inclusive as listadas em bolsa)" in petr
    assert "Localização (País): 105 - Brasil" in petr
    assert "CNPJ da empresa: (preencher)" in petr
    assert "Código de negociação: PETR4" in petr
    assert "500 ações PETR4, custo médio de R$ 10,00 por ação." in petr
    assert "Situação em 31/12/2024 (R$): 10.000,00" in petr
    assert "Situação em 31/12/2025 (R$): 5.000,00" in petr

    fii = block(bens, "HGLG11")["text"]
    assert "Grupo: 07 - Fundos" in fii and "Código: 03 - Fundos de Investimento Imobiliário (FII)" in fii
    assert "CNPJ do fundo: (preencher)" in fii
    assert "10 cotas HGLG11, custo médio de R$ 100,00 por cota." in fii
    assert "Situação em 31/12/2024 (R$): 0,00" in fii and "Situação em 31/12/2025 (R$): 1.000,00" in fii

    # Os mesmos numeros do relatorio, sem outra conta.
    item = next(i for i in seeded["bens_e_direitos"] if i["ticker"] == "PETR4")
    assert f"Situação em 31/12/2025 (R$): {br_money(item['cost'])}" in petr
    # Vendida no ano: ainda declara o 31/12 anterior, zerado no atual.
    vale = [b for b in bens["blocks"] if b["title"].startswith("VALE3")]
    assert vale == []   # comprada e vendida dentro do ano: nao ha saldo em nenhum 31/12
    itub = [b for b in bens["blocks"] if b["title"].startswith("ITUB4")]
    assert itub == []


def test_income_texts_by_paying_source(seeded):
    isentos = section(seeded, "isentos")
    dividend = block(isentos, "09 · PETR4")["text"]
    assert "Código: 09 - Lucros e dividendos recebidos" in dividend
    assert "CNPJ da fonte pagadora: (preencher)" in dividend
    assert "Nome da fonte pagadora: PETR4" in dividend
    assert "Valor (R$): 50,00" in dividend
    fii = block(isentos, "99 · HGLG11")["text"]
    assert "Código: 99 - Outros" in fii and "Rendimentos de FII — HGLG11" in fii
    assert "Valor (R$): 12,34" in fii
    exempt = block(isentos, "20")["text"]
    assert "Valor (R$): 1.000,00" in exempt
    assert "fevereiro/2025: 1.000,00" in exempt

    exclusiva = section(seeded, "exclusiva")
    jcp = block(exclusiva, "10 · PETR4")["text"]
    assert "Código: 10 - Juros sobre capital próprio" in jcp
    assert "Valor (R$): 85,00" in jcp
    assert "Bruto R$ 100,00 − IR retido R$ 15,00" in jcp


def test_renda_variavel_text(seeded):
    variable = section(seeded, "renda_variavel")
    opening = block(variable, "saldo anterior")["text"]
    assert "Operações comuns · Resultado negativo até o mês anterior (R$): 5.000,00" in opening

    february = block(variable, "2025-02")["text"]
    assert february.startswith("Fevereiro/2025")
    assert "Mercado à vista - ações (R$): 0,00" in february
    assert "Rendimentos isentos, código 20" in february

    april = block(variable, "2025-04")["text"]
    assert "Mercado à vista - ações (R$): -8.000,00" in april
    assert "prejuízo a compensar 13.000,00" in april

    may = block(variable, "2025-05")["text"]
    assert "Fundos de Investimento Imobiliário · Resultado líquido do mês (R$): 100,00" in may
    assert "imposto devido 20,00" in may
    assert "Imposto pago (R$): 20,00 — DARF 6015" in may
    assert "Mercado à vista" not in may   # sem venda de acoes no mes

    # A secao inteira e a juncao dos blocos, pronta para "copiar tudo".
    assert variable["text"] == "\n\n".join(b["text"] for b in variable["blocks"])


def test_empty_year_has_empty_sections(client, auth):
    body = report(client, auth)
    assert all(sec["blocks"] == [] and sec["text"] == "" and sec["empty"] for sec in body["irpf_text"]["sections"])
    assert "IRPF" in body["irpf_text"]["code_table"]


def test_another_users_data_stays_out_of_the_text(client, user, other_user):
    theirs = trade(client, other_user["headers"], "PETR4", 100, 10.0, "2025-01-10")
    proceed(client, other_user["headers"], theirs["asset_id"], "2025-03-20", 50)
    trade(client, other_user["headers"], "PETR4", -100, 12.0, "2025-04-10")
    mine = trade(client, user["headers"], "VALE3", 100, 10.0, "2025-01-10")
    proceed(client, user["headers"], mine["asset_id"], "2025-04-20", 7)
    body = report(client, user["headers"])

    everything = "\n".join(sec["text"] for sec in body["irpf_text"]["sections"])
    assert "PETR4" not in everything
    assert "VALE3" in everything
    assert section(body, "renda_variavel")["blocks"] == []
