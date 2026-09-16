# CLAUDE.md

Guidance for Claude Code when working in this repository.

## The session process — read this first

This project is worked on in discrete sessions, each starting from a clean context. Three documents
carry state between them. **Start every session by reading them in this order:**

1. **`docs/handoff.md`** — what the last session did, what it deliberately left undone, and what it
   recommends next. Most recent session is at the top. This is the fastest way into context.
2. **`docs/next-steps.md`** — the active, prioritized work plan. Phases, functional gaps, technical
   debt. This is the source of truth for *what to work on*.
3. **`ROADMAP.md`** — historical record of what has been built and the original direction. Read for
   background; it does not drive work anymore.

**End every session by:**

- Updating `docs/next-steps.md` — tick off what you completed, and rewrite the affected section
  rather than appending a note to it. A stale plan is worse than no plan.
- Prepending a new session entry to `docs/handoff.md`, covering: what was done, **what was not done
  and why**, what the next session should pick up, and anything non-obvious you learned along the
  way (a fixture quirk, a bug you found, a decision you made and its reasoning).
- Committing the work.

Be explicit in the handoff about partial work. "Phase 1 complete except automatic backup, because X"
is useful; "Phase 1 done" when it isn't costs the next session an hour of confusion.

## What this is

A personal finance manager, single-user, running locally. Income and expenses, credit cards with
installments and invoice settlement, and a fairly deep investments module (FIFO cost basis, realized
results, estimated tax, proceeds, quotes).

**Stack:** React 18 + Vite + Tailwind · Flask 3 · local SQLite with versioned migrations · hand-rolled
HS256 JWT auth · yfinance for quotes.

The goal is a tool the owner actually uses daily — not a portfolio piece. Prefer the change that makes
daily use better over the change that makes the architecture prettier.

## Running it

```powershell
.\start.ps1              # backend (:5000) + frontend (:5173), Ctrl+C stops both
.\start.ps1 -Tests       # run the backend test suite
.\start.ps1 -NoBrowser   # start without opening a browser
```

Manually, if you need the two halves separate:

```powershell
cd backend;  ..\.venv\Scripts\python.exe app.py
cd frontend; npm run dev
```

## Tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest
```

127 tests in `backend/tests/`, covering FIFO, tax rules, credit card invoices (settlement and the
invoice-month rule), the investment↔cash link, `user_id` isolation, and backup retention. They run against a throwaway SQLite database built by the real
migrations — **the real `backend/finance.db` is never touched.**

`app.py` reads config and calls `init_db()` at import time, so `conftest.py` sets `DATABASE_PATH` and
friends in `os.environ` *before* importing it. If you add a test that needs different config, set it
there, not inside the test.

Fixtures: `client`, `user`, `other_user`, `auth`.

**Add tests for financial rules you touch.** That is the whole reason they exist — the plan calls for
refactoring `app.py`, and that refactor is only safe with the suite in place.

## Layout

```
backend/
  app.py              # ~4,000 lines: routes, SQL, auth, portfolio, tax, FIFO, yfinance
  scripts/            # one-off seeds — destructive, read scripts/README.md first
  tests/              # pytest suite
  .env                # local config, gitignored — .env.example is the template
database/
  schema.sql          # reference schema
  migrations/         # versioned, applied automatically on boot
frontend/src/
  pages/              # Dashboard, Transactions, Carteira, Investments, Proventos
  lib/                # api.js, auth.js, dataApi.js
docs/
  next-steps.md       # the plan
  handoff.md          # session log
```

## Conventions

- **Money.** Always round through `rounded_money()` (`backend/app.py:713`) — it is ROUND_HALF_UP via
  `Decimal`. Python's built-in `round()` is banker's rounding and is wrong for currency. Never
  introduce a bare `round()` on a monetary value.
- **`user_id` on everything.** Every table carries it and every query must filter on it. There are
  tests asserting this; do not add an endpoint that skips it.
- **Migrations are append-only.** Add a new numbered file in `database/migrations/`; never edit one
  that has been applied. They run automatically at boot.
- **Destructive endpoints take a confirmation guard.** Deleting by asset requires the matching
  `asset_class`; deletions that would leave a sale or redemption unbacked are refused. Keep that
  pattern for anything new that destroys data.
- **Comments and identifiers are a mix of Portuguese and English.** User-facing strings and error
  messages are Portuguese; documentation in `docs/` is English. Match the surrounding file rather
  than converting it.
- **`CATTLE` is a live asset class**, not dead code — see `docs/next-steps.md` §2 before touching it.

## Known sharp edges

- `backend/app.py` is one ~4,000-line file. Splitting it is planned (§4.1) but should happen
  incrementally, one blueprint at a time, with the suite green between steps.
- The credit card **invoice-month rule now lives in the backend** (`compute_invoice_start()` in
  `backend/app.py`, behind `POST /api/cc-expenses/purchases`), covered by
  `backend/tests/test_invoice_month.py`. It used to be in `Carteira.jsx`; don't reintroduce a
  client-side copy.
- `formatCurrency` is duplicated across five frontend files and `formatDateBR` across three.
