# CLAUDE.md

Guidance for Claude Code in this repository.

## Session process

Work happens in sessions that start from a clean context. Start by reading:

1. `docs/handoff.md` — the last session only: what was done, left undone, recommended next.
2. `docs/next-steps.md` — the prioritized plan (open work only).
3. `docs/done-tasks.md` — finished work; read when you need to know whether something exists.

`session-scout` (`.claude/agents/`) can read these for you on a cold start; skip it when the prompt
already says what to do. If `subagent_type` is "not found", use `general-purpose` with "Read
.claude/agents/session-scout.md and follow it".

End every session by: removing finished tasks from `next-steps.md` and recording them in
`done-tasks.md` (what a task left undone stays in the plan, rewritten, no `[x]`); replacing the
entry in `docs/handoff.md` (done, **not done and why**, next, non-obvious lessons — be explicit
about partial work); committing.

## What this is

A single-user personal finance manager: income and expenses, credit cards with installments and
invoice settlement, and an investments module (weighted average cost, realized results, monthly
tax apuração, proventos, quotes). The goal is a tool the owner uses daily — prefer what makes
daily use better over prettier architecture.

**Stack:** React 18 + Vite + Tailwind (browser) · Kotlin + Compose (the APK, no WebView) ·
Flask 3 · SQLite with versioned migrations · hand-rolled HS256 JWT ·
yfinance/brapi/BCB/Tesouro/StatusInvest for market data.

## Running it

```powershell
.\start.ps1 -Tests             # backend test suite
.\start.ps1 -Local             # dev: backend :5000 + frontend :5173
.\start.ps1 -Local -Built      # Flask serves the built frontend (one origin)
```

The home server is the only real backend; `backend\finance.db` on the PC is a dev copy, so
`start.ps1` refuses to start without `-Local`. Production is the Docker image
`ghcr.io/guneves/financas-app`, deployed by `.github/workflows/deploy.yml` on every push to `main`
(tests → GHCR → Tailscale SSH → `docker compose pull/up`); data lives in the `financas_data`
volume. `DEPLOY.md` has setup, manual deploy, import and rollback. **Off the VPN**, Funnel publishes
only :8443, to Caddy on `127.0.0.1:8102` (`compose.yaml`): browsers pass oauth2-proxy (Google, one
email), the APK a device key (`X-Device-Key`, `outbox/DeviceKey.java`); the app's JWT still applies
behind both, and a proxy 401 (`X-Proxy-Auth: required`) never clears it. 443 stays tailnet-only,
straight to the app. No CORS: dev is one origin through Vite's `/api` proxy. README "Remote access".

## Tests

```powershell
cd backend; ..\.venv\Scripts\python.exe -m pytest     # ~2700 tests in backend/tests/
cd frontend; npm test                                 # node --test over src/**/*.test.js
```

Test files are named for what they cover (`test_invoice_month.py`, `test_average_cost.py`,
`test_route_map.py` for every route and its `@token_required`, …). They run on a throwaway SQLite
built by the real migrations — **`backend/finance.db` is never touched.**

- `conftest.py` sets `DATABASE_PATH` and friends in `os.environ` when it is imported, *before* any
  test imports `db` or `app` (the `app_module` fixture then drops
  `app` and `config` from `sys.modules`), because `config.py` reads the environment once and
  `app.py` runs `init_db()` at import. Different config goes there, not in a test.
- A test never imports `db`, `routes.*` or `services.*` at the top; use a fixture or
  `importlib.import_module` inside the test. Pure modules (`brapi_client`, `statement_import`,
  `export_csv`, `market_catalog`, `irpf_text`) are fine at the top.
- `conftest.py` blanks `BRAPI_TOKEN`, `PLUGGY_CLIENT_ID/SECRET`, `TESOURO_PRICES_URL/FILE`,
  `HISTORY_CACHE_FILE`, sets `QUOTE_AUTO_REFRESH_SECONDS=0`, `OPEN_FINANCE_SYNC_SECONDS=0`,
  `AUTO_RECORD_DEFAULT=0` (inbox tests; `test_auto_record.py` turns it on per user),
  `MANUAL_ONLY_OFF_PLUGGY=0` (the default too; `test_pluggy_owner_rules.py` turns the brake on per test) and
  `ALLOW_SIGNUP=1`. Open Finance tests use `open_finance.set_client(FakePluggy())`
  (`tests/open_finance_world.py`); `pluggy_client` tests patch `pluggy_client.urlopen`. StatusInvest is patched in
  `test_proceeds_sync.py` (`statusinvest_client.get_proceed_events`, plus `clear_cache()`); Tesouro
  prices via `tesouro_client.set_prices(...)` (and `None` after).
- **Patch where the name is read, not where it is defined** — a wrong target silently does nothing:
  `db` (backup settings), `routes.attachments` (upload limits), `services.invoices` *and*
  `routes.cards` (`local_today`), `services.goals` (goals), `services.monthly_plan` *and*
  `services.goals` (plan), `services.prices` (`download_close_prices`, `download_daily_history`;
  clear `_daily_history_cache`), `services.fixed_income` (`fetch_bcb_series`; clear
  `_index_history_cache`), `services.fx` (`fetch_bcb_window`; `reset_fetch_throttle()`),
  `services.benchmarks` (`download_monthly_history`; `reset_fetch_throttle()`), `brapi_client`
  (`get_history`/`get_sectors`/`get_listing`/`is_configured`; `services.market_listing.reset_cache()`),
  `routes.investments` (`refresh_market_prices`, `get_daily_history`), and *both* `services.prices`
  and `routes.investments` for `yf`. History refreshes run behind: wait with
  `wait_history_refreshes()`.
- Fixtures: `client`, `user`, `other_user`, `auth`, `app_module`, `db_module`, `invoices_module`,
  `prices_module`, `fixed_income_module`, `realized_results_module`, `portfolio_module`,
  `daily_history_from_months`; shared setup in `tests/finance_world.py`.
- **Add tests for every financial rule you touch.** A frontend rule tested with node imports nothing
  from the browser, React or `lib/api.js`; a rule moved to the server takes its node cases to pytest.

## Layout

```
backend/
  app.py            Flask app, blueprint list, boot      config.py   env, read once at import
  db.py             connection, migrations, backups      validators.py / money.py / dates.py
  auth.py           JWT, token_required                  responses.py  CSV/.xlsx downloads
  applog.py         JSON logging (never print())         integrations.py  provider health
  history_store.py  disk copy of chart history caches    gov_http.py   GET to BCB/Tesouro
  statement_import.py, export_csv.py, export_xlsx.py, irpf_text.py, statusinvest_client.py,
  tesouro_client.py, brapi_client.py, market_catalog.py   (pure or client modules)
  services/         domain rules (accounts, invoices, card_invoices, home, attention, budgets,
                    monthly_plan, recurring, inbox, inbox_decisions, import_rules, sharing,
                    attachments, investments, prices, fixed_income, fx, treasury, portfolio,
                    realized_results, variable_income_tax, tax_report, proceeds, proceeds_sync,
                    proceeds_cash, returns, benchmarks, allocation, goals, sectors, ...)
  routes/           one blueprint per area; frontend.py serves frontend/dist at /
  tests/            pytest
database/migrations/  versioned, applied on boot
frontend/src/
  pages/            Início (Dashboard), lancamentos/, Orcamento, Recorrentes, Metas,
                    investimentos/, Proventos, Ajustes, Importar — map in lib/navigation.js
  components/       Layout, NewEntrySheet, CashLinkField, ui.jsx (the UI kit), charts.jsx
  lib/              api.js, queries.js (TanStack Query), format.js, outbox.js + outboxRules.js,
                    transactions.js, monthlyPlan.js, ... (pure rules have *.test.js)
frontend/android/   the Android app, all native Kotlin/Compose (see mobile-docs/native/ before touching it)
docs/               next-steps.md, done-tasks.md, handoff.md
```

## Conventions

### Money, dates, identity
- **Money** rounds only through `rounded_money()` (`money.py`, ROUND_HALF_UP via `Decimal`); never
  a bare `round()`. Request amounts go through `parse_money()`: rounded, ≥ R$ 0,01 (unless
  `allow_zero`), ≤ `MAX_MONEY`.
- **Dates and months** are 1900–2199 (`MIN_YEAR`/`MAX_YEAR`, `require_date()`/`normalize_month()`)
  and stored zero-padded ("2026-1-5" → "2026-01-05"); filters compare them as text. Investment
  metadata dates go through `validate_movement_metadata()`.
- **`user_id` on every table and every query.** Tests assert it.
- **Migrations are append-only**: a new numbered file, never edit an applied one. (027/029 are
  empty placeholders from the Pluggy removal; keep their numbers.)
- **Destructive endpoints take a confirmation guard** (asset deletes need the matching
  `asset_class`; deletes that would leave a sale unbacked are refused).
- Comments and identifiers mix Portuguese and English — match the file. User-facing text is
  Portuguese; `docs/` is English.

### Accounts, categories, transfers
- **Transfers are one row** (`account_id` → `transfer_account_id`); anything summing
  `transactions` skips `type = 'TRANSFER'`.
- **Categories: the id decides** (035). Tables keep both `category` (name) and `category_id`
  (`transactions`, `cc_expenses`, `recurring_transactions`, `import_rules`, `inbox_items`); screens
  send `category_id`. A bare name resolves root first, then the oldest subcategory
  (`category_id_for_name()`); an edit sending the row's own name keeps its id. Renaming rewrites
  all five tables (`rename_category_rows()`).
- **Accounts, categories and cards are archived, never deleted** (`archived_at`). A card
  (037) with an `OPEN` item refuses delete (409), one with history is archived, only an empty one is
  deleted. An archived card takes no purchase, refund, autopay or approval (`require_active_card()`).
- **One default account, active and never the Corretora** (`ensure_default_account()`).
- **An edit keeps the row's own account even when archived** (`keep_or_require_account()`); a new
  choice must be active; `account_id: ""` is refused. A recurrence whose account is archived lands
  in `/run`'s `blocked`.
- **Signup is closed once a user exists** (`ALLOW_SIGNUP=1` opens it). A missing/example
  `JWT_SECRET` is replaced by a random one in `JWT_SECRET_FILE`.
- **Consolidated balance = sum of reais account balances** (archived included, Corretora and Conta global out), from
  `consolidated_balance` of `GET /api/home`; never sum `transactions` (it drops `initial_balance`).

### Idempotency (materialized rows)
- Rows written on demand carry `source_type` + `source_id` under the unique index
  `idx_transactions_user_source`, so a repeat is a no-op: recurrences
  (`'<recurrence>:<AAAA-MM-DD>'`), autopay (`CC_AUTOPAY`, `'<card>:<AAAA-MM>'`), statement import
  (row hash or `'ofx:<conta>:<FITID>'`, occurrence suffix for duplicates in one file), investment
  cash, paid proventos. Keep that shape for anything new.
- **"+ Novo" creations are idempotent by `client_id`** (024): `POST /api/transactions`,
  `/api/transfers`, `/api/cc-expenses/purchases`. A repeat returns the first result (200) — the
  lookup runs before validation. The row stays "Manual" and editable.
- **The outbox holds creations only, and only when the request never reached the app**
  (`ApiNetworkError`, or the auth proxy refused it: `ApiProxyAuthError`). A proxy 401 never clears
  the JWT; the page reloads into the Google login at most once per 30 s (`lib/proxySession.js`). A creation times out at 6 s and is queued (offline: queued without trying);
  reads 45 s; edits and deletes have no timeout and are never queued. Rules in `lib/outboxRules.js`
  (tested): a pending transfer leaves the balance alone, a pending card purchase touches no account,
  a balance counting pending items is labelled an estimate.

### Cards and invoices
- **A card purchase is its `client_id`** (035): all installments share it; old rows have
  `legacy:<id>`. Receipts, sharing, A receber and installments go through `same_purchase_sql()` /
  `cc_purchase_expense_ids()`; screens group by `cardPurchaseKey()`.
- **The invoice-month rule is backend-only** (`compute_invoice_start()`, closing day 29–31 clamped,
  `test_invoice_month.py`); don't add a client copy.
- **An invoice is paid only after it closes** (`invoice_closing_date()`, `ensure_invoice_closed()`)
  and **only by `POST /api/cc-expenses/pay-invoice`**. Reopening is "Desfazer pagamento"
  (`DELETE /api/cc-expenses/payments/<id>`: reopens what it paid, writes `cc_invoice_manual` so
  autopay won't debit it again; refused while the payment has a receipt).
- **A paid invoice is history** (037): paid items are never deleted; a new purchase or refund never
  lands in a paid invoice (`first_unpaid_invoice()`); `settle_invoice()` stamps `paid_by`.
- **The next invoice is per card, by due date** (`services/card_invoices.py`, `open_invoices()`):
  `next` feeds Início and the bell, `nearest` (oldest overdue with total > 0, else first `next`) is
  what Cartões pays. Overdue = after the due day.
- **Card functions** (041): `debit_account_id` makes a débito purchase a plain EXPENSE in that
  account; `credit_enabled = 0` is debit-only (refused on credit paths, no autopay). The debit
  account is never a Corretora.
- **Débito automático** (`autopay_account_id`) is materialized on read by `apply_due_autopay()` on
  the due day, only for invoices due on/after `autopay_start_date`, and **only when the account's
  balance at the end of the due day** (`account_balance_until()`, rows dated ≤ it, earlier debits of
  the same pass included) covers the invoice (owner 2026-11-05); without it the invoice stays open
  for Pagar. **A Pluggy-mapped card is debited too** (owner 2026-11-05, reversing 2026-10-30), only up
  to `AUTOPAY_CONNECTED_DAYS` (5) after the due day and never with a loose bank invoice payment
  (`pluggy:` source id) on that account within ±5 days; the bank's payment later links to the
  autopay row (`invoice_payment_link()` same cents, `_kept_payment()` same day, same cents ≤ 5 days,
  or an autopay row ≤ 5 days within `AUTOPAY_NEAR_PERCENT`, 5%) and takes the bank's amount; farther amounts on
  another day stay two payments.
- **A refund is a credit row** (033, `kind = 'REFUND'`, stored positive, 1/1, never shared); sum card
  rows through `signed_amount()` / `signed_amount_sql()` / `cardSignedAmount()`. An invoice in
  credit is refused (409) and rides along with the next payment.

### Banking views, plan and budgets
- **Início is banking only, in reais**: consolidated balance and accounts, never the portfolio.
  Aporte/resgate/provento are kept apart from despesa/receita (`isInvestmentOutflow()` /
  `isInvestmentInflow()`). "Resumo do mês" reads `summary` of `GET /api/home`.
- **Investimento is not a category** (039): a row is aporte/resgate/provento by origin only
  (`INVESTMENT_SOURCE_TYPES`, or a bank ↔ Corretora transfer). Don't give a category name meaning.
- **Whose expense it is** (032, `services/sharing.py`, `lib/sharing.js`): owner, `SPLIT` or
  `OTHERS`. Balances never change; budget, plan and Início count only the owner's part
  (`own_amount_sql()` / `ownAmount()`). A receber lists the others' part until `share_settled_at`.
- **The app is reais-only on screen**: no currency choice, no foreign symbol; an account balance
  shows `accountBalanceBrl()` or "sem câmbio hoje". Exceptions: the IR tab's "Aplicações no
  exterior" when the year has a foreign result, and **the Conta global** (below).
- **Conta global** (047, owner 2026-10-27; `services/global_account.py`, `lib/globalAccount.js`,
  `rules/GlobalAccount.kt`): the owner's Wise USD account. The **one** screen in another currency is
  `/inicio/conta-global`, opened from "Conta global" under the accounts on Início and from Ajustes ›
  Contas: balance and statement in US$ (`formatForeignCurrency()`), a "≈ R$ …" from today's PTAX
  (`balance_brl`) or "sem câmbio hoje". The only currency choice is the "Conta global (US$)" type
  of Ajustes › Nova conta (CHECKING + `currency: USD`). **It is never in "Saldo em contas"** (owner
  2026-10-28 and 2026-10-30, list and total: `consolidated_balance()` skips non-BRL accounts, so
  Extrato/Cartões projections too): on Início it is only the "Conta global" entry, and it pays no
  invoice. A `NET_WORTH` goal still counts it converted. A foreign
  account is never the default nor the Corretora. Its own despesas/receitas stay out of every reais
  total (Resumo do mês, plan, budget, the Extrato without `account_id`, the review queue/count):
  they are listed and reviewed on its screen. "+ Novo" doesn't offer it.
- **A transfer between currencies is one row with two amounts** (047): `amount` leaves
  `account_id` in its currency, `transfer_amount` lands in `transfer_account_id` (NULL = same
  currency). `POST /api/transfers` and the PATCH require it across currencies and refuse it
  otherwise (`transfer_amount_for()`); a balance counts a cross-currency transfer without it as 0
  (never R$ as US$). A transfer is never income nor expense. A reais account that only received
  transfers can become USD (`PATCH /api/accounts/<id> {currency}`, `convert_to_foreign()`); its
  transfers wait for Pluggy to fill `transfer_amount`.
- **Pluggy and the Conta global**: a USD Pluggy account maps only to a USD account (and BRL to BRL);
  its rows stay in US$ end to end (`normalize_transaction(account_currency=)`, item, lançamento,
  snapshot, Conferência). A BRL Pix whose counterparty/description names the global account
  ("WISE BRASIL CORRETORA DE CAMBIO") is an own transfer that waits for the dollar side; the Wise
  credit pairs with it by day (±1) and counterparty, never by cents; two on one day go to the pair
  whose rate is closest to the PTAX (`place()` step 2, `_place_cross_currency()`). A Wise credit
  is recorded at once (a US$ receita); untouched, the BRL side later turns it into the transfer. A credit matching a transfer already in the app fills its `transfer_amount`.
- **The monthly plan starts from income** (025, 038, `services/monthly_plan.py`): `PUT
  /api/monthly-plan` writes `income_amount` (> 0) and `invest_percent`/`spend_percent` (sum ≤ 100).
  Every R$ is computed on read via `percent_of()`; percentages are TEXT read as `Decimal`, never
  float. A month without a row inherits the latest earlier plan and its categories. **Saldo do
  plano** (`plan_balance`) = Gastar R$ − spent; "Disponível por dia" = it ÷ days left, server-side,
  shown in Orçamento. Invested = `month_investment_flow()` (same rule as `investment_flow_sql()`).
  Old plans without income are `needs_income`.
- **The Inter line** (`MONTH_SUMMARY`, owner 2026-10-31): the month's net moved into Inter (no Pluggy), one row, source
  id `inter:<AAAA-MM>`. Not spending: it moves the balance and the Evolução, and stays out of Fluxo, Resumo, Orçamento,
  plan, Ritmo and Extrato totals. A rebuild keeps it.
- **A repasse** (owner 2026-10-31): money from someone else to pay something of theirs. Revisar's "É repasse"
  (`POST /api/review` with `repasse: true`, `person`) makes an INCOME `share_mode = 'OTHERS'`, settled: in the balance,
  out of income. Marking a share paid in A receber asks which income paid it (053, owner 2026-11-02, `share_paid_by`,
  `link_income()`): that income carries the share as the others' (`SPLIT`/`OTHERS`), in its own month. Without one, it cuts
  the income of the month of the mark (`apply_settled_others()`); a repasse **of the same person** (or unnamed) covers it
  first, so nothing cuts twice, and `net` doesn't move. Web `PaidBySheet`, APK `PaidBySheet`; a paid item can change income.
- **The invoice tile on Início** (2026-10-31): "Fatura de <mês>", a dropdown per invoice, closed by default, and
  Pagar. No "Próximas faturas" panel, no open-items list. The Ritmo counts reais accounts only.
- **A budget is a % of Gastar** (038, `services/budgets.py`): `planned_percent` only, categories
  sum ≤ 100% (400; an over-100 month may lower, not raise), "Sem categoria" is the rest. Categories
  come from the latest month ≤ it with a plan (`category_source_month()`); writes in an inherited
  month go through `materialize_month()`. Rollover is computed on read. `DELETE` is a real delete.
  Spent: card purchases in full in the purchase month, refunds subtract, invoice payments never.
- Orçamento's percentages are `PercentSlider`s bounded by `percentRoom()`/`clampPercent()`
  (`lib/monthlyPlan.js`). Plan flags and Início's attention cards are dismissed per device
  (localStorage, keys `planFlagKey()` / the item `key`).
- **"Precisa de atenção"** is `GET /api/attention` (`services/attention.py`), shown on Início and
  in the bell; the server sends numbers and keys, the text lives in `components/Attention.jsx`.
- **A recurrence is a template**: `POST /api/recurring/run` writes real rows; deleting keeps them.
  Pauses skip only their window (`pause_gaps`, `recurring_occurrence_dates()`/`skip_pause_gaps()`).
- **Rules touch the past only on confirmation**: `/api/import-rules/apply/preview` never writes;
  `apply` rewrites only the sent ids, re-checking the rule. Transfers, investment cash, proventos
  and invoice payments are out of reach.

### Notifications are fast, Pluggy is the record (owner 2026-11-04)
**A phone notice records at once; Pluggy confirms it later and is the record.** The Flash, which Pluggy
doesn't cover, comes only from notices (and typing).
- **Everything can be typed** (owner 2026-11-05, reversing 2026-10-31): "+ Novo" (web and APK) offers every reais
  account and every card, Pluggy-mapped or not; the engine links a typed look-alike to what the bank brings later
  (`free_candidates()`, the investments' typed twin), never a second row. The old rule survives as a brake,
  `MANUAL_ONLY_OFF_PLUGGY` (env, **default off**, `services/manual_entries.py`): on, a mapped account or card refuses
  a typed row, purchase, refund and statement import (400), a transfer needs one side off Pluggy, and the Pluggy-fed
  Corretora refuses typed operations (below). `pluggy` on `GET /api/accounts` and `/api/credit-cards` stays.
- **There is no Aprovar screen** (owner 2026-10-31): page and route are gone, `/aprovar` and `/lancamentos/aprovar`
  redirect to the Extrato. Waiting items resolve there: `WaitingItems` (web), `ReviewSection` (APK), shown only
  while one exists. Ajustes has no Aprovar section and no "Gravar sozinho" switch; the settings stay on the API
  as the brake. The owner's only job: categories and doubts, in Revisar.
- **Who speaks** (`NOTIFICATION_POLICY` + `notification_wanted(detection)` in `services/inbox.py`, pure; the
  APK's `NotifyRules.APPS`, manifest `<queries>` and `NotifyParsers.parse()` repeat it, but an old APK is safe
  because the server decides):

  | App | Accepted |
  |-----|----------|
  | Flash app; Samsung Wallet with the Flash card (`is_flash_detection()`) | outgoing only, no `CREDIT_PURCHASE`; `DECLINED` |
  | `com.itau`, `br.com.bb.android`, `com.btg.pactual.banking` | every kind of `KIND_SHAPES`, plus `DECLINED` |
  | `com.btg.pactual.digital.mobile` (BTG Investimentos) | only `MOVEMENT_KINDS` (Pix/TED in and out) |
  | Samsung Wallet with any other card; any other app | nothing |

  Investment words (`INVESTMENT_TEXT`: aplicação, resgate, CDB, LCI, LCA, tesouro direto, fundo de
  investimento, ordem de compra/venda, provento, dividendo, JCP; word boundaries over `normalized()`) block a
  Pix/TED (merchant and counterparty) and everything from the brokerage app, **never** a card purchase's
  merchant ("FUNDO DE QUINTAL BAR" is a bar). The APK also drops an invoice payment ("fatura" + pago/paga/
  pagamento/quitada, before `kindOf()`) and sends `international: true` for internacional/exterior/US$/USD/
  EUR/€/£. Anything else answers `ignored` and leaves no `notify_detections` row.
- **The brake: "Avisos dos bancos"** (`bank_notifications` in `user_settings`, `GET/PATCH /api/inbox/settings`,
  booleans only; default `BANK_NOTIFICATIONS_DEFAULT`, env, on). Off, only the Flash passes, and a bank notice
  is `ignored` with no trace, so switching it back on records nothing old. Web: Ajustes › Avisos do celular;
  APK: Ajustes › Notificações do celular.
- A Samsung Flash purchase records at once; a later decline removes the untouched row. Flash receitas are typed
  by the owner.
- **Everything updates by itself**: one tick covers accounts, cards, Wise, BTG and the Conferência; a
  failing item doesn't stop the others; first tick 60 s after boot. `sync_hours`: `off` = owner's choice,
  a stored `0` means 6 h. GET only and the 6 h floor stay. **Between pulls, every 5 min** (owner 2026-11-01,
  `sync_fresh_items()`): one `GET /items/{id}` per connection, and a connection whose `lastUpdatedAt` moved past
  our `pluggy_updated_at` is pulled at once, so a movement enters the moment Pluggy has it.
- **A bank invoice payment is recorded from Pluggy** (`services/open_finance_invoices.py`): with no
  app row it settles that invoice through the settlement path, idempotent by Pluggy id. Recurrences
  never write on a Pluggy-mapped card or account; autopay does (Cards above), and the bank's payment joins it.
- **Categories**: owner's import rule → merchant table → CNAE → Pluggy's category → default
  (`open_finance_categories.py`); merchant data from 050.
- **The pull writes what Pluggy brings** (owner 2026-10-30): every 6 h, the 5-minute freshness check, or the
  "Atualizar" button; what a pull brings is recorded in that pull. A read (`record_due()`) records only
  notifications.
- **The app waits for the bank before flagging** (owner 2026-10-30, `awaiting_bank()` /
  `bank_refreshed_since()` in `open_finance_auto.py`): a pending Pluggy item stays out of `waiting` (`GET
  /api/review`) until every active connection has `pluggy_updated_at` after the item and the app read it;
  `BANK_WAIT_MAX_DAYS` (3) stops a dead connection hiding it. `GET /api/inbox` marks `awaiting_bank`. The
  Conferência does the same for app rows (`awaiting_bank` instead of `app_only`, `newer_than_bank()`).
- **Income is never a transfer** (`is_income_row()`): an incoming row with Pluggy category `01...` or salary
  text. A one-sided transfer "não é entre minhas contas" takes the side the bank saw
  (`settle_one_side()`): only a destination is an INCOME there, whatever the screen sent.
- **A despesa/receita can become a transfer** (`PATCH /api/transactions/<id>` with `type: TRANSFER`, `account_id`
  and `transfer_account_id`, one of them the row's own): loses category and share, leaves review.
  `absorb_other_side()` drops the other side Pluggy recorded (OPEN_FINANCE, no receipt, no share, same cents,
  ±3 days) or closes its waiting item; a later row links through `recorded_transfer_for_row()`. Web and APK
  offer reais accounts only. The way back (transfer → despesa) is refused.
- **The broker's balance is its statement** (owner 2026-10-30, `services/broker_statement.py`): Pluggy's
  BTG Investimentos balance = every line from zero, minus `CONTA REMUNERADA` (proved to the cent). So a
  line is a `sweep` (COVERED), the trade's `VISTA BRUTO` (COVERED: the operations' cash, at settlement) or
  a `BROKER_STATEMENT` row (fee, IR, fixed income, cashback; in `INVESTMENT_SOURCE_TYPES`, never income or
  expense). A proceed the app has takes the bank's value and day, `sync_locked`; a typed operation of the
  same amount is linked. Fixed-income ETFs (`FIXED_INCOME_ETFS`, AUPO11 included) settle D+1. The
  Conferência compares the Corretora on settled cash and skips trade cash (the bank side is COVERED).
- **A card mirrors the bank** (owner 2026-10-30, `mirror_cards()`): the open invoice comes `PENDING` from
  Pluggy, so a card always brings pending rows (a bank account too since 2026-11-01, `include_pending` on by
  default; watch a pending salary beside the posted one, the Itaú/BTG portability). `bill_month` (`billForecastDate`, 051) decides the invoice, over `compute_invoice_start()`;
  an open purchase has one app line per bank line: an installment the bank doesn't list leaves, a new one
  enters. `closing_day` is the bank's (`GET /bills`). BB's balance rounds up (`rounded_up`).
- **Anticipated installments** (owner 2026-10-31, `_anticipations()`): the bank discounts each one ("Desconto Na
  Parcela 3 De 6 Rota Transportes") and charges it in the discount's invoice, but Pluggy leaves that charge off the
  bill's lines and keeps later ones `PENDING` in future invoices. The credit decides: installment N goes to its
  invoice with its status (a missing one is created), never back; the Conferência adds the unlisted ones. Proved on
  BTG's October bill to the cent (lines + 0,32 carried + 237,16).
- **A posted row's invoice is its `billId`** (`card_rows_with_bill()`, `GET /bills`), over `billForecastDate`.
- **A payment the app has is linked, never doubled** (`_kept_payment()` in `record_bank_payments()`): no target,
  same account, same day (any amount) or same cents within 5 days; it takes the bank's amount. Without it, 11
  autopay rows with other amounts were recorded twice on 2026-10-31.
- **A bank's own fund is an aporte/resgate** (`BANK_INVESTMENT`, in `INVESTMENT_SOURCE_TYPES`,
  `mark_bank_investments()`): Pluggy `0302` on a bank account (RF High, RF LP Selic, Tesouro Reserva) stays in the
  balance, never expense nor income, no review. It runs after each pull; Rende Fácil stays out (below).
- **A notified row Pluggy never lists: the bank's balance decides** (Phase 5, owner 2026-11-04,
  `services/open_finance_orphans.py`): `sweep()` runs last in each pull (after `record_bank_payments()`,
  `mark_bank_investments()` and the `last_sync_at` stamp), only with auto-record on, only on **mapped BANK
  accounts in reais** (never the Corretora, never the Conta global). **Cards are list-only** (their balance
  mixes the used limit, pending holds and BB's rounding). An orphan: EXPENSE/INCOME recorded by a notification
  item, no live Pluggy claim, date ≤ today − `OPEN_FINANCE_LATE_POST_DAYS`, and `bank_refreshed_since(date + 5
  days)`. The difference is the Conferência's own (`open_finance_check.balance_difference()`, bank − app in
  cents, the one formula the overview uses; the app side is the balance **up to today**,
  `account_balance_until()`, so a future-dated typed row is no difference): removing an expense of X fixes +X, an income −X; the oldest orphan
  whose fix equals it leaves, or all when their sum does; no subset search, no tolerance. Removal is like
  `undo_declined()` (item `REMOVED`, reason `orphan`), counted as `removed_orphans` in the pull result and log.
  Never removed: a receipt, a share, "Aconteceu", an amount the owner typed (≠ the snapshot's), a transfer;
  review doesn't protect. Difference 0 → the row stays and the Conferência lists it under `balance_confirmed`
  ("Confirmado pelo saldo", web and APK), including an international purchase "em processamento".
- **The Conferência's buttons** (`services/open_finance_resolve.py`, web): "Lançar" records a bank-only row
  (a one-sided transfer takes the side the bank saw), "Aconteceu" keeps an app-only row
  (`open_finance_confirmed`, 051; listed in `confirmed`, "Desfazer"). A difference that is only `awaiting`
  reads "Confere". A category 0301 row with a sale text (`TES RESERV VEND`) is real money, a
  `BROKER_STATEMENT` row. A deposit in US$ isn't listed: Wise reports it in the unused BRL pocket.
- **A provisional buy** (`fill_position_gaps()`, rebuild only): a position ahead of the operations (today's
  trade) gets `metadata.provisional`, the position's price, no cash; the real operation replaces it.
- **Rebuild** (`scripts/rebuild_from_pluggy.py`, `services/open_finance_rebuild.py`): dry-run by
  default; `--apply` needs the app stopped and runs in a one-off container (DEPLOY.md). Flash's rows
  are never wiped; investments only as told.
The sections below describe the engine. Tests of the engine open the gate with the fixture
`any_bank_notifications` (`notification_wanted` → `lambda detection: True`); the gate itself is tested in
`test_notification_policy.py`, which never uses it.

### Auto-record → reconcile → review (045, owner 2026-10-27)
The paradigm: **notifications record, Pluggy reconciles (and feeds Investimentos), the owner only
confirms and categorizes.** The inbox engine below (`inbox_items`, pairing, hints) still runs, but
as plumbing: an item lives for milliseconds, then `approve_item()` records it.
- **A notification is a lançamento at once** (`services/auto_record.py`, called after
  `POST /api/inbox/detections` and by `record_due()` on `GET /api/transactions`, `/api/home`,
  `/api/review`): Flash and every bank. What the item doesn't know is guessed
  (`services/inbox_defaults.py`: no credit/debit → the guessed card else debit; no card → the
  issuer's first card else the first credit card; no account → the issuer's account else the
  default one, never the Corretora) and nothing is remembered (`remember: False`). A look-alike the
  owner typed is linked (`free_candidates()`), never duplicated, and needs no review.
- **Nothing waits** (owner 2026-11-04): an **own transfer with one side** is
  recorded as the despesa/receita of the side the notification saw (`auto_record.one_side_now()`),
  and the other side, from either channel, turns that same row into the transfer
  (`inbox.absorb_recorded_side()`). Only a one-sided transfer touching **the Corretora** (an
  income/expense there would distort Investimentos) or the Conta global still waits. A notice **in
  another currency** on a reais card/account is recorded at the day's PTAX
  (`open_finance_auto.in_reais_now()`; the detection keeps its currency, so the near match treats it
  as international); without a PTAX yet it waits. A Samsung-only purchase still waits
  `NOTIFY_WINDOW_MS` for the bank's notice. **There is no Aprovar screen; waiting items resolve in Revisar**
  (the APK's Extrato lists them under "Não gravou sozinho": the other account or the amount in reais
  → `POST /api/inbox/<id>/approve` with `remember: false`, "não é entre minhas contas" → despesa/
  receita, or Descartar). The inbox API stays for those and for the brake.
- **The switches** default to `AUTO_RECORD_DEFAULT` (config, on): `auto_record` in
  `GET/PATCH /api/inbox/settings` (notifications) and in `/api/open-finance/settings` (Pluggy).
  Off is the emergency brake, API only: items wait in the Extrato's list. `conftest.py` sets `AUTO_RECORD_DEFAULT=0` so the
  inbox tests see pending items; `test_auto_record.py` turns them on per user.
- **Review** (`services/review.py`, `GET/POST /api/review`): an auto-recorded row has
  `needs_review = 1` (`transactions` and every installment of a card purchase, by `client_id`);
  typed and screen-generated rows are 0. Reviewing = "é meu" + optional `category_id` (a transfer
  keeps its category); a batch is all or nothing (404 on an unknown id). The Extrato shows the
  `ReviewPanel` (one tap per row, "Confirmar todos"), an "A revisar" badge, `?review=1`; the header
  pill and the Extrato tab count it (`review_count` in `GET /api/home`).
- **Only guesses are reviewed** (Phase 4, `open_finance_inbox.settle_review()`): a row leaves
  review by itself, in the same pass that records or confirms it, when Pluggy confirms it
  (`reconcile_recorded()`'s untouched path, which the near match goes through, and
  `open_finance_auto.record_item()`) and `category_decision()` of the Pluggy row comes from
  `CONFIDENT_CATEGORY_SOURCES` (rule, merchant, CNAE): that category is set while untouched, `needs_review = 0`,
  and the snapshots are refreshed in the same transaction (`review.clear()` + `refresh_snapshots()`). A
  transfer leaves review when both sides are observed and one is Pluggy's (`inbox.settle_transfer_review()`:
  `finish_absorb()`, a side joining a recorded transfer, Pluggy recording both). These stay: Pluggy's tree or
  the default category, a card refund, the Flash (no Pluggy), the Conta global (its own screen), a row the
  owner changed.
- **"Untouched" is the snapshot, never the review** (Phase 4): `notification_untouched()`,
  `recorded_snapshot.untouched()` and the absorb helper compare the snapshot only. "É meu" without a change
  is not a touch (the bank's date, amount, vanish, other side and near match still apply); a new category,
  amount, date, account, share or receipt is. Whenever the server changes a recorded row it refreshes the
  item's and the Pluggy rows' snapshots (`refresh_snapshots()`, also in `apply_change()`). So a Flash decline
  removes a row the owner only reviewed, and keeps one they recategorised.
- **Twins: "2× igual"** (Phase 4, `services/twins.py`): `twin` on the rows of
  `GET /api/transactions` (paged too), `GET /api/review` and `GET /api/cc-expenses/statement`: another expense
  (EXPENSE or card purchase) on the same account/card, same cents, same `normalized()` description, ≤ 60 min
  apart when both have a time, else the same date; queried for the page's dates ±1 day. A neutral `Badge`
  (web Extrato row and `ReviewPanel`; APK Extrato row and `ReviewSection`, `twin_badge`); no attention card,
  nothing to dismiss, no action.
- **Pluggy reconciles what a notification recorded** (`reconcile_recorded()` in
  `open_finance_inbox.py`): the item keeps `auto_recorded_at` + `recorded_snapshot`. Same date and
  target and still untouched (equals the snapshot) → the Pluggy row becomes
  the source (transaction `source_type = 'OPEN_FINANCE'`, card `client_id = 'pluggy:<id>'`, OF
  snapshot), so later bank changes apply as for a Pluggy-recorded row; another date or account/card
  → the row is deleted and the item re-recorded the bank's way right after the pull; edited (snapshot
  differs) or a transfer → only `MATCHED` (a transfer's guessed side still follows the bank,
  `follow_bank_side()`, below).
- **Card purchases are in the Extrato** (`GET /api/cc-expenses/statement`,
  `services/card_statement.py`): one row per purchase (total, installments, `needs_review`), the
  Extrato's filters (type EXPENSE = purchases, INCOME = refunds, TRANSFER or an account → none),
  merged client-side by `mergeStatement()` (`lib/review.js`; paged: only down to the oldest loaded
  day). They never count in the day total or the filter totals (the invoice payment moves the
  account); a day with only card rows shows no total.

### The inbox engine
- Detections arrive as parsed fields at `POST /api/inbox/detections` and become items; with the
  switches on they are recorded right away (above), and a look-alike of an existing lançamento is
  an item with a candidate.
- **Settles a recurrence's occurrence** (034, `suggest_for_item()`: same type, ±7 days, exact amount
  or within 20% with a shared word/category; INCOME within 20% regardless). Approving writes a
  `recurring_settlements` row; "Não é esta" sets `recurring_off`.
- **Never remembers an ambiguous target** (`ambiguous_target()`: no card final and several active
  accounts/cards whose *bank field* names the bank). "Sempre perguntar" (036) makes every target a
  confirm.
- **Own transfer vs someone else is the counterparty** (031): "it's me" is learned into
  `inbox_hints` (`self:doc:` / `self:name:`); BTG Investimentos transfers are always own. Pairing
  (`same_purchase()`) is one to one, same cents, compatible card, within `NOTIFY_WINDOW_MS`; the
  bank's notification wins over Samsung's.
- **Open Finance (Pluggy) reconciles the connected banks** (043, 044, 045, `services/open_finance.py` +
  `open_finance_inbox.py`): pulled (no webhooks: only the gated :8443 proxy is public) into
  `open_finance_transactions`, unique `pluggy:<id>` per user, feeding `inbox_items` like
  notifications. A Pluggy account goes only where the owner mapped it (a card needs credit; the
  Corretora takes only the broker's investments account, `is_investment_account()`), or is
  "não usar" (`ignored_at`). A notification and a Pluggy row of one movement are **one item in either order**
  (same cents, ≤ 1 day, the mapped target; `notification_item_for_open_finance()` /
  `open_finance_item_for_detection()`), through the item's free **Pluggy slot of that side** (a
  transfer has one per side; a `REMOVED` or `vanished` row occupies none).
  **Claims are per channel** (I2, `inbox.pluggy_claimed()` / `notification_claimed()`):
  `existing_rows(claimed_by="notify"|"pluggy")`, `free_candidates()` (the item's channel:
  Pluggy if it has a Pluggy `SOURCE`) and `_linked_elsewhere()` hide a lançamento only when another
  observation of the **same** channel claims it; a typed row is free for both. A transfer's side is
  a slot per channel too: a late notice of a side Pluggy already brought joins that transfer
  (`approved_transfer_awaiting(channel=)`). Two identical real
  purchases stay two (rows = max(notified, posted)). `identity_invariants.violations()` checks it;
  every test of `test_notify_pluggy_identity.py` ends with `assert_identity()`, and the owner runs
  `scripts/check_identity.py --email X` (read-only) on the server.
  **Succession**: the pull computes `missing_rows()` (the account's live rows in
  the window Pluggy didn't return, `MATCHED`/`PAIRED` included) before `ingest()`; a new id that
  continues one (`successor_for()`: same account and direction, same cents or BB rounding, same
  installment, ≤ 3 days; one to one; a near amount only for a single-installment purchase, same
  merchant, unique each way) takes its place with `hand_over()`: role, item, target, snapshot,
  `source_id`, the card purchase's `client_id`, the item's `client_key`; the old row is `REMOVED`
  with `superseded_by` (054) and never comes back. Only what nobody took over goes through
  `vanish_rows()`; a `MATCHED`/`PAIRED` row without successor gets `conflict = 'vanished'` (the
  Conferência lists it); an empty pull vanishes nothing recorded. So pending → posted under a new
  id keeps the same lançamento, reviewed or not.
  **The guessed side of a recorded transfer follows the bank** (`follow_bank_side()` in
  `reconcile_recorded()`): untouched by the item's snapshot, the side in `guessed` and not `edited`
  takes the account Pluggy shows (never both sides on one account, never the Conta global).
  **Near match**: the same purchase posted with another amount. A pass after the
  pull's exact pairing and before `record_pending()` (`near_match_pass()`), and step 2b for a late
  notification (`near_item_for_detection()`): purchases only (a notification of `PURCHASE_KINDS`
  with a merchant, a Pluggy row without movement, out, 1 installment; never Pix, refund, invoice
  payment, installments, the Corretora or the Conta global), same target, `merchant_agrees()`,
  `near_amount()` within `NEAR_MATCH_FOREIGN_PERCENT` (10, international: the detection's
  `international` flag or currency, or Pluggy's `original_currency`, 055) or
  `NEAR_MATCH_DOMESTIC_PERCENT` (30), the exact date window, except international up to
  `LATE_POSTING_DAYS` after the notice (the Claude R$ 110 "em processamento"), and **unique each
  way**. The Pluggy item is `REMOVED` (`near_match`) and the row joins the notification's;
  **the bank's amount wins** (`follow_bank_amount()`), reviewed or recategorised too, unless the
  owner typed the amount (current ≠ the snapshot's): then only `MATCHED` + `conflict = 'changed'`.
  An untouched row keeps its id and takes the bank's date. With no pair on the day, a bank row also pairs with a
  notification that already became a lançamento up to `OPEN_FINANCE_LATE_POST_DAYS` (5) before it
  (the bank posts late), never a second row. **Banco do Brasil rounds up** (owner, 2026-10-27:
  18,19 reaches Pluggy as 19,00): for a `ROUNDS_UP_ISSUERS` connection a whole-reais amount pairs
  with the one it rounds up from (`rounded_up()`), the notification's cents stay, and the invoice
  payment link accepts it too; installments 2..n are `COVERED`, invoice payments never an
  item, a card credit is a `REFUND` item; a row that vanishes or changes amount before approval
  makes the item `REMOVED` (if no other source). Approval stamps `source_type = 'OPEN_FINANCE'`.
  The card sign is learned per account (`learn_charge_sign()`): the sandbox contradicts the docs.
  **GET only** (owner, 2026-10-27): the app never asks the bank for new data (`PATCH /items` spends
  the free MeuPluggy CPF quota and blocks the account for the month); `pluggy_client.call()` refuses
  PATCH. Pluggy refreshes banks itself (6–24 h); the app reads what it has. Settings live in
  `user_settings` (`GET/PATCH /api/open-finance/settings`): `sync_hours` per user (0 = button only,
  else **6–24**; the thread ticks every 15 min and pulls whoever is due), `include_pending`,
  `first_sync_days`, `auto_record`.
- **Gravar sozinho** (044, owner's reversal of 2026-10-27: they checked the real data and trust it;
  `services/open_finance_auto.py`): with `auto_record` on, a Pluggy movement of a mapped account
  becomes a lançamento by itself — the same item, approved by `approve_item()` right after the pull
  (source OPEN_FINANCE + `source_id` = Pluggy id; a card purchase `client_id = 'pluggy:<id>'`).
  Turning it on is refused (400) unless every BANK/CREDIT account of every active connection is
  mapped or "não usar" and each connection was pulled OK in the last 48 h (`blockers()`); on, the
  waiting Pluggy backlog is recorded in one pass. Since 045 it is on unless the owner turned it
  off, and what an item lacks is guessed (`fill_defaults()`), recorded with `needs_review = 1`.
  **Nothing waits** (owner 2026-11-01: "every transaction updates the moment it arrives, no matter what
  it is"): a Pix to/from someone else is a despesa/receita in the pull that brings it,
  and an own transfer with one side is recorded as the despesa/receita of the side the bank saw
  (`one_side_now()`). When the other side arrives (another bank's pull or a notification), the same
  row becomes the transfer (`inbox.absorb_recorded_side()`, shared by `place()` and
  `_ingest_alone()`: untouched **by the snapshot**, never by `needs_review`; same cents, opposite
  direction, another reais account, ±`TRANSFER_MATCH_DAYS`, no share, its side observed at most once
  per channel (a notice and the Pluggy row that confirmed it), all movements, counterparties that can
  be one person; a notice that joined an item Pluggy recorded has no snapshot of its own and doesn't
  decide, the Pluggy row's does); an edited side stays and the other side is its own row. The snapshot helpers live in `services/recorded_snapshot.py` (re-exported by
  `open_finance_inbox`). Both sides in one pull pair before
  recording, as before. A Pix to the Conta global is a despesa in reais until the dollar credit turns it
  into the transfer (`_absorb_recorded_real_side()`). A row in another currency on a reais account takes
  the day's PTAX (`in_reais_now()`); only without a PTAX yet does it wait for the next pull. **Pending bank
  rows come in by default** (052, `include_pending` unless "0"); one that posts under a new id is
  succeeded (above). `TRANSFER_HOLD_DAYS` is only the rebuild's. A bank's fund (Pluggy `0302`) is recorded
  as `BANK_INVESTMENT`, an aporte/resgate; other category 03 rows on a bank account stay despesa/receita for review.
  A look-alike the owner typed is **linked** (first free candidate), never duplicated; manual rows
  are never deleted. On the Corretora account only bank ↔ Corretora transfers become rows
  (aporte/resgate, 039); the rest is `COVERED`. A bank invoice payment links to the app's
  pay-invoice/autopay row (`invoice_payment_link()`), never records one. Category: owner's import
  rule, else Pluggy's category through `open_finance_categories.py`, else the default. **Mutation
  guard**: an auto-recorded row keeps `recorded_snapshot`; if the bank changes the amount or drops
  it, the lançamento is corrected/deleted only while it equals the snapshot (no edit, receipt) and
  was created by that Pluggy row (`apply_change()` / `apply_vanish()`; never a transfer, never a
  paid installment, never on an empty pull); otherwise `conflict` and the Conferência lists it.
  Which phone notices reach this engine: the policy above.
- **BB Rende Fácil is never in the app** (046, owner 2026-10-27): the bank's automatic investment
  ("RENDE FACIL"/"REND.FACIL", `inbox.is_auto_invest()`) is `COVERED` in `place()` (no item, no
  lançamento, not in the Conferência) and its phone notice is `ignored`. So BB's app balance leaves
  out what sits in Rende Fácil; the owner's targets are the checking balance.
- **History** (`history_preview()` / `history_apply()`, `POST /api/open-finance/history/preview|apply`):
  preview reads N days (GET) and counts per account (linked, to_link, to_record, waiting, covered,
  app_only) without writing; apply needs `confirm: true` and Gravar sozinho, re-pulls from that date
  and runs the same engine. The **Conferência** (`services/open_finance_check.py`, `check` on each
  account of `GET /api/open-finance`) only points: bank-only (with a `reason`), app-only, awaiting,
  `conflicts`, and `explanation` (balance difference = bank-only + awaiting − app-only + before the
  window).
- **BTG Investimentos in Investimentos** (044, `services/open_finance_investments.py`): the same pull
  reads `/investments` and each position's transactions (GET). Equity BUY/SELL become movements on
  the trade date with cash through the Corretora (as typed ones), idempotent by
  `open_finance_investment_operations.op_key`; a typed twin (same asset and sign, ±2 days, one trade or several summing to it) is
  linked; an unknown ticker, a sale without position, a date before the latest corporate action,
  TRANSFER and equity INTEREST are `HELD` for the owner. Deleting a recorded one is
  `DISMISSED` for good (a recorded coupon: deleting its provento, `proceed_id`, 056). Positions are never
  written into the portfolio: `portfolio_check()` compares quantities (D-1 position + later operations)
  and the broker cash, where trades of the last 2 business days are "a liquidar" (D+2 settlement).
- **Fixed income from Pluggy only with exact data** (Phase 3, `services/open_finance_fixed_income.py`):
  each pull stores the whole position (`open_finance_positions.raw`, 056, minus `transactions`); a
  FIXED_INCOME BUY/SELL/INTEREST is recorded only when `title_terms()` maps the position exactly: CDI +
  `rate` = % do CDI, IPCA + `fixedAnnualRate` = IPCA+, PRE + `fixedAnnualRate` = pré (Pluggy's unit is
  percent; outside `CDI_PERCENT_RANGE`/`ANNUAL_PERCENT_RANGE` even the unit would be a guess), `subtype`
  → `TITLE_TYPES` (decides IR and category); Tesouro needs the title in the Tesouro price file, the same
  indexer and the `dueDate`. Anything else waits `HELD missing:<field>` / `unmapped:<field>` — **never
  guess a rate** (SELIC waits). A held line is re-decided every pull, so it fills itself when the
  position completes. No cash link: the money is already a `BROKER_STATEMENT` line. A redemption takes
  the buys of the same Pluggy investment, oldest first (PEPS), by Pluggy units (`open_finance_units`);
  a coupon is an INTEREST provento on that title's asset, taxed from the first buy, and the statement
  line that paid it becomes its row (`broker_statement.adopt_proceed_line()`). Typed twins (same cents,
  ±2 days) are linked. `scripts/position_fields.py --email X` (read-only) lists which keys MeuPluggy
  fills, never values.
- **The brake can refuse typing on the Pluggy-fed Corretora** (Phase 3, `manual_entries.require_manual_investment_cash()`,
  only while `MANUAL_ONLY_OFF_PLUGGY`, off by default since 2026-11-05): `POST /api/investments`, `/api/investments/redemptions` and
  `/api/investment-proceeds` answer 400 "A Pluggy traz as operações da corretora." when the cash account
  (a provento: the portfolio account from `portfolio_since`, `proceed_cash_account_id()`) is in
  `bank_fed_account_ids()`; a PATCH moving an operation onto it too. `cash_account_id: null` or another
  account passes (crypto stays typed). **The exception**: `metadata.open_finance_op_key` naming a `HELD`
  line of this user (`held_operation()`); it passes and `complete_held()` makes the line `RECORDED` with
  the new id in the same transaction (another user's, unknown or not-held key: 400). Only the routes are
  guarded: `proceeds_sync`, `apply_paid_proceeds()` and `open_finance_investments` never.
  `portfolio_check()`'s `held` carries `op_key` and a `prefill` (`held_prefill()`: kind `operation`,
  `redemption` or `proceed`; equity cash = the Corretora, fixed income none). Web: "Lançar" in Ajustes ›
  Open Finance (operation → `InvestmentLaunchModal prefill`, coupon/redemption one tap,
  `lib/openFinance.js` `heldLaunch()`); APK: "Lançar" opens `LaunchSheet` (operations only,
  `rules/InvestmentPrefill.kt`). On a fed Corretora the cash field defaults to "Não descontar" with a note
  (`cashLinkWithAccounts()` in `lib/portfolioAccount.js` / `PortfolioAccount.kt`); the owner may pick the Corretora.

### Receipts
- **A receipt is a file on disk referenced by a row** (014; card purchases 016): bytes in
  `ATTACHMENTS_DIR/<user_id>/<generated name>`, type sniffed from bytes, routes check both ids.
  Write the file before the row, remove it after the commit; `prune_orphan_attachment_files()` at
  boot. Backups mirror the folder into `backups/attachments/`.

### Investments
- **Cost is the weighted average, never FIFO** (`apply_average_cost()` in `fetch_investments()`);
  the price stored on a SELL is never a cost. Fixed income stays per title.
- **One monthly tax rule** (`services/variable_income_tax.py`, `monthly_apuration()`): R$ 20 mil
  exemption for ações only; ETFs/BDRs 15%, no exemption, stocks' loss pool; FIIs 20% own pool;
  fixed-income ETFs out of the DARF. Each sale stores its share of the month's tax. The exemption
  meter reads the IR report's apuração — no second copy. Tributação exclusiva is declared net.
- **Movements and BRL**: `fetch_investments()` is the BRL stream (realized result, portfolio,
  evolution, IR read it); `fetch_investment_rows()` is native currency for screens and edits.
- **A corporate action is applied on write** (017): earlier movements and quotes are rescaled
  (originals in `metadata.corporate_adjustments`), a bonus is a zero-cash BUY; nothing may be
  entered before the latest event, and only the latest can be undone.
- **Cash goes through the portfolio account**: `metadata.cash_account_id` is switch and account —
  present means exactly one linked lançamento (`INVESTMENT_TRANSACTION`), absent means none
  (`investment_cash_account_id()`, `resolve_investment_cash_account()`). A POST without the key
  uses the Corretora (`portfolio_cash_account_id()`); `null` = "Não descontar". Paid proventos land
  in it (`apply_paid_proceeds()`, `INVESTMENT_PROCEED`) from `metadata.portfolio_since` on. Its
  balance shows only in Investimentos.
  When the Corretora is Pluggy-fed, typing an operation, redemption or provento into it is refused
  (except a `HELD` line's "Lançar"), and HELD lines are recorded as in "Fixed income from Pluggy only
  with exact data" above.
- **Trade cash moves on the liquidation date** (owner 2026-10-28, no migration; `services/settlement.py`):
  the linked lançamento is dated D+2 business days for STOCKS/REIT (B3 calendar: weekends, national
  holidays, Carnival/Good Friday/Corpus Christi, 24 and 31/12), D+1 abroad, same day otherwise;
  `metadata.settlement_date` overrides, never before the trade (400); `metadata.settlement_amount`
  (the note's net value, fees included; Pluggy's `netAmount`) overrides the cash amount. **Conta
  investimento** (`GET /api/investments/settlement`, `services/broker_cash.py`, Posição): Saldo hoje
  = Corretora rows dated ≤ today, Em trânsito = later rows + announced proventos (payment > today),
  Saldo = both; it moves rows still on the trade date (`resync_investment_cash_dates()`).
  `cash_check()` compares Pluggy's balance with the app up to Pluggy's balance day.
- An operation's sign is its type: `PATCH /api/investments/<id>` keeps the stored sign.
- **Proventos of ações/FIIs are computed** (026, `proceeds_sync.py`): StatusInvest value × position
  on the data com; idempotent by `sync_key`; typed ones are never touched, edited ones are
  `sync_locked`, deleted ones are dismissed for good. JCP 15% to 2025, 17.5% from 2026;
  `TAXABLE_INCOME` 22.5%. Renamed tickers need `TICKER_ALIASES`.
- **Coupons and amortizations are typed proventos** (040, `INTEREST`): regressive IR from the
  first BUY (`interest_tax_rate()`); `repeat: {every_months, count}` writes all or none.
- **The category refines the class on read** (`services/asset_categories.py`), never stored; don't
  rebuild `assets` for a new class.
- **Tesouro Direto is marked to market** (`services/treasury.py`, `tesouro_client.py`): titles =
  amount ÷ purchase-day PU (or `metadata.treasury_units`), net of B3 custody, IOF and IR per
  purchase; Posição groups by title, redemptions are PEPS (`lib/treasury.js`). A read never waits
  for the price file (falls back to the curve); the file downloads at most once a day.
- **Returns**: TWR is daily (`services/returns.py`), closes put back in the stored-quantity basis
  (`restore_quantity_basis()`); Rentabilidade compares from the same 0% over the compared months
  (`compared_months()`). A bonificação is never a flow.
- **Chart history is served stale and refreshed behind** (15 min fresh, 7 days stale,
  `schedule_history_refresh()`), with a disk copy in `HISTORY_CACHE_FILE`; index closes follow the
  same rule. Quotes refresh hourly in a thread (`services/quote_refresh.py`). The quote button
  and that thread wait `PRICE_REFRESH_TIMEOUT_SECONDS` (25 s; reads wait 6 s); a provider slower
  than that still records its quotes when they arrive (`on_late`, response `late: true`).
- **A save waits only for its own request**: `apiFetch` already invalidates every query; awaiting
  `invalidateServerData()` joins those refetches, never restarts them. The Extrato changes the row in the
  cache at once (`dropStatementRow()`, `updateStatementRow()`; the APK in `rows`) and never awaits the reload. The quote refresh after a
  write runs after the sheet closes (`refreshQuotes()`). Writes don't rebuild
  `investment_positions`; `replace_realized_results()` writes only on change.
- **Allocation targets and goals are plans** (020, 021): computed on read from
  `build_portfolio_snapshot()`, never stored.
- BCB and Tesouro are fetched through `gov_http.get()` (Python 3.14 strict X.509 flag dropped,
  one retry). A test's fake `urlopen` takes `**kwargs`.
- Registrar provento picks the type first, then only assets that can pay it
  (`lib/proceedsRules.js`). `CATTLE` was removed (2026-09-27): the API refuses it.
- The Extrato has two views (`?ver=contas|investimentos`); an operação can be deleted from either.

## Known sharp edges

- **Strict layering**: `config` ← `applog`/`source_types` ← `db` ← `validators`/`money`/`dates`/`auth`/
  `asset_classes`/`responses` ← `services/*` ← `routes/*` ← `app`. Nothing imports `app`; a blueprint never
  imports another (shared code goes in `services/`). A new blueprint goes in `app.py`'s list, or
  `test_route_map.py` fails. **`test_architecture.py` checks it from the code**: the layers, no import
  cycle (function-level imports count: never "fix" a cycle with an import inside a function), and a
  ratchet on uses of another module's `_private` name (`tests/architecture_private_uses.txt` only
  shrinks: a new use fails, a removed use must leave the list).
- `formatCurrency` and the date helpers live in `lib/format.js`; `pages/lancamentos/helpers.js`
  keeps a local `getLocalDateString`/`formatDateBR` on purpose (clock hook, `''` vs `'-'`).
- **The "+" lives in the bottom bar, at its center** (owner 2026-11-05): web `Layout.jsx` (middle of the bar;
  desktop: the header) and APK `ShellBottomBar` (after Lançamentos, `ShellNav.NEW_ENTRY_AFTER`, on every page with
  the bar). Never a floating button over the page: it covered the end of the lists. **Ajustes is not a bottom tab**
  (owner 2026-11-05): the bar is `ShellNav.BAR` (Início, Lançamentos, "+", Planejar, Investir); Ajustes opens from
  the gear at the top (`SettingsButton` in `NativeTopBar` and Início's header; web: the header's gear).
- **Frontend**: pages use only `ui.jsx` pieces; emerald is the only accent; tabs come from the URL;
  data via `useQuery`; `apiFetch` invalidates after every write (no manual refetch). Loading lists
  show `ListSkeleton`. Headline numbers in one `SummaryPanel`; two+ row actions behind a `Menu`;
  success is `toast()`, errors `AlertMessage`, destructive confirms `confirmAction()` — never
  `window.confirm`/`prompt`/`alert`.
- **Privacy mode** hides balances and the portfolio via `usePrivateFormatter()` /
  `usePrivateAxisFormatter()` / `MetricCard sensitive` (`lib/privacy.js`), without remounting.
- **Visual rules**: green/red/amber/sky only for gain/loss/warning/info; signed amounts via
  `formatSignedCurrency`; numeric cells `.num`; 44 px touch targets below `lg` (already in the kit);
  `inputMode` on numeric fields; no `overflow-x`/`overflow-hidden` around sticky tables (use
  `overflow-clip`); big values in `FitValue`, never `truncate`.
- **Theme**: only `zinc`, `emerald`, `rose`, `amber`, `sky`, `white`, `brand` (CSS variables in
  `index.css`); dark mode swaps the variables — never `dark:` classes or other Tailwind families.
  Charts use `CHART`/`FLOW`/`SERIES`/`OTHER_COLOR` from `charts.jsx`. Font is Plus Jakarta Sans
  from `public/fonts` (no Google Fonts).
