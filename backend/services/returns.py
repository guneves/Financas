"""Rentabilidade ponderada no tempo (TWR), da carteira e de cada ativo.

Metodo: retorno diario encadeado (o "uma vez ao dia" do Investidor10). Para
cada dia,

    r = (V1 + S + D) / (V0 + B) - 1

V0 e V1 sao o valor no fim do dia anterior e deste, B as compras do dia (entram
no inicio, pelo preco pago), S as vendas e resgates (saem no fim, pelo valor
recebido) e D os proventos pagos no dia (renda, nao fluxo). O mes e o produto
dos seus dias; TWR = produto(1 + r) - 1. Uma bonificacao nao e fluxo: as cotas
chegam sem dinheiro, e o preco cai na mesma proporcao.

Valor BRUTO: V0 e V1 sao o valor de mercado antes do IR estimado da renda fixa
(o que corretoras e o Investidor10 mostram).

Cada dia vale:
- cotados: quantidade x o ultimo fechamento ate o dia, na base das quantidades
  gravadas (`restore_quantity_basis()`: o Yahoo trata bonificacao como
  desdobramento); sem fechamento nenhum, o custo;
- renda fixa: o aplicado corrigido pela serie do BCB, exata no fim de cada mes
  e interpolada (geometricamente) entre um fim de mes e o seguinte;
- hoje: o que a Posicao mostra (`position_value_today()`).

Distorcoes conhecidas (tambem em `RETURN_NOTES`, que vai na resposta):
- ativos sem cotacao (outros, preco manual) ficam no custo, e o ganho inteiro
  cai hoje (ou no dia da venda);
- ativo no exterior: cada dia pela PTAX do fim do seu mes; proventos de ativo
  no exterior entram como reais.

As funcoes de conta (`daily_return`, `chain_returns`, `cdi_monthly_returns`,
`year_month_table`) sao puras; `build_investment_returns()` junta as posicoes,
os fluxos e os proventos do usuario.
"""

from bisect import bisect_right
from datetime import datetime, timedelta

from asset_classes import is_quoted_asset
from dates import month_end, month_key, month_label, subtract_months
from db import get_db
from money import rounded_money
from services.benchmarks import benchmark_note
from services.corporate_actions import is_bonus_movement
from services.fixed_income import accrual_factor_until
from services.investments import investment_cash_amount, investment_gross_proceeds
from services.portfolio import (
    add_movement_to_positions,
    evolution_group_key,
    investment_movement_date,
    position_is_open,
    position_value_today,
)
from services.prices import ticker_key
from validators import safe_float

# O fechamento vem com auto_adjust=False (services/prices.py): o preco NAO
# desconta os proventos, entao eles entram como renda no dia em que sao pagos.
# Se o historico passar a vir ajustado, isto vira True e os proventos deixam
# de ser somados — senao contariam duas vezes.
PRICES_ARE_DIVIDEND_ADJUSTED = False

VALUE_BASIS = "gross"
VALUE_BASIS_LABEL = "Valor bruto (antes do IR estimado da renda fixa)"

RETURN_NOTES = [
    "Rentabilidade ponderada no tempo (TWR): retorno diário encadeado, como o Investidor10.",
    "Valores brutos, antes do IR estimado da renda fixa.",
    "Proventos pagos no dia entram como rendimento (o histórico de preços não é ajustado por proventos).",
    "Bonificação não é aporte: as cotas chegam sem dinheiro.",
    "Ativos sem cotação (outros, preço manual) ficam no custo; o ganho aparece hoje ou na venda.",
    "Hoje vale a cotação atual: o mesmo valor da Posição.",
    "Índices de comparação: IPCA pela variação mensal do IBGE (BCB); Ibovespa, IFIX e IDIV pelo fechamento do fim de cada mês (índices de retorno total).",
    "Comparação justa: a carteira, o CDI e cada índice partem de 0% no mesmo ponto — o fim do mês anterior ao período, ou ao mês da primeira operação quando ela veio depois do início do período.",
]

# Abaixo disto (em reais) a base do dia e zero: o dia e pulado.
EPSILON = 0.005


def returns_evaluated_months(months_back):
    """Meses avaliados para uma janela de `months_back`: um a mais (o V0 do
    primeiro) e, no minimo, o ano corrente inteiro (acumulado no ano)."""
    return max(months_back, datetime.now().month) + 1


def daily_return(previous_value, value, inflow=0.0, outflow=0.0, income=0.0):
    """Retorno do dia (fracao) ou None quando nao ha base (dia sem valor nem compra).

    `inflow` sao as compras do dia (entram no inicio, pelo preco pago);
    `outflow`, o que vendas e resgates pagaram (sai no fim); `income`, os
    proventos pagos no dia.
    """
    previous_value = max(safe_float(previous_value), 0.0)
    value = max(safe_float(value), 0.0)
    income = 0.0 if PRICES_ARE_DIVIDEND_ADJUSTED else safe_float(income)
    base = previous_value + safe_float(inflow)
    if base <= EPSILON:
        return None
    return (value + safe_float(outflow) + income) / base - 1


def chain_returns(returns):
    """Encadeia retornos (fracoes); None e periodo pulado. None se nenhum conta."""
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


def movement_flow_amount(investment):
    """Fluxo externo em reais: + compra, - venda/resgate (o que entrou no caixa).

    Bonificacao e zero: nenhum dinheiro entrou; o custo atribuido a ela e regra
    do IR, nao aporte."""
    metadata = investment.get("metadata") or {}
    if is_bonus_movement(metadata):
        return 0.0
    quantity = safe_float(investment.get("quantity"))
    if quantity > 0 and not metadata.get("is_redemption"):
        return quantity * safe_float(investment.get("average_price"))
    cash = investment_cash_amount(investment)
    if cash is None:
        cash = investment_gross_proceeds(investment, metadata)
    return -safe_float(cash)


def movement_flows(investments):
    """{group_key: {AAAA-MM-DD: (compras, vendas)}} e a data da primeira compra de cada posicao."""
    flows = {}
    first_purchase = {}
    for investment in investments:
        group_key = evolution_group_key(investment)
        if group_key is None:
            continue
        date = investment_movement_date(investment)
        amount = movement_flow_amount(investment)
        by_day = flows.setdefault(group_key, {})
        inflow, outflow = by_day.get(date.strftime("%Y-%m-%d"), (0.0, 0.0))
        if amount > 0:
            inflow += amount
        else:
            outflow -= amount
        by_day[date.strftime("%Y-%m-%d")] = (inflow, outflow)
        if amount > 0 or safe_float(investment.get("quantity")) > 0:
            if group_key not in first_purchase or date < first_purchase[group_key]:
                first_purchase[group_key] = date
    return flows, first_purchase


def fetch_period_income(current_user_id, investments, start_date, end_date, asset_class=None):
    """Proventos liquidos pagos entre as datas: {group_key: {AAAA-MM-DD: valor}}.

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
        key = str(row["payment_date"])[:10]
        bucket = income.setdefault(group_key, {})
        bucket[key] = bucket.get(key, 0.0) + safe_float(row["net_amount"])
    return income


class PriceHistory:
    """Ultimo fechamento ate um dia, por ticker, de {ticker: {AAAA-MM-DD: preco}}."""

    def __init__(self, daily_prices):
        self.days = {}
        self.prices = {}
        for ticker, by_day in (daily_prices or {}).items():
            ordered = sorted(by_day)
            self.days[ticker] = ordered
            self.prices[ticker] = [by_day[day] for day in ordered]

    def close_on(self, ticker, day):
        days = self.days.get(ticker)
        if not days:
            return None
        index = bisect_right(days, day)
        return self.prices[ticker][index - 1] if index else None


class FixedIncomeCurve:
    """Fator de correcao de um titulo em qualquer dia: exato no fim de cada mes
    (e hoje), interpolado geometricamente por tempo corrido entre um e outro.
    Calcular a serie inteira em cada dia seria quadratico nos dias."""

    def __init__(self, index_series, today_end):
        self.index_series = index_series
        self.today_end = today_end
        self.anchors = {}
        # {(titulo, compra, ano, mes): (inicio, fator no inicio, fator no fim, duracao)}:
        # os dias de um mes so mudam o peso da interpolacao.
        self.segments = {}

    def anchor(self, metadata, purchase, until):
        key = (id(metadata), purchase, until)
        if key not in self.anchors:
            self.anchors[key] = accrual_factor_until(metadata, purchase, until, self.index_series)
        return self.anchors[key]

    def segment(self, metadata, purchase, day_end):
        key = (id(metadata), purchase, day_end.year, day_end.month)
        if key not in self.segments:
            end = min(month_end(day_end), self.today_end)
            end_factor = self.anchor(metadata, purchase, end)
            if end_factor is None:
                self.segments[key] = None
            else:
                start = month_end(subtract_months(day_end.replace(day=1), 1))
                if start < purchase:
                    start, start_factor = purchase, 1.0
                else:
                    start_factor = self.anchor(metadata, purchase, start)
                self.segments[key] = (start, start_factor, end_factor, (end - start).total_seconds())
        return self.segments[key]

    def factor(self, metadata, purchase, day_end):
        if not self.index_series or purchase is None:
            return None
        purchase = datetime(purchase.year, purchase.month, purchase.day)
        if day_end <= purchase:
            return 1.0
        segment = self.segment(metadata, purchase, day_end)
        if segment is None:
            return None
        start, start_factor, end_factor, span = segment
        if not start_factor or start_factor <= 0 or span <= 0:
            return end_factor
        weight = min(max((day_end - start).total_seconds() / span, 0.0), 1.0)
        return start_factor * (end_factor / start_factor) ** weight


def position_value_on(position, day_end, is_today, prices, curve, day_key=None):
    """Valor bruto de uma posicao no fim do dia (`day_key`: o dia em AAAA-MM-DD)."""
    quantity = position["quantity"]
    applied = position["applied"]
    if is_today:
        return position_value_today(
            position["class"], quantity, applied, position["original_applied"],
            position.get("current_price"), position["metadata"],
        )
    if is_quoted_asset(position["class"], position["ticker"]):
        price = prices.close_on(position["ticker"], day_key or day_end.strftime("%Y-%m-%d"))
        if price is None:
            price = applied / quantity
        return quantity * price
    if position["class"] == "FIXED_INCOME":
        factor = curve.factor(position["metadata"], position.get("purchase_date"), day_end)
        return applied * factor if factor else applied
    return applied


def daily_group_values(investments, daily_prices, index_series, first_day, now):
    """[(AAAA-MM-DD, {group_key: valor bruto})] no fim de cada dia, de `first_day` a hoje."""
    today = datetime(now.year, now.month, now.day)
    prices = PriceHistory(daily_prices)
    curve = FixedIncomeCurve(index_series, today.replace(hour=23, minute=59, second=59))
    # A data de cada movimentacao, lida uma vez (nao a cada dia do laco).
    ordered = sorted(
        ((investment_movement_date(investment), investment) for investment in investments),
        key=lambda item: item[0],
    )
    positions = {}
    cursor = 0
    days = []
    day = datetime(first_day.year, first_day.month, first_day.day)
    while day <= today:
        day_end = day.replace(hour=23, minute=59, second=59)
        while cursor < len(ordered) and ordered[cursor][0] <= day_end:
            add_movement_to_positions(positions, ordered[cursor][1])
            cursor += 1
        is_today = day == today
        day_key = day.strftime("%Y-%m-%d")
        values = {
            group: position_value_on(position, day_end, is_today, prices, curve, day_key)
            for group, position in positions.items()
            if position_is_open(position)
        }
        days.append((day_key, values))
        day += timedelta(days=1)
    return days


def monthly_chain(days, group_keys, flows, income):
    """Retornos diarios encadeados por mes para `group_keys` (None = todos).

    Devolve ({AAAA-MM: retorno}, {AAAA-MM: (valor no fim, fluxo liquido, proventos)});
    o primeiro dia de `days` e so o valor inicial."""
    flow_groups = list(flows) if group_keys is None else [g for g in group_keys if g in flows]
    income_groups = list(income) if group_keys is None else [g for g in group_keys if g in income]

    def value_of(values):
        if group_keys is None:
            return sum(values.values())
        return sum(values.get(group, 0.0) for group in group_keys)

    factors = {}
    totals = {}
    previous = value_of(days[0][1]) if days else 0.0
    for day, values in days[1:]:
        inflow = outflow = 0.0
        for group in flow_groups:
            day_in, day_out = flows[group].get(day, (0.0, 0.0))
            inflow += day_in
            outflow += day_out
        day_income = sum(income[group].get(day, 0.0) for group in income_groups)
        value = value_of(values)
        result = daily_return(previous, value, inflow, outflow, day_income)
        key = day[:7]
        if result is not None:
            factors[key] = factors.get(key, 1.0) * (1 + result)
        _, net_flow, month_income = totals.get(key, (0.0, 0.0, 0.0))
        totals[key] = (value, net_flow + inflow - outflow, month_income + day_income)
        previous = value
    return {key: factor - 1 for key, factor in factors.items()}, totals


def group_monthly_returns(days, groups, flows, income):
    """{grupo: {AAAA-MM: retorno}} de cada um de `groups`, numa passada so por `days`.

    E o `monthly_chain(days, {grupo}, ...)` de cada grupo (a TWR por ativo),
    sem percorrer os dias uma vez por ativo."""
    groups = list(groups)
    factors = {group: {} for group in groups}
    if not days:
        return factors
    previous = {group: days[0][1].get(group, 0.0) for group in groups}
    no_flow = (0.0, 0.0)
    for day, values in days[1:]:
        key = day[:7]
        for group in groups:
            group_flows = flows.get(group)
            inflow, outflow = group_flows.get(day, no_flow) if group_flows else no_flow
            value = values.get(group, 0.0)
            last = previous[group]
            previous[group] = value
            # A conta de daily_return, escrita aqui: e o laco mais quente da
            # rentabilidade (ativos x dias). Sem valor nem compra nao ha base.
            base = max(last, 0.0) + inflow
            if base <= EPSILON:
                continue
            day_income = 0.0
            if not PRICES_ARE_DIVIDEND_ADJUSTED:
                group_income = income.get(group)
                if group_income:
                    day_income = group_income.get(day, 0.0)
            by_month = factors[group]
            result = (max(value, 0.0) + outflow + day_income) / base - 1
            by_month[key] = by_month.get(key, 1.0) * (1 + result)
    return {group: {key: factor - 1 for key, factor in by_month.items()} for group, by_month in factors.items()}


def build_investment_returns(
    current_user_id,
    investments,
    daily_prices,
    months_back,
    *,
    index_series=None,
    cdi_series=None,
    benchmarks=None,
    asset_class=None,
):
    """TWR da carteira no periodo e no ano, serie mensal, tabela ano x mes e TWR por ativo.

    `daily_prices` e {ticker: {AAAA-MM-DD: fechamento}} na base das quantidades
    (`load_history_inputs()` em routes/investments.py). `benchmarks` e o que
    `services.benchmarks.load_benchmarks()` devolve:
    {codigo: {"label", "monthly": {AAAA-MM: fracao}, "source", "error", ...}}.
    """
    now = datetime.now()
    evaluated = returns_evaluated_months(months_back)
    current_month = datetime(now.year, now.month, 1)
    month_starts = [subtract_months(current_month, evaluated - 1 - index) for index in range(evaluated)]
    # O valor inicial do primeiro mes da conta e o fim do mes anterior a ele.
    days = daily_group_values(investments, daily_prices, index_series, month_end(month_starts[0]), now)
    flows, first_purchase = movement_flows(investments)
    income = fetch_period_income(current_user_id, investments, month_starts[1], now, asset_class)

    keys = [month_key(month_start) for month_start in month_starts]
    cdi = cdi_monthly_returns(cdi_series, keys) if cdi_series else {}

    portfolio_returns, portfolio_totals = monthly_chain(days, None, flows, income)
    monthly = []
    for month_start in month_starts[1:]:
        key = month_key(month_start)
        value, net_flow, month_income = portfolio_totals.get(key, (0.0, 0.0, 0.0))
        monthly.append({
            "month_start": month_start,
            "return": portfolio_returns.get(key),
            "value": value,
            "net_flow": net_flow,
            "income": month_income,
        })

    window = monthly[-months_back:]
    current_year = now.year
    ytd = [item for item in monthly if item["month_start"].year == current_year]

    benchmarks = benchmarks or {}
    window_keys = [month_key(item["month_start"]) for item in window]
    # Comparacao justa: a carteira e cada indice partem de 0% no mesmo dia. Os
    # meses da janela antes da primeira operacao ficam de fora (o indice nao
    # rende sozinho enquanto a carteira nao existia), e o ponto de partida e o
    # fim do mes anterior ao primeiro comparado.
    compared = compared_months(window)
    compared_keys = [month_key(item["month_start"]) for item in compared]
    ytd_compared = compared_months(ytd)
    ytd_keys = [month_key(item["month_start"]) for item in ytd_compared]
    base_month = subtract_months(compared[0]["month_start"], 1)
    base_key = month_key(base_month)
    if base_key in portfolio_totals:
        base_value = portfolio_totals[base_key][0]
    else:
        base_value = sum(days[0][1].values()) if days else 0.0
    benchmark_paths = {
        code: accumulate_benchmark(entry.get("monthly") or {}, compared_keys, from_zero=True)
        for code, entry in benchmarks.items()
    }

    series = [{
        "base": True,
        "benchmarks": {
            code: {"return_percent": None, "accumulated_percent": percent(path[0])}
            for code, path in benchmark_paths.items()
        },
        "month_key": base_key,
        "month": month_label(base_month),
        "return_percent": None,
        "accumulated_percent": 0.0,
        "cdi_return_percent": None,
        "cdi_accumulated_percent": 0.0 if cdi else None,
        "value": rounded_money(base_value),
        "net_flow": 0.0,
        "income": 0.0,
    }]
    accumulated = 1.0
    cdi_accumulated = 1.0
    for position, item in enumerate(compared, start=1):
        key = month_key(item["month_start"])
        if item["return"] is not None:
            accumulated *= 1 + item["return"]
        cdi_return = cdi.get(key)
        if cdi_return is not None:
            cdi_accumulated *= 1 + cdi_return
        series.append({
            "base": False,
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
    # O CDI e os indices cobrem os mesmos meses da carteira (`compared`).
    cdi_period = chain_returns(cdi.get(key) for key in compared_keys) if cdi else None
    cdi_ytd = chain_returns(cdi.get(key) for key in ytd_keys) if cdi else None

    # Por ativo: TWR desde a primeira compra, limitado a janela pedida.
    window_start = window[0]["month_start"]
    window_first_day = month_end(subtract_months(window_start, 1)).strftime("%Y-%m-%d")
    window_days = [(day, values) for day, values in days if day >= window_first_day]
    in_window = set()
    for _, values in window_days:
        in_window.update(values)
    for group, by_day in flows.items():
        if any(day > window_first_day for day in by_day):
            in_window.add(group)
    group_info = {}
    for investment in investments:
        group = evolution_group_key(investment)
        if group in in_window and group not in group_info:
            group_info[group] = {
                "ticker": ticker_key(investment.get("ticker_or_name")),
                "class": investment.get("asset_class"),
            }

    last_values = days[-1][1] if days else {}
    assets = []
    all_group_returns = group_monthly_returns(window_days, group_info, flows, income)
    for group, info in group_info.items():
        group_returns = all_group_returns[group]
        returns = [group_returns.get(key) for key in window_keys]
        asset_twr = chain_returns(returns)
        if asset_twr is None:
            continue
        purchase = first_purchase.get(group)
        capped = purchase is None or purchase < window_start
        since = window_start if capped else purchase.replace(day=1)
        current = last_values.get(group)
        assets.append({
            "key": group,
            "ticker": info["ticker"],
            "class": info["class"],
            "twr_percent": percent(asset_twr),
            "first_purchase": purchase.strftime("%Y-%m-%d") if purchase else None,
            "since": month_key(since),
            "capped": capped,
            "months_counted": sum(1 for value in returns if value is not None),
            "current_value": rounded_money(current) if current else 0.0,
            "open": current is not None,
        })
    assets.sort(key=lambda item: (not item["open"], -item["current_value"], item["ticker"] or ""))

    return {
        "method": "daily_chained",
        "basis": VALUE_BASIS,
        "basis_label": VALUE_BASIS_LABEL,
        "months": months_back,
        "period": {"start": window_keys[0], "end": window_keys[-1]},
        # Os meses comparados com o CDI e os indices, todos a partir de 0% no
        # fim de `base_month`; `start` depois do da janela quando a carteira
        # (ou a classe) comecou dentro dela.
        "comparison": {
            "base_month": base_key,
            "start": compared_keys[0],
            "end": compared_keys[-1],
            "months": len(compared_keys),
            "starts_after_window": compared_keys[0] != window_keys[0],
        },
        "twr_percent": percent(twr),
        "ytd_percent": percent(ytd_twr),
        "cdi_available": bool(cdi),
        "cdi_percent": percent(cdi_period),
        "ytd_cdi_percent": percent(cdi_ytd),
        "percent_of_cdi": percent_of(twr, cdi_period),
        "ytd_percent_of_cdi": percent_of(ytd_twr, cdi_ytd),
        "benchmarks": [
            benchmark_summary(code, benchmarks[code], compared_keys, ytd_keys, twr)
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


def compared_months(months):
    """Os meses a partir do primeiro com retorno da carteira (todos, se nenhum tem).

    E o trecho em que carteira e indices sao comparados: antes da primeira
    operacao nao ha carteira, e o indice acumularia sozinho."""
    for index, item in enumerate(months):
        if item["return"] is not None:
            return months[index:]
    return months


def accumulate_benchmark(monthly, keys, *, from_zero=False):
    """Acumulado (fracao) de um indice em cada mes de `keys`.

    None no mes sem retorno (antes do primeiro dado, ou o IPCA ainda nao
    divulgado): a linha do grafico some ali em vez de ficar reta. O acumulado
    segue dos meses que existem.

    `from_zero`: um ponto a mais na frente (o fim do mes anterior ao primeiro
    de `keys`), e a linha parte de 0% no fim do mes anterior ao primeiro dado
    do indice — o mesmo ponto de partida da carteira quando ele cobre o
    periodo inteiro."""
    factor = 1.0
    path = [None] if from_zero else []
    started = False
    for key in keys:
        value = monthly.get(key)
        if value is None:
            path.append(None)
            continue
        if from_zero and not started:
            path[-1] = 0.0
        started = True
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
