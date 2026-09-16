# Backend scripts

One-off maintenance scripts. They are not imported by the app and are not part of
any request path. Run them from `backend/` with the virtualenv active.

| Script | What it does |
|---|---|
| `seed_true_portfolio.py` | Loads a real portfolio snapshot (assets, investment transactions and positions) into the local database. Used to rebuild the investment state from a known good snapshot. |
| `seed_wallet_mock.py` | Generates mock wallet data (transactions, cards, invoices) for exercising the UI on an empty database. |

Both write directly to the SQLite file resolved from `DATABASE_PATH` (default
`backend/finance.db`). **Back up first** — they are destructive for the tables
they touch.

```powershell
cd backend
python scripts/seed_wallet_mock.py
```
