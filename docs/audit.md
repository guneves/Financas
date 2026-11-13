# Architecture audit — Phase 1 (read-only)

> 2026-11-11, on `main` at `79aaa33`. Nothing in the code was changed and nothing was committed.
> Every probe ran on a throwaway SQLite built by the real migrations, in a scratch directory outside the
> repository; `backend/finance.db` and the server were never touched.
> Evidence standard: each finding has `file:line`, the defect, a concrete failure scenario, a severity
> and a confidence. **Confirmed** = reproduced by a test or script here. **Plausible** = read in the code.
> Rules marked "owner AAAA-MM-DD" in `CLAUDE.md` are treated as decisions, never as findings; where a
> finding touches one, it is listed under "Questions for the owner" instead.

## 1. Baseline (measured, not remembered)

| Check | Result |
|-------|--------|
| `python -m pytest` (backend) | **2871 collected: 2868 passed, 3 failed**, 519 s. Python 3.13.18 here; CI and the image use 3.14 |
| `npm test` (frontend) | 245 pass, 0 fail |
| `uvx ruff check backend` (ruff 0.17.4, no config file) | **406** findings: 240 in app code, 166 in tests. 213 auto-fixable |
| APK unit tests | not run (no Android SDK in this container; `dl.google.com` blocked) |
| `backend/finance.db` after the full run | not created: the "some test writes to finance.db" item of `next-steps.md` did not reproduce here |

The three failures are finding **A1** below. Ruff by rule, app code only: I001 ×88 (import order),
BLE001 ×29, FURB157 ×21, TRY401 ×17, UP017 ×16, RUF100 ×10, RUF046 ×8, FURB162 ×8, **F821 ×4**
(finding C1), PLR0124 ×4 (NaN checks, harmless), F402 ×3, F401 ×3, F601 ×2 (harmless duplicate keys in
`routes/cards.py:163`). All 48 F811 and all 41 RUF059 are in tests.

Sizes: 40.7 k lines of Python outside tests (111 modules), 34.2 k lines of tests (120 files), 25.0 k of
JS/JSX, 36.6 k of Kotlin/Java in `app/src/main`, 125 API routes.

## 2. The real layer map

Measured with an AST import graph over the 111 backend modules (top-level and function-level imports).

```
config
  ← applog, source_types, asset_classes, dates            (leaves: config or nothing)
  ← db (imports config + applog)
  ← validators ← money ; auth (db, config) ; responses
  ← pure/client modules: brapi_client, pluggy_client, tesouro_client, statusinvest_client,
    statement_import, export_csv, export_xlsx, irpf_text, market_catalog, gov_http, history_store,
    integrations, open_finance_categories, identity_invariants, gzip_responses
  ← services/*   (63 modules)
  ← routes/*     (21 blueprints)
  ← app
```

- **No layer violation**: no leaf imports `services`, no service imports `routes`, no blueprint imports
  another, nothing imports `app`. `test_route_map.py` holds.
- **No top-level import cycle.** One cycle exists through a function-level import
  (`services/inbox.py:2291`, `from services.open_finance import LATE_POSTING_DAYS`): it ties ten modules
  into one strongly connected component (`inbox`, `inbox_decisions`, `inbox_defaults`, `global_account`,
  `open_finance`, `open_finance_auto`, `open_finance_check`, `open_finance_inbox`,
  `open_finance_invoices`, `open_finance_orphans`). Finding D2.
- `CLAUDE.md`'s layering line omits `applog` and `source_types` (both leaves under `db`/`services`); the
  code is consistent, the sentence is incomplete.
- Fan-in: `validators` 60, `db` 59, `money` 53, `dates` 30, `source_types` 23, `services.accounts` 22,
  `services.invoices` 20, `services.investments` 15, `services.inbox` 14.
- Not imported by the app: `identity_invariants` and `services/open_finance_rebuild` (scripts and tests
  only, by design).
- Module boundaries are porous inside `services/`: **about 75 calls to another module's `_private`
  function** (`inbox._reais` ×15, `inbox._cents` ×10, `inbox._shift` ×6, `inbox._date_gap` ×6,
  `open_finance_invoices._cents` ×5, `open_finance_inbox._drop_target` ×2 …); 31 of them are made from
  `open_finance_inbox.py`, 14 from `inbox_decisions.py`.
- All 125 routes carry `@token_required` except `/api/health`, `/api/auth/signup`, `/api/auth/login`
  and the static frontend. Every SQL statement touching a user table filters by `user_id`, with two
  cosmetic exceptions that re-read rows the same request just inserted by fresh id
  (`routes/cards.py:147`, `routes/cards.py:531`).

## 3. Findings, by severity

### A. High

**A1. `main` cannot deploy: three tests fail from 2026-11-11 on because they hard-code November 2026
dates against the real clock.** — *confirmed*
- `backend/tests/test_broker_settlement.py:157-167`
  (`test_an_announced_provento_is_in_transit`, payment date `2026-11-10`);
  `backend/tests/test_open_finance_rebuild.py:535-560` (`autopay_world` "fecha 03/11, vence 10/11";
  `test_autopay_debits_a_connected_card_on_the_due_day`,
  `test_the_banks_later_payment_links_to_the_autopay_with_its_amount`).
- Scenario: any push to `main` on or after 2026-11-11 → the `test` job of `deploy.yml` fails → `build`,
  `apk` and `deploy` are skipped. It already happened: deploy run 127 (PR #75, 2026-11-11 22:05 UTC)
  failed at "Run python -m pytest"; run 126 (2026-11-06) was green. **The Extrato/quote change of
  2026-11-11 is merged but not on the server.**
- Reproduction: the full suite here; then the two autopay tests re-run with the clock moved
  (`time-machine`, scratch venv only): both pass at 2026-11-06 and fail at 2026-11-12. The provento test
  did not pass under the moved clock either (it mixes a patched `local_today` with real `date.today()`
  elsewhere), so its exact trigger is *plausible*, not confirmed.
- Wider risk: 23 test files contain literal `2026-11`/`2026-12`/`2027-0x` dates; `datetime.now()` /
  `date.today()` are read directly in about 40 places in `services/` and `routes/` next to the patchable
  `invoices.local_today()`, so a test cannot freeze "today" in one place. More time bombs are likely.
- This is a test defect, not a product defect: no rule changed.

**A2. Two concurrent requests can pay the same invoice twice.** — *confirmed (forced interleaving)*
- `backend/routes/cards.py:944-962`, `backend/services/invoices.py:284-325`, `backend/db.py:49-60`.
- Defect: `settle_invoice()` reads the open lines, then inserts the payment. The read runs outside any
  transaction (Python's `sqlite3` opens one only at the first write, and nothing issues
  `BEGIN IMMEDIATE`), and a manual payment's `source_id` ends in a fresh `new_id()`, so the unique index
  `idx_transactions_user_source` cannot stop a second one.
- Scenario: invoice of R$ 100, account with R$ 1.000. Two `POST /api/cc-expenses/pay-invoice` arrive
  together (double tap, a client retry after a slow answer, or "Pagar" pressed while a `GET /api/home`
  is applying the débito automático of the same invoice on the due day: autopay uses another
  `source_id`). Both read the same open lines, both insert an EXPENSE → statuses `[201, 201]`, two
  payments of R$ 100, balance **R$ 800 instead of R$ 900**; `paid_by` points only to the second, so
  "Desfazer pagamento" of the first reopens nothing.
- Reproduction: probe in Appendix A (a barrier after `invoice_open_lines()` makes both requests read
  before either writes). The natural window is microseconds wide, with one gunicorn worker and 8
  threads; rare, but the outcome is money debited twice.
- The same check-then-write shape, without a transaction around the check, is everywhere a guard is a
  `SELECT` followed by a write (budget sum ≤ 100%, "sale without position", card delete guards, signup
  "closed once a user exists" at `routes/auth.py:48-55`). Idempotent creations are **not** affected:
  `client_id`/`source_id` unique indexes catch the repeat and the routes return the first result
  (verified in `routes/cards.py:627-631`).

### B. Medium

**B1. A network call runs while the SQLite write lock is held.** — *confirmed (mechanism); path read*
- `backend/services/fx.py:130-134` (`rate_on()` calls `fetch_and_store()` → BCB over HTTP on the
  caller's connection); called from `backend/services/open_finance_auto.py:248` (`in_reais_now()`),
  which runs inside the pull's single write transaction (`backend/services/open_finance.py:789-879`,
  opened by `_save_item_status()` at line 790) and inside `record_due()` on `GET /api/home`,
  `/api/transactions`, `/api/review`.
- Scenario: a pull brings a purchase in US$ on a reais card on a day whose PTAX is not stored yet, and
  the BCB is slow (30 s timeout, one retry). The pull keeps the write lock for the whole wait; any write
  of the owner in that window (edit a lançamento, pay an invoice, review) waits `busy_timeout` (5 s) and
  answers **500 `database is locked`**. "+ Novo" survives (it times out at 6 s and goes to the outbox);
  edits and deletes do not.
- Reproduction: Appendix A — a connection that wrote and then calls `fx.rate_on()` with a 7 s fake BCB;
  a concurrent `POST /api/transactions` returned 500 after 5.0 s.
- Related, by reading: the whole post-pull pipeline (ingest, succession, near match, auto-record,
  invoice payments, bank investments, orphans) is one transaction; CPU-bound today, but any future
  network call added under it inherits the problem.

**B2. Three implementations of "what was spent this month", and they disagree.** — *confirmed*
- `backend/services/home.py:83-131` (integer cents in SQL, skips rows of a Corretora account),
  `backend/services/monthly_plan.py:85-115` (float `SUM`, counts them), `backend/services/budgets.py:288-312`
  (a third copy). The "is an invoice payment" test is a category-name prefix in all three
  (`'Pagamento Fatura%'`), beside the `source_type` test.
- Scenario: one EXPENSE of R$ 100 in a bank account and one of R$ 40 typed in a Corretora account, same
  month → `GET /api/home` `summary.expense` = **100,00**; `GET /api/monthly-plan` `spend.realized` and
  `GET /api/budgets` `totals.plan_spent` = **140,00**. Início and Orçamento show different "gasto".
- This divergence is the open owner decision "B2" in `next-steps.md`; the finding is that the rule
  lives in three places, so any decision has to be applied three times. See Questions.

**B3. The web Início and Extrato download the whole history and recompute, in JavaScript, panels the
server already serves.** — *confirmed (measured)*
- `frontend/src/pages/Dashboard.jsx:106-143` (`buildSpending`) and `:166` (`useInicioMovements`),
  `frontend/src/pages/lancamentos/useLancamentos.js`, against `GET /api/home/panels`
  (`backend/services/home_panels.py`), which only the APK reads.
- Scenario: on a seeded 3-year database (1.4 k requests of seed data) one open of Início fetches
  `GET /api/transactions` = **548 KB** and `GET /api/cc-expenses` = **671 KB** of JSON, growing linearly
  with history, to compute four panels that `/api/home/panels` returns in 5 KB / 7 ms. Two
  implementations of the same banking panels (JS and Python) can drift; one drift is already recorded in
  `next-steps.md` ("Despesas por categoria" sums R$ 1.397,14 against R$ 1.365,41 spent).
- Already listed as open work; here it has numbers and is the main frontend/backend rule duplication
  that is *not* intentional.

### C. Low

**C1. `PATCH /api/categories/<id>` with a `currency` key answers 500.** — *confirmed*
- `backend/routes/accounts.py:434-455`: the "virar conta global" block of `account_detail` was also
  pasted into `category_detail`; it reads `account` and `account_id`, which do not exist there (ruff
  F821 ×4).
- Scenario: `PATCH /api/categories/<id> {"name": "X", "currency": "BRL"}` → `NameError: name 'account'
  is not defined` → 500. No screen sends that key, so nobody sees it; it is dead, wrong code inside a
  write route.

**C2. Eight private "cents" helpers, seven of them built on Python's `round()`.** — *confirmed
(helper outputs); impact plausible*
- `services/inbox.py:186`, `twins.py:29`, `recorded_snapshot.py:25`, `open_finance_check.py:68` and
  `:256`, `open_finance_invoices.py:67`, `open_finance_fixed_income.py:243`, `broker_statement.py:55`,
  `sharing.py:332` — all `int(round(float(v) * 100))`; only `open_finance_inbox.py:121` (`to_cents`)
  uses `Decimal` + `ROUND_HALF_UP`, the rule of `money.py`.
- Scenario: for 10.125 the `round()` helpers give 1012, `to_cents()` and `rounded_money()` give 1013
  (also 1.005 → 100 vs 101; 18.185 → 1818 vs 1819). Stored amounts have two decimals, where both agree,
  so today this only bites a value with a third decimal (a Pluggy amount compared in cents with a
  stored row): "same cents" would miss by one and the movement would be recorded twice instead of
  linked. No such input was found; the convention ("never a bare `round()`") is broken in seven places.

**C3. Login has no attempt limit; the password floor is 6 characters; any non-example `JWT_SECRET` is
accepted, however short.** — *plausible*
- `backend/routes/auth.py:68-80`, `:37`; `backend/config.py:74-78`.
- Scenario: a device inside the tailnet (443 has no proxy in front) can try passwords without limit;
  a server configured with `JWT_SECRET=abc` signs forgeable 30-day tokens. Behind :8443 both proxies
  stand in front, so exposure is the tailnet only. Tokens cannot be revoked (no logout server-side, no
  password change route).

**C4. An unhandled exception answers Flask's HTML 500, not JSON.** — *confirmed (seen in C1/B1 probes)*
- `backend/app.py` registers no error handler. Scenario: any 500 (the lock in B1) reaches the clients
  as an HTML page; the web shows a generic failure and the outbox treats it as "server down, retry".

**C5. N+1 in `GET /api/investment-proceeds`.** — *confirmed (measured)*
- `backend/services/proceeds.py:64-66` and `:112` (`asset_movement_rows()` once per provento).
- Scenario: 114 proventos → 114 identical statements (122 in the request), 12 ms today, linear in the
  number of proventos. Same shape, smaller: `recurring.settled_dates()` once per recurrence
  (`services/recurring.py:480`), 14 statements in `/api/attention` and `/api/recurring`.
- The rest of the read path is healthy on the 3-year seed: `/api/home` 23 statements / 9 ms,
  `/api/transactions?limit=50` 16 / 6 ms, portfolio 24 / 11 ms. `GET /api/investments/returns` took
  2.2 s only because yfinance was unreachable (first open after a restart waits for the provider, as
  `next-steps.md` already says).

### D. Structure (no wrong result today)

**D1. Business rules inside route functions.** `routes/investments.py`: `investment_detail` is 219
lines and `create_movements` 172; `routes/cards.py`: 760 of 990 lines are view bodies with 33
`execute()` calls (`cc_expenses` 148 lines, `update_credit_card` 93); `routes/transactions.py`:
`update_transaction` 141 lines; `routes/accounts.py`: `account_detail` 127. Consequence already
visible: the engine cannot call the routes, so it re-implements creation — `transactions` is inserted
from 10 modules and `cc_expenses` from 3 (`routes/cards.py` ×3, `inbox_decisions.py` ×2,
`open_finance_invoices.py` ×2), each with its own column list.

**D2. `services/inbox.py` ↔ `services/open_finance*.py` form one 10-module knot** held apart by a single
function-level import (`inbox.py:2291`). Scenario: moving that import to the top of the file (what an
import sorter or a tidy-up would do) makes the app fail at boot with a circular `ImportError`.

**D3. Two parallel auto-record pipelines** with the same function names and near-identical steps:
`services/auto_record.py` (`enabled`, `hold_reason`, `one_side_now`, `record_item`) and
`services/open_finance_auto.py` (same four). A change to "nothing waits" has to be made twice.

**D4. "Today" has many sources**: `invoices.local_today()` (patched in tests) plus ~40 direct
`datetime.now()` / `date.today()` reads. It is what makes A1 possible and what forces the
"patch in `services.invoices` *and* `routes.cards`" rule in `CLAUDE.md`.

## 4. The ten files carrying the most debt

| # | File | Lines | Why |
|---|------|------:|-----|
| 1 | `backend/services/inbox.py` | 2749 | 139 functions: notification policy, parsing, pairing, hints, settings, serialization, transfer absorption, plus the money/date helpers the rest of the engine calls as `inbox._x` (~45 private uses from outside); the lazy import of D2 |
| 2 | `backend/services/open_finance_inbox.py` | 1864 | Pure Pluggy normalization, ingest/placement (`place` 112 lines), succession, near match, reconciliation, review settling and bank funds in one file; 31 calls into other modules' privates |
| 3 | `backend/services/open_finance.py` | 1221 | Settings, connection CRUD, mapping, the pull (`_sync_item_locked`, 130 lines, one transaction: B1), history preview/apply and the list view |
| 4 | `backend/routes/investments.py` | 1464 | D1: rules in views (219- and 172-line functions), history/benchmark orchestration with thread pools in a blueprint |
| 5 | `backend/routes/cards.py` | 990 | D1: 33 SQL calls in views; three purchase-insert paths; A2 lives here |
| 6 | `backend/services/inbox_decisions.py` | 945 | Re-implements "create a lançamento/purchase/refund" beside the routes (`create_entry` 87 lines); 14 private cross-module calls |
| 7 | `frontend/src/pages/Dashboard.jsx` | 1300 | One 700-line component (`Dashboard`, lines 145-842) plus `buildSpending`: B3 |
| 8 | `frontend/src/pages/lancamentos/Extrato.jsx` | 1016 | Two views, filters, paging, review, card merge and editing in one page; still fed by the whole-history hook |
| 9 | `backend/services/open_finance_rebuild.py` | 1459 | A one-off tool the size of the engine, reaching into 9 privates; isolated from the app (only the script imports it), so the risk is contained, the maintenance cost is not |
| 10 | `backend/routes/accounts.py` + `routes/transactions.py` | 515 + 533 | 127- and 141-line views with branching by payload key; C1 is a copy-paste casualty of exactly this shape |

Large but cohesive, not ranked: `frontend/src/components/ui.jsx` (1064, the UI kit),
`pages/investimentos/Posicao.jsx` (1008), the APK's `AjustesScreen.kt`/`AjustesViewModel.kt`
(1077/977), `services/portfolio.py`, `services/prices.py`.

## 5. Duplications

### Intentional (server decides, a client repeats for UX or offline) — document, do not merge

| Server | Client copy | Why it stays |
|--------|-------------|--------------|
| `NOTIFICATION_POLICY`, `notification_wanted()` (`services/inbox.py`) | `NotifyRules.APPS`, manifest `<queries>`, `NotifyParsers.parse()` | the phone filters before sending; the server still decides, so an old APK is safe |
| `NOTIFY_WINDOW_MS` | `NotifyPairing.DEFAULT_WINDOW_MS` | kept equal by hand; the phone-side pairing is unwired |
| `services/global_account.py` | `lib/globalAccount.js`, `rules/GlobalAccount.kt` | US$ formatting and labels on screen |
| outbox rules: none on the server | `lib/outboxRules.js` ↔ `OutboxRules.java` | offline queue, one per client |
| `services/sharing.py` (`own_amount_sql`) | `lib/sharing.js`, Kotlin `rules/` | form validation before the request |
| `services/treasury.py` (PEPS) | `lib/treasury.js` | grouping on screen |
| `services/monthly_plan.py` / `budgets.py` | `lib/monthlyPlan.js` (`percentRoom`, `clampPercent`) | slider bounds; the server re-validates |
| every `lib/*.js` rule | the matching `rules/*.kt` | the native port mirrors the JS on purpose |

### Accidental (same side, same rule, more than one copy)

| What | Where | Risk |
|------|-------|------|
| reais → cents | 8 helpers (C2) | rounding rule differs between copies |
| month's spent / income / invoice-payment test | `home.py`, `monthly_plan.py`, `budgets.py` (B2) | already diverged |
| banking panels | `Dashboard.jsx` `buildSpending` vs `services/home_panels.py` (B3) | already diverged once |
| auto-record pipeline | `auto_record.py` vs `open_finance_auto.py` (D3) | double edits |
| insert a lançamento / a card purchase | routes vs `inbox_decisions.py` vs `open_finance_invoices.py` (D1) | a new column must be added in up to 10 places |
| timestamp → seconds | `open_finance.py:718`, `open_finance_auto.py:68` (`_seconds`) | — |
| value → date | `fx.py:65`, `treasury.py:94`, `tesouro_client.py:242` (`_as_date`) beside `dates.parse_iso_date` | — |
| description normalizer | `inbox.normalized()` and `twins._normalized()`, both thin wrappers over `statement_import.normalize_description` | pairing, twins and the import hash share one function: changing the import hash silently changes matching |
| `'Pagamento Fatura'` literal | `home.py:41` (constant), `monthly_plan.py:99`, `budgets.py:312`, `invoices.py:312`, `open_finance_invoices.py:471` | a category the owner names "Pagamento Fatura …" drops out of spent |
| `SELECT DISTINCT user_id FROM open_finance_items …` | twice in `open_finance_refresh.py:46` and `:61` | — |

## 6. Hygiene

- **A dead WebView build ships in every APK** — *confirmed*: 52 tracked files (1.3 MB) under
  `frontend/android/app/src/main/assets/` (`capacitor.config.json`, `capacitor.plugins.json`,
  `public/assets/*.js`: an old build of the web UI) plus `frontend/android/capacitor-cordova-android-plugins/`.
  No Kotlin/Java source references a WebView or Capacitor; Gradle packs `assets/` by default.
- Backend functions referenced nowhere, tests included: `export_csv.transaction_row`,
  `export_csv.transactions_csv`, `export_csv.portfolio_csv`, `global_account.unconfirmed_transfers`,
  `invoices.ensure_credit_card_owner`, `open_finance.set_first_sync_days`, `prices.get_monthly_history`.
  Referenced only by tests: `brapi_client.clear_sector_cache`, `export_csv.portfolio_row`,
  `market_catalog.is_known`, `fixed_income.refresh_fixed_income_prices`. Unused imports:
  `routes/proceeds.py:30`, `routes/transactions.py:9`, `services/open_finance_inbox.py:53`.
- Frontend exports with no importer outside their own tests (leftovers of the removed Aprovar screen
  and others): `inboxRules.js` `decisionText`, `readyIds`, `pendingNoticeText`, `approveReadySummary`,
  `hintText`; `review.js` `waitingNoticeText`; `openFinance.js` `autoRecordHint`; `attentionRules.js`
  `isPastDue`; `compoundInterest.js` `futureValue`; `portfolioAccount.js` `isPluggyFedAccount`;
  `proceedsRules.js` `typeForAsset`; `transactions.js` `portfolioCashBalance`. With no importer at all:
  `investmentStatement.js` `STATEMENT_KINDS`; `layers.js` `closeTopLayer`; `outbox.js` `outboxItems`,
  `reloadOutbox`; `outboxRules.js` `ENTRY_KINDS`; `privacy.js` `valuesHiddenNow`,
  `onValuesHiddenChange`; `theme.js` `themePreferenceNow`, `useIsDark`; `charts.jsx`
  `compactCurrency`, `Sparkline`; `lancamentos/helpers.js` `getPurchaseGroupKey`, `readStoredNumber`.
  (Found by name search: *plausible*, each needs a look before removal.)
- Routes neither the web nor the APK calls: `POST /api/database/backups`, `GET /api/database/status`,
  `DELETE /api/investments/by-ticker/<ticker>`, `PATCH /api/investments/price-by-ticker`; and the list
  `POST /api/cc-expenses` that `next-steps.md` already flags. An old APK may still call something:
  see Questions.
- `backend/scripts/seed_wallet_mock.py:9` and `seed_true_portfolio.py:8` compute their own
  `DATABASE_PATH` (default `backend/finance.db`) instead of reading `config`; the wipe list of
  `seed_three_years_mock.py:45-60` stops at the tables of ~migration 021 (no inbox, Open Finance,
  review or goals tables), though the script still runs.
- Supabase: only a sentence in `README.md` and a note in `handoff.md` (old keys in the PC's
  `frontend/.env.local`, untracked). Nothing in code.
- `sqlite3` connections are never closed explicitly (`with get_db()` only commits); CPython's
  refcounting closes them at function exit, so no leak was observed.
- Stale plan item: `next-steps.md` still lists the 21:00–midnight failure of `test_fixed_income_interest`;
  `services/proceeds_cash.py:43-46` already converts `created_at` to the local day (*plausible*: not
  re-run at that hour).
- No eslint config (already in `next-steps.md`); no ruff config, so the 406 depends on ruff's defaults
  of the day.

## 7. Checked and found sound

- JWT: fixed HS256, constant-time signature compare, expiry enforced, user re-read on every request;
  the secret is generated to a 0600 file when the environment has an example value.
- Uploads: size refused from the header and again after the read, type sniffed from bytes, generated
  file name, parent and attachment ids both checked against `user_id`, file written before the row and
  removed after the commit, orphans pruned at boot.
- Logs: no payload, token, description or counterparty is logged; Pluggy errors are truncated to 300
  characters.
- Idempotency of creations (`client_id`) and of materialized rows (`source_type` + `source_id`): unique
  indexes exist and the routes turn the `IntegrityError` into "return the first result".
- The pull fetches everything from Pluggy **before** opening its write transaction (the exception is B1).
- No sum over `transactions` includes a `TRANSFER` as income or expense; `signed_amount_sql()` is a ±1
  factor and is used as such in all three call sites.

## 8. Questions for the owner (not findings)

1. **B2**: should the plan's "spent" follow Início (ignore a despesa typed in a Corretora account), or
   stay as it is? Either way the three copies can become one function; the question is only which
   answer it returns.
2. The four routes no current client calls, and the list `POST /api/cc-expenses`: may they go, or can
   an installed older APK still call them?
3. The WebView assets under `frontend/android/app/src/main/assets/`: safe to delete from the APK, or
   is the old launcher/installer path still relying on them?
4. A2's fix means a write route may answer 409 "já paga" to the slower of two simultaneous payments.
   That is a behaviour change at the HTTP edge (today: 201 twice). Acceptable?
5. C3: is a login attempt limit wanted, given the two proxies on :8443 and a tailnet-only 443?

## Appendix A — probes (kept here so Phase 2 can turn them into tests)

All three use the suite's own `conftest.py` and `tests/finance_world.py` on a temporary database.

- **A2, double payment**: card with one closed invoice of R$ 100; patch `services.invoices.invoice_open_lines`
  and `routes.cards.invoice_open_lines` with a wrapper that, on each thread's second call
  (`settle_invoice`'s own read), waits on a `threading.Barrier(2)`; fire two
  `POST /api/cc-expenses/pay-invoice` from two threads with two test clients. Observed: statuses
  `[201, 201]`, two `CC_INVOICE_PAYMENT` rows of 100.0, account balance 800.0.
- **B1, write lock across a BCB call**: `fx.reset_fetch_throttle()`; patch `services.fx.fetch_bcb_window`
  to sleep 7 s; in a thread, open `db.get_db()`, run any `UPDATE`, then `fx.rate_on(conn, user, "USD")`;
  meanwhile `POST /api/transactions` from the test client. Observed: 500 after 5.0 s
  (`sqlite3.OperationalError: database is locked`).
- **C1**: `PATCH /api/categories/<id>` with `{"name": "X", "currency": "BRL"}` → 500, `NameError` at
  `routes/accounts.py:440`.
- **B2**: bank EXPENSE 100 + Corretora EXPENSE 40 in the current month, plan with income 5000 / 20 / 80
  → `/api/home` `summary.expense` 100.0; `/api/monthly-plan` `spend.realized` 140.0; `/api/budgets`
  `totals.plan_spent` 140.0.
- **A1**: `python -m pytest` today; the two autopay tests with `time-machine` at 2026-11-06 (pass) and
  2026-11-12 (fail).
- **Performance table**: `scripts/seed_three_years_mock.py` (a scratch copy pointed at a scratch
  database), then each GET through the test client with a `sqlite3` trace callback counting statements.
