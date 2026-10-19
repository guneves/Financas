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
3. **`docs/done-tasks.md`** — everything already completed, moved out of the plan. Read it when you
   need to know whether something exists or how a finished feature behaves.
4. **`ROADMAP.md`** — historical record of what has been built and the original direction. Read for
   background; it does not drive work anymore.

Cheaper route for the same thing: run the **`session-scout` subagent** (see below) and let it read
those documents for you. It hands back a one-page briefing and keeps the reading in its own context
instead of yours.

**End every session by:**

- Updating `docs/next-steps.md` — **remove every task you completed from it and record it in
  `docs/done-tasks.md`** (a row in the table, plus a note if the detail is worth keeping). The plan
  holds only open work: no `[x]` boxes, no "done" sections, no struck-through decisions. What a
  finished task left undone (a "not built", an owner walk-through) stays in `next-steps.md` as an
  open item. Rewrite the affected section rather than appending a note to it. A stale plan is worse
  than no plan.
- Replacing the session entry in `docs/handoff.md` with a new one — the file holds only the latest
  session, so delete the previous entry rather than stacking on top of it. Carry forward anything
  from it that is still open and still matters. Cover: what was done, **what was not done
  and why**, what the next session should pick up, and anything non-obvious you learned along the
  way (a fixture quirk, a bug you found, a decision you made and its reasoning).
- Committing the work.

Be explicit in the handoff about partial work. "Phase 1 complete except automatic backup, because X"
is useful; "Phase 1 done" when it isn't costs the next session an hour of confusion.

## The subagent routine

One read-only subagent opens a session: `session-scout`, in `.claude/agents/`. It does not edit,
commit, or run the app against `backend/finance.db`. Discovery by `subagent_type` failed repeatedly
around 2026-09-15/16 but has worked since; if it fails again, use the fallback documented at the end
of this section.

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

### If `subagent_type` is not found

Custom agent definitions are discovered by Claude Code at startup, and on 2026-09-15 and twice on
2026-09-16 `Agent(subagent_type=...)` returned *"Agent type not found"* even though the
file had been committed sessions earlier. It has worked directly in every session since, so try it
first and reach for the fallback after one failed attempt rather than investigating. Do not conclude
the file is broken — it is a discovery problem, not a definition problem. The fallback gives the
same briefing:

```
Agent(subagent_type="general-purpose",
      prompt="Read .claude/agents/session-scout.md in full and follow it exactly as your "
             "instructions. Brief me for this session. You are read-only.")
```

If the fallback is what you used, say so in the handoff.

## What this is

A personal finance manager, single-user, running locally. Income and expenses, credit cards with
installments and invoice settlement, and a fairly deep investments module (weighted average cost,
realized results, monthly tax apuração, proceeds, quotes).

**Stack:** React 18 + Vite + Tailwind · Flask 3 · local SQLite with versioned migrations · hand-rolled
HS256 JWT auth · yfinance for quotes.

The goal is a tool the owner actually uses daily — not a portfolio piece. Prefer the change that makes
daily use better over the change that makes the architecture prettier.

## Running it

```powershell
.\start.ps1 -Tests             # run the backend test suite
.\start.ps1 -Local             # dev only: backend (:5000) + frontend (:5173), Ctrl+C stops both
.\start.ps1 -Local -NoBrowser  # same, without opening a browser
```

**The home server is the only real backend** (since 2026-10-16). The PC's `backend\finance.db` is
a development copy, not the owner's data, so `start.ps1` refuses to start without `-Local`.

**Production** runs on the home server as the Docker image
`ghcr.io/guneves/financas-app`, deployed by `.github/workflows/deploy.yml` on every push to `main`
(tests → GHCR → Tailscale SSH → `docker compose pull/up`). The server holds only `compose.yaml` and
`.env`; data is in the `financas_data` volume. `DEPLOY.md` has setup, the manual `deploy.ps1`, the
data import and rollback.

Manually, if you need the two halves separate:

```powershell
cd backend;  ..\.venv\Scripts\python.exe app.py
cd frontend; npm run dev
```

## Tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest
```

1346 tests in `backend/tests/`, covering the URL map (`test_route_map.py`: every route, its methods
and its `@token_required`), the charts' history fetch (`test_history_fetch.py`: per-ticker and
per-series caches that cover every period, a stale entry served while it refreshes in the background, and the fetches running at once), the weighted average cost (`test_average_cost.py`), tax rules and the
monthly variable-income apuração (`test_variable_income_tax.py`: stock exemption, ETFs/BDRs, the
per-sale share of the month's tax), credit card invoices (settlement, the closed-only payment rule, débito automático and the
invoice-month rule), the opt-in investment↔cash link, bank accounts and transfers, categories, editing a
transaction, monthly budgets, recurring entries, the monthly plan from income (`test_monthly_plan_income.py`: percentages at both levels, inheritance, Saldo do plano, migration 038 and `needs_income`), statement import and its rules (including applying
them to recorded lançamentos), CSV/.xlsx exports, receipts (per lançamento and per card purchase), corporate actions,
multi-currency, the IR report and the monthly exemption meter, allocation targets and concentration, goals,
proventos per asset and total return, automatic proventos (position on the data com × StatusInvest), time-weighted return and its benchmarks, sectors, the IRPF paste text, monthly contributions, the integrations healthcheck, `user_id` isolation, idempotent creation by `client_id`, the built frontend served by Flask, the APK's screen bundle (`test_app_bundle.py`), Aprovar (`test_inbox.py`: the phone's notifications waiting for the owner; `test_inbox_counterparty.py`: own-account transfer vs Pix to someone else, from the captured texts; `test_inbox_recurring.py`: a notification settling a recurrence's occurrence; `test_inbox_ambiguous.py`: the ambiguous target and "Sempre perguntar"), expense sharing and A receber (`test_expense_share.py`), card refunds (`test_cc_refund.py`), the card history (`test_card_history.py`: paid installments stay, a purchase skips a paid invoice, card archive, undoing an invoice payment), categories by id and the rename carrying everywhere (`test_category_identity.py`), each card purchase its own `client_id` and migration 035's backfill (`test_cc_purchase_identity.py`), editing a card (`test_card_edit.py`), closed signup and the generated `JWT_SECRET` (`test_signup_and_secret.py`), and backup
retention and the receipts mirror. `conftest.py` blanks `BRAPI_TOKEN`, so no test reaches brapi
unless it patches it in, and no test reaches StatusInvest: `test_proceeds_sync.py` patches
`statusinvest_client.get_proceed_events` (call `statusinvest_client.clear_cache()` too). They run
against a throwaway SQLite database built by the real migrations — **the real
`backend/finance.db` is never touched.**

`config.py` reads the environment once, at import, and `app.py` calls `init_db()` at import time,
so `conftest.py` sets `DATABASE_PATH` and friends in `os.environ` *before* importing `app` (it drops
`app` and `config` from `sys.modules` first). If you add a test that needs different config, set it
there, not inside the test. A test never imports an app module (`db`, `routes.*`, `services.*`) at
the top of the file — reach it through a fixture or `importlib.import_module` inside the test, after
`app_module` has loaded. The pure modules (`brapi_client`, `statement_import`, `export_csv`,
`market_catalog`, `irpf_text`) are fine at the top.

**Patch where the name is read, not where it is defined.** Modules import settings and helpers by
name (`from config import ATTACHMENT_MAX_BYTES`), so `monkeypatch.setattr` must target the module
whose code reads the name: `db` for the backup settings, `routes.attachments` for the upload limits,
*both* `services.invoices` and `routes.cards` for the `local_today` clock (`services.goals` for goals, `services.monthly_plan` *and* `services.goals` for the monthly plan), `services.prices` for
`download_close_prices` and `download_daily_history` (the real `get_daily_history()` and its
per-ticker cache run; clear `_daily_history_cache`), `services.fixed_income` for `fetch_bcb_series` (clear `_index_history_cache`; it returns datetimes), `services.fx` for
`fetch_bcb_window` (PTAX; call `reset_fetch_throttle()` too), `services.benchmarks` for
`download_monthly_history` (call its `reset_fetch_throttle()` too), `brapi_client` for `get_history` /
`get_sectors` / `get_listing` / `is_configured` (call `services.market_listing.reset_cache()` too), `routes.investments` for
`refresh_market_prices` (registering a corporate action fetches a quote), and *both*
`services.prices` and `routes.investments` for `yf`. A patch on the wrong module does not fail — it
silently does nothing. `app.py` itself exposes almost nothing now; reach code through the module
that defines it.

Fixtures: `client`, `user`, `other_user`, `auth`, `app_module`, `db_module`, `invoices_module`,
`prices_module`, `fixed_income_module`, `realized_results_module`, `portfolio_module`.

**Add tests for financial rules you touch.** That is the whole reason they exist — the Phase 5 split
of `app.py` was only safe because the suite was in place.

The frontend has no test runner installed. Its pure rule modules are tested with Node's own:
`cd frontend; npm test` runs `node --test` over `src/**/*.test.js` (today `outboxRules`, `format`,
`monthlyPlan`, `investmentStatement`, `appBundleRules`, `notifyRules`, `portfolioAccount`, `inboxRules`, `attentionRules`, `transactions`, `sharing` and `compoundInterest`, 120 tests). A module tested this way imports nothing from the browser, React or `lib/api.js`.

## Layout

```
backend/
  app.py              # Flask app + CORS + blueprint registration + boot (~60 lines)
  config.py           # env / .env, read once at import
  db.py               # connection, migrations, backups, row helpers
  validators.py       # ValidationError + require_* / parse_* for request payloads
  auth.py             # hand-rolled JWT, token_required
  money.py            # rounded_money()
  applog.py           # structured JSON logging; every module logs through get_logger(), never print()
  integrations.py     # last success/failure of each external provider (yfinance, brapi, BCB)
  dates.py            # ISO parsing and month arithmetic
  source_types.py     # transactions.source_type values (who wrote the row)
  asset_classes.py    # asset-class constants and the class filter
  responses.py        # download/export responses (CSV or .xlsx, ?format=&columns=) shared by blueprints
  services/           # domain rules: accounts, invoices, attachments, prices (quotes, caches),
                      # fixed_income (BCB, accrual), fx (PTAX), investments (movements, cash link,
                      # BRL conversion, the average cost), corporate_actions,
                      # realized_results (cost and IR of each sale), variable_income_tax
                      # (monthly IR of stocks/ETFs/BDRs/FIIs, pure),
                      # portfolio (positions, evolution), tax_report (IR, exemption meter),
                      # allocation (targets, contribution split, concentration), goals,
                      # proceeds (proventos read, by asset), proceeds_sync (automatic proventos),
                      # proceeds_cash (paid proventos into the portfolio account), returns (TWR), contributions
                      # (aportes x resgates), benchmarks (IPCA/IBOV/IFIX/IDIV closes),
                      # sectors (brapi sector per asset, breakdown), health (integrations),
                      # app_bundle (the APK's screens, zipped for the phone), import_rules
                      # (categorization shared by import and Aprovar), inbox + inbox_decisions
                      # (Aprovar: the phone's notifications waiting for the owner),
                      # recurring (the recurrences' calendar, /run, Aprovar's settlements),
                      # budgets (categories as % of Gastar, the plan row, inheritance),
                      # monthly_plan (income, Investir/Gastar %, Saldo do plano, flags)
  routes/             # one Flask blueprint per area: system, auth, accounts, transactions,
                      # attachments, budgets, recurring, imports, cards, investments,
                      # proceeds, market, allocation, goals, inbox, app_bundle (GET /api/app-bundle),
                      # frontend (serves frontend/dist at /)
  statement_import.py # leitura de extrato CSV/OFX (funcoes puras, sem banco)
  export_csv.py       # tabelas de exportacao (colunas tipadas) e o CSV (funcoes puras, sem banco)
  export_xlsx.py      # a mesma tabela em .xlsx, uma ou varias abas (zipfile, sem dependencia)
  irpf_text.py        # texto para colar no programa do IRPF, sobre o relatorio de IR (funcoes puras)
  statusinvest_client.py # historico de proventos por ticker na StatusInvest (funcoes puras + cache)
  scripts/            # one-off seeds — destructive, read scripts/README.md first
  tests/              # pytest suite
  .env                # local config, gitignored — .env.example is the template
database/
  schema.sql          # reference schema
  migrations/         # versioned, applied automatically on boot
frontend/src/
  pages/              # Dashboard (Início), lancamentos/, Orcamento, Recorrentes, Metas, investimentos/
                      # (incl. Calculadora: compound interest, lib/compoundInterest.js),
                      # Proventos, Ajustes + ajustes/, Importar — screen map in lib/navigation.js
  components/         # Layout (nav, "+ Novo" host), NewEntrySheet (banking only), CashLinkField
                      # (the portfolio account + "Não descontar de nenhuma conta"),
                      # ui.jsx (the UI kit)
  lib/                # api.js, auth.js, dataApi.js, format.js, navigation.js, newEntry.js,
                      # queries.js (TanStack Query), confirm.js, toast.js, scroll.js,
                      # outbox.js + outboxRules.js (offline queue), offlineStore.js (IndexedDB),
                      # queryPersist.js (saved read cache), connection.js,
                      # inboxRules.js (Aprovar's texts and requests)
docs/
  next-steps.md       # the plan — open work only
  done-tasks.md       # completed work, moved out of next-steps.md
  handoff.md          # latest session only
frontend/android/      # Capacitor's Android project (committed); native code in
                      # app/src/main/java/br/financas/app/ (outbox/ = the native queue and sender,
                      # bundle/ = the screen self-update, notify/ = the bank-notification
                      # listener and NotifyPairing, the bank × Samsung rule); app/src/debug/ = the test APK's name
frontend/native-level.txt   # the APK's native level; a screen goes only to an APK at or above its level
frontend/scripts/      # bundle-manifest.mjs: writes bundle.json into the APK build
mobile/
  build-apk.ps1       # web build for the APK + cap sync + signed release + adb install
  new-keystore.ps1    # creates the release key outside the repo; run once, back it up
mobile-docs/
  steps-to-production.md  # the Android app plan: decisions, phases and their status
.claude/agents/
  session-scout.md    # the start-of-session briefing subagent
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
- **`transactions.category` still holds the category *name*, but the id decides** (035). `category_id`
  was added in migration 008; the text column is what the Dashboard groups on and what survives a
  category being archived. The same name exists under different parents ("Outros" at the root,
  "Alimentação › Outros", "Lazer › Outros"), so every table that keeps a category keeps both —
  `transactions`, `cc_expenses` (035), `recurring_transactions`, `import_rules`, `inbox_items` —
  and every screen's category select sends `category_id` (value = id, never the name). A bare name
  (old client, an outbox item queued before the id) resolves to the root first, then the oldest
  subcategory (`category_id_for_name()`, `CATEGORY_NAME_ORDER` in `services/accounts.py`; the
  budget's fallback for rows with no id reads the same order), and an edit that sends back the
  row's own name keeps its id (`resolve_category(current=...)`). Renaming rewrites the name in all
  five tables (`rename_category_rows()`), and a row with only the old text adopts the id when that
  name was this category's. The import commit accepts a rule's archived category
  (`allow_archived`); a new choice by the owner does not.
- **A card purchase is its `client_id`** (035). Every installment shares it and every purchase has
  one: the delivery's, one generated when the client sends none (`POST /api/cc-expenses/purchases`,
  refunds, Aprovar), or `legacy:<id>` for those written before 024 (the migration splits identical
  old purchases by write order). Receipts, sharing, A receber, the attachment count and the
  purchase's installments (`GET /api/cc-expenses/candidates?id=<any installment>`) go through
  `same_purchase_sql()` / `cc_purchase_expense_ids()` in `services/attachments.py`; the screens
  group by `cardPurchaseKey()` (`lib/transactions.js`). Card + description + date + category is
  only the fallback for a row with no `client_id` (the old list `POST /api/cc-expenses`): it made two
  identical Uber rides one purchase.
- **There is always one default account, active and not the Corretora** (2026-10-18 night).
  `ensure_default_account()` (`DEFAULT_ACCOUNT_ORDER` in `services/accounts.py`: the marked one,
  else the first non-Corretora by name — the list's order) writes `is_default` when none is
  marked, so server and screens read the same flag. Archiving the default or making it Corretora
  hands the mark on; `is_default` on a Corretora is refused; a PATCH clears the other marks only
  after its own UPDATE went through (a repeated name, 409, changes nothing).
- **An edit keeps the row's own account even when archived** (`keep_or_require_account()`); a new
  choice must be active, and `account_id: ""` on an edit is refused, never "the default". The
  Extrato sends the account only when it changed. A transfer edit checks currencies like the
  creation (`TRANSFER_CURRENCY_MESSAGE`). A recurrence whose account is archived does not post:
  `/run` lists it in `blocked`.
- **Signup is closed once a user exists** (`ALLOW_SIGNUP=1` opens it; `conftest.py` sets it). A
  missing or example `JWT_SECRET` (`PUBLIC_JWT_SECRETS` in `config.py`) is replaced by a random one
  stored in `JWT_SECRET_FILE` (`.jwt_secret` next to the DB, mode 600), never the public default.
- **Accounts and categories are archived, never deleted.** Both use `ON DELETE SET NULL`, so a real
  delete would silently orphan lancamentos. `DELETE` on either endpoint sets `archived_at`.
  **Cards too** (037): `cc_expenses` cascade from `credit_cards`, so `DELETE /api/credit-cards/<id>`
  refuses (409) while the card has an `OPEN` item, archives one with history (paid items or
  payments; autopay off) and really deletes only an empty one. An archived card is out of the GET
  (`?include_archived=1`) and takes no purchase, refund, autopay or Aprovar approval
  (`require_active_card()`).
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
  lançamento does not have to rewrite a chain of months. **A budget is a % of the month's Gastar**
  (038, `services/budgets.py`): `planned_percent` only, never a fixed R$; its R$ = Gastar R$ × % on
  read (`percent_of()`), the categories sum to at most 100% of Gastar (400; a month converted over
  100% may lower one, not raise it), and "Sem categoria" is the rest. A month's categories are
  those of the latest month ≤ it with a plan row or budget rows (`category_source_month()`), so a
  month without its own inherits them; any write in an inherited month (POST, PATCH/DELETE/lines
  `?month=`, copy) goes through `materialize_month()` first, which copies the inherited plan and
  categories into it. Rollover's leftover is the previous month's own Gastar × its %. A row with
  `planned_percent` NULL predates 038 and waits for income (`needs_income`, status
  `NEEDS_INCOME`); `planned_amount` is read only to convert it, and new rows write 0 there.
- **A recurrence is a template, not money.** `recurring_transactions` rows generate real
  `transactions` rows via `POST /api/recurring/run`; nothing is projected into the statement. Each
  occurrence writes `source_type = 'RECURRING_TRANSACTION'` and
  `source_id = '<recurrence>:<AAAA-MM-DD>'`, so the unique index `idx_transactions_user_source`
  makes a second run a no-op. Keep that shape for anything else that materializes rows on demand —
  it is what makes the button safe to press twice. Deleting a recurrence keeps its lançamentos.
  A pause skips only its own window (019): `paused_at` on pause, `(paused_at, resume day)` appended
  to `pause_gaps` on resume, so an occurrence due before the pause stays pending. Anything that walks
  occurrences goes through `recurring_occurrence_dates()` / `skip_pause_gaps()`, and revival starts
  after the stored `last_occurrence_date`, not after the last surviving lançamento. That calendar
  lives in `services/recurring.py` (the blueprint only validates and serves).
- **Aprovar settles a recurrence's occurrence** (034, owner 2026-10-18). A pending item shows the
  open occurrence it looks like (`suggest_for_item()`: same type — an outflow/card purchase is an
  EXPENSE, an inflow an INCOME, a transfer never —, within `RECURRING_MATCH_DAYS` = 7 days, and the
  exact amount, or within 20% when the description shares a word or the category matches; an
  INCOME within 20% even without the name, because the salary arrives in the employer's name).
  Approving it (or "É este" on a lançamento already there) writes a `recurring_settlements` row:
  `/run` skips that date, it is not pending, it leaves the forecast, and the cursor walks over a
  settled prefix. The approved lançamento keeps the notification's real amount, card or account;
  it takes the recurrence's category only when the item had the import default. "Não é esta"
  (`PATCH /api/inbox/<id>` `{recurring: false}`, `inbox_items.recurring_off`) holds for "Aprovar
  todos" too; `approve` takes `recurring: false` or an explicit `{recurring_id, date}`, checked
  before anything is written.
- **Only `pay-invoice` marks an invoice paid** (2026-10-18 night): `PATCH /api/cc-expenses/status`
  and `/invoice-status` were removed — they set `PAID` with no payment, and reopen + pay debited
  twice. Reopening is "Desfazer pagamento". `compute_invoice_start()` clamps a closing day 29–31
  to the purchase month's last day, as `invoice_closing_date()` does.
- **An invoice is paid only once it has closed.** `invoice_closing_date()` in `backend/services/invoices.py`
  is the rule (same shift as `compute_invoice_start()`; closed *on* the closing day). Every path
  that sets `PAID` goes through `ensure_invoice_closed()`, and the real payment is
  `POST /api/cc-expenses/pay-invoice` — don't go back to a client-side EXPENSE + status PATCH.
  The client reads `invoice_closed` / `invoice_closing_date` from `GET /api/cc-expenses`.
- **A paid invoice is history** (037). A paid item is never deleted (`DELETE /api/cc-expenses`
  refuses it; Cartões deletes only a purchase's `OPEN` installments), and a new purchase or refund
  never lands in a paid invoice: `first_unpaid_invoice()` starts it at the first one from its date
  with an open item or no paid one (the autopay `source_id` is taken, so it would never be debited).
  `settle_invoice()` stamps each item's `paid_by` (the payment lançamento);
  `DELETE /api/cc-expenses/payments/<id>` (Extrato › "⋯" › Desfazer pagamento) removes the payment,
  reopens what it paid (or, before 037, its invoice's paid items without `paid_by`) and writes
  `cc_invoice_manual`, so autopay never debits that invoice again — it goes back to "Pagar".
  Refused while the payment has a receipt.
- **The next invoice is per card, by due date, never "next month's"** (2026-10-18). The invoice
  month is the due month, so a card that closes before its due day (3/10) pays this month's
  invoice and one that closes after it (25/5) next month's. `nextInvoices()` in
  `lib/attentionRules.js` (each card's open invoice with the earliest due date from today on) feeds
  Início's "Próxima fatura", its "Pagar fatura", the projection and the bell;
  `nearestOpenInvoice()` (overdue first) is the one Cartões opens and pays from its header. Overdue
  means after the due day (`isPastDue()`), on every screen.
- **Débito automático** (`credit_cards.autopay_account_id`, migration 011) is materialized on read
  by `apply_due_autopay()`, dated on the due day, with `source_type = 'CC_AUTOPAY'` and
  `source_id = '<card>:<AAAA-MM>'` — same idempotency shape as recurrences. Only invoices due on or
  after `autopay_start_date` are paid, and a reopened invoice is not debited twice.
- **An import is idempotent by construction.** CSV/OFX rows are written by
  `POST /api/import/commit` with `source_type = 'STATEMENT_IMPORT'` and `source_id` = the row's
  hash (account + date + amount + normalized description) or `'ofx:<conta>:<FITID>'` when the file
  carries one, so the unique index makes a re-import a no-op — same shape as recurrences and
  autopay. Two identical rows in one file get an occurrence suffix, so they are still two
  lançamentos. A FITID repeated inside one file gets the same occurrence suffix. Parsing lives in
  `backend/statement_import.py` (pure functions, no DB) and `POST /api/import/preview` never
  writes. Amounts: the last separator is the decimal, a dot in groups of three is thousands
  ("1.500"), a comma alone is always decimal; OFX's own amount may use a comma. In the type
  column, short codes ("d", "db") count only on their own, words by prefix.
- **Dates and months are stored zero-padded**: `require_date()` / `normalize_month()` accept
  "2026-1-5" and return "2026-01-05" — the filters and the budget compare them as text.
- **A "+ Novo" creation is idempotent by `client_id`** (024). `POST /api/transactions`,
  `/api/transfers` and `/api/cc-expenses/purchases` take an optional `client_id`; a repeated one
  returns what the first delivery created, with 200, and writes nothing. The lookup runs *before*
  validation, so a replay succeeds even if the account was archived in between. It is a column,
  not `source_type`/`source_id`: such a row was typed by the owner and stays "Manual", editable and
  deletable. All installments of a purchase share the id (the `cc_expenses` index includes
  `installment_info`). The frontend always sends one (`createEntry()` in `lib/outbox.js`).
- **The outbox holds creations only, and only when the request never reached the server**
  (`ApiNetworkError` in `lib/api.js`). A response from the server, whatever it is, is never queued
  or retried on its own. A timeout counts as never reaching it only where that is safe: a
  creation (`timeoutMs`, 6 s; `client_id` makes the resend harmless — and with no network at all,
  `backend.isOffline()`, it is queued without trying) and a read (45 s); an edit
  or delete has no timeout, because one that timed out may have gone through. One queue and one sender per platform: IndexedDB and `flush()` in the
  browser; in the APK both become native (`setOutboxBackend()`), because sending must work with
  the app closed. The rules — what each response does to an item, what a pending item does to a
  balance — live in `lib/outboxRules.js` with tests; a pending transfer leaves the consolidated
  balance alone and a pending card purchase touches no account. A balance that counts pending
  items is labelled an estimate. In the APK the queue and the sender are Java
  (`frontend/android/.../outbox/`, swapped in by `lib/nativeApp.js`), and `OutboxRules.java` is a
  port of `outboxRules.js`: change one, change the other, with a test on each side.
- **The APK's screens come from the server** (2026-10-17, `services/app_bundle.py`,
  `android/.../bundle/`, `lib/appBundle.js`). The image builds the frontend for the APK into
  `frontend/dist-android` with a `bundle.json` (content-hash version, native level, API address);
  the phone downloads it, checks the SHA-256 and opens it on the next start on trial. A bundle
  that does not call `ready()` within 30 s of opening (`AppStarted` in `main.jsx`, after the first
  render) is dropped for good and the APK's own screens come back. A bundle's native level is the
  **minimum** APK level it needs. **Bump `frontend/native-level.txt`** in the same commit as any
  change the screens depend on that lives in the APK — a Java plugin or method the JS calls, a
  Capacitor/plugin upgrade, a permission — so an old APK never loads screens calling Java it does
  not have, and never remove a Java method that lower-level screens still call (a newer APK runs
  them). `GET /api/app-bundle*` is public on purpose (the same frontend `/` serves).
- **A new APK comes from CI, never from GitHub Releases** (2026-10-17). The `apk` job of
  `deploy.yml` runs only when `frontend/android/`, `native-level.txt` or `capacitor.config.json`
  changed. It signs with the `android-release` environment's key (checked against
  `mobile/release-cert-sha256.txt`), uses `versionCode = 10000 + run number`, and copies the APK and
  `version.json` to `/srv/apps/financas/apk/`, served at `/apk/` by `tailscale serve`. The app
  (`android/.../update/ApkUpdatePlugin.java`, `ApkUpdateBanner.jsx`) offers "Nova versão
  disponível" when that versionCode is higher than the installed one, then downloads the APK and
  opens Android's installer. DEPLOY.md, "Updating the phone". The same job builds the **test APK**
  (debug build, package `br.financas.app.debug`, "Finanças debug") and copies it as
  `financas-debug.apk`, outside `version.json`: it installs beside the real app by `adb install`,
  never over it, and is never offered as an update.
- **Bank notifications are read on the phone and stay there** (Phase 6, 2026-10-17,
  `android/.../notify/`, `lib/notifyCapture.js`, Ajustes › Notificações dos bancos). The
  allow-list is `NotifyRules.APPS` plus the manifest's `<queries>` (a JVM test keeps them equal);
  anything else is dropped unread. Only a debug build accepts `com.android.shell` (adb-posted
  test notifications) — never widen that to release. Capture mode is off by default, keeps each
  notification word for word in `financas_notify.db`, and its texts leave the phone only through
  the export (share sheet); never send them to the server or a third party. The listener
  deduplicates only the same posting (`dedupKey`: package + key + posted time). Samsung Wallet is
  heard again (owner, 2026-10-17, later the same day) as a **fallback**: the bank app's notification
  wins, Samsung's counts only when no bank notification for that purchase arrives, and Samsung
  only ever yields card purchases (never Pix, transfer or estorno). The pairing runs **on the
  server** (`services/inbox.py`, `same_purchase()`: one to one, same amount in cents, a card
  neither side contradicts, within `NOTIFY_WINDOW_MS`; only the bank's decline cancels);
  `notify/NotifyPairing.java` is the same rule, JVM-tested, and stays unwired because the phone
  sends every detection at once. Itaú Cartões and Ourocard stay off (they repeat the bank apps),
  so don't add them back. Parsers are written against exported captures, never against examples
  from the web.
- **Every money notification goes to Aprovar, as parsed fields only** (2026-10-17). The listener
  hands every allowed notification to `notify/NotifyParsers.java` (pure, `NotifyParsersTest`),
  capture on or off; a detection (kind, amount in cents, merchant, card final, installments, and
  for a Pix/transfer the counterparty's name, the masked CPF's visible digits and institution)
  goes to `DetectionQueue` and `DetectionWorker` POSTs it to `/api/inbox/detections`. The text
  itself never leaves the phone. A parser change gets a test case from a real capture first.
  Nothing a notification brings is recorded without the owner's approval: a detection that looks
  like an existing lançamento is a pending item with it as candidate, never a silent match.
- **Aprovar never remembers an ambiguous target** (2026-10-18, `ambiguous_target()` in
  `services/inbox.py`): no card final and more than one active account (or card) whose *bank
  field* names the notification's bank — never the name — means no hint is saved, none applies,
  no guess, and the item asks every time. Accounts/cards without a bank don't count (today's
  behaviour). Every item shows its target with "Trocar". "Sempre perguntar a conta/cartão"
  (`user_settings`, 036, `GET/PATCH /api/inbox/settings`) makes every target a confirm
  (`confirm_targets()`), so "Aprovar prontos" takes nothing.
- **Own-account transfer vs someone else is the counterparty** (031, `services/inbox.py`). "It's
  me" is learned, never typed: `inbox_hints` keys `self:doc:<digits>` / `self:name:<name>`,
  written when an OUT and an IN leg pair into a transfer and when the owner approves a transfer.
  A single leg whose counterparty is the owner is drafted as a TRANSFER (other side guessed from
  the cited institution, or asked); otherwise it is a despesa/receita "Pix para/de <nome>"
  (`external_transfer`). A transfer seen by the brokerage app (`BROKERAGE_APP`, BTG
  Investimentos) is always the owner's own, the other side BTG Banking. Two legs whose CPF digits
  or first names differ never pair. The same
  notification posted twice by a bank (same app, kind, amount, event time, merchant) is
  `repeated`, not a second item.
- **No bank-statement API** (owner, 2026-10-17): Pluggy was removed — its free plan gives no
  access. Aprovar (028) takes the phone's notifications only. At the owner's request, the
  migrations no longer mention it either. This was the one deliberate break of append-only,
  done only after the server had applied 029: `027_reserved.sql` and `029_reserved.sql` are
  empty but keep their numbers, because a database that already applied them would skip a new
  file with the same number. 028 lost its Pluggy lines, and 030 renames the two rows in
  `schema_migrations`. On a database that applied the old 028, the stored `CREATE TABLE
  inbox_items` still carries one Pluggy word in a comment. Rewriting it would need a table
  rebuild, which isn't worth it for a comment.
- **Flask serves the built frontend** (`routes/frontend.py`, `.\start.ps1 -Local -Built`): screen and API
  on one origin, which is what the phone opens. A production build calls the API same-origin;
  `vite dev` keeps `http://localhost:5000`. `/api/*` never falls back to `index.html`.
- **Rules touch the past only on confirmation.** `POST /api/import-rules/apply/preview` never writes;
  `POST /api/import-rules/apply` rewrites only the `transaction_ids` it is sent, and re-runs the
  rule on each before writing, so a stale list cannot recategorize a row the rule no longer matches.
  TRANSFER, investment cash, paid proventos and invoice payments are outside its reach.
- **A receipt is a file on disk, referenced by a row.** `transaction_attachments` (migration 014)
  holds the reference; the bytes live in `ATTACHMENTS_DIR/<user_id>/<stored_name>`, where
  `stored_name` is generated — the uploaded name is only displayed, never a path. The type is
  sniffed from the bytes, not trusted from the browser. Routes nest under the lançamento and check
  both ids (that is the delete's guard). Write the file before the row and remove the file only
  after the commit; `prune_orphan_attachment_files()` sweeps leftovers at boot. Receipts are not in
  the backup zip: every backup mirrors `ATTACHMENTS_DIR` into `backups/attachments/` (one copy per
  file; deleted ones go to `backups/attachments-removed/AAAAMMDD/`). Card purchases have their own
  table (`cc_expense_attachments`, 016), listed across all installments of the purchase.
- **A corporate action is applied on write** (017, `services/corporate_actions.py`): earlier
  movements and quotes of the asset are rescaled in place (originals in
  `metadata.corporate_adjustments`), a bonus is a zero-cash BUY row. So stored values are always in
  the basis of the asset's latest event: no movement may be entered or moved before it, and only the
  latest event with nothing after its ex date can be undone. Keep those guards.
- **Foreign currency is stored native, calculated in BRL** (018): quantities, prices and quotes in
  the asset's currency, the movement's rate in `metadata.fx_rate`. `fetch_investments()` — the
  stream the realized result, portfolio, evolution and the IR report read — returns BRL (cost at the movement's
  rate, value at today's PTAX); `fetch_investment_rows()` is native (screens, edits). The cash link
  is BRL. Anything new that computes money from movements must read `fetch_investments()`.
- **The app is reais-only on screen** (owner, 2026-10-12: "Everything on the app should be reais").
  No form offers a currency (accounts, operations), and no screen prints a foreign one. An account
  balance on screen goes through `accountBalanceBrl()` (`lib/transactions.js`): the converted
  value, or "sem câmbio hoje". The 018 machinery above stays in the backend, tested and reachable
  only through the API — never add a currency choice or a foreign symbol back to a screen unless
  the owner asks. One deliberate exception: the IR tab's "Aplicações no exterior" panel and the
  matching row of the IR export appear when, and only when, the year has a foreign result (in
  reais), so an estimated tax can never be hidden.
- **Investments and banking are separate areas; a movement's cash goes through the portfolio
  account** (2026-10-12; portfolio account 2026-10-17). `metadata.cash_account_id` on the movement
  is both the switch and the account:
  present, exactly one linked lançamento exists in that account (`source_type =
  'INVESTMENT_TRANSACTION'`, `source_id` = the movement id, BRL, category "Investimento"); absent,
  nothing is written. The rule is `investment_cash_account_id()`, checked first in
  `sync_investment_cash_transaction()`; `resolve_investment_cash_account()` validates the account
  (the user's, active, BRL) before any write. On `PATCH` an omitted key keeps the link and `null`
  removes it — refused (409) while the lançamento has a receipt. A movement that asks for the
  Extrato but has no cash amount to write is refused (400), so the key never says "no extrato"
  without a row. Each movement decides for itself, and nothing financial reads the link (cost, IR
  and the portfolio read movements, not cash). **The portfolio account** (owner, 2026-10-17): an
  active BRL account of type Corretora (`BROKERAGE`) is linked to the portfolio, and every new
  operation comes out of it (a sale or redemption goes into it) unless the owner ticks "Não
  descontar de nenhuma conta", which sends `cash_account_id: null`. The API applies it to a POST
  without the key (`portfolio_cash_account_id()`: default account first, then the name — the
  order of the account list), and keeps such a movement out instead of refusing it when it has
  nothing to write; with no Corretora account the API writes nothing (the tests and seeds post
  that way). The screens always send the key, and refuse a new operation until a Corretora
  account exists (`lib/portfolioAccount.js`, tested); an edit of an old one is not blocked. The
  three forms share `CashLinkField`; Ajustes › Contas links an account by "Vincular à carteira"
  (PATCH type). **Paid proventos go into it too** (`services/proceeds_cash.py`,
  `apply_paid_proceeds()`, materialized on read next to `apply_due_autopay()` in the accounts and
  transactions reads): each provento with payment date ≤ today and net > 0 is one INCOME row
  (`source_type = 'INVESTMENT_PROCEED'`, `source_id` = the provento id, category "Investimento"),
  locked in the Extrato (409), following its provento (edit, delete, back to scheduled). Only
  proventos paid on or after the account's `metadata.portfolio_since` (set by the PATCH that makes
  it Corretora; `created_at` for one created as Corretora) — earlier ones are already in its
  initial balance, and the automatic proventos carry years of history. A written row stays in the
  account it was born in. **Its balance is shown only in Investimentos** (owner, 2026-10-17):
  `consolidatedBalance()` / `openingBalanceTotal()` skip Corretora accounts, Início reads
  `bankingTransactions()` (rows inside a Corretora leave; a transfer bank → Corretora is an aporte,
  back a resgate), Ajustes › Contas says "Em Investimentos" instead of the amount, the
  invoice-payment sheet and the autopay warning never print it, and Posição's summary has "Saldo
  na corretora" (`portfolioCashBalance()`). All in `lib/transactions.js`, tested.
- **Início is the banking area only, and in reais.** Its headline is the consolidated account
  balance; the portfolio never appears there, so nobody reads invested money as money to spend. A
  foreign-currency account appears only by its converted value (`accountBalanceBrl()` in
  `lib/transactions.js`, "sem câmbio hoje" when there is no rate) — never in its own currency. A lançamento
  that is linked, or typed in the category "Investimento", is an aporte (EXPENSE) or a resgate
  (INCOME), not a despesa or a receita — `isInvestmentOutflow()` / `isInvestmentInflow()` in
  `lib/transactions.js` — and every banking total (Início, Extrato, Recorrentes) keeps it apart.
  "+ Novo" is banking-only (despesa, receita, transferência, cartão); inside `/investimentos` the
  same button opens "Registrar operação".
- **Whose expense it is** (032, `services/sharing.py`, `lib/sharing.js`): a despesa/receita or a
  card purchase can be the owner's, `SPLIT` (others' part in `share_others_amount`) or `OTHERS`,
  with `share_person`. Balances never change; the budget, the monthly plan, Despesas por categoria
  and Início's cash flow count only the owner's part (`own_amount_sql()` / `ownAmount()`), the flow
  shows "Outras pessoas" apart. A card purchase's share covers every installment, split
  proportionally. Lançamentos › A receber lists the others' part of each expense until marked paid
  (`share_settled_at`); marking writes no money. Transfers and investment cash are never shared.
- **"Precisa de atenção" lives in two places** (owner, 2026-10-18): Início's cards and the bell in
  the header (where the theme toggle was). Both read `lib/attentionRules.js` (pure, tested): each
  item carries a `key` naming the case (the invoices, the recurrence's last occurrence, the
  budget month and category), not the kind. Início's X dismisses the items on screen for this
  device (`lib/attention.js`, localStorage), so the same case never comes back there and a new one
  does; the bell always lists every current item. The bell runs Início's own queries
  (`useInicio*()`, same keys), so the cache is shared.
- **A card refund is a credit row** (033, `POST /api/cc-expenses/refunds`): `cc_expenses.kind =
  'REFUND'`, amount stored positive, always 1/1, never shared. Anything that sums card rows goes
  through the sign — `signed_amount()` / `signed_amount_sql()` in `services/invoices.py`,
  `cardSignedAmount()` in `lib/transactions.js`. It lands in its date's invoice, or the next one
  not yet paid. An invoice zeroed by a refund is settled without a lançamento; one in credit is
  refused (409) and its rows ride along with the next invoice's payment (`invoice_open_lines()`).
- **Budget spent (decision 1):** card purchases count in full in the purchase month (a refund
  subtracts in its month); invoice payments never count.
- **"Disponível por dia" lives in Planejar › Orçamento, not Início** (2026-10-19): the month
  plan's Saldo do plano (`plan_balance`) ÷ days left in the month, today included, read from the
  server's `daily_available` — never computed on the client, and no fallback without a plan. In its
  old place Início has **"Resumo do mês"** (`MonthSummary` in `pages/Dashboard.jsx`): Resultado
  (receitas − despesas, the owner's part), Entrou, Saiu, Investido (aportes − resgates, when either
  happened) and the net of other people (label by sign, value unsigned, → A receber), all from the
  cash flow's current month (`lib/cashFlow.js`); privacy mode masks every value and Resultado's
  colour. The hero holds only the balance and the accounts.
- **Orçamento's percentages slide, they are not typed** (2026-10-19, owner): Investir, Gastar and
  each category's % are a `PercentSlider` (`ui.jsx`: range of 1 point, − and + for the fine step,
  the R$ beside it). Each stops at what is still free (`percentRoom()` / `clampPercent()` /
  `stepPercent()` in `lib/monthlyPlan.js`, tested): Investir at 100 − Gastar and back, a category at
  100% of Gastar − the others (an edit in a month already over 100% may lower, never raise). The
  income stays typed; Metas (the investing goals) are unchanged. In an old plan without income
  both start blank ("—") and "Converter os valores antigos" blanks them again.
- **The plan's flags can be dismissed per device** (`lib/planFlags.js`, localStorage, like
  Início's attention cards): the key is `planFlagKey()` in `lib/monthlyPlan.js` — flag code +
  month (+ `goal_id`) — so the same flag stays gone that month, a new code, another goal or the
  next month comes back. The Gastar bar's colour still reads every flag; nothing goes to the server.
- **Proventos of ações/FIIs are computed, not typed** (026, `services/proceeds_sync.py`):
  `POST /api/investment-proceeds/sync` takes each event from StatusInvest (`statusinvest_client.py`;
  brapi's dividends need a paid plan) and multiplies its value per share by the position on its
  *data com* (`accumulate_position()`, the manual form's rule), so a buy entered with a past date
  brings the proventos it earned and deleting one takes them away. Idempotent like recurrences:
  `sync_key` = `<ticker>:<kind>:<data com>:<pagamento>#n` with a unique partial index. A typed
  provento (`sync_key` NULL) is never touched and stands in for the automatic one of the same type and
  data com, an edited automatic one is `sync_locked`, a deleted
  one goes to `proceeds_sync_dismissed` and stays gone; a ticker whose fetch fails keeps its rows.
  The frontend asks for it (`lib/proceedsSync.js`) when an investments screen opens (at most every
  10 min) and 1.5 s after any write to `/api/investments*` or `/api/corporate-actions*`; the server
  caches each ticker's history for 6 h and paces requests (StatusInvest answers bursts with 429/403).
  StatusInvest's values before a split are already in today's basis, as are our stored quantities;
  before a bonificação they are not, and neither are ours — so quantity × value is right either way
  (checked against Investidor10). A renamed ticker needs an entry in `TICKER_ALIASES`. JCP's
  default tax is 15% with data com up to 2025 and 17.5% from 2026; "rendimento tributável" is a
  JCP row with `metadata.kind = TAXABLE_INCOME` at 22.5% (`default_tax_rate()` in
  `services/proceeds.py`).
- **The Extrato has two views** (`?ver=contas|investimentos`, last choice kept on the device): the
  accounts' lançamentos, and a read-only investments statement of operações + proventos
  (`lib/investmentStatement.js`, tested). The investments one writes nothing and never touches an
  account balance; editing stays in Operações and Proventos.
- **The monthly plan is a plan, like budgets, and starts from income** (025, 038,
  `services/monthly_plan.py`): `PUT /api/monthly-plan` writes one month's `income_amount` (the only
  typed R$, required, > 0 — no plan without income) and `invest_percent` / `spend_percent` of it
  (required, 0 allowed, sum ≤ 100, else 400). Every R$ is computed on read from the **planned**
  income (income × %, then Gastar R$ × category %, through `percent_of()`), never stored; "Sem
  destino" = 100% − Investir − Gastar is returned. Percentages are TEXT with six decimals read as
  `Decimal` (`to_percent()`), never float. A month without a row inherits the latest earlier plan,
  categories included; a PUT that creates a month's plan copies the inherited categories into it,
  and `DELETE` (real, no guard) removes the month's plan and its categories. Spent and invested
  are computed on read: spent is the budget's rule without categories (no transfers, invoice
  payments or aportes; card purchases in full in the purchase month), invested is aportes −
  resgates of movements, never the linked cash; the received income only compares. **Saldo do
  plano** (`plan_balance`) = Gastar R$ − the month's spent is the one "still to spend" number
  (`progress.spend_remaining` and `/api/budgets` `totals.plan_balance` are the same); budgets'
  `totals.remaining` is only the categories' own leftover. An old plan without income
  (`spend_percent` NULL) is `needs_income`: nothing is computed from it, and the PUT with the
  income converts it (percentages omitted = from the old R$, 038's formula) and the old categories
  of the months it governs. Flags are codes plus amounts; the Portuguese text lives in
  `lib/monthlyPlan.js`. Goal flags are per goal, never summed.
- **Allocation targets and goals are plans, like budgets** (020, 021): `PUT /api/allocation/targets`
  replaces the whole set (class targets sum to 100%; asset targets are % *within* their class and
  sum to 100% in any class that has one), and `DELETE /api/goals/<id>` is a real delete with no
  guard. Current values, gaps, the contribution split and the goal forecast are computed on read
  from `build_portfolio_snapshot()` (net values) — never stored.
- **The chart history is served stale and refreshed behind** (2026-10-19, owner: "Evolução de
  patrimônio is taking too long"). The Yahoo closes (`get_daily_history()`) and the BCB series
  (`_bcb_series_since()`) are fresh for `HISTORY_CACHE_TTL_SECONDS` (15 min); after that, up to
  `HISTORY_CACHE_STALE_MAX_SECONDS` (7 days), the request reads the cache at once and
  `schedule_history_refresh()` (`services/prices.py`, one per key) downloads again in the
  background. Only past months read it — the current month uses the live quote. A refresh that
  fails or brings a ticker with no closes keeps the old history. Past the stale limit, or a
  ticker never fetched, the request waits as before. Tests wait with `wait_history_refreshes()`.
- **TWR is daily and the closes are in the basis of the stored quantities** (2026-10-18,
  `services/returns.py`): each day r = (V1 + sales + proventos) / (V0 + buys) − 1, months are
  products of their days — Investidor10's method. Yahoo records a bonificação as a split and
  adjusts the earlier closes; a bonus here is its own BUY row and earlier quantities are not
  rescaled, so `restore_quantity_basis()` (`services/prices.py`) undoes every Yahoo event except
  a registered SPLIT/REVERSE_SPLIT. Returns and evolution both read `get_daily_history()` through
  `load_history_inputs()` (tests patch `routes.investments.get_daily_history`; the
  `daily_history_from_months` fixture builds it from monthly paths). A bonificação is never a
  flow (`movement_flow_amount()`).
- **The exemption meter reads the IR report's own apuração** (`exemption_meter()` calls
  `renda_variavel()` up to the month), so the R$ 20 mil figure on the IR tab and in the sale form
  always matches the annual report. Don't give it a second copy of the rule.
- **Cost is the weighted average (custo médio ponderado), never FIFO** (2026-10-17): the Receita's
  rule for stocks, FIIs, ETFs and BDRs (Lei 8.981/1995, art. 72, §2º; IN RFB 1.585/2015, art. 58).
  `apply_average_cost()` in `services/investments.py`, run inside `fetch_investments()`, gives each
  movement `cost_amount` (how much the position's cost changes; a sale removes quantity × the
  average of that moment) and each sale `average_cost`. Posição, the evolution, the realized
  result and Bens e Direitos all sum those, so they agree. **The price stored on a SELL row is
  never a cost**: the screen sends the position's average there and the API used to accept the
  sale price — neither is read. Fixed income stays per title (quantity × price, as stored).
- **One monthly tax rule for variable income** (`services/variable_income_tax.py`, pure):
  `monthly_apuration()` is the IR tab's month-by-month *and* the IR of each sale — the realized
  result stores the sale's share of its month's tax (`apply_monthly_tax()`), so an exempt sale
  shows IR 0 in Operações exactly as on the IR tab. The R$ 20 mil exemption is for **ações only**
  (units count as ações); ETFs and BDRs pay 15% with no exemption, don't count toward the limit
  and share the stocks' loss pool; FIIs 20% with their own pool; fixed-income ETFs (IR withheld at
  source, Lei 13.043/2014) stay out of the DARF. The kind comes from `market_catalog.tax_kind()`
  (catalog kind, `FIXED_INCOME_ETFS`, BDR ticker suffix), through `market_listing.tax_kind()`.
  Foreign assets and "outros" keep a per-sale estimate. Tributação exclusiva (códigos 06 e 10) is
  declared at the **net** value: the IR tab, the paste text and the export show that.
- **`CATTLE` (Gado) was removed on 2026-09-27** at the owner's request: the API refuses it and no screen
  lists it. The migrations' `CHECK` constraints still allow the value (append-only; no table rebuild
  for it) — don't read that as the class being alive.

## Known sharp edges

- **The layering is strict** (Phase 5, done 2026-09-23): `config` ← `db` ←
  `validators`/`money`/`dates`/`auth`/`asset_classes`/`responses` ← `services/*` ← `routes/*` ←
  `app`. Among the investment services: `variable_income_tax` (pure: `money`/`validators`, read by
`realized_results` and `tax_report`), `proceeds` (only `db`/`money`/`dates`/`validators`) and
  `prices` ← `fixed_income` ← `fx` ← `investments` ← `corporate_actions` / `realized_results` /
  `portfolio` ← `tax_report` / `allocation` / `goals` / `returns` / `contributions`, `allocation` ←
  `sectors`, `fixed_income`/`prices` ← `benchmarks` (read by `routes/investments.py`); `health` sits
  on top. `inbox` sits on `import_rules`; `inbox_decisions` on `inbox` and `invoices`, and is read
  by `routes/inbox.py`, `routes/transactions.py` and `routes/cards.py` (`absorb_created`). `monthly_plan` sits on `budgets` (the plan row, Gastar R$ and the categories live in
  `budgets`; `routes/budgets.py` reads `build_budget_view()` from `monthly_plan`). `routes/proceeds.py` is write-only now — reads go through `services/proceeds.py`. Nothing imports
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
  tabs come from the URL. Server data is read with `useQuery` (`lib/queries.js`); `apiFetch`
  invalidates the whole cache after every successful write, so a page never refetches by hand
  (call `invalidateServerData()` only to *await* the refresh). `useDataVersion()` is only the
  Extrato "arrived" flash. A list that is loading shows `ListSkeleton`, not its empty state. Since the 2026-09-23 remodel: a page's
  headline numbers go in one `SummaryPanel` (not a row of `MetricCard`s), two or more row actions go
  behind a `Menu` ("⋯"), a success message is `toast()` from `lib/toast.js` (errors stay in
  `AlertMessage`), a destructive confirmation is `await confirmAction({...})` from
  `lib/confirm.js`, and nothing uses `window.confirm` / `prompt` / `alert`.
- **Privacy mode** (the eye) hides balances and the portfolio only, and never remounts
  the page. `formatCurrency` and friends always show the value; a sensitive spot uses
  `usePrivateFormatter()` / `usePrivateAxisFormatter()` or `MetricCard sensitive` from
  `lib/privacy.js`, which re-render on toggle through `useSyncExternalStore`.
- **Visual rules** (2026-09-22 design pass): green/red/amber/sky only when they mean gain, loss,
  warning or info — labels, counts and normal states are neutral. A signed amount in a list goes
  through `formatSignedCurrency`; a numeric table cell gets `.num` (right-aligned, no wrap).
  Touch targets are 44 px below `lg` (Phase 2, 2026-10-16): `Button`, `IconButton`,
  `SegmentedControl` and `Tabs` already do it, so don't add `h-11 lg:h-9` by hand; a numeric
  field gets `inputMode` (`decimal` for money, `numeric` for counts — not where a value can be
  negative). The "+ Novo" forms open on a large, focused amount field, in typing order. Tables
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
  `text-on-accent`. Charts take colours from `CHART` (grid, axes, ink), `FLOW` / `SERIES` / `OTHER_COLOR` in `charts.jsx` (CSS
  variables), never a hex literal. The theme lives in `lib/theme.js` (system by default; Sistema / Claro / Escuro
  in Ajustes › Aparência — no header toggle) and `index.html` applies it before first paint. The font is Plus Jakarta
  Sans served from `public/fonts` (the app must open offline) — no Google Fonts link.
- **Consolidated balance = sum of `/api/accounts` balances**, fetched with `include_archived`
  (`consolidatedBalance()` in `lib/transactions.js`). Summing `transactions` left each account's
  `initial_balance` out; don't go back to it.
