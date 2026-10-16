"""The URL map is the API contract: the Phase 5 split of app.py must not change it.

Each area of app.py moves into a blueprint in `routes/`. A blueprint that is
written but never registered in app.py drops its routes silently — every one of
them 404s and only the tests that happen to call them notice. This pins the
full list (captured from app.py before the split, at 4182be2), so a missing
registration, a typo in a rule or a lost method fails here by name.

Adding or removing an endpoint on purpose means updating EXPECTED_ROUTES too.
"""

EXPECTED_ROUTES = {
    # O frontend construido (routes/frontend.py): publico, como qualquer pagina.
    ("/", "GET"),
    ("/<path:path>", "GET"),
    ("/api/accounts", "GET,POST"),
    ("/api/accounts/<account_id>", "DELETE,PATCH"),
    ("/api/assets", "GET"),
    ("/api/auth/login", "POST"),
    ("/api/auth/me", "GET,PATCH"),
    ("/api/auth/signup", "POST"),
    ("/api/budgets", "GET,POST"),
    ("/api/budgets/<budget_id>", "DELETE,PATCH"),
    ("/api/budgets/copy", "POST"),
    ("/api/categories", "GET,POST"),
    ("/api/categories/<category_id>", "DELETE,PATCH"),
    ("/api/cc-expenses", "DELETE,GET,POST"),
    ("/api/cc-expenses/candidates", "GET"),
    ("/api/cc-expenses/invoice-status", "PATCH"),
    ("/api/cc-expenses/pay-invoice", "POST"),
    ("/api/cc-expenses/purchases", "POST"),
    ("/api/cc-expenses/status", "PATCH"),
    ("/api/credit-cards", "GET,POST"),
    ("/api/credit-cards/<card_id>", "PATCH"),
    ("/api/credit-cards/<card_id>", "DELETE"),
    ("/api/database/backups", "POST"),
    ("/api/database/status", "GET"),
    ("/api/health", "GET"),
    ("/api/import-rules", "GET,POST"),
    ("/api/import-rules/<rule_id>", "DELETE,PATCH"),
    ("/api/import-rules/apply", "POST"),
    ("/api/import-rules/apply/preview", "POST"),
    ("/api/import/commit", "POST"),
    ("/api/import/preview", "POST"),
    ("/api/investment-positions", "GET"),
    ("/api/investment-proceeds", "GET,POST"),
    ("/api/investment-proceeds/<proceed_id>", "DELETE,PATCH"),
    ("/api/investment-proceeds/calendar", "GET"),
    ("/api/investment-proceeds/summary", "GET"),
    ("/api/investment-realized-results", "GET"),
    ("/api/investment-transactions", "GET"),
    ("/api/investments", "GET,POST"),
    ("/api/investments/<investment_id>", "DELETE,PATCH"),
    ("/api/investments/by-asset/<asset_id>", "DELETE"),
    ("/api/investments/by-ticker/<path:ticker>", "DELETE"),
    ("/api/investments/history", "GET"),
    ("/api/investments/contributions", "GET"),
    ("/api/investments/returns", "GET"),
    ("/api/investments/portfolio", "GET"),
    ("/api/investments/portfolio/export", "GET"),
    ("/api/investments/export", "GET"),
    ("/api/investment-proceeds/export", "GET"),
    ("/api/exports/columns", "GET"),
    ("/api/health/integrations", "GET"),
    ("/api/corporate-actions", "GET,POST"),
    ("/api/tax-report", "GET"),
    ("/api/tax-report/export", "GET"),
    ("/api/tax-report/exemption", "GET"),
    ("/api/allocation", "GET"),
    ("/api/allocation/targets", "PUT"),
    ("/api/allocation/sectors", "GET"),
    ("/api/allocation/sectors/refresh", "POST"),
    ("/api/assets/<asset_id>/sector", "PATCH"),
    ("/api/goals", "GET,POST"),
    ("/api/goals/<goal_id>", "DELETE,GET,PATCH"),
    ("/api/monthly-plan", "DELETE,GET,PUT"),
    ("/api/corporate-actions/<action_id>", "DELETE"),
    ("/api/investments/price-by-asset/<asset_id>", "PATCH"),
    ("/api/investments/price-by-ticker", "PATCH"),
    ("/api/investments/update-prices", "POST"),
    ("/api/market/tickers", "GET"),
    ("/api/market/tickers/<ticker>", "GET"),
    ("/api/recurring", "GET,POST"),
    ("/api/recurring/<recurring_id>", "DELETE,PATCH"),
    ("/api/recurring/forecast", "GET"),
    ("/api/recurring/run", "POST"),
    ("/api/transactions", "GET,POST"),
    ("/api/transactions/<item_id>", "PATCH"),
    ("/api/transactions/<item_id>", "DELETE"),
    ("/api/transactions/<item_id>/attachments", "GET,POST"),
    ("/api/transactions/<item_id>/attachments/<attachment_id>", "DELETE"),
    ("/api/transactions/<item_id>/attachments/<attachment_id>/file", "GET"),
    ("/api/cc-expenses/<item_id>/attachments", "GET,POST"),
    ("/api/cc-expenses/<item_id>/attachments/<attachment_id>", "DELETE"),
    ("/api/cc-expenses/<item_id>/attachments/<attachment_id>/file", "GET"),
    ("/api/transactions/export", "GET"),
    ("/api/transfers", "POST"),
}


def current_routes(app):
    return {
        (rule.rule, ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"})))
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }


def test_every_expected_route_is_registered(app_module):
    missing = EXPECTED_ROUTES - current_routes(app_module.app)
    assert not missing, f"rotas sumiram (blueprint nao registrado?): {sorted(missing)}"


def test_no_unexpected_route_appeared(app_module):
    extra = current_routes(app_module.app) - EXPECTED_ROUTES
    assert not extra, f"rotas novas — atualize EXPECTED_ROUTES se for de proposito: {sorted(extra)}"


def test_every_route_but_health_and_login_requires_a_token(client, app_module):
    """Um blueprint novo nao pode esquecer o @token_required."""
    public = {"/api/health", "/api/auth/signup", "/api/auth/login", "/", "/<path:path>"}
    for rule, methods in sorted(EXPECTED_ROUTES):
        if rule in public:
            continue
        url = rule.replace("<path:ticker>", "PETR4")
        for part in ("<item_id>", "<attachment_id>", "<account_id>", "<category_id>", "<budget_id>",
                     "<recurring_id>", "<rule_id>", "<card_id>", "<proceed_id>", "<investment_id>",
                     "<asset_id>", "<ticker>", "<action_id>", "<goal_id>"):
            url = url.replace(part, "x")
        assert "<" not in url, url
        for method in methods.split(","):
            response = client.open(url, method=method)
            assert response.status_code == 401, f"{method} {rule} -> {response.status_code}"
