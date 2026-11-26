# Domain rules

> The finance rules and the owner's decisions. **Read the section you touch before changing it**; a rule
> changes only with the owner's word (add the date). Names in backticks are the code that holds the rule.
> The long version with its history: `git show 16b7a6a:docs/domain-rules.md`.

## Basics
- Money: `rounded_money()` (ROUND_HALF_UP, `Decimal`); requests via `parse_money()` (≥ 0,01 unless `allow_zero`, ≤ `MAX_MONEY`).
- Dates 1900–2199 (`require_date()`, `normalize_month()`), zero-padded, compared as text; investment metadata dates via `validate_movement_metadata()`.
- Migrations 027/029 are empty placeholders: keep the numbers.
- Destructive guards: an asset delete needs the matching `asset_class`; a delete that leaves a sale unbacked is refused.
- Signup closes once a user exists (`ALLOW_SIGNUP=1` opens it); a missing/example `JWT_SECRET` is replaced by a random one in `JWT_SECRET_FILE`.

## Accounts, categories, transfers
- **A transfer is one row** (`account_id` → `transfer_account_id`); sums over `transactions` skip `TRANSFER`. Never income nor expense.
- **Categories: the id decides** (035). `transactions`, `cc_expenses`, `recurring_transactions`, `import_rules`, `inbox_items` keep name + `category_id`; screens send the id. A bare name → root first, then the oldest subcategory (`category_id_for_name()`); an edit sending the row's own name keeps its id; a rename rewrites all five (`rename_category_rows()`).
- **Archive, never delete** (`archived_at`). A card with an `OPEN` item refuses delete (409), with history is archived, empty is deleted; an archived card takes no purchase, refund, autopay or approval (`require_active_card()`).
- One default account, active, never the Corretora nor foreign (`ensure_default_account()`).
- An edit keeps the row's own account even if archived (`keep_or_require_account()`); a new choice must be active; `account_id: ""` is refused. A recurrence on an archived account lands in `/run`'s `blocked`.
- **Consolidated balance** = sum of reais account balances (archived included; Corretora and foreign accounts out), `consolidated_balance` of `GET /api/home`; never sum `transactions` (drops `initial_balance`).
- A despesa/receita can become a transfer (`PATCH /api/transactions/<id>` with `type: TRANSFER` and both accounts, one the row's own; reais accounts only): loses category and share, leaves review; `absorb_other_side()` drops the other side Pluggy recorded (OPEN_FINANCE, no receipt/share, same cents, ±3 days) or closes its waiting item. Transfer → despesa is refused.

## Idempotency and the outbox
- Rows written on demand carry `source_type` + `source_id` (unique `idx_transactions_user_source`): recurrences `'<rec>:<AAAA-MM-DD>'`, autopay `CC_AUTOPAY` `'<card>:<AAAA-MM>'`, import (row hash or `'ofx:<conta>:<FITID>'`, suffix for duplicates in a file), investment cash, paid proventos. New ones keep the shape.
- "+ Novo" creations are idempotent by `client_id` (024: `POST /api/transactions`, `/api/transfers`, `/api/cc-expenses/purchases`); a repeat returns the first result (200), looked up before validation.
- **The outbox holds creations only, and only when the request never reached the app** (`ApiNetworkError`, or the proxy refused it: `ApiProxyAuthError`). A creation times out at 6 s and is queued (offline: without trying); reads 45 s; edits/deletes have no timeout and are never queued. A proxy 401 never clears the JWT; the page reloads into the Google login at most once per 30 s (`lib/proxySession.js`). `lib/outboxRules.js`: a pending transfer leaves balances alone, a pending card purchase touches no account, a balance with pending items is labelled an estimate.

## Cards and invoices
- **A card purchase is its `client_id`** (035; old rows `legacy:<id>`); receipts, sharing, A receber and installments go through `same_purchase_sql()` / `cc_purchase_expense_ids()`; screens group by `cardPurchaseKey()`.
- **The invoice month is backend-only** (`compute_invoice_start()`, closing day 29–31 clamped); no client copy. For Pluggy cards the bank decides (below).
- Paid only after it closes (`ensure_invoice_closed()`), only by `POST /api/cc-expenses/pay-invoice`. "Desfazer pagamento" (`DELETE /api/cc-expenses/payments/<id>`) reopens what it paid and writes `cc_invoice_manual` (no autopay again); refused while the payment has a receipt.
- **A paid invoice is history** (037): paid items are never deleted; a new purchase/refund never lands in it (`first_unpaid_invoice()`); `settle_invoice()` stamps `paid_by`.
- Next invoice per card by due date (`open_invoices()`): `next` feeds Início and the bell; `nearest` (oldest overdue with total > 0, else first `next`) is what Cartões pays. Overdue = after the due day.
- Card functions (041): `debit_account_id` makes a débito purchase a plain EXPENSE there (never a Corretora); `credit_enabled = 0` is debit-only (credit paths refused, no autopay).
- **Autopay** (`apply_due_autopay()`, on read, on the due day, invoices due ≥ `autopay_start_date`) debits only when the account's balance at the end of the due day covers it (`account_balance_until()`, same-pass debits included; owner 2026-11-05); else the invoice stays for Pagar. Pluggy-mapped cards too, up to `AUTOPAY_CONNECTED_DAYS` (5) after the due day and never with a bank invoice payment (`pluggy:`) on that account within ±5 days; the bank's payment later links to it and takes its amount (below).
- **A refund is a credit row** (033, `kind = 'REFUND'`, positive, 1/1, never shared); sum card rows with `signed_amount()` / `signed_amount_sql()` / `cardSignedAmount()`. An invoice in credit can't be paid (409); it rides with the next payment.
- Card purchases appear in the Extrato (`GET /api/cc-expenses/statement`, one row per purchase, merged by `mergeStatement()`), never in day or filter totals.

## Banking views, plan and budgets
- **Início is banking only, in reais**, never the portfolio; aporte/resgate/provento apart from despesa/receita (`isInvestmentOutflow()`/`isInvestmentInflow()`). Invoice tile: "Fatura de <mês>", a dropdown per invoice, Pagar (2026-10-31).
- **Investimento is not a category** (039): aporte/resgate/provento by origin only (`INVESTMENT_SOURCE_TYPES`, or a bank ↔ Corretora transfer).
- **The month's spending is one rule everywhere** (owner 2026-11-13, `services/spending_rules.py`): Início, plan and budget count the same rows. A despesa/receita in a Corretora counts nowhere. An invoice payment (by `source_type`, or a category starting "Pagamento Fatura", any case) is never expense nor income; the pending estimates repeat the name test (`isInvoicePayment()`).
- **Whose expense** (032, `services/sharing.py`): owner, `SPLIT`, `OTHERS`. Balances never change; budget, plan, Início count the owner's part (`own_amount_sql()`/`ownAmount()`); A receber lists the rest until `share_settled_at`. Marking it paid asks which income paid it (053, `link_income()`): that income carries the share as the others'; without one it cuts the income of the month of the mark (`apply_settled_others()`), a repasse of the same person covering it first.
- **A repasse** (owner 2026-10-31): an INCOME `share_mode = 'OTHERS'`, settled — in the balance, out of income. API only (`POST /api/review` with `repasse`); no screen since 2026-11-22.
- **The Inter line** (`MONTH_SUMMARY`, `inter:<AAAA-MM>`, owner 2026-10-31): the month's net moved into Inter (no Pluggy). Moves the balance and Evolução; out of Fluxo, Resumo, Orçamento, plan, Ritmo and Extrato totals; a rebuild keeps it.
- **The plan starts from income** (025, 038, `services/monthly_plan.py`): `income_amount` > 0, `invest_percent` + `spend_percent` ≤ 100, percentages TEXT read as `Decimal`; every R$ on read (`percent_of()`). A month without a row inherits the latest earlier plan and its categories. Saldo do plano = Gastar − spent; "Disponível por dia" = it ÷ days left (server). Invested = `month_investment_flow()`. Old plans without income are `needs_income`.
- **A budget is a % of Gastar** (038, `services/budgets.py`): categories sum ≤ 100% (an over-100 month may lower, not raise), "Sem categoria" is the rest; categories from the latest month ≤ it with a plan (`category_source_month()`), writes in an inherited month via `materialize_month()`; rollover on read; `DELETE` is real. Spent: card purchases in full in the purchase month, refunds subtract, invoice payments never.
- Plan flags and Início's attention cards are dismissed per device (`planFlagKey()`, the item `key`). "Precisa de atenção" = `GET /api/attention`: numbers and keys from the server, text in `Attention.jsx`.
- Orçamento's percentages are `PercentSlider`s bounded by `percentRoom()`/`clampPercent()` (`lib/monthlyPlan.js`).
- A recurrence is a template: `/run` writes real rows, deleting keeps them; pauses skip only their window (`skip_pause_gaps()`).
- Import rules touch the past only on confirmation: preview never writes; `apply` rewrites only the sent ids, re-checking the rule; never transfers, investment cash, proventos or invoice payments.

## Conta global (047, owner 2026-10-27)
- The owner's Wise USD account; the **one** screen in another currency: `/inicio/conta-global` (from Início and Ajustes › Contas), balance and statement in US$ plus "≈ R$" at today's PTAX or "sem câmbio hoje". The only currency choice: Ajustes › Nova conta › "Conta global (US$)" (CHECKING + `currency: USD`).
- **Never in "Saldo em contas"**, list or total (owner 2026-10-28/30); pays no invoice; never default nor Corretora; not offered in "+ Novo". Its own despesas/receitas stay out of every reais total and are listed on its screen.
- **A cross-currency transfer is one row with two amounts**: `amount` leaves in its currency, `transfer_amount` lands in the other (NULL = same currency); required across currencies, refused otherwise (`transfer_amount_for()`); without it a balance counts 0. A reais account that only received transfers can become USD (`convert_to_foreign()`).
- Pluggy: a USD account maps only to a USD account; its rows stay US$ end to end. A BRL Pix naming the account ("WISE BRASIL CORRETORA DE CAMBIO") is an own transfer: the Wise credit pairs with it by day (±1) and counterparty, never cents; two on a day go to the rate closest to the PTAX (`_place_cross_currency()`). The credit records at once as a US$ receita; the BRL side (Pluggy or a notice: `_notified_pix_to()`, `absorb_dollar_income_for_notice()`) turns it into one transfer. A credit matching an existing transfer fills its `transfer_amount`.

## Sources: phone notices and Pluggy (owner 2026-11-04)
- **A notice records at once; Pluggy confirms later and is the record.** The Flash (no Pluggy) comes only from notices and typing.
- **Everything can be typed** (owner 2026-11-05): "+ Novo" offers every reais account and card; a typed look-alike is linked to what the bank brings (`free_candidates()`), never doubled. Brake `MANUAL_ONLY_OFF_PLUGGY` (env, off): on, mapped accounts/cards and the Pluggy-fed Corretora refuse typing (400; a HELD line's "Lançar" passes via `metadata.open_finance_op_key`).
- **No Aprovar and no Revisar screen.** What didn't record itself is listed in the Extrato (web `WaitingItems`, APK "Não gravou sozinho"): pick the other account or the amount in reais (`approve` with `remember: false`), "não é entre minhas contas", or Descartar.
- **Who speaks** (`NOTIFICATION_POLICY`, `notification_wanted()` in `inbox_rules.py`; the APK repeats it, the server decides):

  | App | Accepted |
  |-----|----------|
  | Flash app; Samsung Wallet with the Flash card (`is_flash_detection()`) | outgoing only, no `CREDIT_PURCHASE`; `DECLINED` |
  | `com.itau`, `br.com.bb.android`, `com.btg.pactual.banking` | every `KIND_SHAPES` kind, `DECLINED` |
  | `com.btg.pactual.digital.mobile` (BTG Investimentos) | `MOVEMENT_KINDS` only (Pix/TED) |
  | anything else | nothing (`ignored`, no row) |

  `INVESTMENT_TEXT` words (aplicação, resgate, CDB, LCI, LCA, tesouro direto, fundo de investimento, ordem de compra/venda, provento, dividendo, JCP) block a Pix/TED and everything from the brokerage app, never a card merchant. The APK drops invoice-payment notices and flags `international` (internacional/exterior/US$/USD/EUR/€/£).
- **"Avisos dos bancos"** (`bank_notifications`, default on): off, only the Flash passes and bank notices leave no trace.
- Engine tests open the gate with the fixture `any_bank_notifications`; the gate itself is tested only in `test_notification_policy.py`.
- **Pulls** (GET only; never `PATCH /items`, it spends the MeuPluggy CPF quota — `pluggy_client.call()` refuses it): every `sync_hours` (6–24, "off" = button only, a stored 0 = 6 h), plus every 5 min `sync_fresh_items()` pulls a connection whose `lastUpdatedAt` moved, plus "Atualizar" and the APK's pull on Início (`POST /api/open-finance/refresh`, 2026-11-26). A pull records what it brings; a read (`record_due()`) records only notices. A failing connection doesn't stop the others. A repeating cursor is a `PluggyError`, never a short list.
- A Pluggy account goes only where mapped (a card needs credit; the Corretora takes only the broker's investment account) or "não usar". `include_pending` is on by default (052) — watch Itaú's pending salary beside BTG's TedSalary (portability: one salary).
- **Categories**: owner's import rule → merchant table → CNAE → Pluggy's category → default (`open_finance_categories.py`).
- **Income is never a transfer** (`is_income_row()`: Pluggy `01…` or salary text). A one-sided "não é entre minhas contas" takes the side the bank saw (`settle_one_side()`).
- **BB Rende Fácil is never in the app** (046): `COVERED`, notice `ignored`; BB's app balance excludes it.
- A bank's own fund (Pluggy `0302` on a bank account) is `BANK_INVESTMENT`, an aporte/resgate (`mark_bank_investments()`); other 03 rows stay despesa/receita.
- Waiting for the bank (`awaiting_bank()`): a pending Pluggy item stays out of `waiting` until every active connection refreshed after it (max `BANK_WAIT_MAX_DAYS`, 3); the Conferência does the same for app rows.

## Recording and review (045, owner 2026-10-27)
- **Notifications record, Pluggy reconciles, nothing waits** (owner 2026-11-01/04). `auto_record` (`AUTO_RECORD_DEFAULT`, on) in `/api/inbox/settings` and `/api/open-finance/settings` is the emergency brake (API only). A notice records in `auto_record.py` (after `POST /api/inbox/detections` and in `record_due()`); a Pluggy row in `open_finance_auto.py` right after the pull (source OPEN_FINANCE, card `client_id = 'pluggy:<id>'`). Turning Pluggy's on is refused unless every account is mapped/"não usar" and pulled OK in 48 h (`blockers()`).
- What an item lacks is guessed (`inbox_defaults.py`): the issuer's card/account, else the first credit card / default account, never the Corretora; nothing remembered.
- **An own transfer with one side** is recorded as the despesa/receita of the side seen (`one_side_now()`); the other side, from either channel, turns that row into the transfer (`absorb_recorded_side()`: untouched by the snapshot, same cents, opposite direction, another reais account, ±`TRANSFER_MATCH_DAYS`, no share, counterparties that can be one person). An edited side stays; the other becomes its own row. **Touching the Corretora** it waits `TRANSFER_MATCH_DAYS`, then becomes the aporte/resgate with the bank side guessed (`brokerage_side_now()`).
- A guessed side follows the bank (`follow_bank_side()`), and a real side arriving on another account takes it over (`move_guessed_side()`, 2026-11-17), never a second row.
- A notice in another currency on a reais target records at the day's PTAX (`in_reais_now()`), else the last stored (`fx_fallback()`, a decision when > 4 days old); with none it waits.
- **Review is automatic and invisible** (owner 2026-11-22): `needs_review = 1` only marks "category still a guess". It clears when Pluggy confirms the row with a confident category (rule, merchant, CNAE: `settle_review()`), when both sides of a transfer are seen and one is Pluggy's, or after `review_auto_days` (default 3; on a Pluggy-fed target it first waits for a Pluggy row; `review_auto.py`). Pluggy's tree fills a row still on the default category (`fill_default_category()`).
- **"Untouched" = equal to the snapshot** (`recorded_snapshot`), never the review flag; a new category, amount, date, account, share or receipt is a touch. Every server change refreshes the snapshots (`refresh_snapshots()`).
- **Automatic decisions are logged and undoable** (058, `auto_decisions`, `GET /api/review/auto`, `POST /api/review/auto/<id>/undo`; Ajustes › "Decidido sozinho", the Conferência's "Resolvido automaticamente"). Kinds: `pluggy_category`, `auto_confirm` (hidden), `transfer_guess`, `fx_fallback`, `conflict_changed`, `conflict_vanished`, `investment_custody`, `investment_proceed_link`, `investment_closed_fund` (undo: the line waits again), `investment_custody_in`, `investment_rate_deduced` (not undoable: delete the operation). An undone decision is never retaken on that row. A weekly log line counts them; `review_breakdown.py` dates them by the row's own date.
- Twins "2× igual" (`twins.py`): same account/card, cents and normalized description, ≤ 60 min (else same date): a neutral badge, no action.

## The matching engine (`inbox.py`, `open_finance_inbox.py`)
- **One movement, one row**: a notice and a Pluggy row (same cents, ≤ 1 day, the mapped target) are one item in either order, through the item's free Pluggy slot of that side. Claims are per channel (`pluggy_claimed()`/`notification_claimed()`); a typed row is free to both. Two identical real purchases stay two. `identity_invariants.violations()` checks it; `scripts/check_identity.py` on the server must print nothing.
- **A bank's notice is never another bank's movement** (2026-11-20, `account_bank()`/`card_bank()`), even when the target is a guess. A notice never links to an invoice payment, investment cash or the Inter line.
- **Two sides are one person** (owner 2026-11-20): two CPFs decide; names by first + last (`same_person_name()`), never the first name alone; named + unnamed only when one is known to be the owner; two unnamed pair. "It's me" is learned into `inbox_hints`; BTG Investimentos transfers are own.
- A recurrence occurrence is settled by a notice (034: same type, ±7 days, exact or within 20% with a shared word/category). An ambiguous target is never remembered (`ambiguous_target()`).
- A refund notice naming a card is a card credit (`refund_card()`). A repost of the same app is recognised (`_repeated_posting()`, `REPOST_CLOSE_MS`). Bank × Samsung pair one to one within `NOTIFY_WINDOW_MS`; the bank wins. A Samsung Flash purchase records at once; a later decline removes the untouched row.
- **Reconcile a recorded row** (`reconcile_recorded()`): untouched, same date and target → the Pluggy row becomes its source; another date/target → the row follows the bank in place (owner 2026-11-20); account ↔ card → re-recorded the bank's way; a purchase notice without credit/debit lets the bank decide. Edited → `MATCHED` only. A card purchase with a paid installment is never redone.
- **Succession**: a new Pluggy id continuing a missing one (`successor_for()`: same account/direction, same cents or BB rounding, ≤ 3 days, one to one; a 1/1 continued by 1/n with the total) takes its place (`hand_over()`); the old row is `REMOVED` with `superseded_by`. What nobody took over vanishes (`vanish_rows()`; a matched row gets `conflict = 'vanished'`); an empty pull vanishes nothing.
- **Near match** (same purchase, another amount; purchases only, never Pix/refund/installments/Corretora/global): same target, `merchant_agrees()`, within 10% international / 30% domestic, unique each way; international up to `LATE_POSTING_DAYS` late. The bank's amount wins unless the owner typed it (then `conflict = 'changed'`). `late_near_pass()` joins a pair that became unique later. A bank row also pairs with a notice up to `OPEN_FINANCE_LATE_POST_DAYS` (5) before it.
- **BB rounds up** (`ROUNDS_UP_ISSUERS`, `rounded_up()`): 18,19 pairs with 19,00; the notice's cents stay. Installments 2..n are `COVERED`; invoice payments are never items; a card credit is a `REFUND` item. The card sign is learned per account (`learn_charge_sign()`).
- **Mutation guard**: a bank change or vanish corrects/deletes a row only while it equals the snapshot and was created by that Pluggy row (never a transfer, a paid installment, an empty pull); else a `conflict`. **Conflicts resolve themselves** (`conflict_resolution.py`): `changed` takes the bank's amount after `CHANGED_WAIT_DAYS` (7), same direction, never with a receipt, share, "Aconteceu" or typed amount; `vanished` leaves only by the balance proof below.
- **Orphans by balance** (`open_finance_orphans.py`, last step of a pull; mapped reais BANK accounts only, cards list-only): a notice-recorded despesa/receita no Pluggy row claims, older than 5 days and after a bank refresh, is removed when its fix equals the Conferência's difference (or all of them do); never a receipt, share, "Aconteceu", typed amount or transfer. Difference 0 → listed as "Confirmado pelo saldo".

## Pluggy cards, payments, Conferência
- **A card mirrors the bank** (owner 2026-10-30, `mirror_cards()`): pending rows come in; the invoice is the bank's (`billId` for posted rows, else `billForecastDate`, over `compute_invoice_start()`); one app line per bank line; `closing_day` from `GET /bills`.
- **Anticipated installments** (`_anticipations()`): the discount credit decides — installment N goes to the discount's invoice. A purchase the owner typed or changed only moves its lines' invoices (`_move_line()`), never its amounts.
- **A bank invoice payment** with no app row settles that invoice (`open_finance_invoices.py`, by Pluggy id); a payment the app has is linked, never doubled (`_kept_payment()`: same account, same day any amount, or same cents ≤ 5 days, or an autopay within `AUTOPAY_NEAR_PERCENT` 5%), taking the bank's amount. Recurrences never write on mapped targets.
- **Conferência** (`open_finance_check.py`) only points: bank-only, app-only, awaiting, conflicts, explanation (difference = bank-only + awaiting − app-only + before the window). "Lançar" records a bank-only row; "Aconteceu" keeps an app-only one (`open_finance_confirmed`, "Desfazer"). Only `awaiting` → "Confere".
- History preview/apply (`POST /api/open-finance/history/preview|apply`): preview never writes; apply needs `confirm` and auto-record. Rebuild (`scripts/rebuild_from_pluggy.py`): dry-run by default; `--apply` with the app stopped; Flash rows never wiped.

## Broker and investments from Pluggy
- **The broker's balance is its statement** (`broker_statement.py`): BTG's balance = every line minus `CONTA REMUNERADA`. Lines are a sweep or the trade's `VISTA BRUTO` (`COVERED`), or a `BROKER_STATEMENT` row (fee, IR, fixed income, cashback; never income/expense). A proceed the app has takes the bank's value and day (`sync_locked`). Fixed-income ETFs settle D+1.
- **Equity** (`open_finance_investments.py`): BUY/SELL → movements with cash through the Corretora, by `op_key`; a typed twin (same asset/sign, ±2 days, or several summing) is linked; unknown ticker, sale without position or a date before a corporate action → `HELD`. Decided alone: custody TRANSFER dismissed when the app holds enough; INTEREST links to the computed provento (±3 days, ≤ 5 cents); a closed bank fund's line dismissed. Deleting a recorded one dismisses it for good. Positions are never written: `portfolio_check()` compares (D+2 "a liquidar").
- **Fixed income only with exact data** (`open_finance_fixed_income.py`, `title_terms()`): CDI + `rate` = % do CDI, IPCA + `fixedAnnualRate` = IPCA+, PRE + `fixedAnnualRate` = pré, `subtype` → `TITLE_TYPES`; Tesouro needs the price file, indexer and `dueDate`. Else `HELD missing:/unmapped:` — **never guess a rate**. Deductions allowed: `rate` 0 with `fixedAnnualRate` > 0 is pré; a Renda+ without year by type + `dueDate` (commercial name). A TRANSFER in is a no-cash BUY at `netAmount` (`custody_transfer`). Redemptions take the same investment's buys PEPS by Pluggy units; a coupon is an INTEREST provento; typed twins only of the same title (`title_fit()`), a buy within 1% of the same type and maturity too. Held lines re-decide every pull.
- HELD lines carry `op_key` and a `prefill` (`held_prefill()`): web "Lançar" in Ajustes › Open Finance, APK `LaunchSheet` (operations only). On a Pluggy-fed Corretora the cash field defaults to "Não descontar" (`cashLinkWithAccounts()`).
- A provisional buy (`fill_position_gaps()`, rebuild only): a position ahead of the operations gets `metadata.provisional` at the position's price, no cash; the real operation replaces it.

## Receipts
- A file on disk referenced by a row (014, 016): `ATTACHMENTS_DIR/<user_id>/<name>`, type sniffed from bytes, both ids checked. File before the row, removal after the commit; orphans pruned at boot; backups mirror the folder.

## Investments
- **Weighted average cost, never FIFO** (`apply_average_cost()`); a SELL's price is never a cost; fixed income per title.
- **One monthly tax rule** (`monthly_apuration()`): R$ 20 mil exemption for ações only; ETFs/BDRs 15% with the stocks' loss pool; FIIs 20% own pool; fixed-income ETFs out of the DARF. Each sale stores its share; the exemption meter reads the IR report. Tributação exclusiva declared net.
- `fetch_investments()` is the BRL stream (results, portfolio, evolution, IR); `fetch_investment_rows()` native currency for screens and edits.
- **Corporate actions apply on write** (017): earlier movements and quotes rescaled (originals in metadata); a bonus is a zero-cash BUY; nothing before the latest event; only the latest can be undone.
- **Cash through the portfolio account**: `metadata.cash_account_id` present = exactly one linked lançamento, absent = none; a POST without it uses the Corretora; `null` = "Não descontar". Paid proventos land there from `portfolio_since`.
- **Trade cash on the settlement date** (`settlement.py`): D+2 business days (B3 calendar) for STOCKS/REIT, D+1 abroad, same day otherwise; `settlement_date` (never before the trade) and `settlement_amount` override. Conta investimento: Saldo hoje / Em trânsito (`broker_cash.py`).
- An operation's sign is its type (PATCH keeps it).
- **Proventos of ações/FIIs are computed** (026, StatusInvest × position on the data com, by `sync_key`): typed ones untouched, edited `sync_locked`, deleted dismissed. JCP 15% to 2025, 17.5% from 2026; renamed tickers need `TICKER_ALIASES`.
- Coupons/amortizations are typed proventos (040, `INTEREST`): regressive IR from the first BUY; `repeat` writes all or none.
- The category refines the class on read (`asset_categories.py`), never stored.
- **Tesouro marked to market** (`treasury.py`): titles = amount ÷ purchase-day PU, net of custody, IOF and IR; redemptions PEPS; a read never waits for the price file (curve fallback, one download a day).
- Returns: daily TWR (`returns.py`), from the same 0% over compared months; a bonificação is never a flow. Chart history served stale and refreshed behind (15 min fresh, 7 days stale, disk copy); quotes hourly; refresh waits ≤ 25 s, late quotes still recorded.
- A save waits only for its own request (`apiFetch` invalidates; the Extrato edits its cache at once).
- Allocation targets and goals are computed on read; **a goal's "Atual" is what is invested today** (057), never an account balance.
- BCB/Tesouro via `gov_http.get()`. Registrar provento: type first, then assets that can pay it. `CATTLE` is refused.

## Navigation
- **The "+" is at the center of the bottom bar** (owner 2026-11-05), never floating; the bar is Início, Lançamentos, "+", Planejar, Investir. **Ajustes opens from the gear at the top**, not a tab.
