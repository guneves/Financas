# Proposal: home, attention and invoice endpoints

| | |
|---|---|
| Status | **Approved** (PR #35 merged) and **implemented §1–4** in session 6 (2026-10-23), web switched. §5 (paging) waits for the native Extrato, as *Order of implementation* says. One reading of §1: `applyPendingToHome()` applies a pending item to the month of its date (any month in `flow`) and moves the balance from there on, which is exactly the old `buildMonthlyFlow()` over pending rows; a pending item of the current month behaves as written. |
| Replaces | `lib/transactions.js` money (`consolidatedBalance`, `openingBalanceTotal`, `bankingTransactions` + the investment classification), `lib/cashFlow.js` (`buildMonthlyFlow`), `lib/attentionRules.js` items (`nextInvoices`, `payableInvoices`, `overdueInvoices`, `autopayShortfalls`, `attentionItems`, `nearestOpenInvoice`), Cartões' inline `openInvoicesByCard` and its delete filter |
| Serves | Início (`03-inicio.md`), the bell (`00-shell.md`), Cartões (`05-cartoes.md`), the Extrato's list (`04-extrato.md`), on the web and on native |
| Does not replace | The pending overlay (`outboxRules.js`, ported to `rules/OutboxPending.kt` in the same session as this proposal), the dismissals (`attention.js`, `addDismissed`, `undismissedItems`), the texts (`overdueDetail`, labels) |

## Why

Início and the bell download **every transaction and every card row ever written**
(`GET /api/transactions` with no filter, `GET /api/cc-expenses` with no status) and run about 1000
lines of money logic on them. Cartões groups invoices and adds money as floats. A native screen
would need all of it ported, which would leave three copies of the same rule (server, JS, Kotlin).
`rules-port.md` says money rules move to the server. This proposal gives the concrete shapes.

## One new service, three readers

All three reads share one module, so Início, the bell and Cartões agree by construction:

```
backend/services/card_invoices.py   (new)  open invoices per card, next / overdue / payable / nearest
backend/services/home.py            (new)  balance, accounts, the month's flow (cashFlow.js on the server)
backend/services/attention.py       (new)  the attention items and their keys (attentionRules.js)
backend/routes/home.py              (new)  GET /api/home, GET /api/attention, GET /api/cc-invoices
```

The layering: `card_invoices` sits on `invoices` (`serialize_cc_expense()`, `signed_amount()`,
`local_today()`) and `attachments` (`same_purchase_sql()`). `home` sits on `accounts`
(`account_balance_rows()`), `fx` (the BRL balance), `sharing` (`own_amount_sql()`) and
`card_invoices`. `attention` sits on `card_invoices`, `home` (the BRL balances), `recurring`
(`recurring_pending_count()`) and `monthly_plan` (`build_budget_view()`). The blueprint only reads
and serializes. It goes in `app.py`'s `for blueprint_module in (...)` list, and each route gets a
row in `test_route_map.py`.

Each read first does what the reads it replaces do: `ensure_default_account()`,
`apply_due_autopay()` and `apply_paid_proceeds()`. `GET /api/accounts` and `GET /api/transactions`
run them today. Without them, the hero would miss an autopay debited today.

"Today" is `services.invoices.local_today()`, as `invoice_closed` already is. The image runs with
`TZ=America/Sao_Paulo`, so the server's today is the owner's. Tests freeze it by patching
`local_today` **in every module that reads it** (`services.card_invoices`, `services.attention`,
`services.home`), following CLAUDE.md's "patch where the name is read".

Money is summed in `Decimal` and returned through `rounded_money()`. A per-row amount from the JS
side was `Math.round(x * 100)`. The server reads the stored value, which is already rounded to
cents, so the two agree.

---

## 1. `GET /api/home`

The banking area's headline numbers: the consolidated balance, the accounts, the month's
Resultado, Entrou, Saiu, Investido and others' net, and the next invoice of each card.

**Query:** `?months=N` (optional, 1–24, default 1). It returns the last N months of the flow,
ending with the current month. Início asks for `months=12`, which also feeds the "Fluxo de caixa"
chart and "Evolução do saldo" (see *Beyond the brief*).

**Response** (200):

```json
{
  "today": "2026-10-23",
  "month": "2026-10",
  "consolidated_balance": 5234.10,
  "accounts": [
    {"id": "a1", "name": "Itaú", "type": "CHECKING", "currency": "BRL", "is_default": true,
     "archived_at": null, "balance": 4100.00, "balance_brl": 4100.00, "initial_balance": 800.00},
    {"id": "a2", "name": "Nubank", "type": "CHECKING", "currency": "BRL", "is_default": false,
     "archived_at": null, "balance": 1134.10, "balance_brl": 1134.10, "initial_balance": 0},
    {"id": "a3", "name": "Velha", "type": "SAVINGS", "currency": "BRL", "is_default": false,
     "archived_at": "2026-03-01T10:00:00Z", "balance": 0, "balance_brl": 0, "initial_balance": 0}
  ],
  "summary": {
    "income": 9000.00,
    "expense": 3120.45,
    "result": 5879.55,
    "invested": 2000.00,
    "redeemed": 0,
    "investment_net": 2000.00,
    "others_paid": 150.00,
    "others_received": 40.00,
    "others_net": -110.00
  },
  "flow": [
    {"month": "2026-10", "income": 9000.00, "expense": 3120.45, "invested": 2000.00, "redeemed": 0,
     "others_paid": 150.00, "others_received": 40.00, "net": 3769.55, "balance": 5234.10}
  ],
  "next_invoices": [
    {"card_id": "c1", "card_name": "Nubank", "invoice_month": 11, "invoice_year": 2026,
     "due_date": "2026-11-10", "closing_date": "2026-11-03", "closed": false, "payable": false,
     "total": 812.30, "item_count": 6}
  ],
  "next_invoices_total": 812.30,
  "next_closing_date": "2026-11-03"
}
```

- `accounts`: every account, archived and Corretora included, as `GET /api/accounts?include_archived=1`
  returns them (`with_balance_in_brl()`). Native and the web filter with the predicates they already
  port (`isPortfolioAccount`, `activeAccounts`). The client needs the full list to apply pending
  items to balances.
- `consolidated_balance` = `consolidatedBalance()`: the sum of `balance_brl` of every
  **non-Corretora** account, archived included. A `balance_brl` of `null` (a foreign account with
  no rate today) is left out.
- `summary` is `flow[-1]` relabelled, so Início reads one object. `result` = `income − expense`
  (MonthSummary's "Resultado do mês"). `investment_net` = `invested − redeemed` ("Investido"). The
  "Investido" row shows when either term ≠ 0. `others_net` = `others_received − others_paid`. Its
  sign picks the label, and the value is shown unsigned.
- `flow[i]`: `buildMonthlyFlow()` field by field, in reais and with positive magnitudes. The chart's
  negative `expense`/`investment` are a drawing choice and stay on the client. `net` = income −
  expense − invested + redeemed + others_received − others_paid. `balance` is the month-end
  balance: banking `initial_balance` + every banking row up to the end of that month.
- `next_invoices`: `card_invoices.next_invoices()`, the same entries `/api/cc-invoices` flags
  `next` (§3). `next_closing_date` is the earliest `closing_date` of a not-closed next invoice.
  Início prints it as "fecha dd/mm".

### The rule, on the server (`services/home.py`)

`buildMonthlyFlow({transactions: bankingTransactions(all), ccExpenses, keys, openingBalance:
openingBalanceTotal(accounts)})`, line by line:

1. **The banking view** (`bankingTransactions()`). A non-TRANSFER row in a Corretora account is
   left out. A TRANSFER between two non-Corretora accounts stays a transfer, so the flow skips it.
   A TRANSFER between two Corretora accounts is left out. A bank → Corretora TRANSFER is an
   EXPENSE aporte on the bank side, and Corretora → bank is an INCOME resgate on the bank side.
   One SQL pass joins `accounts` twice, like `month_investment_flow()`.
2. **Per row**, for each month key in the window:
   - `cash` += ±amount. This only feeds `balance`.
   - It is a resgate when the row is INCOME and is either a portfolio transfer or has a
     `source_type` in `INVESTMENT_SOURCE_TYPES`. It is an aporte when the row is EXPENSE with the
     same origin.
   - Any other INCOME adds `own_amount_sql()` to `income` and the others' part to `others_received`.
   - An EXPENSE that is not an invoice payment adds the owner's part to `expense` and the others'
     part to `others_paid`. An invoice payment is `source_type` in `CC_INVOICE_PAYMENT`/`CC_AUTOPAY`
     or a category starting "Pagamento Fatura", the same set as `INVOICE_PAYMENT_SOURCE_TYPES`
     plus the `LIKE` that `month_banking_totals()` uses.
   - A row before the window adds ±amount to the opening balance.
3. **Card rows**, by `purchase_date` month, **paid and open**. A refund subtracts its full amount
   from `expense` and is never shared. A purchase adds the owner's part to `expense` and the
   others' part to `others_paid`.
4. **Opening** = Σ `initial_balance` of non-Corretora accounts, archived included, + every banking
   row before the window. `balance` runs from there.

`month_investment_flow()` already is the SQL twin of step 2's aporte/resgate for one month. The
service reuses its CASE expressions, extracted to a shared helper so the plan and Início can never
disagree on "Investido". It does **not** reuse `month_banking_totals()` for income/expense, because
the two differ today (see *Behaviour changes*, B2).

### How the web switches

- New `homeApi.get({months})` in `lib/dataApi.js` and `useHome()` in `lib/attention.js` (key
  `['inicio','home']`, shared with the bell).
- `Dashboard.jsx`: `BalanceHero`, `MonthSummary`, `NextInvoiceTile`, the "Fluxo de caixa" chart and
  stats, and "Evolução do saldo" read `useHome()`. The pending overlay applies on top (below).
- `['inicio','movimentos']` stays only for the panels this proposal does not cover (categories,
  pace, installments, invoice projection; see *Beyond the brief*). Once those move too, Início
  stops downloading the history.
- `cashFlow.js` and the money half of `transactions.js` (`consolidatedBalance`,
  `openingBalanceTotal`, `bankingTransactions`) are deleted once no screen imports them. The
  Extrato's "Saldo em contas" reads `consolidated_balance` too. Their node tests are deleted with
  them; the pytest cases below carry the same inputs.

### Pending items (offline) on top of `/api/home`

The server cannot see the phone's queue. Today a pending despesa lowers its account, the hero
**and** the month's "Saiu". To keep that, the client applies one overlay, a pure function in the
pending family (`outboxRules.js` ↔ `rules/OutboxPending.kt`, tested on both sides):

```
applyPendingToHome(home, pendingItems) → home'
  accounts             = applyPendingToAccounts(home.accounts, items)          (exists, ported)
  consolidated_balance = home.consolidated_balance + Σ pending cents of BRL non-Corretora accounts
  summary / flow[-1]   = + pending EXPENSE/INCOME of the current month (own part = whole amount;
                         a pending item is never shared); a pending TRANSFER bank → Corretora is
                         invested, Corretora → bank redeemed, bank → bank nothing; a row whose
                         account is a Corretora is left out; CARD touches nothing
  balance_estimated    = any account changed
```

That is `bankingTransactions()` + `buildMonthlyFlow()` restricted to the pending rows of one month.
It is small and testable in cents, and it is the only money arithmetic left on the client.

---

## 2. `GET /api/attention`

"Precisa de atenção": the items Início shows as cards and the bell lists, with the same `key`s, so
the dismissals on each device keep working unchanged.

**Response** (200):

```json
{
  "today": "2026-10-23",
  "items": [
    {"key": "fatura-vencida:c1|2026-10", "kind": "INVOICE_OVERDUE", "tone": "danger",
     "total": 150.00, "item_count": 2,
     "invoices": [{"card_id": "c1", "card_name": "Nubank", "invoice_month": 10, "invoice_year": 2026,
                   "due_date": "2026-10-10", "total": 150.00, "count": 2}]},
    {"key": "debito-sem-saldo:a1:2026-10-25", "kind": "AUTOPAY_SHORTFALL", "tone": "danger",
     "account_id": "a1", "account_name": "Itaú", "total": 100.00, "first_due": "2026-10-25",
     "balance": 80.00, "missing": 20.00},
    {"key": "recorrencias:r3@2026-09-01x1", "kind": "RECURRING", "tone": "info", "count": 1},
    {"key": "orcamento:2026-10:cat4", "kind": "OVER_BUDGET", "tone": "warning",
     "category_id": "cat4", "category_name": "Alimentação › Mercado", "spent": 120.00, "available": 100.00}
  ]
}
```

An `INVOICE_PAYABLE` item is `{key: "fatura-fechada:…", kind, tone: "warning", total, invoices:
[{card_id, invoice_month, invoice_year, total}]}`. The JSON keys move to snake_case
(`itemCount` → `item_count`, `accountId` → `account_id`, `categoryName` → `category_name`,
`firstDue` → `first_due`). Only field names change. **The `key` strings are byte for byte today's.**

### The rule (`services/attention.py`)

`attentionItems()`'s order and conditions, unchanged:

1. **Overdue.** One item for every open invoice whose `due_date < today` and whose signed total is
   `> 0`, sorted by due date. The item appears when Σcount > 0 and Σtotal > 0. Its key is
   `fatura-vencida:` + the sorted, comma-joined list of `<card_id>|<year>-<month>`. **The month is
   not zero-padded** (`invoiceId()` writes `2026-9`), and the server must reproduce that.
2. **Payable**, only when there is no overdue item. Take the items of each card's next invoice
   (§3), keep those with `invoice_closed`, group them per card, and keep a card when its total is
   `≥ 0`. The item appears when Σtotal > 0. Its key is `fatura-fechada:` + the same id list.
3. **Autopay shortfall**, one per account. Take cards with `autopay_account_id`, and their open
   items due between today and today + 31 days inclusive. Sum them per account and remember the
   earliest due date. Skip an account that is missing, archived or Corretora, and one whose
   `balance_brl` is null. A shortfall is `balance_brl < total`, with `missing = total − balance`.
   Items are sorted by `first_due`, and the key is `debito-sem-saldo:<account_id>:<first_due>`.
4. **Recurring.** One item when Σ`pending_count` > 0, where `pending_count` is
   `recurring_pending_count()` for each recurrence, the same as `GET /api/recurring`. The key is
   `recorrencias:` + sorted, comma-joined `<id>@<last_occurrence_date or ''>x<pending_count>`.
5. **Over budget.** `build_budget_view(today's month)` items with status `OVER`, sorted by
   `spent − available` descending. The key is `orcamento:<month>:<category_id or item id>`. The
   name is `"<parent> › <name>"` when the category has a parent.

The texts stay on the client: titles, `overdueDetail()`, and whether a value is masked. They are
ported as presentation (`rules/AttentionTexts.kt`), like the plan's flags. CLAUDE.md, "Flags are
codes plus amounts; the Portuguese text lives in `lib/monthlyPlan.js`".

### How the web switches

`useAttentionItems()` in `lib/attention.js` becomes `useQuery(['atencao'], attentionApi.list)`.
`Dashboard.jsx` reads the same hook, so the bell and Início share one request. Início's "Pagar"
opens `PayInvoiceSheet` with `item.invoices`, as it does now. `undismissedItems()` and
`addDismissed()` stay in JS, and native ports them.

---

## 3. `GET /api/cc-invoices`

Cartões' invoices per card, with totals summed on the server and the nearest invoice flagged.
`/api/home` and `/api/attention` use the same function, so all three agree.

**Response** (200):

```json
{
  "today": "2026-10-23",
  "nearest": {"card_id": "c1", "invoice_month": 11, "invoice_year": 2026},
  "open_total": 1604.60,
  "cards": [
    {
      "card_id": "c1", "card_name": "Nubank", "due_day": 10, "closing_day": 3,
      "autopay_account_id": "a1", "credit_enabled": true, "total": 1604.60,
      "invoices": [
        {
          "invoice_month": 11, "invoice_year": 2026, "key": "2026-11",
          "closing_date": "2026-11-03", "due_date": "2026-11-10",
          "closed": false, "past_due": false, "payable": false,
          "next": true, "nearest": true, "future": false,
          "total": 812.30, "item_count": 6,
          "purchases": [
            {"id": "e1", "client_id": "k1", "kind": "PURCHASE", "description": "Geladeira",
             "category": "Casa", "category_id": "cat9", "purchase_date": "2026-09-20",
             "amount": 333.34, "installment_info": "2/3", "installment_current": 2,
             "installment_total": 3, "attachment_count": 1,
             "share_mode": null, "share_person": null, "share_others_amount": null,
             "installments_open": 2, "installments_paid": 1}
          ]
        }
      ]
    }
  ]
}
```

- **Only `OPEN` rows**, as Cartões reads today (`GET /api/cc-expenses?status=OPEN`).
- A card appears when it has an open row. It is sorted by name with a case- and accent-folded key;
  the client's `localeCompare` is close but not identical. Its invoices are sorted by
  (year, month), and its purchases by description, folded the same way.
- `total` per invoice and per card is the Σ `signed_amount()` in `Decimal` (a refund subtracts). A
  negative invoice total is the "Crédito" badge.
- `past_due` = `due_date < today`. This is the "Em atraso" badge and `isPastDue()`. Unlike
  attention's overdue it has no `total > 0` condition, as today.
- `payable` = `closed && total ≥ 0`, the "Pagar" button's gating. The server still re-checks on
  `pay-invoice`.
- `next`: per card, the invoice with the earliest `due_date ≥ today`, i.e. `nextInvoices()`.
- `nearest`: across cards, the oldest `past_due` invoice whose total is `> 0`. If there is none, it
  is the first `next` invoice by due date. This is `nearestOpenInvoice()`, and it is the invoice
  Cartões expands and pays from its header. The top-level `nearest` repeats it.
- `future`: the invoice comes after the card's first not-closed invoice. This is the inline
  current/future split, so Cartões folds future invoices without porting the split.
- `purchases`: **one entry per row**. Since 035 every row has a `client_id`, so a purchase has one
  row per invoice and the old grouping key merged nothing. `installments_open` and
  `installments_paid` count the purchase's rows (`same_purchase_sql()`) by status. The delete
  confirmation's text needs them, and it then no longer fetches `/candidates` first.
- The card's `due_day` and `closing_day` are the stored ones. A debit-only card (`credit_enabled =
  0`) has no new open rows, but one switched off with open rows left would still appear, flagged.
  Cartões shows it as today.

### How the web switches

`Cartoes.jsx` reads `useQuery(['cartoes','faturas'], ccInvoicesApi.list)` in place of
`openInvoicesByCard`, `nearestOpenInvoice` and `openCreditTotal`. `paymentHint()` and
`getInvoiceStatus()` become pure mappings of the flags. `useLancamentos()` drops
`GET /api/cc-expenses?status=OPEN` once the Extrato's projections are served too (see *Beyond the
brief*). Until then it keeps the call.

---

## 4. `DELETE /api/cc-expenses/purchases/<id>`

Deletes the **open installments** of the purchase that row `<id>` belongs to, in one transaction.
`<id>` can be any of its installments, or a refund row (1/1).

**Response** (200): `{"deleted": 2, "kept_paid": 1, "ids": ["e2", "e3"]}`

- The rows come from `cc_purchase_expense_ids(conn, user, id)`, the same purchase receipts and
  sharing use. Only `status = 'OPEN'` rows are deleted, and paid ones stay (037).
- **404** "Compra nao encontrada." when the row is not the user's.
- **409** "Nenhuma parcela em aberto foi encontrada para essa compra." when every installment is
  paid. Nothing is deleted.
- Receipts go with the rows by CASCADE. The files are read before the DELETE
  (`cc_expense_attachment_names()`) and removed after the commit, as `DELETE /api/cc-expenses`
  does.
- The route sits next to `POST /api/cc-expenses/purchases` in `routes/cards.py`. It is no new
  blueprint, and `test_route_map.py` gains `("/api/cc-expenses/purchases/<item_id>", "DELETE")`.

**Web:** `handleDeleteCCPurchase` builds its confirmation from the purchase's
`installments_open`/`installments_paid` (§3), then calls
`ccExpensesApi.removePurchase(purchase.id)`. `handleDeleteRefund` uses the same call.
`purchaseInstallments()` stays for `refundPrefillAmount()` only.

---

## 5. Paging on `GET /api/transactions` (optional)

**Query:** `?limit=N` (1–500) and `&cursor=<opaque>`. **Without `limit`, nothing changes**: a bare
array, every row, today's order. With it, the response is an object:

```json
{
  "items": [ /* the same row shape, at most N */ ],
  "next_cursor": "MjAyNi0xMC0yMHwyMDI2LTEwLTIwVDEyOjAwOjAwWnx0eDQy",
  "totals": {"income": 9000.00, "expense": 3120.45, "investment": 2000.00},
  "day_totals": {"2026-10-23": -45.90, "2026-10-22": 9000.00}
}
```

- Keyset, never `OFFSET`. The order becomes `date DESC, created_at DESC, id DESC`; adding `id` only
  orders rows that tie today. The cursor is base64 of the last row's `(date, created_at, id)`.
  `next_cursor` is null on the last page. A row written while paging appears on a fresh first page
  and is never duplicated.
- `totals`: the Extrato's `statementTotals` over **the whole filtered set**, not the page. INCOME
  is income and EXPENSE is expense, except investment rows (`source_type` in
  `INVESTMENT_SOURCE_TYPES`), which go to `investment` (out − in). The Extrato does not use the
  banking view today (`04-extrato.md`, open owner question). The server keeps that until the owner
  decides.
- `day_totals`: `groupByDay()`'s INCOME − EXPENSE for every day that has a row **on this page**,
  computed over that whole day. A day split across two pages then shows the same total on both.
- Filters are the existing `transaction_filter_clause()`, unchanged.

**Web:** the Extrato's filtered list asks for `limit=200` with "Carregar mais" (TanStack
`useInfiniteQuery`). Pending rows go first, on page one only. Native does the same with lazy
loading. The unfiltered shared load (`useLancamentos()`) stays until the Extrato reads its totals
from here and its balance from `/api/home`.

---

## Behaviour changes, and what I recommend

| # | Today | With the endpoint | Recommendation |
|---|---|---|---|
| B1 | A pending (offline) item enters the hero, the accounts and the month's Entrou/Saiu/Investido | The server's figures exclude pending items | **Keep today's behaviour** with `applyPendingToHome()` (§1), a pure overlay ported on both sides. The alternative, overlaying balances only, makes "Saiu" lag the hero while offline |
| B2 | `month_banking_totals()` (the plan's "spent") counts a despesa/receita **typed in a Corretora account**. Início's Saiu/Entrou leave it out (`bankingTransactions()`) | Unchanged on both sides: `/api/home` follows Início, so the two "spent" numbers can differ by such a row | **Ask the owner.** The cleaner answer is to make the plan follow Início, so a Corretora row is never banking spending, one rule for both. It is already listed as "Corretora accounts appear in banking forms" (`findings.md`) |
| B3 | Autopay shortfall compares against balances **with pending items** applied (`useAttentionItems()`) | Against server balances only | **Accept.** It affects only an offline despesa from the autopay account in the 31-day window, and it corrects itself when the item arrives. Overlaying it would need the shortfall rule on the client again |
| B4 | Totals summed as floats (`nextInvoices`, Cartões' invoice totals, attention totals) | `Decimal`, rounded once | **Accept**, a fix. A one-cent difference was possible on long invoices |
| B5 | Foreign-currency accounts: the hero uses `balance_brl`, but the flow and the opening add their native amounts as reais (`buildMonthlyFlow` has no rate), so "Evolução do saldo" does not end at the hero | Same, for exact parity | **Keep parity now**, because the app is reais-only on screen and the owner has no foreign account. If one ever exists, convert at the movement's date in a later change |
| B6 | "Today" is the device's date | The server's `local_today()`, America/Sao_Paulo | **Accept.** `invoice_closed` already comes from the server, so the client's date and the server's could already disagree at midnight. Now it is one clock |
| B7 | Cards and purchases sorted by `localeCompare` (pt) | Python, case- and accent-folded | **Accept.** It only differs on unusual names |
| B8 | Attention items carry `detail` text (`overdueDetail()`) | Numbers only, and the client writes the text | **Accept.** The text is the same, and it is presentation |
| B9 | Deleting a purchase fetches `/candidates`, filters within one cent and the same count, then sends a list | One atomic request by `client_id`; the cent filter goes (every row has a `client_id` since 035) | **Accept.** A half-deleted purchase is no longer possible |

Nothing else the client does changes: keys, orders, conditions and amounts are today's.

## Beyond the brief (not proposed here; next proposal)

- `/api/home?months=12` already covers "Fluxo de caixa" and "Evolução do saldo". The rest of
  Início still needs the history: "Despesas por categoria" (and its grouping by name, an open
  owner question), "Ritmo de gastos", "Parcelamentos abertos", and the 6-month invoice projection.
  A second proposal (`home-panels.md`) would add them, after which Início stops calling
  `GET /api/transactions` and `GET /api/cc-expenses` altogether.
- The Extrato's projections (`projections()` in `useLancamentos.js`, untested) can come from the
  `/api/cc-invoices` totals: next month = balance − the open totals of next month's invoices.
  That is the same proposal.

---

## pytest cases

New files: `test_home.py`, `test_attention.py`, `test_cc_invoices.py`, `test_cc_purchase_delete.py`
and `test_transactions_paging.py`. Each JS test is listed with the case that carries it. A `→ stays
client` line means the JS function is presentation and keeps its node test (and gets a Kotlin port).
The case shown beside it is the server half.

### From `transactions.test.js` (10 tests)

| JS test | pytest case |
|---|---|
| a Corretora account is not saldo em conta | `test_home.py::test_corretora_is_not_saldo_em_conta`: accounts banco 1000/800, poupança 500/500, corretora 7000/5000. `consolidated_balance` is 1500, the opening of a window before any row is 1300, and `accounts` still lists all three |
| what happens inside the Corretora stays out of the banking view | `::test_rows_inside_the_corretora_stay_out`: a compra (EXPENSE, INVESTMENT_TRANSACTION) and a provento (INCOME, INVESTMENT_PROCEED) in the Corretora and a 50 mercado in banco give expense 50, income 0, invested 0, redeemed 0 |
| a transfer into the Corretora is an aporte, out of it a resgate | `::test_transfer_to_corretora_is_aporte_back_is_resgate`: banco → corretora 300 and corretora → poupança 100 give invested 300, redeemed 100, expense 0, income 0. Balance: banco −300, poupança +100 |
| transfers between banks stay transfers; between brokerages they leave | `::test_bank_to_bank_and_brokerage_to_brokerage_are_not_flow`: banco → poupança 10 and corretora → xp 10 leave every summary field at 0 and the consolidated balance unchanged |
| without a Corretora nothing changes | `::test_without_corretora_an_expense_is_an_expense`: one EXPENSE 1 in banco gives expense 1, and the consolidated balance is the sum of every account |
| the Corretora balance is summed apart | `::test_corretora_balance_is_not_in_home`: `consolidated_balance` excludes 7000. Posição's "Saldo na corretora" keeps `portfolioCashBalance()` (→ stays client until Posição's proposal) |
| a card refund subtracts from the invoice; a purchase adds | `test_cc_invoices.py::test_refund_subtracts_purchase_adds`: purchase 120.50 + refund 40 in one invoice give total 80.50, and a refund-only invoice has total −40 and is not payable. `test_home.py::test_card_refund_subtracts_from_expense_in_its_month` |
| a card purchase is its client_id: two identical rides stay two purchases | `test_cc_invoices.py::test_two_identical_rides_are_two_purchases`: two Uber 10 rows with different `client_id`s are 2 entries with total 20. `::test_installments_share_the_purchase`: 100 in 3x lists `installments_open` 3. `test_cc_purchase_delete.py::test_deletes_only_this_ride` |
| blockedRecurringMessage | → stays client (text). Server half: `test_attention.py::test_blocked_recurrence_still_counts_as_pending`, where a recurrence on an archived account counts in the RECURRING item exactly as in `GET /api/recurring`'s `pending_count` |
| investment is the origin of the row, never a category (039) | `test_home.py::test_investimento_category_is_an_ordinary_expense`: an EXPENSE with category "Investimento" is expense, an EXPENSE INVESTMENT_TRANSACTION in banco is invested, an INCOME INVESTMENT_PROCEED in banco is redeemed, and a transfer to the Corretora is invested |

### From `attentionRules.test.js` (13 tests)

| JS test | pytest case |
|---|---|
| fatura vencida: so a que passou do vencimento, somada por fatura | `test_attention.py::test_overdue_is_past_due_summed_per_invoice`: on 2026-10-18 two Oct rows (100 + 50, due 10/10) and one Nov row give one INVOICE_OVERDUE with total 150, item_count 2 and card_name "Nubank" |
| fatura fechada: uma por cartao, so as fechadas | `::test_payable_one_per_card_only_closed`: card 1 closed rows 100 + 20 and card 2 open give an INVOICE_PAYABLE whose invoices are `[(card 1, 120)]` |
| fatura fechada nao aparece junto da vencida | `::test_payable_hidden_while_an_invoice_is_overdue`: with both, only INVOICE_OVERDUE. With the overdue one paid, INVOICE_PAYABLE |
| debito automatico: a conta que nao cobre a fatura dos proximos dias | `::test_autopay_shortfall_in_the_next_31_days`: autopay into Itaú with balance 80, rows due 10/25 (100) and 12/25. On 10/18 the item has missing 20, account_name Itaú, and only the October row counts |
| a chave identifica o caso | `::test_keys_identify_the_case`: the recurring key changes with `last_occurrence_date` (after `/run`), and the budget key with the month. `category_name` "Mercado" |
| dispensar esconde so os casos dispensados | `::test_item_order_and_stable_keys`: an OVER and an OK budget plus 2 pending recurrences give `[RECURRING, OVER_BUDGET]` in that order, and two reads return the same keys. → `undismissedItems` stays client (node test kept, Kotlin port) |
| a lista de dispensados nao cresce sem fim e nao repete | → stays client (`addDismissed`, device storage). No server case: the server never sees dismissals |
| estorno abate a fatura: em credito nao e vencida nem pagavel | `::test_refund_credit_is_neither_overdue_nor_payable`: card 1 100 − 30 is overdue 70, card 2 10 − 50 is not overdue, and closed 10 − 40 is not payable. `test_cc_invoices.py::test_credit_invoice_is_past_due_not_payable` |
| proxima fatura: quem fecha antes de vencer paga a do proprio mes | `test_cc_invoices.py::test_next_closes_before_due_is_this_months`: a card closing on the 3rd, due on the 10th. On 2026-11-05, Nov (1000 + 200 closed) is `next` with total 1200, `closed`, `payable` and item_count 2, and Dec is not next. `test_home.py::test_next_invoices_match_cc_invoices` |
| proxima fatura: no dia do vencimento ainda e ela; no dia seguinte e a vencida | `test_cc_invoices.py::test_due_day_is_not_past_due`: on 11-10, Nov is next and not past_due. On 11-11, Dec is next and Nov is past_due and nearest. `test_attention.py::test_overdue_starts_the_day_after_due` |
| proxima fatura: quem fecha depois de vencer ja tem fechada a do mes seguinte | `test_cc_invoices.py::test_next_closes_after_due_is_next_months`: closing 25, due 5. On 2026-11-26, Dec/2026 is next, total 300, closed |
| proxima fatura: uma por cartao, pela ordem do vencimento; paga nao conta | `::test_one_next_per_card_by_due_date_paid_ignored`: the Nubank Nov invoice was paid through `pay-invoice`. On 11-12 the next invoices are `[(late, 12, 300), (nubank, 12, 80)]` in that order |
| fatura mais proxima (tela Cartoes) | `::test_nearest_overdue_first_else_first_next`: on 11-05 nearest is Nubank Nov. On 11-20 it is Nubank Nov (overdue). With no open rows, `nearest` is null |

Extra cases these JS tests never covered:

- `test_attention.py::test_overdue_key_month_is_not_zero_padded`: September is `fatura-vencida:c1|2026-9`.
- `::test_shortfall_skips_archived_corretora_and_no_rate_accounts`: one case for each of the three skips.
- `::test_shortfall_window_is_inclusive`: due exactly today + 31 counts, + 32 does not.
- `::test_over_budget_sorted_by_overspend_with_parent_name`: "Alimentação › Mercado".
- `::test_user_isolation`: another user's invoices, accounts and recurrences never appear. The same case goes in each new file.
- `test_cc_invoices.py::test_future_is_after_first_not_closed`, `::test_installment_counts`, `::test_sorted_by_card_name_then_month_then_description`.

### New: `cashFlow.js` (no node test today)

`test_home.py`, every rule of `buildMonthlyFlow()`. The month is frozen at 2026-10 unless stated.

1. `test_income_and_expense_are_the_owners_part`: INCOME 1000 with SPLIT others 400 gives income 600 and others_received 400. EXPENSE 100 OTHERS gives expense 0 and others_paid 100.
2. `test_card_purchase_counts_in_purchase_month_not_invoice`: a 300 purchase on 2026-10-28 in the Nov invoice is expense 300 in Oct and 0 in Nov.
3. `test_card_installments_count_in_full_in_purchase_month`: 300 in 3x bought in October gives an October expense of 300, and Nov/Dec get nothing.
4. `test_paid_card_rows_still_count`: a paid invoice's purchases stay in their month's expense.
5. `test_card_share_split_proportionally`: a SPLIT purchase across installments gives the owner's part in expense and the rest in others_paid.
6. `test_invoice_payment_is_never_expense`: `CC_INVOICE_PAYMENT`, `CC_AUTOPAY`, and a typed EXPENSE with category "Pagamento Fatura Nubank" give expense 0 while the balance still drops.
7. `test_transfer_between_banks_is_not_flow`.
8. `test_result_is_income_minus_expense`: `result` excludes investment and others.
9. `test_net_includes_investment_and_others`: net = income − expense − invested + redeemed + others_received − others_paid.
10. `test_month_end_balance_ends_at_consolidated`: with `months=12`, `flow[-1].balance == consolidated_balance` for BRL accounts, archived included.
11. `test_opening_includes_rows_before_the_window`: a row from 13 months ago moves every balance in the window but no month's income or expense.
12. `test_archived_account_rows_still_count`.
13. `test_empty_month_is_zero_not_missing`: `months=3` with activity in only one month gives three entries, two of them all zero.
14. `test_months_param_bounds`: 0, 25 and "abc" give 400, and the default is 1.
15. `test_cents_exact`: 0.10 + 0.20 (three of them) gives expense 0.60 exactly, and so does 33.33 × 3 + 0.01.
16. `test_autopay_debited_today_is_in_home`: `apply_due_autopay()` runs before the read. The payment lowers the balance but not the expense.
17. `test_paid_provento_in_bank_account_is_redeemed`: `apply_paid_proceeds()` runs, and an INVESTMENT_PROCEED row in a non-Corretora account is redeemed, not income.
18. `test_investido_matches_monthly_plan`: for the same month, `summary.invested − summary.redeemed` equals the plan's `invested` (`month_investment_flow()`).

### `DELETE /api/cc-expenses/purchases/<id>`

`test_cc_purchase_delete.py`:

- `test_deletes_open_installments_keeps_paid`: 3x with the first invoice paid gives deleted 2 and kept_paid 1, the paid row stays, and the payment stays.
- `test_any_installment_id_works`: deleting through the 3rd installment's id gives the same result.
- `test_all_paid_is_409_and_writes_nothing`.
- `test_another_purchase_is_untouched`: identical rides, different `client_id`.
- `test_legacy_purchase_by_legacy_client_id`: a `legacy:<id>` purchase from 035.
- `test_refund_row`: deletes the refund (1/1).
- `test_receipt_files_removed_after_commit`: the receipt file of an open installment goes, and a paid installment's receipt stays.
- `test_other_user_404`.
- `test_route_map.py`: the new row.

### Paging

`test_transactions_paging.py`:

- `test_without_limit_unchanged`: a bare array, same rows, same order.
- `test_pages_cover_everything_once`: 7 rows with `limit=3` give 3 + 3 + 1, no duplicate, the last `next_cursor` null, and the same set as without `limit`.
- `test_ties_on_date_and_created_at_are_ordered_by_id`.
- `test_filters_apply_to_pages_and_totals`: category, account and search, with `totals` over the whole filter, not the page.
- `test_totals_keep_investment_apart`: investment out − in, the extrato's rule.
- `test_day_totals_cover_a_split_day`: a day split across pages has the same total on both.
- `test_bad_limit_and_cursor_are_400`: 0, 501, "x", and a tampered cursor.
- `test_user_isolation`.

## Native, once these exist

- Início: `GET /api/home?months=12` + `GET /api/attention` + `applyPendingToHome()` + the dismissals.
  No history download.
- The bell: `GET /api/attention`.
- Cartões: `GET /api/cc-invoices` + `DELETE /api/cc-expenses/purchases/<id>`. Nothing from
  `attentionRules.js` is ported.
- `rules-port.md` then reads "endpoint, done" for `cashFlow.js` and for the money of
  `transactions.js` and `attentionRules.js`. What is left to port: `isPortfolioAccount`,
  `activeAccounts`, `cardSignedAmount` (only if a native screen still sums card rows), the attention
  texts and dismissals, and `applyPendingToHome()`.

## Order of implementation (once approved)

1. `services/card_invoices.py` + `GET /api/cc-invoices` + its tests. Cartões on the web switches.
   This is the smallest change and shows the shape.
2. `DELETE /api/cc-expenses/purchases/<id>` + its tests. Cartões' delete switches.
3. `services/home.py` + `GET /api/home` + the cashFlow tests. Then `applyPendingToHome()` in JS and
   Kotlin. Início's hero, summary, tile and flow switch.
4. `services/attention.py` + `GET /api/attention` + its tests. The bell and Início switch.
5. Paging, when the Extrato is built natively (step 4 of `migration-order.md`).

Each step is one PR, with the web switched in the same PR, so no endpoint exists without a reader.
Before switching a screen, a parity check should run the JS function and the endpoint over the
same seeded database and compare every number. This would be a one-off script, not kept.
