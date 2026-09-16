"""Axis 1: FIFO lot consumption on sales.

`build_variable_realized_result` mutates the `lots` list in place — consumed
lots are popped, partially consumed ones keep a reduced `remaining_quantity`.
That side effect is part of the contract: the caller walks transactions in
chronological order and reuses the same list for the next sale.
"""

import pytest


def make_lot(transaction_id, quantity, unit_cost, purchase_date="2026-01-10"):
    return {
        "transaction_id": transaction_id,
        "purchase_date": purchase_date,
        "remaining_quantity": quantity,
        "unit_cost": unit_cost,
        "metadata": {},
    }


def make_sale(quantity, sale_price, *, asset_class="STOCKS", fee=0, date="2026-06-10", average_price=0):
    """A SELL movement as `fetch_investment_rows` would hand it over."""
    return {
        "id": f"sell-{quantity}-{sale_price}",
        "user_id": "user-1",
        "asset_id": "asset-1",
        "asset_class": asset_class,
        "movement_type": "SELL",
        "quantity": -abs(quantity),
        "average_price": average_price,
        "current_price": sale_price,
        "fee_amount": fee,
        "transaction_date": date,
        "metadata": {"sale_date": date, "sale_price": sale_price, "fee_amount": fee},
    }


@pytest.fixture()
def build(app_module):
    return app_module.build_variable_realized_result


class TestLotConsumption:
    def test_sale_smaller_than_the_first_lot_consumes_it_partially(self, build):
        lots = [make_lot("buy-1", 100, 10.0)]
        result = build(make_sale(40, 15.0), lots)

        assert len(lots) == 1
        assert lots[0]["remaining_quantity"] == pytest.approx(60)
        assert result["quantity"] == pytest.approx(40)
        assert result["cost_basis"] == pytest.approx(400.0)
        assert result["gross_proceeds"] == pytest.approx(600.0)
        assert result["realized_profit"] == pytest.approx(200.0)

    def test_sale_matching_a_lot_exactly_removes_it(self, build):
        lots = [make_lot("buy-1", 100, 10.0)]
        build(make_sale(100, 12.0), lots)
        assert lots == []

    def test_sale_spanning_two_lots_consumes_the_oldest_first(self, build):
        lots = [
            make_lot("buy-1", 100, 10.0, "2026-01-10"),
            make_lot("buy-2", 100, 20.0, "2026-03-10"),
        ]
        result = build(make_sale(150, 30.0), lots)

        allocations = result["metadata"]["allocations"]
        assert [a["buy_transaction_id"] for a in allocations] == ["buy-1", "buy-2"]
        assert allocations[0]["quantity"] == pytest.approx(100)
        assert allocations[1]["quantity"] == pytest.approx(50)
        # 100 * 10 (oldest lot, in full) + 50 * 20 (newest lot, partially)
        assert result["cost_basis"] == pytest.approx(2000.0)

        assert len(lots) == 1
        assert lots[0]["transaction_id"] == "buy-2"
        assert lots[0]["remaining_quantity"] == pytest.approx(50)

    def test_full_exit_across_every_lot_empties_the_list(self, build):
        lots = [make_lot("buy-1", 30, 10.0), make_lot("buy-2", 70, 20.0)]
        result = build(make_sale(100, 25.0), lots)

        assert lots == []
        assert result["cost_basis"] == pytest.approx(30 * 10 + 70 * 20)
        assert result["metadata"]["unmatched_quantity"] == pytest.approx(0)

    def test_sequential_sales_keep_consuming_the_same_lot_list(self, build):
        lots = [make_lot("buy-1", 100, 10.0), make_lot("buy-2", 100, 20.0)]

        first = build(make_sale(60, 15.0), lots)
        assert first["cost_basis"] == pytest.approx(600.0)
        assert lots[0]["remaining_quantity"] == pytest.approx(40)

        second = build(make_sale(60, 15.0), lots)
        # 40 left at 10, then 20 at 20
        assert second["cost_basis"] == pytest.approx(40 * 10 + 20 * 20)
        assert len(lots) == 1
        assert lots[0]["remaining_quantity"] == pytest.approx(80)

    def test_empty_lot_list_falls_back_to_the_average_price(self, build):
        sale = make_sale(50, 15.0, average_price=8.0)
        result = build(sale, [])

        assert result["metadata"]["unmatched_quantity"] == pytest.approx(50)
        assert result["cost_basis"] == pytest.approx(400.0)
        assert result["metadata"]["allocations"][0]["unmatched"] is True

    def test_selling_more_than_the_lots_hold_marks_only_the_excess_unmatched(self, build):
        lots = [make_lot("buy-1", 30, 10.0)]
        result = build(make_sale(50, 20.0, average_price=12.0), lots)

        allocations = result["metadata"]["allocations"]
        assert len(allocations) == 2
        assert allocations[0]["quantity"] == pytest.approx(30)
        assert allocations[1].get("unmatched") is True
        assert allocations[1]["quantity"] == pytest.approx(20)
        assert result["cost_basis"] == pytest.approx(30 * 10 + 20 * 12)

    def test_exhausted_lots_left_in_the_list_are_skipped(self, build):
        lots = [make_lot("stale", 0, 99.0), make_lot("buy-1", 50, 10.0)]
        result = build(make_sale(50, 12.0), lots)

        assert result["metadata"]["allocations"][0]["buy_transaction_id"] == "buy-1"
        assert result["cost_basis"] == pytest.approx(500.0)
        assert lots == []


class TestFeesAndTax:
    def test_fees_are_deducted_from_the_net_proceeds(self, build):
        lots = [make_lot("buy-1", 100, 10.0)]
        result = build(make_sale(100, 15.0, fee=25.0), lots)

        assert result["gross_proceeds"] == pytest.approx(1500.0)
        assert result["fee_amount"] == pytest.approx(25.0)
        assert result["net_proceeds"] == pytest.approx(1475.0)
        assert result["realized_profit"] == pytest.approx(475.0)

    def test_stock_profit_is_taxed_at_fifteen_percent(self, build):
        lots = [make_lot("buy-1", 100, 10.0)]
        result = build(make_sale(100, 20.0), lots)

        assert result["realized_profit"] == pytest.approx(1000.0)
        assert result["tax_amount"] == pytest.approx(150.0)
        assert result["net_profit_after_tax"] == pytest.approx(850.0)

    def test_reits_are_taxed_at_twenty_percent(self, build):
        lots = [make_lot("buy-1", 100, 10.0)]
        result = build(make_sale(100, 20.0, asset_class="REIT"), lots)
        assert result["tax_amount"] == pytest.approx(200.0)

    def test_a_loss_generates_no_tax(self, build):
        lots = [make_lot("buy-1", 100, 20.0)]
        result = build(make_sale(100, 10.0), lots)

        assert result["realized_profit"] == pytest.approx(-1000.0)
        assert result["tax_amount"] == pytest.approx(0.0)

    def test_holding_days_are_measured_per_lot(self, build):
        lots = [
            make_lot("buy-1", 50, 10.0, "2026-01-01"),
            make_lot("buy-2", 50, 10.0, "2026-05-01"),
        ]
        result = build(make_sale(100, 12.0, date="2026-06-10"), lots)

        allocations = result["metadata"]["allocations"]
        assert allocations[0]["holding_days"] == 160
        assert allocations[1]["holding_days"] == 40

    def test_the_cost_method_is_reported_as_fifo(self, build):
        result = build(make_sale(10, 12.0), [make_lot("buy-1", 10, 10.0)])
        assert result["metadata"]["cost_method"] == "FIFO"
