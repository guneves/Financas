"""Dinheiro: todo valor monetario arredonda por aqui, nunca pelo round() do Python."""

import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from validators import safe_float


def rounded_money(value):
    """Arredonda valores monetarios para centavos com ROUND_HALF_UP.

    O round() do Python usa banker's rounding (metade para o par), entao
    0.125 virava 0.12 e 0.135 virava 0.14 — comportamento inconsistente para
    dinheiro. A conversao via str() recupera a intencao decimal do float
    antes de quantizar, evitando herdar o erro de representacao binaria.
    """
    numeric = safe_float(value)
    if not math.isfinite(numeric):
        return 0.0
    try:
        return float(Decimal(str(numeric)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0.0


CENT = Decimal("0.01")


def percent_of(amount, percent):
    """`percent`% de `amount`, em reais: a regra de rounded_money() (ROUND_HALF_UP
    em centavos) aplicada ao produto exato em Decimal.

    `percent` e o Decimal guardado com seis casas (038); passar o produto por
    float antes de arredondar perderia digitos. Plano do mes: renda x Investir/
    Gastar %, e Gastar em reais x % da categoria.
    """
    base = Decimal(str(rounded_money(amount)))
    value = base * Decimal(percent) / Decimal(100)
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))
