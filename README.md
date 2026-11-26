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

The screen and the API share one origin: in development Vite forwards `/api` to Flask on
`127.0.0.1:5000` (`vite.config.js`), and the server has no CORS. No `frontend/.env` is needed.

Install dependencies and run:

```bash
cd frontend
npm install
npm run dev
```

The frontend comes up at `http://127.0.0.1:5173`.

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
- `FLASK_DEBUG`: use `1` only in local development when you need debug mode.
- `PRICE_CACHE_TTL_SECONDS`: how long yfinance quotes are cached, in seconds.
- `PRICE_FETCH_TIMEOUT_SECONDS`: how long the API waits before falling back to cache or a stored value.
- `PRICE_DOWNLOAD_TIMEOUT_SECONDS`: timeout passed through to the yfinance call.
- `PRICE_FETCH_WORKERS`: maximum number of parallel quote lookups.
- `PRICE_QUOTE_STALE_HOURS`: maximum quote age before it is marked stale. Default: `36`.

### Frontend

- `VITE_API_BASE_URL`: base URL of the Flask API. Empty by default; if set, it must be the same
  origin as the screen (there is no CORS).

## Remote access

The app is reachable off the VPN through **Tailscale Funnel on port 8443 only**, with a login in
front of it. Port 443 stays tailnet-only and goes straight to the app, as before; it is the bridge
for installing a new APK and the rollback.

```
Internet: https://guilhermeserver.tail5084ff.ts.net:8443   (Funnel; on the tailnet, `tailscale serve`)
  └─ 127.0.0.1:8102  Caddy ("proxy" in compose.yaml)
       ├─ /oauth2/*                       → oauth2-proxy (Google login flow)
       ├─ X-Device-Key == PROXY_DEVICE_KEY → header stripped → app / /apk/*   (the APK)
       ├─ /api/*  Google session?  yes → app   no → 401 + X-Proxy-Auth: required
       └─ else    Google session?  yes → app or /apk/*   no → 302 to the Google sign-in
Tailnet only: https://guilhermeserver.tail5084ff.ts.net (443) → 127.0.0.1:8101 (the app)
```

Behind either gate the app's own login (JWT) still applies.

- **Browsers** sign in with Google. Only the address in `OAUTH2_ALLOWED_EMAILS` gets through, and
  the Google consent screen stays in Testing with that one test user. The session lasts **7 days**,
  re-checked with Google every hour. Sign out at `https://…ts.net:8443/oauth2/sign_out`. When the
  session ends on an open page, the next API call gets the proxy's 401: the page reloads into the
  Google login (at most once per 30 s), the app login is kept, and a "+ Novo" saved at that moment
  goes to the pending queue and is sent after the login.
- **The APK** sends a device key in `X-Device-Key` on every request (screens, the pending queue,
  bank notifications, APK updates). Paste the key once: on the login screen ("Chave de acesso
  remoto") or in Ajustes › Perfil › "Trocar chave de acesso". "Sair" does not erase it. A wrong or
  missing key shows "Chave de acesso inválida ou ausente" with a field to paste it; nothing is
  lost, and queued entries and notifications are sent once the key is right.

### Secrets (server only, `/srv/apps/financas/`, never in git)

| File | Variables | Used by |
|---|---|---|
| `oauth2.env` (chmod 600) | `OAUTH2_PROXY_CLIENT_ID`, `OAUTH2_PROXY_CLIENT_SECRET` (the Google OAuth client), `OAUTH2_PROXY_COOKIE_SECRET` (`openssl rand -base64 32 \| tr -- '+/' '-_'`) | oauth2-proxy |
| `proxy.env` (chmod 600) | `PROXY_DEVICE_KEY` (`openssl rand -base64 32 \| tr -- '+/' '-_' \| tr -d '='`, at least 32 characters) | Caddy |
| `.env` | `OAUTH2_ALLOWED_EMAILS` (the Google address let in; empty = nobody), `PROXY_PORT` (default 8102) | compose |

Both files are optional to compose: a missing one fails closed (oauth2-proxy stops and the
browser routes answer 502; without a key no device passes), and the app's deploy still works.

After changing one of them:

```bash
cd /srv/apps/financas
sudo docker compose up -d --force-recreate oauth2-proxy   # oauth2.env, or OAUTH2_ALLOWED_EMAILS
sudo docker compose up -d --force-recreate proxy          # proxy.env
```

- **Rotate the device key:** new `PROXY_DEVICE_KEY` in `proxy.env`, recreate `proxy`, paste the
  new key in the APK (Ajustes › Perfil).
- **End every browser session:** new `OAUTH2_PROXY_COOKIE_SECRET`, recreate `oauth2-proxy`.
- **Change who may sign in:** edit `OAUTH2_ALLOWED_EMAILS` in `.env`, recreate `oauth2-proxy`.

### Rollback

- `sudo tailscale funnel --https=8443 off`: 8443 is tailnet-only again; the APK keeps working on
  the VPN, no reinstall.
- Full revert: also `sudo tailscale serve --https=8443 off`, remove the `funnel` nodeAttr from the
  tailnet policy, and `git revert` the APK commit ("APK: reach the server on :8443 with a device
  key") so CI ships an APK pointing at 443 again.

DEPLOY.md ("Remote access: the auth proxy on :8443") has the first-time setup and rollout.

## Notes

- `backend/finance.db` and local data should not be versioned.
- For production, replace `JWT_SECRET` with a strong, private value.
- SQLite serves local/MVP use well. For real multi-user use on a server, the natural next step is migrating the persistence layer to a self-hosted PostgreSQL, keeping the same Flask API.
- See `docs/next-steps.md` for the active work plan.

## License

[MIT](LICENSE) © 2026 guneves.
