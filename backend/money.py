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
