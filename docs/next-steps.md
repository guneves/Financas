# Next Steps — FinanceMVP

> Full repository sweep, 2026-09-15.
> Stated goal: turn this project into a **personal finance manager for my own use** (single-user, running locally).
> This document replaces `ROADMAP.md` as the active work plan. `ROADMAP.md` remains valid as a record of what has already been built.

---

## 1. Where the project stands today

**Stack:** React 18 + Vite + Tailwind (frontend) · Flask 3 (backend, single file) · local SQLite with versioned migrations · hand-rolled HS256 JWT auth · yfinance for quotes.

**Size:** `backend/app.py` = 5,344 lines · frontend = ~6,100 lines across 7 pages · 9 migrations · 249 backend tests (as of 2026-09-16).

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
| Bank accounts with per-account balance, and transfers that don't distort totals | Done (2026-09-16) |
| Categories as a table, with subcategories | Done (2026-09-16) |
| Editing a transaction | Done (2026-09-16) |
| Monthly budget by category, with rollover | Done (2026-09-16) |
| Category management screen (create, rename, archive) | Done (2026-09-16) |

The **investments** core is considerably more mature than the **everyday finances** core. That asymmetry is the central thing to correct if the goal is a complete personal finance manager.

---

## 2. Immediate housekeeping — DONE (2026-09-15)

Low cost, high payoff. All of it is cleanup the sweep turned up.

- [x] **Delete the 19 forgotten test databases.** Already gone (commit `7e17371`).
- [x] **Add `tmp_*.db` and `*.log` to `.gitignore`.** Done in `7e17371`; the loose `server.*.log` / `vite.*.log` files are gone too.
- [x] **Remove the `venv/` directory.** No longer present — only `.venv/` remains.
- [x] **Remove `frontend/dist/`.** Not present in the working tree.
- [x] **Check the `JWT_SECRET` in `backend/.env`.** `backend/.env` had **no** `JWT_SECRET` at all, so the app was running on the `dev-secret-change-me` default. It now carries a 48-byte random secret. The file also still held three dead `SUPABASE_*` keys from the pre-Flask stack; those were removed. *Existing sessions were invalidated by the change — log in again.*
- [x] **Decide what happens to the seed scripts.** Moved to `backend/scripts/` with a `README.md` describing what each one does and warning that both write directly to the database. Their `BASE_DIR` was adjusted so `DATABASE_PATH` still resolves to `backend/`.
- [x] **Drop `CATTLE` from the `asset_class` enum** — **decided: it stays.** See below.

### Why `CATTLE` stayed

Commit `7f9de03 retirar cattle` removed the dedicated *screen*, not the asset class. The class is still wired end to end and working:

- `ALLOWED_ASSET_CLASSES` and `DEFAULT_REALIZED_TAX_RATES` (15%) — `backend/app.py:66,76`
- A mortality-rate adjustment applied to the position quantity — `backend/app.py:1660,3812`
- A selectable option in the launch modal — `frontend/src/components/InvestmentLaunchModal.jsx:10`
- Display labels — `Investments.jsx:390`, `Proventos.jsx:44`

Removing it would mean a migration rewriting the `CHECK` constraint on two tables plus deleting live logic, with no benefit. The CHECK constraints in `schema.sql` and the migrations are therefore **correct as they stand**, not stale.

### Also fixed while here

- **`backend/.env.example` shipped a broken `DATABASE_MIGRATIONS_DIR=../database/migrations`.** That value is resolved against the *project* root, not `backend/`, so it pointed one level above the repo and the backend refused to boot with `RuntimeError: Diretorio de migrations nao encontrado`. The built-in default was right, which is why nobody hit it — but anyone copying `.env.example` to `.env` would have. Corrected to `database/migrations` in both files.

## 3. Functional gaps — what's missing for this to be a "finance manager"

Ordered by impact on daily use. Each item names the tables/endpoints/screens involved.

### 3.1 Bank accounts — DONE (2026-09-16)

There used to be **a single implicit balance**, derived from summing `transactions`, with no account
entity at all. Migration `007_accounts_and_transfers.sql` introduced one.

- [x] **`accounts` table** — id, user_id, name, type `CHECKING|SAVINGS|BROKERAGE|CASH|OTHER`,
  institution, initial_balance, currency, is_default, archived_at, metadata.
- [x] **`transactions.account_id`**, backfilled to an auto-created **"Conta Principal"** per user.
  Every one of the 49 existing rows was backfilled; verified on a copy of the real database with
  `PRAGMA foreign_key_check` and `integrity_check` both clean.
- [x] **`TRANSFER` as its own type**, via `POST /api/transfers`.
- [x] **Per-account balance** on the Dashboard ("Saldo por conta") and on the Movimentações page.
- [x] **CRUD**: `GET/POST /api/accounts`, `PATCH/DELETE /api/accounts/<id>`.

**A transfer is one row, not two.** `type='TRANSFER'` leaves `account_id` and arrives at
`transfer_account_id`. The alternative — two sibling rows that have to be kept in sync — buys
nothing here and doubles the ways the data can go wrong. Because it is one row of a distinct type,
the consolidated total ignores it for free, and the per-account balance subtracts at the origin and
adds at the destination.

Consequence for anything that sums `transactions`: **skip `type = 'TRANSFER'`**, or moving money
between your own accounts will read as an expense. Two places already did this and were fixed
(`Dashboard.jsx`, `Transactions.jsx`); a `CHECK` constraint keeps the column combinations valid but
cannot help a caller that sums naively.

Accounts are **archived, never deleted** (`archived_at`), because `transactions.account_id` uses
`ON DELETE SET NULL` and a real delete would silently orphan lançamentos. Archiving the last active
account is refused.

### 3.2 Categories as data — DONE (2026-09-16)

`CATEGORY_OPTIONS` was hardcoded in `frontend/src/pages/Transactions.jsx` with 10 fixed values.
Migration `008_categories_table.sql` moved them into the database.

- [x] **`categories` table** — id, user_id, name, kind `INCOME|EXPENSE|BOTH`, parent_id, color, icon,
  archived_at. `BOTH` exists because "Investimento" is legitimately either side.
- [x] **The 10 original categories are seeded** per user — by the migration for existing users, and by
  `seed_default_categories()` at signup for new ones.
- [x] **`transactions.category_id`**, backfilled by matching on name. Any category that only ever
  existed as free text in `transactions` ("Freelance", "Salário", "Pagamento Fatura do Mês") was
  promoted to a real row, so no historical lançamento is orphaned.
- [x] **Subcategories** via `parent_id`, one level deep. The API rejects a grandchild.
- [x] **CRUD**: `GET/POST /api/categories`, `PATCH/DELETE /api/categories/<id>`, with
  `?kind=` and `?include_archived=` filters.

**`transactions.category` (the text) did not go away, and should not.** It is what the Dashboard
groups on, and it is what survives a category being archived. `category_id` is the new link;
the name is still the value. Renaming a category therefore rewrites both — `PATCH /api/categories/<id>`
updates the linked lançamentos' text in the same transaction, or the grouping would split in two.

Free-text categories are still accepted on `POST /api/transactions` (they come back with
`category_id: null`). Rejecting them would break `backend/scripts/`.

- [x] **Management screen** (2026-09-16) — the "Categorias" tab of `Orcamento.jsx`: create
  (with a parent), rename, change kind, archive and reactivate. Until then the API could do five
  things and the UI could only list them.

### 3.3 Monthly budget by category — DONE (2026-09-16)

Migration `009_budgets.sql`. The biggest practical win for personal use, and it only became possible
after 3.2: the plan is keyed by `category_id`, not by the category's text, so renaming a category
does not orphan its budget.

- [x] **`budgets` table** — id, user_id, category_id, month `YYYY-MM`, planned_amount, rollover, note.
  `UNIQUE(user_id, category_id, month)`: one plan per category per month.
- [x] **`GET /api/budgets?month=`** returns the month with the actuals already computed — planned,
  carryover, available, spent, remaining, percent and a `OK|WARNING|OVER` status per category, plus
  the totals. Defaults to the current month.
- [x] **`POST`, `PATCH /api/budgets/<id>`, `DELETE /api/budgets/<id>`**, and
  **`POST /api/budgets/copy`** (`from_month` defaults to the month before `to_month`;
  `overwrite` decides what happens to a category already planned there).
- [x] **Screen** — `frontend/src/pages/Orcamento.jsx`, a bar per category over planned × spent ×
  remaining, month navigation, inline edit of the planned value, and "copiar mês anterior".

**The realized amount is read from `transactions`, never stored.** A category whose `kind` is
`INCOME` realizes income; every other kind realizes expense. `TRANSFER` is excluded — the same rule
§3.1 imposed on everything that sums `transactions`. Lançamentos that carry only the category *text*
(free text, or anything older than migration 008) are matched by name, so historical months still
add up.

**A subcategory without its own budget counts against its parent's.** Budgeting "Alimentação" has to
cover what was spent on "Alimentação › Delivery", or the planned figure never reconciles with the
statement. Give the subcategory its own budget and it stops counting against the parent.

**`rollover` carries only what was left over, and only one month back.** The carry-over is computed
on read, not stored: storing it would mean recalculating a chain of months every time a retroactive
lançamento lands. An overrun does *not* become next month's debt — the carry-over floors at zero,
which is the behaviour that keeps the plan usable rather than punitive.

`DELETE` here is a real delete and has no confirmation guard, unlike accounts and categories. A
budget is a plan; removing one destroys no lançamento. `test_delete_removes_the_budget_and_keeps_the_transactions` pins that.

**Open, and deliberately so: credit card purchases do not count as budget spending.** The
realized amount is read from `transactions`, and a card purchase lives in `cc_expenses` until the
invoice is settled — at which point it enters as a single lançamento in a
`Pagamento Fatura <cartão>` category, not under the category the purchase was made in. For a
household that puts most spending on the card, a per-category budget therefore under-reports until
the invoice is paid, and then over-reports one category. The page says so. Three ways out, none
taken yet:

1. Budget the "Pagamento Fatura" categories themselves — works today, no code, but it is a
   budget for *the card*, not for what was bought.
2. Count open `cc_expenses` of the month into the matching category's `spent`, and exclude the
   invoice-payment lançamento to avoid counting it twice. The most useful, and the most invasive.
3. Materialize each installment as a real `transactions` row when the invoice is settled. Cleanest
   model, largest migration.

Decide before §3.4, because recurring entries will raise the same "where does the spending live"
question.

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

- [x] **~~Edit a transaction.~~ Done (2026-09-16):** `PATCH /api/transactions/<id>`, partial — it only
  touches the fields present in the payload. Inline editing in the statement table on the
  Movimentações page. Two things it refuses: editing a lançamento mirrored from an investment
  (`source_type = 'INVESTMENT_TRANSACTION'` → 409, same rule `DELETE` already had), and converting a
  plain lançamento into a transfer or back.
- [ ] **Attachments/receipts** per transaction (store the file locally, path in `metadata`).
- [ ] **Search and filters on the statement** — by period, category, account, amount range, free text.
- [ ] **Export to CSV/Excel** for the statement and the portfolio.
- [ ] **Corporate actions** (splits, reverse splits, bonus shares) — the portfolio already has FIFO and tax, but a split today would silently corrupt the average price.
- [ ] **Real multi-currency.** `assets.currency` exists but nothing converts; a USD asset enters net worth as if it were BRL.

---

## 4. Technical debt

### 4.1 `backend/app.py` at 4,946 lines

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

### 4.2 Automated tests — 249 in place (2026-09-16)

Was zero three sessions ago. There are now **249 passing tests** in `backend/tests/`, run with pytest against a throwaway SQLite database built by the real migrations.

```powershell
.\start.ps1 -Tests          # or:  cd backend; ..\.venv\Scripts\python.exe -m pytest
```

Coverage against the five axes this document named:

| # | Axis | File | Tests | Status |
|---|---|---|---|---|
| 1 | Sale FIFO — lot consumption, partial, full exit | `test_fifo.py` | 14 | Covered |
| 2 | Regressive fixed-income tax + money rounding | `test_tax_rules.py` | 27 | Covered |
| 3 | Credit card invoice — settlement | `test_credit_card_invoices.py` | 16 | Covered |
| 3 | Credit card invoice — which invoice a purchase lands in | `test_invoice_month.py` | 24 | Covered |
| 4 | Investment ↔ cash linkage | `test_investment_cash_link.py` | 9 | Covered |
| 5 | `user_id` isolation | `test_user_isolation.py` | 22 | Covered |
| — | Automatic backup and retention | `test_backups.py` | 15 | Covered |
| 6 | Bank accounts, per-account balance, transfers | `test_accounts_and_transfers.py` | 31 | Covered |
| 7 | Categories, subcategories, rename propagation | `test_categories.py` | 23 | Covered |
| 8 | Editing a transaction | `test_transaction_edit.py` | 24 | Covered |
| 9 | Monthly budget — actuals, rollup, rollover, isolation | `test_budgets.py` | 44 | Covered |

**Axis 3 is now complete.** The rollover rule ("closing day, month rollover, which invoice an installment lands in") used to live in `frontend/src/pages/Carteira.jsx`, where it could not be tested. It moved to the backend on 2026-09-15 — `compute_invoice_start()`, `split_installments()` and `POST /api/cc-expenses/purchases` — and `test_invoice_month.py` pins the behaviour, including the December→January rollover and the cent-exact installment split.

Fixture notes for whoever extends this: `app.py` reads its config and calls `init_db()` at import time, so `backend/tests/conftest.py` sets `DATABASE_PATH` and friends in `os.environ` *before* importing the module. `load_dotenv()` does not override already-set variables, which is why the real `backend/finance.db` is never touched. Fixtures available: `client`, `user`, `other_user`, `auth`.

### 4.3 Frontend

- [x] **~~`formatCurrency` duplicated across 5 files.~~ Done (2026-09-16):** `frontend/src/lib/format.js`
  holds `formatCurrency`, `formatUnitCurrency`, `formatPercent`, `parseLocalDate`, `formatDateBR`,
  `getLocalDateString`, `monthKey`, `monthLabel` and `shiftMonth`; the six files that had copies now
  import them. **Two local copies survive deliberately:** `Carteira.jsx` and `Transactions.jsx`
  default `getLocalDateString` to their `getNow()` clock hook instead of `new Date()`, and
  `Transactions.jsx`'s `formatDateBR` returns `''` where the shared one returns `'-'`. Collapsing
  those would change behaviour, not just remove duplication.
- **`Carteira.jsx` is ~1,300 lines** and `Investments.jsx` is 875. Break them into per-section components.
- **No centralized server state.** Every page does its own `useEffect` + `fetch` + `loading` + `error`. TanStack Query would handle caching, revalidation, and the repeated error pattern — roughly 200 fewer lines and better behavior.
- **Inconsistent error messages** — each page handles failure its own way. Standardize on a single toast/banner.
- **No loading skeletons** on the heavy screens (the portfolio takes a while when refreshing quotes).

### 4.4 Operations

- [x] **~~Backup is manual.~~ Done (2026-09-15):** `run_startup_backup()` runs right after `init_db()`. It backs up on boot, skips if a backup already ran inside `AUTO_BACKUP_MIN_INTERVAL_HOURS` (default 12, so restarting the app all day does not fill the directory), then prunes anything past `BACKUP_RETENTION_DAYS` (default 7). `POST /api/database/backups` prunes too and reports what it removed. Configurable via `AUTO_BACKUP_ON_BOOT`, `AUTO_BACKUP_MIN_INTERVAL_HOURS` and `BACKUP_RETENTION_DAYS`.
  **Retention only ever touches files named `finance-AAAAMMDD-HHMMSS.{db,sql,zip}`** — the ones the app generates. Hand-named milestone backups (`finance-before-<thing>-*.db`) are deliberately excluded; see the handoff for why that rule exists.
- **No integration healthcheck** — if yfinance goes down or changes, you find out visually, by noticing a stale quote.
- **No structured logging.** `server.err.log` is empty; external integration errors vanish.
- [x] **~~No single start script.~~ Done (2026-09-15):** `start.ps1` at the repo root starts backend and frontend together, waits for `/api/health` and for Vite, opens the browser, and stops both on Ctrl+C. `.\start.ps1 -Tests` runs the test suite instead; `-NoBrowser` skips opening the browser.

---

## 5. Suggested plan

A sequence aimed at real personal use, not at a code portfolio. Each phase ships something usable.

### Phase 0 — Cleanup — DONE (2026-09-15)
All of section 2. Nothing depends on it, but everything gets lighter.

### Phase 1 — Safety net (1 week) — DONE (2026-09-15)
The tests from section 4.2 + automatic backup + single start script.
*Without this, every refactor that follows is a gamble.*

- [x] Tests — 127 of them, in `backend/tests/`. See section 4.2.
- [x] Single start script — `start.ps1` (`.\start.ps1`, or `.\start.ps1 -Tests`).
- [x] Automatic backup on boot with 7-day retention. See section 4.4.

### Phase 2 — Data foundation — DONE (2026-09-16)
Bank accounts (3.1) → categories as a table (3.2) → edit transaction (3.7).
Two migrations with backfill, both verified against a copy of the real database before landing.

- [x] Bank accounts + transfers — migration 007. See §3.1.
- [x] Categories as a table — migration 008. See §3.2.
- [x] Edit a transaction — `PATCH /api/transactions/<id>`. See §3.7.

### Phase 3 — What makes it useful daily (2–3 weeks) — IN PROGRESS
Monthly budget (3.3) → recurring entries (3.4) → statement search and filters (3.7).
*This is where the app starts replacing the spreadsheet.*

- [x] Monthly budget by category, with rollover — migration 009 + `Orcamento.jsx`. See §3.3.
- [x] Category management screen — the loose end 3.2 left. See §3.2.
- [ ] Recurring entries (3.4). Next.
- [ ] Search and filters on the statement (3.7).

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
