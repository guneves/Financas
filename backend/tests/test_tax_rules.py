"""Axis 2: regressive fixed-income tax, realized tax rates and money rounding."""

import pytest


@pytest.fixture()
def mod(app_module):
    return app_module


class TestRegressiveFixedIncomeTax:
    """The four Brazilian holding-period brackets, checked at their edges."""

    @pytest.mark.parametrize(
        "days, expected",
        [
            (0, 0.225),
            (1, 0.225),
            (180, 0.225),
            (181, 0.200),
            (360, 0.200),
            (361, 0.175),
            (720, 0.175),
            (721, 0.150),
            (5000, 0.150),
        ],
    )
    def test_bracket_boundaries(self, mod, days, expected):
        assert mod.fixed_income_tax_rate_for_days(days) == expected

    def test_negative_and_none_days_fall_into_the_first_bracket(self, mod):
        assert mod.fixed_income_tax_rate_for_days(-10) == 0.225
        assert mod.fixed_income_tax_rate_for_days(None) == 0.225

    def test_rate_never_increases_with_holding_time(self, mod):
        rates = [mod.fixed_income_tax_rate_for_days(d) for d in range(0, 900, 17)]
        assert rates == sorted(rates, reverse=True)


class TestRealizedTaxRate:
    def test_default_rate_per_asset_class(self, mod):
        assert mod.realized_tax_rate("STOCKS") == 0.15
        assert mod.realized_tax_rate("REIT") == 0.20
        assert mod.realized_tax_rate("OTHER") == 0.15

    def test_unknown_asset_class_is_not_taxed(self, mod):
        assert mod.realized_tax_rate("SOMETHING_ELSE") == 0

    def test_fixed_income_uses_the_regressive_table_when_holding_days_are_known(self, mod):
        assert mod.realized_tax_rate("FIXED_INCOME", {}, holding_days=100) == 0.225
        assert mod.realized_tax_rate("FIXED_INCOME", {}, holding_days=900) == 0.150

    def test_fixed_income_without_holding_days_falls_back_to_the_default(self, mod):
        assert mod.realized_tax_rate("FIXED_INCOME", {}) == 0.15

    def test_tax_free_fixed_income_is_exempt(self, mod):
        assert mod.realized_tax_rate("FIXED_INCOME", {"is_tax_free": True}, holding_days=30) == 0

    def test_explicit_rate_in_metadata_wins_over_every_default(self, mod):
        assert mod.realized_tax_rate("STOCKS", {"tax_rate": 0.05}) == 0.05
        assert mod.realized_tax_rate("FIXED_INCOME", {"tax_rate": 0.1}, holding_days=10) == 0.1

    def test_percent_style_rates_are_normalized_to_a_fraction(self, mod):
        # 20 means "20%", not "2000%".
        assert mod.realized_tax_rate("STOCKS", {"tax_rate": 20}) == 0.20
        assert mod.realized_tax_rate("STOCKS", {"tax_rate_percent": 15}) == 0.15

    def test_invalid_explicit_rates_are_ignored(self, mod):
        assert mod.realized_tax_rate("STOCKS", {"tax_rate": -1}) == 0.15
        assert mod.realized_tax_rate("STOCKS", {"tax_rate": "abc"}) == 0.15


class TestRoundedMoney:
    @pytest.mark.parametrize(
        "value, expected",
        [
            (0.125, 0.13),   # banker's rounding would give 0.12
            (0.135, 0.14),
            (2.675, 2.68),   # the classic float-representation trap
            (1.005, 1.01),
            (10, 10.0),
            (-0.125, -0.13),
            (0, 0.0),
        ],
    )
    def test_half_up_rounding(self, mod, value, expected):
        assert mod.rounded_money(value) == expected

    def test_non_finite_and_garbage_values_collapse_to_zero(self, mod):
        assert mod.rounded_money(float("inf")) == 0.0
        assert mod.rounded_money(float("nan")) == 0.0
        assert mod.rounded_money(None) == 0.0
        assert mod.rounded_money("not a number") == 0.0
