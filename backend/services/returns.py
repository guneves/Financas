"""Rentabilidade ponderada no tempo (TWR), da carteira e de cada ativo.

Metodo: Dietz modificado mes a mes, encadeado. Para cada mes,

    r = (V1 - V0 - F + D) / (V0 + soma(w_i * F_i))

V0 e V1 sao o valor no fim do mes anterior e deste, F o fluxo externo liquido
(compras menos vendas/resgates, em reais), cada fluxo pesado pela fracao do mes
em que ficou investido, e D os proventos pagos no mes (renda, nao fluxo).
TWR = produto(1 + r) - 1. Mensal e a resolucao que os dados permitem: o passado
dos cotados vem do fechamento mensal (`get_monthly_history()`).

Valor BRUTO: V0 e V1 sao o valor de mercado antes do IR estimado da renda fixa
(o que corretoras e o Investidor10 mostram). A evolucao do patrimonio usa o
liquido; as duas saem da mesma avaliacao (`iter_portfolio_months()`).

Distorcoes conhecidas (tambem em `RETURN_NOTES`, que vai na resposta):
- meses passados de classes sem cotacao (outros, preco manual) ficam no
  custo, e o ganho inteiro cai no mes atual;
- um mes passado sem fechamento no yfinance usa o anterior, ou o preco de hoje;
- o mes atual vale o que a Posicao mostra (`position_value_today()`): a
  ultima cotacao gravada, nao o fechamento do mes nem a serie do BCB;
- eventos corporativos ja estao reescalados nas movimentacoes gravadas;
- ativo no exterior: cada mes pela PTAX do fim daquele mes (o historico ja
  chega em reais); proventos de ativo no exterior entram como reais.

As funcoes de conta (`flow_weights`, `modified_dietz`, `chain_returns`,
`cdi_monthly_returns`, `year_month_table`) sao puras; `build_investment_returns()`
junta as posicoes, os fluxos e os proventos do usuario.
"""

from datetime import datetime
import calendar

from dates import month_key, month_label
from db import get_db
from money import rounded_money
from services.benchmarks import benchmark_note
from services.investments import investment_cash_amount, investment_gross_proceeds
from services.portfolio import evolution_group_key, investment_movement_date, iter_portfolio_months
from services.prices import ticker_key
from validators import safe_float

# O fechamento mensal vem com auto_adjust=False (services/prices.py): o preco
# NAO desconta os proventos, entao eles entram como renda no mes em que sao
# pagos. Se o historico passar a vir ajustado, isto vira True e os proventos
# deixam de ser somados — senao contariam duas vezes.
PRICES_ARE_DIVIDEND_ADJUSTED = False

VALUE_BASIS = "gross"
VALUE_BASIS_LABEL = "Valor bruto (antes do IR estimado da renda fixa)"

RETURN_NOTES = [
    "Rentabilidade ponderada no tempo (TWR): Dietz modificado mês a mês, encadeado.",
    "Valores brutos, antes do IR estimado da renda fixa.",
    "Proventos pagos no mês entram como rendimento (o histórico de preços não é ajustado por proventos).",
    "Meses passados de ativos sem cotação (outros, preço manual) ficam no custo; o ganho aparece no mês atual.",
    "Mês sem fechamento no histórico usa o último disponível ou o preço de hoje.",
    "O mês atual vai até hoje, pela cotação atual: o mesmo valor da Posição.",
    "Índices de comparação: IPCA pela variação mensal do IBGE (BCB); Ibovespa, IFIX e IDIV pelo fechamento do fim de cada mês (índices de retorno total).",
]

# Abaixo disto (em reais) um valor ou a base do mes e zero: o mes e pulado.
EPSILON = 0.005


def returns_evaluated_months(months_back):
    """Meses avaliados para uma janela de `months_back`: um a mais (o V0 do
    primeiro) e, no minimo, o ano corrente inteiro (acumulado no ano)."""
    return max(months_back, datetime.now().month) + 1


def flow_weights(flows, period_days, v0, v1):
    """Peso de cada fluxo [(dia, valor)]: a fracao do periodo em que ficou investido.

    Um fluxo no dia d entra no inicio do dia; o periodo vai do inicio do dia 1
    ao fim do dia `period_days`. Sem valor inicial (V0 = 0), o periodo comeca na
    primeira entrada — senao uma compra no dia 30 teria a base dividida por 30 e
    o ganho dela multiplicado por 30. Sem valor final (venda total), o periodo
    termina na ultima saida, pelo mesmo motivo.
    """
    start = 0.0
    end = float(period_days)
    if v0 <= EPSILON:
        inflow_days = [day for day, amount in flows if amount > 0]
        if inflow_days:
            start = float(min(inflow_days) - 1)
    if v1 <= EPSILON:
        outflow_days = [day for day, amount in flows if amount < 0]
        if outflow_days:
            end = float(max(outflow_days) - 1)
    length = end - start
    weights = []
    for day, amount in flows:
        if length <= 0:
            # Entrou e saiu no mesmo dia: a base e o que entrou.
            weight = 1.0 if amount > 0 else 0.0
        else:
            weight = (end - (day - 1)) / length
        weights.append(min(max(weight, 0.0), 1.0))
    return weights


def modified_dietz(v0, v1, flows=(), income=0.0, period_days=30):
    """Retorno do mes (fracao) ou None quando nao ha base (mes sem valor nem aporte).

    `flows` e [(dia do mes, valor)]: positivo e aporte, negativo e retirada.
    `income` sao os proventos pagos no mes.
    """
    flows = [(int(day), safe_float(amount)) for day, amount in flows if safe_float(amount) != 0]
    v0 = max(safe_float(v0), 0.0)
    v1 = max(safe_float(v1), 0.0)
    if not PRICES_ARE_DIVIDEND_ADJUSTED:
        income = safe_float(income)
    else:
        income = 0.0
    net_flow = sum(amount for _, amount in flows)
    weights = flow_weights(flows, period_days, v0, v1)
    base = v0 + sum(weight * amount for weight, (_, amount) in zip(weights, flows))
    if base <= EPSILON:
        return None
    return (v1 - v0 - net_flow + income) / base


def chain_returns(returns):
    """Encadeia retornos mensais (fracoes); None e mes pulado. None se nenhum conta."""
    factor = 1.0
    counted = 0
    for value in returns:
        if value is None:
            continue
        factor *= 1 + value
        counted += 1
    return factor - 1 if counted else None


def cdi_monthly_returns(cdi_daily, keys):
    """{AAAA-MM: retorno do CDI no mes} a partir da serie diaria (decimal ao dia)."""
    factors = {}
    for day, rate in cdi_daily or []:
        key = month_key(day)
        factors[key] = factors.get(key, 1.0) * (1 + safe_float(rate))
    return {key: factors[key] - 1 for key in keys if key in factors}


def year_month_table(monthly):
    """[(AAAA-MM, retorno ou None)] -> uma linha por ano, 12 colunas e o total do ano."""
    years = {}
    for key, value in monthly:
        year, month = int(key[:4]), int(key[5:7])
        years.setdefault(year, [None] * 12)[month - 1] = value
    return [
        {
            "year": year,
            "months": [percent(value) for value in values],
            "total_percent": percent(chain_returns(values)),
        }
        for year, values in sorted(years.items())
    ]


def percent(value):
    """Fracao -> percentual com duas casas (nao e dinheiro)."""
    return None if value is None else round(value * 100, 2)


def period_days_of(month_start, now):
    if month_key(month_start) == month_key(now):
        return now.day
    return calendar.monthrange(month_start.year, month_start.month)[1]


def movement_flow_amount(investment):
    """Fluxo externo em reais: + compra, - venda/resgate (o que entrou no caixa)."""
    metadata = investment.get("metadata") or {}
    quantity = safe_float(investment.get("quantity"))
    if quantity > 0 and not metadata.get("is_redemption"):
        return quantity * safe_float(investment.get("average_price"))
    cash = investment_cash_amount(investment)
    if cash is None:
        cash = investment_gross_proceeds(investment, metadata)
    return -safe_float(cash)


def movement_flows(investments):
    """{group_key: {AAAA-MM: [(dia, valor)]}} e a data da primeira compra de cada posicao."""
    flows = {}
    first_purchase = {}
    for investment in investments:
        group_key = evolution_group_key(investment)
        if group_key is None:
            continue
        date = investment_movement_date(investment)
        amount = movement_flow_amount(investment)
        flows.setdefault(group_key, {}).setdefault(month_key(date), []).append((date.day, amount))
        if amount > 0 or safe_float(investment.get("quantity")) > 0:
            if group_key not in first_purchase or date < first_purchase[group_key]:
                first_purchase[group_key] = date
    return flows, first_purchase


def fetch_period_income(current_user_id, investments, start_date, end_date, asset_class=None):
    """Proventos liquidos pagos entre as datas: {group_key: {AAAA-MM: valor}}.

    Renda fixa agrupa pelo titulo: a amortizacao aponta para o ativo, e o ativo
    vai para o primeiro titulo (compra) dele."""
    fixed_income_groups = {}
    for investment in investments:
        if (
            investment.get("asset_class") == "FIXED_INCOME"
            and safe_float(investment.get("quantity")) > 0
            and investment.get("asset_id")
        ):
            key = evolution_group_key(investment)
            if key is not None:
                fixed_income_groups.setdefault(str(investment["asset_id"]), key)

    query = """
        SELECT p.asset_id, p.payment_date, p.net_amount, a.asset_class, a.ticker
        FROM investment_proceeds p
        JOIN assets a ON a.id = p.asset_id AND a.user_id = p.user_id
        WHERE p.user_id = ?
          AND p.payment_date >= ?
          AND p.payment_date <= ?
    """
    params = [current_user_id, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]
    if asset_class:
        query += " AND a.asset_class = ?"
        params.append(asset_class)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()

    income = {}
    for row in rows:
        if row["asset_class"] == "FIXED_INCOME":
            group_key = fixed_income_groups.get(str(row["asset_id"]))
            if group_key is None:
                continue
        else:
            group_key = f"{row['asset_class']}:{ticker_key(row['ticker'])}"
        key = str(row["payment_date"])[:7]
        bucket = income.setdefault(group_key, {})
        bucket[key] = bucket.get(key, 0.0) + safe_float(row["net_amount"])
    return income


def month_return(month_index, months, group_keys, flows, income, now):
    """Retorno do mes `month_index` para o conjunto `group_keys` (None = todos)."""
    month_start, positions = months[month_index]
    _, previous = months[month_index - 1]
    key = month_key(month_start)

    def value_of(valued):
        return sum(
            item["gross"] for group, item in valued.items()
            if group_keys is None or group in group_keys
        )

    selected = flows.keys() if group_keys is None else [g for g in group_keys if g in flows]
    month_flows = [flow for group in selected for flow in flows[group].get(key, [])]
    selected_income = income.keys() if group_keys is None else [g for g in group_keys if g in income]
    month_income = sum(income[group].get(key, 0.0) for group in selected_income)
    v0 = value_of(previous)
    v1 = value_of(positions)
    value = modified_dietz(v0, v1, month_flows, month_income, period_days_of(month_start, now))
    return value, v1, sum(amount for _, amount in month_flows), month_income


def build_investment_returns(
    current_user_id,
    investments,
    historical_prices,
    months_back,
    *,
    index_series=None,
    cdi_series=None,
    benchmarks=None,
    asset_class=None,
):
    """TWR da carteira no periodo e no ano, serie mensal, tabela ano x mes e TWR por ativo.

    `benchmarks` e o que `services.benchmarks.load_benchmarks()` devolve:
    {codigo: {"label", "monthly": {AAAA-MM: fracao}, "source", "error", ...}}.
    """
    now = datetime.now()
    evaluated = returns_evaluated_months(months_back)
    months = list(iter_portfolio_months(investments, historical_prices, evaluated, index_series))
    flows, first_purchase = movement_flows(investments)
    first_month = months[1][0]
    income = fetch_period_income(current_user_id, investments, first_month, now, asset_class)

    keys = [month_key(month_start) for month_start, _ in months]
    cdi = cdi_monthly_returns(cdi_series, keys) if cdi_series else {}

    monthly = []
    for index in range(1, len(months)):
        value, v1, net_flow, month_income = month_return(index, months, None, flows, income, now)
        monthly.append({
            "month_start": months[index][0],
            "return": value,
            "value": v1,
            "net_flow": net_flow,
            "income": month_income,
        })

    window = monthly[-months_back:]
    current_year = now.year
    ytd = [item for item in monthly if item["month_start"].year == current_year]

    benchmarks = benchmarks or {}
    window_keys = [month_key(item["month_start"]) for item in window]
    benchmark_paths = {
        code: accumulate_benchmark(entry.get("monthly") or {}, window_keys)
        for code, entry in benchmarks.items()
    }

    series = []
    accumulated = 1.0
    cdi_accumulated = 1.0
    for position, item in enumerate(window):
        key = month_key(item["month_start"])
        if item["return"] is not None:
            accumulated *= 1 + item["return"]
        cdi_return = cdi.get(key)
        if cdi_return is not None:
            cdi_accumulated *= 1 + cdi_return
        series.append({
            "benchmarks": {
                code: {
                    "return_percent": percent((benchmarks[code].get("monthly") or {}).get(key)),
                    "accumulated_percent": percent(path[position]),
                }
                for code, path in benchmark_paths.items()
            },
            "month_key": key,
            "month": month_label(item["month_start"]),
            "return_percent": percent(item["return"]),
            "accumulated_percent": percent(accumulated - 1),
            "cdi_return_percent": percent(cdi_return),
            "cdi_accumulated_percent": percent(cdi_accumulated - 1) if cdi else None,
            "value": rounded_money(item["value"]),
            "net_flow": rounded_money(item["net_flow"]),
            "income": rounded_money(item["income"]),
        })

    twr = chain_returns(item["return"] for item in window)
    ytd_twr = chain_returns(item["return"] for item in ytd)
    ytd_keys = [month_key(item["month_start"]) for item in ytd]
    cdi_period = chain_returns(cdi.get(key) for key in window_keys) if cdi else None
    cdi_ytd = chain_returns(cdi.get(key) for key in ytd_keys) if cdi else None

    # Por ativo: TWR desde a primeira compra, limitado a janela pedida.
    window_start_index = len(months) - months_back
    window_start = months[window_start_index][0]
    group_info = {}
    for month_start, positions in months[window_start_index - 1:]:
        for group, item in positions.items():
            group_info[group] = {"ticker": item["ticker"], "class": item["class"]}
    for investment in investments:
        group = evolution_group_key(investment)
        if group is None or group in group_info:
            continue
        if month_key(investment_movement_date(investment)) in window_keys:
            group_info[group] = {
                "ticker": ticker_key(investment.get("ticker_or_name")),
                "class": investment.get("asset_class"),
            }

    last_positions = months[-1][1]
    assets = []
    for group, info in group_info.items():
        returns = []
        for index in range(window_start_index, len(months)):
            value, _, _, _ = month_return(index, months, {group}, flows, income, now)
            returns.append(value)
        asset_twr = chain_returns(returns)
        if asset_twr is None:
            continue
        purchase = first_purchase.get(group)
        capped = purchase is None or purchase < window_start
        since = window_start if capped else purchase.replace(day=1)
        current = last_positions.get(group)
        assets.append({
            "key": group,
            "ticker": info["ticker"],
            "class": info["class"],
            "twr_percent": percent(asset_twr),
            "first_purchase": purchase.strftime("%Y-%m-%d") if purchase else None,
            "since": month_key(since),
            "capped": capped,
            "months_counted": sum(1 for value in returns if value is not None),
            "current_value": rounded_money(current["gross"]) if current else 0.0,
            "open": current is not None,
        })
    assets.sort(key=lambda item: (not item["open"], -item["current_value"], item["ticker"] or ""))

    return {
        "method": "modified_dietz_monthly",
        "basis": VALUE_BASIS,
        "basis_label": VALUE_BASIS_LABEL,
        "months": months_back,
        "period": {"start": window_keys[0], "end": window_keys[-1]},
        "twr_percent": percent(twr),
        "ytd_percent": percent(ytd_twr),
        "cdi_available": bool(cdi),
        "cdi_percent": percent(cdi_period),
        "ytd_cdi_percent": percent(cdi_ytd),
        "percent_of_cdi": percent_of(twr, cdi_period),
        "ytd_percent_of_cdi": percent_of(ytd_twr, cdi_ytd),
        "benchmarks": [
            benchmark_summary(code, benchmarks[code], window_keys, ytd_keys, twr)
            for code in benchmarks
        ],
        "series": series,
        # `monthly` e a janela mais o ano corrente inteiro.
        "years": year_month_table(
            [(month_key(item["month_start"]), item["return"]) for item in monthly]
        ),
        "assets": assets,
        "assets_note": (
            "TWR de cada ativo desde a primeira compra, limitado à janela pedida "
            f"(a partir de {month_label(window_start)}) — 'capped' indica a compra anterior a ela."
        ),
        "notes": RETURN_NOTES,
    }


def accumulate_benchmark(monthly, keys):
    """Acumulado (fracao) de um indice em cada mes de `keys`.

    None no mes sem retorno (antes do primeiro dado, ou o IPCA ainda nao
    divulgado): a linha do grafico some ali em vez de ficar reta. O acumulado
    segue dos meses que existem."""
    factor = 1.0
    path = []
    for key in keys:
        value = monthly.get(key)
        if value is None:
            path.append(None)
            continue
        factor *= 1 + value
        path.append(factor - 1)
    return path


def benchmark_summary(code, entry, window_keys, ytd_keys, twr):
    """Total do indice no periodo e no ano, e quantos meses do periodo ele cobre."""
    monthly = entry.get("monthly") or {}
    covered = [key for key in window_keys if key in monthly]
    period = chain_returns(monthly.get(key) for key in window_keys)
    complete = bool(window_keys) and len(covered) == len(window_keys)
    return {
        "code": code,
        "label": entry.get("label") or code,
        "available": bool(covered),
        "complete": complete,
        "months_covered": len(covered),
        "months_total": len(window_keys),
        "first_month": covered[0] if covered else None,
        "last_month": covered[-1] if covered else None,
        "period_percent": percent(period),
        "ytd_percent": percent(chain_returns(monthly.get(key) for key in ytd_keys)),
        # Diferenca em pontos percentuais so quando o indice cobre o periodo
        # inteiro: comparar 12 meses da carteira com 3 do IFIX engana.
        "difference_pp": (
            round((twr - period) * 100, 2) if complete and twr is not None and period is not None else None
        ),
        "source": entry.get("source"),
        "note": benchmark_note(code, entry, window_keys, covered),
    }


def percent_of(value, benchmark):
    """Retorno como % do CDI no mesmo periodo; None sem CDI positivo."""
    if value is None or benchmark is None or benchmark <= 0:
        return None
    return round(value / benchmark * 100, 2)
