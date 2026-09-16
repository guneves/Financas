# Improvement roadmap

> For the current, prioritized work plan, see `docs/next-steps.md`. This file is kept as a record of what has been built and of the original direction.

## Quick assessment

The project now uses React/Vite on the frontend, Flask as the single API, local SQLite for persistence, and its own JWT authentication. Its strongest points are reduced external dependency, centralization of data rules in the backend, and broad functional coverage for transactions, credit cards, and investments.

The main risks found are in maintenance and configuration:

- The backend still concentrates routes, persistence, authentication, portfolio computation, and external integrations in a single file.
- There are still no automated tests for critical financial rules.
- SQLite is excellent for local/MVP use, but a multi-user deployment should move to a self-hosted PostgreSQL.
- Documentation for migrating legacy data could still be fleshed out with operational examples.

## Short term

- Split the backend into modules (`auth`, `database`, `routes`, `services`).
- Extract shared date, currency, and installment formatters and helpers on the frontend.
- Standardize user-facing error messages.
- Add a visual interface for SQLite status and backup/export.

## Medium term

- Write unit tests for portfolio computation, regressive income tax, CDI, and credit card invoices.
- Add payload validation in the backend.
- Create a domain layer for credit card transactions and investment consolidation.
- Add CI with a frontend build and backend tests.

## Long term

- Add structured logging and failure tracing for external integrations.
- Containerize frontend/backend for reproducible deployment.
- Add support for proceeds, dividends, interest on own capital, and corporate actions.
- Implement statement import, financial goals, and alerts.

## Implemented so far

- Shared HTTP client in `frontend/src/lib/api.js`.
- Local authentication in `frontend/src/lib/auth.js` and `/api/auth/*`.
- Local CRUD in `frontend/src/lib/dataApi.js` and the Flask endpoints.
- Local SQLite initialized automatically by the backend.
- Versioned SQL migrations in `database/migrations`.
- Local SQLite with foreign keys, WAL, synchronous normal, and busy timeout.
- Authenticated status and backup endpoints for the local database.
- Normalized investment model with `assets`, `investment_transactions`, `price_quotes`, and `investment_positions`.
- Automatic migration of legacy `investments` data into the new model.
- Direct endpoints for assets, investment transactions, and materialized positions.
- Investment buys, sells, and redemptions integrated with cash via `transactions.source_type/source_id`.
- Realized results for sales/redemptions with FIFO cost basis, costs, net price, estimated tax, and per-operation tax history.
- Destructive operations and manual quote updates protected by `asset_id`/class, blocking edits/deletions that would leave a sale or redemption unbacked.
- Quotes carrying source, last update, stale/missing status, per-asset failures, and individual per-asset refresh.
- `VITE_API_BASE_URL`, `DATABASE_PATH`, `JWT_SECRET`, and `CORS_ORIGINS` documented.
- Frontend calls for portfolio, history, and price updates using the shared client.
- `/api/health` healthcheck.
- Price updates filtered by `investment_id` when provided.
