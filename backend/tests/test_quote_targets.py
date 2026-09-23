"""Quote refresh only asks the market for assets the user still holds.

A position bought and later sold in full keeps its rows in
`investment_transactions`; it must not be sent to yfinance again.
"""


def movement(asset_id, ticker, quantity, *, asset_class="STOCKS"):
    return {
        "id": f"{asset_id}-{quantity}",
        "asset_id": asset_id,
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
    }


def test_fully_sold_asset_is_not_a_quote_target(portfolio_module):
    investments = [
        movement("bbas", "BBAS3", 100),
        movement("bbas", "BBAS3", -100),
        movement("aapl", "AAPL34", 10),
    ]
    targets = portfolio_module.unique_market_asset_targets(investments)
    assert [t["ticker"] for t in targets] == ["AAPL34"]


def test_partially_sold_asset_is_still_a_target(portfolio_module):
    investments = [movement("bbas", "BBAS3", 100), movement("bbas", "BBAS3", -40)]
    targets = portfolio_module.unique_market_asset_targets(investments)
    assert [t["ticker"] for t in targets] == ["BBAS3"]


def test_open_ids_come_from_the_whole_history_not_the_filtered_rows(portfolio_module):
    # Refreshing by a single buy row of a closed position must not fetch it.
    all_rows = [movement("bbas", "BBAS3", 100), movement("bbas", "BBAS3", -100)]
    open_ids = portfolio_module.open_asset_ids(all_rows)
    assert portfolio_module.unique_market_asset_targets(all_rows[:1], open_ids) == []


def test_float_residue_counts_as_closed(portfolio_module):
    investments = [
        movement("x", "XPTO3", 0.1),
        movement("x", "XPTO3", 0.2),
        movement("x", "XPTO3", -0.3),
    ]
    assert portfolio_module.open_asset_ids(investments) == set()
