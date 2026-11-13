"""Reais <-> centavos por um caminho so (money.to_cents / from_cents).

Havia oito copias de "reais em centavos" nos servicos, sete delas com o
round() do Python (`int(round(float(v) * 100))`), que o projeto proibe para
dinheiro. Este teste prova que trocar todas por `money.to_cents()` (Decimal,
ROUND_HALF_UP, a regra de rounded_money) nao muda nenhum valor que o app guarda:
todo valor de duas casas da o mesmo centavo nas duas formulas. A unica diferenca
e o meio centavo de um numero com tres casas, onde a formula antiga arredondava
para o par (10,125 -> 1012) e a nova segue rounded_money (1013).
"""

import importlib
import random

import pytest


@pytest.fixture(scope="module")
def money(app_module):
    return importlib.import_module("money")


def old_cents(value):
    """A formula das copias antigas."""
    return int(round(float(value) * 100))


def test_every_two_decimal_value_up_to_10_thousand_reais_keeps_its_cents(money):
    for cents in range(-1_000_000, 1_000_001):
        value = cents / 100
        assert money.to_cents(value) == cents == old_cents(value)


def test_sampled_values_up_to_a_trillion_keep_their_cents(money):
    generator = random.Random(20261112)
    for _ in range(200_000):
        cents = generator.randint(-100_000_000_000_000, 100_000_000_000_000)
        value = cents / 100
        assert money.to_cents(value) == cents == old_cents(value)


def test_sums_and_differences_of_stored_values_keep_their_cents(money):
    generator = random.Random(7)
    for _ in range(200_000):
        a, b = generator.randint(0, 50_000_000) / 100, generator.randint(0, 50_000_000) / 100
        for value in (a + b, a - b, money.rounded_money(a - b)):
            assert money.to_cents(value) == old_cents(value)


@pytest.mark.parametrize("value, cents", [
    (10.125, 1013), (1.005, 101), (18.185, 1819), (0.285, 29), (-10.125, -1013), (0.004, 0), (0.005, 1),
])
def test_half_a_cent_follows_rounded_money(money, value, cents):
    assert money.to_cents(value) == cents
    assert money.to_cents(value) == round(money.rounded_money(value) * 100)


def test_what_to_cents_accepts(money):
    assert money.to_cents("12.34") == 1234
    assert money.to_cents(7) == 700
    with pytest.raises(TypeError):
        money.to_cents(None)
    with pytest.raises(ValueError):
        money.to_cents("doze")
    with pytest.raises(ValueError):
        money.to_cents(float("nan"))
    assert money.cents_or_zero(None) == 0
    assert money.cents_or_zero("doze") == 0
    assert money.cents_or_zero(12.34) == 1234


def test_from_cents_is_the_way_back(money):
    for cents in (0, 1, -1, 1013, 99_999_999, -250):
        assert money.to_cents(money.from_cents(cents)) == cents
    assert money.from_cents(1013) == 10.13
