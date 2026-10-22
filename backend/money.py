"""Dinheiro: todo valor monetario arredonda por aqui, nunca pelo round() do Python."""

import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, localcontext

from validators import ValidationError, parse_number, safe_float


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
        # A precisao padrao do Decimal (28 digitos) nao cabe 1e26 com centavos:
        # o quantize dava InvalidOperation e o valor virava 0.0 sem aviso.
        with localcontext() as context:
            context.prec = 400
            return float(Decimal(str(numeric)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0.0


# Teto de um valor digitado: R$ 1 trilhao. Acima disso e erro de digitacao, e a
# soma de valores assim deixaria de caber num float com centavos.
MAX_MONEY = 1_000_000_000_000


def parse_money(payload, key, label, *, allow_zero=False, allow_negative=False):
    """Um valor em reais do pedido, ja arredondado em centavos.

    O "maior que zero" vale depois do arredondamento: 0,004 passava pelo
    parse_number e era gravado como R$ 0,00 (ou batia no CHECK amount > 0 do
    banco, um 500).
    """
    amount = rounded_money(parse_number(
        payload, key, label,
        minimum=None if allow_negative else 0,
        maximum=MAX_MONEY,
    ))
    if allow_negative and amount < -MAX_MONEY:
        raise ValidationError(f"{label} deve ser maior ou igual a {-MAX_MONEY}.")
    if not allow_zero and amount == 0:
        raise ValidationError(f"{label} deve ser de pelo menos R$ 0,01.")
    return amount


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
