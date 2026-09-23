# CLAUDE.md

Guidance for Claude Code when working in this repository.

## The session process — read this first

This project is worked on in discrete sessions, each starting from a clean context. Three documents
carry state between them. **Start every session by reading them in this order:**

1. **`docs/handoff.md`** — what the last session did, what it deliberately left undone, and what it
   recommends next. It holds only the most recent session; older entries live in git history
   (`git log -p docs/handoff.md`). This is the fastest way into context.
2. **`docs/next-steps.md`** — the active, prioritized work plan. Phases, functional gaps, technical
   debt. This is the source of truth for *what to work on*.
3. **`ROADMAP.md`** — historical record of what has been built and the original direction. Read for
   background; it does not drive work anymore.

Cheaper route for the same thing: run the **`session-scout` subagent** (see below) and let it read
those documents for you. It hands back a one-page briefing and keeps the reading in its own context
instead of yours.

**End every session by:**

- Updating `docs/next-steps.md` — tick off what you completed, and rewrite the affected section
  rather than appending a note to it. A stale plan is worse than no plan.
- Running the **`finance-guard` subagent** over the change (see below) and acting on what it finds.
- Replacing the session entry in `docs/handoff.md` with a new one — the file holds only the latest
  session, so delete the previous entry rather than stacking on top of it. Carry forward anything
  from it that is still open and still matters. Cover: what was done, **what was not done
  and why**, what the next session should pick up, and anything non-obvious you learned along the
  way (a fixture quirk, a bug you found, a decision you made and its reasoning).
- Committing the work.

Be explicit in the handoff about partial work. "Phase 1 complete except automatic backup, because X"
is useful; "Phase 1 done" when it isn't costs the next session an hour of confusion.

## The subagent routine

Two read-only subagents bracket a session: one opens it, one closes it. Both live in
`.claude/agents/`. Neither edits, commits, or runs the app against `backend/finance.db`. Discovery by
`subagent_type` failed repeatedly around 2026-09-15/16 but has worked since; if it fails again, use
the fallback documented at the end of this section.

### Opening — `session-scout`

`.claude/agents/session-scout.md`. Reads `docs/handoff.md`, `docs/next-steps.md`, the git log, the
migration directory and the test suite, and returns a one-page briefing: where the project stands,
what the last session genuinely left open, the next task and the concrete files it touches, the traps
from the handoff that apply to *that* task, and any drift between the docs and the repository.

```
Agent(subagent_type="session-scout", prompt="Brief me for this session.")
```

The point is the arithmetic: the handoff, the plan, the git log and the test suite together are
more text than the current task needs. The scout reads all of it and keeps the ~500 words that
matter. Read the documents yourself instead whenever the session is a
follow-up on work still fresh in context — the briefing is for a cold start.

### Closing — `finance-guard`

`.claude/agents/finance-guard.md` defines a read-only auditor. It reads the diff and checks the six
things that are expensive to get wrong here: `user_id` scoping on every query, `rounded_money()`
instead of Python's banker's `round()`, migrations staying append-only (and a rebuilt table getting
all of its indexes back), destructive endpoints keeping their confirmation guard, tests covering any
financial rule the diff touched, and the Portuguese/English split.

```
Agent(subagent_type="finance-guard", prompt="Audit the uncommitted changes. They implement <X>.")
```

**When to run it:** after finishing a chunk of backend work and before committing — that is the point
where a missing `user_id` filter is cheap to fix and after which it is a data leak in production
data. It is worth a second run if the first one found something and you changed code in response.

Why subagents rather than an inline checklist: both jobs are mechanical, both need to read a lot of
text to answer, and none of that reading is worth keeping in the main context afterwards. Each runs
on its own budget and hands back a short report.

They are *reviewers*, not authorities. `finance-guard` has been wrong about pre-existing `round()`
calls on non-monetary values (share quantities at 6 decimal places, yield percentages) — those are
correct as they stand. Check a finding before acting on it.

### If `subagent_type` is not found

Custom agent definitions are discovered by Claude Code at startup, and on 2026-09-15 and twice on
2026-09-16 `Agent(subagent_type="finance-guard")` returned *"Agent type not found"* even though the
file had been committed sessions earlier. It has worked directly in every session since, so try it
first and reach for the fallback after one failed attempt rather than investigating. Do not conclude
the file is broken — it is a discovery problem, not a definition problem. The fallback gives the
same audit:

```
Agent(subagent_type="general-purpose",
      prompt="Read .claude/agents/finance-guard.md in full and follow it exactly as your "
             "instructions. Audit the uncommitted working tree. You are read-only.")
```

Same shape for `session-scout`. If the fallback is what you used, say so in the handoff.

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

605 tests in `backend/tests/`, covering the URL map (`test_route_map.py`: every route, its methods
and its `@token_required`), FIFO, tax rules, credit card invoices (settlement, the closed-only payment rule, débito automático and the
invoice-month rule), the investment↔cash link, bank accounts and transfers, categories, editing a
transaction, monthly budgets, recurring entries, statement import and its rules (including applying
them to recorded lançamentos), CSV export, receipts per lançamento, `user_id`
isolation, and backup retention. They run
against a throwaway SQLite database built by the real migrations — **the real
`backend/finance.db` is never touched.**

`config.py` reads the environment once, at import, and `app.py` calls `init_db()` at import time,
so `conftest.py` sets `DATABASE_PATH` and friends in `os.environ` *before* importing `app` (it drops
`app` and `config` from `sys.modules` first). If you add a test that needs different config, set it
there, not inside the test. A test never imports an app module (`db`, `routes.*`, `services.*`) at
the top of the file — reach it through a fixture or `importlib.import_module` inside the test, after
`app_module` has loaded. The pure modules (`brapi_client`, `statement_import`, `export_csv`,
`market_catalog`) are fine at the top.

**Patch where the name is read, not where it is defined.** Modules import settings and helpers by
name (`from config import ATTACHMENT_MAX_BYTES`), so `monkeypatch.setattr` must target the module
whose code reads the name: `db` for the backup settings, `routes.attachments` for the upload limits,
and *both* `services.invoices` and `routes.cards` for the `local_today` clock. A patch on the wrong
module does not fail — it silently does nothing.

Fixtures: `client`, `user`, `other_user`, `auth`, `app_module`, `db_module`, `invoices_module`.

**Add tests for financial rules you touch.** That is the whole reason they exist — the plan calls for
refactoring `app.py`, and that refactor is only safe with the suite in place.

## Layout

```
backend/
  app.py              # Flask app + blueprint registration + boot; still holds all of investments
                      # (~3,600 lines: FIFO, tax, proceeds, prices, fixed income, portfolio)
  config.py           # env / .env, read once at import
  db.py               # connection, migrations, backups, row helpers
  validators.py       # ValidationError + require_* / parse_* for request payloads
  auth.py             # hand-rolled JWT, token_required
  money.py            # rounded_money()
  dates.py            # ISO parsing and month arithmetic
  source_types.py     # transactions.source_type values (who wrote the row)
  services/           # domain rules shared by several blueprints: accounts, invoices, attachments
  routes/             # one Flask blueprint per area: system, auth, accounts, transactions,
                      # attachments, budgets, recurring, imports, cards
  statement_import.py # leitura de extrato CSV/OFX (funcoes puras, sem banco)
  export_csv.py       # geracao dos CSV de extrato e carteira (funcoes puras, sem banco)
  scripts/            # one-off seeds — destructive, read scripts/README.md first
  tests/              # pytest suite
  .env                # local config, gitignored — .env.example is the template
database/
  schema.sql          # reference schema
  migrations/         # versioned, applied automatically on boot
frontend/src/
  pages/              # Dashboard (Início), lancamentos/, Orcamento, Recorrentes, investimentos/,
                      # Proventos, Ajustes + ajustes/, Importar — screen map in lib/navigation.js
  components/         # Layout (nav, "+ Novo" sheet host), NewEntrySheet, ui.jsx (the UI kit)
  lib/                # api.js, auth.js, dataApi.js, format.js, navigation.js, newEntry.js
docs/
  next-steps.md       # the plan
  handoff.md          # latest session only
.claude/agents/
  session-scout.md    # the start-of-session briefing subagent
  finance-guard.md    # the pre-commit audit subagent
```

## Conventions

- **Money.** Always round through `rounded_money()` (`backend/money.py`) — it is ROUND_HALF_UP via
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
- **A budget is a plan, not a record.** `budgets` rows are keyed by `(category_id, month)` and
  `DELETE /api/budgets/<id>` is a real delete with no confirmation guard — removing one destroys
  no lançamento. The `rollover` carry-over is computed on read, never stored, so a retroactive
  lançamento does not have to rewrite a chain of months.
- **A recurrence is a template, not money.** `recurring_transactions` rows generate real
  `transactions` rows via `POST /api/recurring/run`; nothing is projected into the statement. Each
  occurrence writes `source_type = 'RECURRING_TRANSACTION'` and
  `source_id = '<recurrence>:<AAAA-MM-DD>'`, so the unique index `idx_transactions_user_source`
  makes a second run a no-op. Keep that shape for anything else that materializes rows on demand —
  it is what makes the button safe to press twice. Deleting a recurrence keeps its lançamentos.
- **An invoice is paid only once it has closed.** `invoice_closing_date()` in `backend/services/invoices.py`
  is the rule (same shift as `compute_invoice_start()`; closed *on* the closing day). Every path
  that sets `PAID` goes through `ensure_invoice_closed()`, and the real payment is
  `POST /api/cc-expenses/pay-invoice` — don't go back to a client-side EXPENSE + status PATCH.
  The client reads `invoice_closed` / `invoice_closing_date` from `GET /api/cc-expenses`.
- **Débito automático** (`credit_cards.autopay_account_id`, migration 011) is materialized on read
  by `apply_due_autopay()`, dated on the due day, with `source_type = 'CC_AUTOPAY'` and
  `source_id = '<card>:<AAAA-MM>'` — same idempotency shape as recurrences. Only invoices due on or
  after `autopay_start_date` are paid, and a reopened invoice is not debited twice.
- **An import is idempotent by construction.** CSV/OFX rows are written by
  `POST /api/import/commit` with `source_type = 'STATEMENT_IMPORT'` and `source_id` = the row's
  hash (account + date + amount + normalized description) or `'ofx:<conta>:<FITID>'` when the file
  carries one, so the unique index makes a re-import a no-op — same shape as recurrences and
  autopay. Two identical rows in one file get an occurrence suffix, so they are still two
  lançamentos. Parsing lives in `backend/statement_import.py` (pure functions, no DB) and
  `POST /api/import/preview` never writes.
- **Rules touch the past only on confirmation.** `POST /api/import-rules/apply/preview` never writes;
  `POST /api/import-rules/apply` rewrites only the `transaction_ids` it is sent, and re-runs the
  rule on each before writing, so a stale list cannot recategorize a row the rule no longer matches.
  TRANSFER, investment cash and invoice payments are outside its reach.
- **A receipt is a file on disk, referenced by a row.** `transaction_attachments` (migration 014)
  holds the reference; the bytes live in `ATTACHMENTS_DIR/<user_id>/<stored_name>`, where
  `stored_name` is generated — the uploaded name is only displayed, never a path. The type is
  sniffed from the bytes, not trusted from the browser. Routes nest under the lançamento and check
  both ids (that is the delete's guard). Write the file before the row and remove the file only
  after the commit; `prune_orphan_attachment_files()` sweeps leftovers at boot. Receipts are **not**
  in the backup zip.
- **`CATTLE` is a live asset class**, not dead code — see `docs/next-steps.md` §2 before touching it.

## Known sharp edges

- **Phase 5 is half done.** Everything but investments is out of `backend/app.py` (see Layout);
  investments are the next step — plan in `docs/handoff.md`. The layering is strict: `config` ←
  `db` ← `validators`/`money`/`dates`/`auth` ← `services/*` ← `routes/*` ← `app`. Nothing imports
  `app`, and a blueprint does not import another blueprint (shared code goes in `services/`). A new
  blueprint must be added to the `for blueprint_module in (...)` list in `app.py`; forgetting it
  fails `test_route_map.py` by name.
- The credit card **invoice-month rule now lives in the backend** (`compute_invoice_start()` in
  `backend/services/invoices.py`, behind `POST /api/cc-expenses/purchases`), covered by
  `backend/tests/test_invoice_month.py`. The "+ Novo" card form calls it (`ccExpensesApi.createPurchase`); don't reintroduce a
  client-side copy.
- `formatCurrency` and the date helpers now live in `frontend/src/lib/format.js`. One local
  copy survives on purpose: `pages/lancamentos/helpers.js` defaults `getLocalDateString` to a
  `getNow()` clock hook rather than to `new Date()`, and its `formatDateBR` returns `''` where the
  shared one returns `'-'`.
- **Frontend conventions** (from the 2026-09-21 UX reorganization): pages use only `ui.jsx`
  pieces (`AlertMessage`, `Collapsible`, `Sheet`, `Tabs`…), emerald is the only accent, section
  tabs come from the URL, and a page that shows data saved by "+ Novo" puts `useDataVersion()`
  (`lib/newEntry.js`) in its fetch effect's dependencies. Since the 2026-09-23 remodel: a page's
  headline numbers go in one `SummaryPanel` (not a row of `MetricCard`s), two or more row actions go
  behind a `Menu` ("⋯"), a success message is `toast()` from `lib/toast.js` (errors stay in
  `AlertMessage`), and nothing new uses `window.prompt` / `alert` — use a `Sheet`.
- **Privacy mode** (the eye) hides balances, net worth and the portfolio only, and never remounts
  the page. `formatCurrency` and friends always show the value; a sensitive spot uses
  `usePrivateFormatter()` / `usePrivateAxisFormatter()` or `MetricCard sensitive` from
  `lib/privacy.js`, which re-render on toggle through `useSyncExternalStore`.
- **Visual rules** (2026-09-22 design pass): green/red/amber/sky only when they mean gain, loss,
  warning or info — labels, counts and normal states are neutral. A signed amount in a list goes
  through `formatSignedCurrency`; a numeric table cell gets `.num` (right-aligned, no wrap). Tables
  must not sit inside an `overflow-x` / `overflow-hidden` wrapper, or the sticky header stops
  sticking (use `overflow-clip` on the panel for rounded corners). Row actions use
  `IconButton size="sm"`; a big money value in a card uses `FitValue`, never `truncate`.
- **Theme and tokens** (2026-09-23 remodel, direction C "Cartões"): the palettes pages may use are
  `zinc`, `emerald`, `rose`, `amber`, `sky`, `white` and `brand` — `tailwind.config.js` maps each
  to a CSS variable in `index.css`, and **dark mode is only the `dark` class on `<html>` swapping
  those variables** (the neutral scale inverts: `white` becomes the dark surface, `zinc-950` the
  light text). So never write `dark:` classes and never use another Tailwind family (`slate`,
  `red`, `blue`…) — it does not exist in the theme. `brand` is the deep green of the net-worth block
  and the active nav pill, with `text-brand-ink` on it; text on the bright `emerald-500` fill is
  `text-on-accent`. Charts take colours from `CHART` / `OTHER_COLOR` in `charts.jsx` (CSS
  variables), never a hex literal. The theme lives in `lib/theme.js` (system by default, manual
  toggle next to the eye) and `index.html` applies it before first paint. The font is Plus Jakarta
  Sans served from `public/fonts` (the app must open offline) — no Google Fonts link.
- **Consolidated balance = sum of `/api/accounts` balances**, fetched with `include_archived`
  (`consolidatedBalance()` in `lib/transactions.js`). Summing `transactions` left each account's
  `initial_balance` out; don't go back to it.
