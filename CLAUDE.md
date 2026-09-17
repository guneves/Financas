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
- Running the **`finance-guard` subagent** over the change (see below) and acting on what it finds.
- Prepending a new session entry to `docs/handoff.md`, covering: what was done, **what was not done
  and why**, what the next session should pick up, and anything non-obvious you learned along the
  way (a fixture quirk, a bug you found, a decision you made and its reasoning).
- Committing the work.

Be explicit in the handoff about partial work. "Phase 1 complete except automatic backup, because X"
is useful; "Phase 1 done" when it isn't costs the next session an hour of confusion.

## The `finance-guard` subagent

`.claude/agents/finance-guard.md` defines a read-only auditor for this repository. It reads the diff
and checks the six things that are expensive to get wrong here: `user_id` scoping on every query,
`rounded_money()` instead of Python's banker's `round()`, migrations staying append-only (and a
rebuilt table getting all of its indexes back), destructive endpoints keeping their confirmation
guard, tests covering any financial rule the diff touched, and the Portuguese/English split. It
reports; it never edits, never commits, and never runs the app against `backend/finance.db`.

```
Agent(subagent_type="finance-guard", prompt="Audit the uncommitted changes. They implement <X>.")
```

**When to run it:** after finishing a chunk of backend work and before committing — that is the point
where a missing `user_id` filter is cheap to fix and after which it is a data leak in production
data. It is worth a second run if the first one found something and you changed code in response.

Why a subagent rather than an inline checklist: the checks are mechanical, they need to read a lot of
diff to answer, and none of that reading is worth keeping in the main context afterwards. The audit
runs on its own budget and hands back a short report.

It is a *reviewer*, not an authority. It has been wrong about pre-existing `round()` calls on
non-monetary values (share quantities at 6 decimal places, yield percentages) — those are correct as
they stand. Check a finding before acting on it.

**Note:** Claude Code discovers agent definitions at startup, so a newly created or edited agent file
is only usable from the next session on.

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

205 tests in `backend/tests/`, covering FIFO, tax rules, credit card invoices (settlement and the
invoice-month rule), the investment↔cash link, bank accounts and transfers, categories, editing a
transaction, `user_id` isolation, and backup retention. They run against a throwaway SQLite database built by the real
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
  app.py              # ~4,950 lines: routes, SQL, auth, portfolio, tax, FIFO, yfinance
  scripts/            # one-off seeds — destructive, read scripts/README.md first
  tests/              # pytest suite
  .env                # local config, gitignored — .env.example is the template
database/
  schema.sql          # reference schema
  migrations/         # versioned, applied automatically on boot
frontend/src/
  pages/              # Dashboard, Transactions, Carteira, Investments, Proventos
  lib/                # api.js, auth.js, dataApi.js, portfolio.js
docs/
  next-steps.md       # the plan
  handoff.md          # session log
.claude/agents/
  finance-guard.md    # the pre-commit audit subagent
```

## Conventions

- **Money.** Always round through `rounded_money()` (`backend/app.py:823`) — it is ROUND_HALF_UP via
  `Decimal`. Python's built-in `round()` is banker's rounding and is wrong for currency. Never
  introduce a bare `round()` on a monetary value.
- **`user_id` on everything.** Every table carries it and every query must filter on it. There are
  tests asserting this; do not add an endpoint that skips it.
- **Transfers are one row, not two.** A `TRANSFER` leaves `account_id` and arrives at
  `transfer_account_id` in a single `transactions` row, so the consolidated balance ignores it for
  free. Anything that sums `transactions` must skip `type = 'TRANSFER'` — otherwise moving money
  between your own accounts reads as an expense.
- **`transactions.category` still holds the category *name*.** `category_id` was added in migration
  008, but the text column is what the Dashboard groups on and what survives a category being
  archived. Renaming a category has to rewrite both; `PATCH /api/categories/<id>` does.
- **Accounts and categories are archived, never deleted.** Both use `ON DELETE SET NULL`, so a real
  delete would silently orphan lancamentos. `DELETE` on either endpoint sets `archived_at`.
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

- `backend/app.py` is one ~4,950-line file. Splitting it is planned (§4.1) but should happen
  incrementally, one blueprint at a time, with the suite green between steps.
- The credit card **invoice-month rule now lives in the backend** (`compute_invoice_start()` in
  `backend/app.py`, behind `POST /api/cc-expenses/purchases`), covered by
  `backend/tests/test_invoice_month.py`. It used to be in `Carteira.jsx`; don't reintroduce a
  client-side copy.
- `formatCurrency` is duplicated across five frontend files and `formatDateBR` across three.
