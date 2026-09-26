"""Aportes x resgates por mes (grafico de Operacoes).

Le `fetch_investments()` — o fluxo em reais: a compra de um ativo no exterior
entra pelo cambio da propria compra, a venda pelo cambio da venda. Somar
`fetch_investment_rows()` misturaria dolar com real.

O que conta:

- aporte = compra (quantidade x preco), sem os custos — o mesmo valor que o
  caixa ligado debita e a coluna "Total" da lista mostra;
- resgate = venda (quantidade x preco de venda) ou resgate de renda fixa (o
  valor resgatado), brutos, sem custos nem IR. O vencimento de um titulo e
  registrado como resgate, entao conta aqui;
- a bonificacao (017) e uma compra sem caixa (`corporate_action_id` no
  metadata): fica de fora, nao e dinheiro novo;
- amortizacao e provento (`investment_proceeds`), nao movimentacao: fica de
  fora, como dividendo — e renda do ativo, nao capital que voltou por decisao
  de vender.

A janela sao os ultimos `months` meses ate o atual, todos presentes (mes sem
operacao sai zerado), para o grafico nao pular meses. O mes e o da data da
operacao (`investment_operation_date()`).
"""

from dates import month_key, subtract_months
from money import rounded_money
from services.corporate_actions import is_bonus_movement
from services.investments import (
    fetch_investments,
    investment_gross_amount,
    investment_gross_proceeds,
    investment_movement_type,
    investment_operation_date,
)
from services.invoices import local_today

DEFAULT_MONTHS = 12
MAX_MONTHS = 60


def window_months(months, today):
    """As chaves AAAA-MM dos ultimos `months` meses, do mais antigo ao atual."""
    first_of_month = today.replace(day=1)
    return [month_key(subtract_months(first_of_month, back)) for back in range(months - 1, -1, -1)]


def movement_flow(investment):
    """("aportes" | "resgates", valor bruto em reais) ou None quando nao conta."""
    metadata = investment.get("metadata") or {}
    if is_bonus_movement(metadata):
        return None
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    if movement_type == "BUY":
        return "aportes", investment_gross_amount(investment.get("quantity"), investment.get("average_price"))
    if movement_type in {"SELL", "REDEMPTION"}:
        return "resgates", investment_gross_proceeds(investment, metadata)
    return None


def aggregate_contributions(investments, months, today, asset_class=None):
    """Funcao pura: agrega a lista (ja em reais) nos meses da janela."""
    keys = window_months(months, today)
    buckets = {key: {"aportes": 0.0, "resgates": 0.0, "count": 0} for key in keys}
    for investment in investments:
        if asset_class and investment.get("asset_class") != asset_class:
            continue
        flow = movement_flow(investment)
        if not flow:
            continue
        month = investment_operation_date(investment)[:7]
        bucket = buckets.get(month)
        if bucket is None:
            continue
        side, amount = flow
        if amount > 0:
            bucket[side] += amount
            bucket["count"] += 1

    rows = []
    for key in keys:
        bucket = buckets[key]
        aportes = rounded_money(bucket["aportes"])
        resgates = rounded_money(bucket["resgates"])
        rows.append({
            "month": key,
            "aportes": aportes,
            "resgates": resgates,
            "liquido": rounded_money(aportes - resgates),
            "count": bucket["count"],
        })

    # Totais a partir dos meses ja arredondados: a tabela fecha no centavo.
    total_aportes = rounded_money(sum(row["aportes"] for row in rows))
    total_resgates = rounded_money(sum(row["resgates"] for row in rows))
    return {
        "months": rows,
        "totals": {
            "aportes": total_aportes,
            "resgates": total_resgates,
            "liquido": rounded_money(total_aportes - total_resgates),
            "count": sum(row["count"] for row in rows),
        },
        "start_month": keys[0],
        "end_month": keys[-1],
        "asset_class": asset_class,
    }


def clamp_months(value):
    try:
        months = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MONTHS
    return min(max(months, 1), MAX_MONTHS)


def build_contributions(current_user_id, months=DEFAULT_MONTHS, asset_class=None):
    return aggregate_contributions(
        fetch_investments(current_user_id),
        clamp_months(months),
        local_today(),
        asset_class,
    )
