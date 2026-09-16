# Next Steps — FinanceMVP

> Full repository sweep, 2026-09-15.
> Stated goal: turn this project into a **personal finance manager for my own use** (single-user, running locally).
> This document replaces `ROADMAP.md` as the active work plan. `ROADMAP.md` remains valid as a record of what has already been built.

---

## 1. Where the project stands today

**Stack:** React 18 + Vite + Tailwind (frontend) · Flask 3 (backend, single file) · local SQLite with versioned migrations · hand-rolled HS256 JWT auth · yfinance for quotes.

**Size:** `backend/app.py` = 4,063 lines · frontend = ~5,300 lines across 6 pages · 6 migrations · 0 tests.

**What already works well:**

| Area | Status |
|---|---|
| Local auth (signup/login/JWT) | Done |
| Income and expenses (`/transactions`) | Done |
| Credit cards, installment purchases, invoice settlement | Done |
| Normalized investments (`assets` + `investment_transactions` + `price_quotes` + `investment_positions`) | Done, and well modeled |
| Realized results with FIFO cost basis and estimated tax | Done |
| Investment ↔ cash linkage (`source_type`/`source_id`) | Done |
| Proceeds (dividends/JCP/amortization) with calendar and summary | Done |
| Quotes with `fresh`/`stale`/`missing` status and per-asset refresh | Done |
| Automatic migrations on boot + local backup (.db/.sql/.zip) | Done |
| Dashboard with net worth, balance, expenses by category, installments, next invoice | Done |

The **investments** core is considerably more mature than the **everyday finances** core. That asymmetry is the central thing to correct if the goal is a complete personal finance manager.

---

## 2. Immediate housekeeping (do this before any feature work)

Low cost, high payoff. All of it is cleanup the sweep turned up.

- [ ] **Delete the 19 forgotten test databases.** At the root: `tmp_quote_status_test.db`, `tmp_quote_status_test_final.db`, `tmp_realized_fixed_test.db`, `tmp_realized_result_test.db`, `tmp_safe_asset_ops_test.db`, `tmp_safe_fixed_delete_test.db`. In `backend/`: 13 more `tmp_*.db` files. They total ~4 MB and serve no purpose — they are already covered by `.gitignore` (nothing leaked into Git), but they clutter the tree.
- [ ] **Add `tmp_*.db` and `*.log` to `.gitignore`** so the pattern doesn't come back. The `backend/server.{out,err}.log` and `frontend/vite.{out,err}.log` files are also sitting loose.
- [ ] **Remove the `venv/` directory** (it exists alongside `.venv/` — two virtualenvs, one orphaned).
- [ ] **Remove `frontend/dist/`** from the working tree; it's a build artifact and already gitignored.
- [ ] **Check the `JWT_SECRET` in `backend/.env`.** The code default is `dev-secret-change-me` (`backend/app.py:56`). Even for personal use, generate a random value — `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- [ ] **Decide what happens to `seed_true_portfolio.py` and `seed_wallet_mock.py`.** If they still serve a purpose, move them to `backend/scripts/` with a one-line README. If not, delete them.
- [ ] **Drop `CATTLE` from the `asset_class` enum** or document why it stayed. Commit `7f9de03 retirar cattle` removed the feature, but the CHECK constraint in `schema.sql` and in the migrations still accepts the value.

---

## 3. Functional gaps — what's missing for this to be a "finance manager"

Ordered by impact on daily use. Each item names the tables/endpoints/screens involved.

### 3.1 Bank accounts (highest priority)

Today there is **a single implicit balance**, derived from summing `transactions`. There is no account entity. In practice you have a checking account, savings, and probably a brokerage account — and investments are funded from one of them.

- New `accounts` table (id, user_id, name, type `CHECKING|SAVINGS|BROKERAGE|CASH|OTHER`, institution, initial_balance, currency, archived_at).
- `transactions.account_id` (nullable in the migration, backfilled to an automatically created "Primary" account).
- Transfers between accounts as their own type (`TRANSFER`) — today they'd be recorded as expense + income, distorting every total.
- Per-account balance on the Dashboard, alongside the consolidated one.

### 3.2 Categories as data, not as a constant

`CATEGORY_OPTIONS` is hardcoded in `frontend/src/pages/Transactions.jsx:29` with 10 fixed values. You can't rename, create, or group them.

- `categories` table (id, user_id, name, kind `INCOME|EXPENSE`, parent_id, color, icon, archived_at).
- Auto-seed the current 10 categories on first login so nothing breaks.
- `transactions.category` becomes `category_id` (keep the text column through the migration as a fallback).
- Subcategories: "Food > Groceries" vs "Food > Restaurants" — that's where spending analysis actually becomes useful.

### 3.3 Monthly budget by category

The biggest practical win for personal use, and entirely absent today.

- `budgets` table (id, user_id, category_id, month `YYYY-MM`, planned_amount, rollover boolean).
- `/api/budgets` endpoint returning the month plus computed actuals.
- Screen: a bar per category showing planned × spent × remaining, with a visual alert on overrun.
- Reuse the grouping the Dashboard already does in `expensesByCategory`.

### 3.4 Recurring entries

Rent, salary, subscriptions, tuition. Today these are typed in one by one every month.

- `recurring_transactions` table (template + `frequency` MONTHLY/WEEKLY/YEARLY + `next_run_date` + `end_date`).
- Materialization: on the Dashboard call or via a `/api/recurring/run` endpoint, generate everything pending up to today. Avoids cron and keeps the app fully local.
- A 30/60/90-day cash flow forecast falls out of this for free.

### 3.5 Statement import (OFX / CSV)

Manual data entry is what gets personal finance managers abandoned in month three.

- Start with **CSV** and a configurable column mapping (simpler, covers any bank's export).
- Then **OFX** — Brazilian banks export it; the `ofxparse` library handles it.
- Deduplicate by hash (date + amount + normalized description) so re-imports are idempotent.
- Auto-categorization rules: `description contains "IFOOD" → Food`. `import_rules` table.

### 3.6 Financial goals

- `goals` table (name, target amount, target date, linked account/asset, suggested monthly contribution).
- Progress driven by the linked account's balance or by an asset's position.

### 3.7 Smaller gaps, but annoying ones

- [ ] **Edit a transaction.** Today `/api/transactions/<id>` only accepts `DELETE` (`backend/app.py:1822`). A typo means delete and re-enter.
- [ ] **Attachments/receipts** per transaction (store the file locally, path in `metadata`).
- [ ] **Search and filters on the statement** — by period, category, account, amount range, free text.
- [ ] **Export to CSV/Excel** for the statement and the portfolio.
- [ ] **Corporate actions** (splits, reverse splits, bonus shares) — the portfolio already has FIFO and tax, but a split today would silently corrupt the average price.
- [ ] **Real multi-currency.** `assets.currency` exists but nothing converts; a USD asset enters net worth as if it were BRL.

---

## 4. Technical debt

### 4.1 `backend/app.py` at 4,063 lines

This is structural problem number one. Routes, SQL, auth, portfolio computation, tax, FIFO, and the yfinance integration all live in one file. A suggested split, in order of ease:

```
backend/
├── app.py              # app factory + blueprint registration (~80 lines)
├── config.py           # env reading
├── db.py               # connection, pragmas, migrations
├── auth.py             # JWT, token_required, password hashing
├── validators.py       # require_date, require_choice, ValidationError (already exist, just extract)
├── services/
│   ├── portfolio.py    # consolidation, FIFO, tax — the densest logic
│   ├── prices.py       # yfinance, cache, CDI, staleness
│   └── invoices.py     # credit card invoices, installments
└── routes/
    ├── transactions.py · cards.py · investments.py · proceeds.py · system.py
```

Do this **incrementally**, one blueprint at a time, with the app running between each step. Don't attempt it in one pass.

### 4.2 Zero automated tests

There isn't a single test in the project. The `tmp_*.db` files are residue from manual testing, which confirms the critical rules were validated by hand.

Start with what hurts most when it breaks (pytest + in-memory SQLite):

1. **Sale FIFO** — lot consumption, partial quantity, full exit.
2. **Regressive fixed-income tax** — the holding-period brackets.
3. **Credit card invoice** — closing day, month rollover, which invoice an installment lands in.
4. **Investment ↔ cash linkage** — a buy creates an outflow; deleting the movement removes the linked transaction.
5. **`user_id` isolation** — no endpoint returns another user's data.

Realistic target: ~30 tests covering those five axes. This is what lets you refactor `app.py` without fear — **do it before section 4.1**.

### 4.3 Frontend

- **`formatCurrency` is duplicated across 5 files** and `formatDateBR` across 3 (`Carteira.jsx`, `Dashboard.jsx`, `Investments.jsx`, `Proventos.jsx`, `Transactions.jsx`, `InvestmentLaunchModal.jsx`). Extract to `frontend/src/lib/format.js`.
- **`Carteira.jsx` is 1,380 lines** and `Investments.jsx` is 875. Break them into per-section components.
- **No centralized server state.** Every page does its own `useEffect` + `fetch` + `loading` + `error`. TanStack Query would handle caching, revalidation, and the repeated error pattern — roughly 200 fewer lines and better behavior.
- **Inconsistent error messages** — each page handles failure its own way. Standardize on a single toast/banner.
- **No loading skeletons** on the heavy screens (the portfolio takes a while when refreshing quotes).

### 4.4 Operations

- **Backup is manual** (`POST /api/database/backups`). For personal use, an automatic backup on boot and every N hours with 7-day retention is cheap, and prevents the kind of loss you only discover too late.
- **No integration healthcheck** — if yfinance goes down or changes, you find out visually, by noticing a stale quote.
- **No structured logging.** `server.err.log` is empty; external integration errors vanish.
- **No single start script.** Right now it's two manual terminals. A `docker-compose.yml` or a `start.ps1` removes that daily friction.

---

## 5. Suggested plan

A sequence aimed at real personal use, not at a code portfolio. Each phase ships something usable.

### Phase 0 — Cleanup (a few hours)
All of section 2. Nothing depends on it, but everything gets lighter.

### Phase 1 — Safety net (1 week)
The tests from section 4.2 + automatic backup + single start script.
*Without this, every refactor that follows is a gamble.*

### Phase 2 — Data foundation (1–2 weeks)
Bank accounts (3.1) → categories as a table (3.2) → edit transaction (3.7).
*These are migrations with backfill. Do them early, while the data volume is small.*

### Phase 3 — What makes it useful daily (2–3 weeks)
Monthly budget (3.3) → recurring entries (3.4) → statement search and filters (3.7).
*This is where the app starts replacing the spreadsheet.*

### Phase 4 — Reduce friction (2 weeks)
CSV import → auto-categorization rules → OFX.
*This determines whether you're still using it in month six.*

### Phase 5 — Backend refactor (ongoing)
Section 4.1, one blueprint at a time, protected by the Phase 1 tests.

### Phase 6 — Advanced investments
Corporate actions → multi-currency → annual tax report.

---

## 6. Open decisions

Worth settling before Phase 2, because they change the design:

1. **Stay single-user, or go multi-user?** The whole schema already carries `user_id`, so multi-user is prepared for. If it's just for you, SQLite is plenty and PostgreSQL is noise — `ROADMAP.md` suggests that migration, but for personal use it isn't justified.
2. **Desktop only, or do you want phone access?** If you want mobile, the Layout needs serious responsive work, and it makes sense to host it on a Raspberry Pi/VPS with HTTPS. That shifts the JWT_SECRET item from "housekeeping" to "critical".
3. **Is Open Finance worth it?** The Brazilian Central Bank API allows pulling statements automatically, but requires registering as an institution — not viable for an individual. The realistic alternative remains OFX/CSV (3.5).
4. **Tax: support tool or source of truth?** The README already warns the estimate is operational. If the intent is to use it for filing, the annual report (Phase 6) needs considerably more rigor — and reconciliation against brokerage notes.
