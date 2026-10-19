# FinanceMVP

Full-stack application for managing personal finances and tracking an investment portfolio.

## Current architecture

The project no longer depends on Supabase. The application uses:

- React/Vite frontend for the interface.
- Flask backend as the application's single API.
- Local SQLite as the default database.
- Own authentication with email, hashed password, and JWT.
- External integrations in the backend for asset prices and CDI.

By default the database is created automatically at `backend/finance.db` when the backend starts. That file is kept out of Git for safety and because it holds local data.

## Features

- Local user signup and login.
- Financial dashboard with balance, net worth, investments, and credit card invoices.
- Recording income and expenses.
- Credit card registration.
- Installment purchases and invoice settlement.
- Registration of equity, fixed-income, and other assets.
- Portfolio consolidation, returns, estimated taxes, and allocation by asset class.
- Quote updates through an external API in the backend.

## Structure

```text
Financas/
├── backend/
│   ├── app.py
│   ├── requirements.txt
│   └── .env.example
├── database/
│   └── schema.sql
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── api.js
│   │   │   ├── auth.js
│   │   │   ├── dataApi.js
│   │   │   └── portfolio.js
│   │   ├── pages/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── .env.example
├── docs/
│   └── next-steps.md
├── ROADMAP.md
└── README.md
```

## Running locally

### Quick start

The real app runs on the home server (`DEPLOY.md`); running it on the PC is for development only.

```powershell
.\start.ps1 -Local
```

Without `-Local` the script refuses to start, so the PC's old database is not used by accident.
Starts backend (`:5000`) and frontend (`:5173`) together, waits for both, opens the browser, and
stops both on Ctrl+C. It creates `backend/.env` from the example and runs `npm install` if either is
missing. Use `-NoBrowser` to skip opening the browser.

The manual, two-terminal route is below.

### 1. Backend

Create `backend/.env` from `backend/.env.example`:

```env
DATABASE_PATH=finance.db
DATABASE_MIGRATIONS_DIR=database/migrations
DATABASE_BACKUP_DIR=backups
SQLITE_BUSY_TIMEOUT_MS=5000
JWT_SECRET=change-this-key-in-production
JWT_EXP_DAYS=30
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
FLASK_DEBUG=0
PRICE_CACHE_TTL_SECONDS=60
PRICE_FETCH_TIMEOUT_SECONDS=6
PRICE_DOWNLOAD_TIMEOUT_SECONDS=8
PRICE_FETCH_WORKERS=2
PRICE_QUOTE_STALE_HOURS=36
```

Install dependencies and run:

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The API comes up at `http://localhost:5000`.

### 2. Frontend

Create `frontend/.env` from `frontend/.env.example`:

```env
VITE_API_BASE_URL=http://localhost:5000
```

Install dependencies and run:

```bash
cd frontend
npm install
npm run dev
```

The frontend normally comes up at `http://localhost:5173`.

## Tests

```powershell
.\start.ps1 -Tests
```

or directly:

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

88 tests covering FIFO cost basis, regressive fixed-income tax, credit card invoice settlement, the
investment-to-cash link, and `user_id` isolation. They run against a temporary database built by the
real migrations — your `backend/finance.db` is not touched.

## Database

The default local database lives at `backend/finance.db`. The structure evolves through SQL migrations in `database/migrations`, applied automatically when the backend starts. The `database/schema.sql` file serves as a consolidated reference of the initial schema.

The backend also configures SQLite for more robust local use:

- `PRAGMA foreign_keys = ON`
- `PRAGMA journal_mode = WAL`
- `PRAGMA synchronous = NORMAL`
- `PRAGMA busy_timeout`, configurable via `SQLITE_BUSY_TIMEOUT_MS`

The main tables are:

- `users`
- `transactions`
- `credit_cards`
- `cc_expenses`
- `assets`
- `investment_transactions`
- `price_quotes`
- `investment_positions`
- `investment_realized_results`
- `investments` (legacy/migration, kept to preserve old data)
- `schema_migrations`

Every financial record carries a `user_id` and is filtered by the backend based on the authenticated user's JWT.

### Investments

The investment model was split apart to avoid mixing registration, movement, quoting, and consolidated position:

- `assets`: the asset's registration, per user, class, and ticker/name.
- `investment_transactions`: buys, sells, redemptions, and adjustments.
- `price_quotes`: history of manual, market, CDI, or legacy quotes.
- `investment_positions`: the materialized current position, recomputed after relevant changes.
- `investment_realized_results`: the realized result per sale/redemption, with FIFO cost basis, costs, net amount, profit/loss, estimated tax, and tax allocations in JSON.

The old `/api/investments` endpoints still respond in the format the current interface uses, but now read from and write to the normalized tables. There are also direct queries at `/api/assets`, `/api/investment-transactions`, `/api/investment-positions`, and `/api/investment-realized-results`.

The open position is kept separate from the realized result. Equity sales consume lots by FIFO, and fixed-income redemptions compute the cost of the related lot. The tax estimate is operational and must be validated before any official filing.

Destructive operations and manual quote updates use `asset_id` and `asset_class`, not just the ticker. The broad by-ticker routes were disabled to avoid deleting or updating different assets that share the same code. When deleting or editing a movement, the backend also validates that sales and redemptions will still be backed by a prior purchase/lot.

The portfolio returns current-quote metadata in `asset.quote`, including source, timestamp, age, and status (`fresh`, `stale`, or `missing`). Quote updates can be global or per asset, and return lists of assets that were updated, failed, came from cache, or are still stale.

Buys, sells, and redemptions also generate a linked cash transaction in `transactions`:

- buy: an outflow in the `Investimento` category;
- sell: an inflow for the sale amount net of costs;
- redemption: an inflow for the redeemed amount net of costs.

The link uses `transactions.source_type = INVESTMENT_TRANSACTION` and `transactions.source_id = investment_transactions.id`, with a unique index preventing duplicates. These linked entries should not be deleted by hand from the statement; to undo one, delete the investment movement instead.

### Local backups

Use an authenticated `POST /api/database/backups` to create a backup in `DATABASE_BACKUP_DIR`. The routine produces:

- a `.db` copy made through SQLite's native backup API;
- a `.sql` dump;
- a `.zip` containing both files.

## Important variables

### Backend

- `DATABASE_PATH`: path to the SQLite file. Default: `backend/finance.db`.
- `DATABASE_MIGRATIONS_DIR`: folder holding the SQL migrations. Default: `database/migrations`.
- `DATABASE_BACKUP_DIR`: folder for local backups. Default: `backend/backups`.
- `SQLITE_BUSY_TIMEOUT_MS`: maximum wait when SQLite is busy. Default: `5000`.
- `JWT_SECRET`: token signing key.
- `JWT_EXP_DAYS`: token lifetime in days.
- `CORS_ORIGINS`: origins allowed to reach the API.
- `FLASK_DEBUG`: use `1` only in local development when you need debug mode.
- `PRICE_CACHE_TTL_SECONDS`: how long yfinance quotes are cached, in seconds.
- `PRICE_FETCH_TIMEOUT_SECONDS`: how long the API waits before falling back to cache or a stored value.
- `PRICE_DOWNLOAD_TIMEOUT_SECONDS`: timeout passed through to the yfinance call.
- `PRICE_FETCH_WORKERS`: maximum number of parallel quote lookups.
- `PRICE_QUOTE_STALE_HOURS`: maximum quote age before it is marked stale. Default: `36`.

### Frontend

- `VITE_API_BASE_URL`: base URL of the Flask API.

## Notes

- `backend/finance.db` and local data should not be versioned.
- For production, replace `JWT_SECRET` with a strong, private value.
- SQLite serves local/MVP use well. For real multi-user use on a server, the natural next step is migrating the persistence layer to a self-hosted PostgreSQL, keeping the same Flask API.
- See `docs/next-steps.md` for the active work plan.

## License

[MIT](LICENSE) © 2026 guneves.
