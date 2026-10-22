# Início — native spec

| | |
|---|---|
| Migration order | 3 (see `../migration-order.md`) |
| Status | Not started |
| React source | `frontend/src/pages/Dashboard.jsx` (with its inline `BalanceHero`, `MonthSummary`, `NextInvoiceTile`, `NeedsAttention`, `CategoryList`, `BudgetStrip`, `FlowTooltip`, `InlineStat`, `DashboardSkeleton`, `buildSpending()`), `components/Attention.jsx` (`AttentionCards`), `components/PayInvoiceSheet.jsx`, `components/BudgetProgress.jsx`, `components/charts.jsx` (`DonutChart`, `CHART`, `FLOW`, `SERIES`, `OTHER_COLOR`), `lib/attention.js`, `lib/attentionRules.js`, `lib/transactions.js`, `lib/cashFlow.js`, `lib/sharing.js` (`ownAmount()`, `othersAmount()`), `lib/outboxRules.js` (`applyPendingToAccounts()`, `pendingAsTransactions()`), `lib/format.js`, `lib/privacy.js` |
| Route(s) | `/inicio` (also `/dashboard` → redirect) |
| Endpoints | `GET /api/transactions`, `GET /api/cc-expenses`, `GET /api/accounts?include_archived=1`, `GET /api/credit-cards`, `GET /api/recurring`, `GET /api/budgets?month=AAAA-MM`, `POST /api/recurring/run`, `POST /api/cc-expenses/pay-invoice` |
| Client rules | `lib/transactions.js` (`consolidatedBalance()`, `accountBalanceBrl()`, `bankingAccounts()`, `activeAccounts()`, `openingBalanceTotal()`, `bankingTransactions()`, `isInvestmentOutflow/Inflow()`, `cardSignedAmount()`, `cardPurchaseKey()`, `blockedRecurringMessage()`), `lib/cashFlow.js` (`buildMonthlyFlow()`, `isInvoicePayment()`), `lib/attentionRules.js` (`nextInvoices()`, `payableInvoices()`, `overdueInvoices()`, `overdueDetail()`, `autopayShortfalls()`, `attentionItems()`, `undismissedItems()`, `addDismissed()`, `invoiceMonthKey()`, `isPastDue()`), `lib/attention.js` (dismissals), inline in `Dashboard.jsx` (spending, pace, categories, projection, installments, flow averages) |

## What it is for
The screen the owner opens to see how much money is in the bank accounts, how the month is going
(Resultado, Entrou, Saiu, Investido), what the next card invoice is and what needs action now
(overdue or closed invoice, autopay without balance, overdue recurrences, a category over budget).
It is the banking area only, in reais: the portfolio never appears, so invested money is never read
as money to spend.

## What it shows
Phone, top to bottom (desktop places hero 8 cols + summary/invoice 4 cols, then 3/2-col panels).

1. **Error banner** (rose) when the movements query fails: "Movimentações indisponíveis no momento.
   Detalhe: <message>" (fallback "Não foi possível carregar movimentações e faturas."). Also used
   for the recurring-run / blocked messages.
2. **Estimate banner** (sky/info) when the outbox has `pending` items that touch accounts (not
   `CARD`): "Saldo estimado: 1 lançamento guardado neste aparelho ainda não chegou ao servidor." /
   "Saldo estimado: N lançamentos guardados neste aparelho ainda não chegaram ao servidor."
3. **Saldo em conta** (`BalanceHero`, `bg-brand` block, `text-brand-ink`): heading "Saldo em
   conta", pill with the month ("Outubro de 2026", sentence case of `monthLabel()`); the big number
   = `consolidatedBalance(allAccounts)` (banking accounts incl. archived, each by `balance_brl`,
   foreign without rate skipped), animated, fitted (38→24 px on phone), **masked** `R$ ••••••`.
   Below, a horizontally scrolling strip of **active banking accounts** (`bankingAccounts(activeAccounts())`,
   Corretora excluded): name + `accountBalanceBrl()` (**masked**; negative in `text-rose-200`;
   `null` → "sem câmbio hoje"). Balances already include pending outbox items.
4. **Resumo do mês** (`MonthSummary`) — the current month of `buildMonthlyFlow()`; **every value
   masked in privacy mode, and Resultado's colour too**:
   - "Resultado do mês" = income − expense, `formatSignedCurrency` (+/−), emerald ≥ 0, rose < 0;
     hint "Suas receitas menos suas despesas".
   - "Entrou" (hint "Receitas do mês"), "Saiu" (hint "Despesas e compras no cartão").
   - "Investido" = invested − redeemed, only when either ≠ 0; hint "Aportes R$ X · Resgates R$ Y".
   - Others' net, only when ≠ 0: label "Você pagou para outras pessoas" (< 0) or "Outras pessoas te
     pagaram" (> 0), value unsigned, hint link "Ver em A receber" → `/lancamentos/a-receber`.
5. **Next invoice tile** (`NextInvoiceTile`, taps → `/lancamentos/cartoes`): label "Fatura de
   <mês de aaaa>" (one month) / "Próximas faturas" (several) / "Próxima fatura" (none); total =
   sum of `nextInvoices()` totals (**not masked**); right side badge "Fechada" (warning) when any is
   payable, else "fecha dd/mm" (earliest `invoice_closing_date` of a not-closed next-invoice item).
6. **Precisa de atenção · N** (only with undismissed items): an X ("Dispensar avisos") dismisses
   every item shown → toast "Avisos dispensados. Eles continuam no sino, no topo da tela." (info).
   One card per item (icon by kind and tone, title, detail; texts in `00-shell.md`). Actions:
   `INVOICE_OVERDUE` → "Pagar" (opens the pay sheet for all overdue invoices), `INVOICE_PAYABLE` →
   "Pagar" (pay sheet for the payable next invoices), `RECURRING` → "Lançar" (runs recurrences;
   its link "Ver recorrentes" stays in the detail); others → link ("Ver faturas", "Ver orçamento").
7. **Fluxo de caixa** (title links to the Extrato): description "Receitas e despesas dos últimos 12
   meses." (or "…e investimentos (aportes menos resgates)…") + "Compras no cartão entram no mês da
   compra; pagamento de fatura e transferências entre contas não entram." (+ "O que foi de outras
   pessoas fica à parte."). Stats (not masked): "Média de receitas", "Média de despesas", "Média
   investida"/"Média resgatada" (only with investment), "Taxa de poupança" ((income − expense) /
   income, 1 decimal, "—" without income; rose < 0 else emerald) — averages over months with any
   movement. Chart: 12 monthly stacked bars (income up, expense down, investment net, others net) +
   "Resultado" line; legend "Receitas", "Despesas", "Investimentos", "Outras pessoas", "Resultado".
   Empty: "Sem movimentações" / "O fluxo aparece assim que houver receitas ou despesas lançadas."
8. **Despesas por categoria** (links to Orçamento): "Mês atual. A seta compara com o mês passado
   inteiro." Donut ("No mês") + list sorted by value: colour dot (top 5 coloured, rest grey), name,
   delta badge vs last month (inverse: up is bad), value, bar share, "conta" / "cartão" / "NN%
   conta". Empty: "Nenhuma despesa no mês".
9. **Orçamento do mês** (`BudgetStrip`, only when the month has budget items): "R$ gasto de R$
   disponível" (`totals.spent` / `totals.available`), bar, "Restam R$ X" or "Passou R$ X do planejado"
   (rose), status badge "No plano" / "Perto do limite" / "Estourou"; up to 4 OVER/WARNING categories
   ("Pai › Categoria", spent / available, bar), "+N categoria(s) perto do limite ou acima", or "As N
   categorias com orçamento estão no plano.".
10. **Próximas faturas** (links to Cartões): header total = next-invoice total; bar chart of 6
    invoice months from the first next-invoice month (open items, overdue excluded, refunds
    subtract), next months highlighted; "Em destaque, a fatura de <mês>." / "…a próxima fatura de cada
    cartão."; info "N lançamento(s) em aberto" / "O pagamento lança uma despesa na conta e baixa os
    itens da fatura."; list of next-invoice items (description, card · installment, amount); "A
    fatura fecha em dd/mm/aaaa; o pagamento é liberado depois do fechamento." when nothing payable;
    button "Pagar fatura" (disabled without a payable invoice). Empty: "Nenhuma fatura aberta".
11. **Parcelamentos abertos**: badge = Σ remaining; one card per open multi-installment purchase
    (`cardPurchaseKey()`): description, card, "Nx de R$ Y", remaining "R$ Z" "Restante", progress
    "p/t pagas". Empty: "Sem parcelamentos".
12. **Ritmo de gastos**: cumulative daily spending this month vs the average of the previous 3
    months that had spending; "R$ X acima/abaixo do que você costuma gastar até o dia D" (rose above,
    emerald below) or "Na média"; "Um mês inteiro fecha, em média, em R$ X."; stats per month; line
    chart with a "hoje" marker. Not masked.
13. **Evolução do saldo**: area chart of month-end `balance` from `buildMonthlyFlow()`; badge with
    the consolidated balance (**masked**, rose badge if negative); axis and tooltip **masked**.

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Pay overdue invoices | Atenção › "Pagar" | `PayInvoiceSheet`, then one `POST /api/cc-expenses/pay-invoice` `{card_id, invoice_month, invoice_year, account_id?}` per invoice, sequentially | toast "Fatura paga — R$ X debitado." / "N faturas pagas — R$ X debitado."; sheet error stays on failure (some may have been paid) | refused (network message) |
| Pay closed next invoices | Atenção "Pagar" or Próximas faturas "Pagar fatura" | same | same | refused |
| Run recurrences | Atenção › "Lançar" | `POST /api/recurring/run` `{}` → `{created, blocked[]}` | toast "N lançamento(s) recorrente(s) gerado(s)." (success) or "Nada pendente: todos os lançamentos recorrentes já estão em dia." (info); `blocked` → `blockedRecurringMessage()` in the error banner | refused |
| Dismiss attention | X | none (localStorage) | toast above | works |
| Open a panel's screen | panel titles, tile | navigation | — | — |

Pay sheet (`PayInvoiceSheet`, `allowPerCard`): title "Pagar fatura" / "Pagar faturas" / "Pagar
fatura vencida" / "Pagar N faturas vencidas"; description "A fatura fechada que vence a seguir." /
"N faturas fechadas, a próxima de cada cartão." / `overdueDetail()`; field "Debitar da conta":
"Conta de cada cartão" (empty value: server uses the card's autopay account, else the default;
hint "Cada fatura sai da conta do débito automático do cartão, ou da conta padrão.") + active
accounts "<nome> (padrão) · R$ saldo" (balance hidden in privacy mode and for a Corretora); warning
"O saldo de <conta> (R$ X) não cobre a fatura; a conta ficará negativa."; buttons "Cancelar",
"Pagar R$ X". Server refusals: 409 still open (`ensure_invoice_closed()` message), 409 "A fatura
<mm/aaaa> ficou com credito de estorno; ele abate a proxima fatura.", 409 "Nao ha itens em aberto
nesta fatura.", 404 "Cartao nao encontrado.", 400 account messages.

## Data
Four independent queries (one failing does not hide the others) + the outbox. Today's keys are
shared with the bell (`lib/attention.js`); any write invalidates all; `staleTime` 30 s.

| Query key | Request | Fields used |
|---|---|---|
| `['inicio','movimentos']` | `GET /api/transactions` (no filter: **every row ever**), `GET /api/cc-expenses` (**every row**, paid included), `GET /api/accounts?include_archived=1` | transactions: `type`, `amount`, `date`, `category`, `source_type`, `account_id`, `transfer_account_id`, `share_mode`, `share_others_amount`. cc rows: `status`, `kind`, `amount`, `purchase_date`, `client_id`, `card_id`, `credit_cards.name`, `description`, `category`, `installment_info`, `invoice_month`, `invoice_year`, `invoice_due_date`, `invoice_closing_date`, `invoice_closed` (server-computed), `share_*`. accounts: `id`, `name`, `type`, `archived_at`, `is_default`, `currency`, `balance`, `balance_brl`, `initial_balance` |
| `['inicio','cartoes']` | `GET /api/credit-cards` | `id`, `autopay_account_id` |
| `['inicio','recorrencias']` | `GET /api/recurring` | `items[].id`, `pending_count`, `last_occurrence_date` |
| `['inicio','orcamento', AAAA-MM]` | `GET /api/budgets?month=` | `month`; `items[]`: `id`, `category_id`, `category_name`, `parent_name`, `spent`, `available`, `percent`, `status` (`OK`/`WARNING`/`OVER`/`NEEDS_INCOME`); `totals.available`, `totals.spent`, `totals.remaining` |
| outbox | `useOutbox()` (native: `OutboxStore.all()`) | `pending` items → `applyPendingToAccounts()` (balances, `balance_estimated`) and `pendingAsTransactions()` (flow rows) |

Reads write on the server: `/api/accounts` and `/api/transactions` materialize autopay
(`apply_due_autopay()`) and paid proventos (`apply_paid_proceeds()`); `/api/cc-expenses` and
`/api/credit-cards` materialize autopay only.

## Client rules
**Candidates for an endpoint** (all are money rules and Início downloads the whole history to run
them; a single `GET /api/home?month=` — proposal, does not exist — returning balance, month summary,
next invoices, attention items, flow, categories, projection, installments and pace would replace
four queries and ~1000 lines of client logic; native keeps only the pending-item overlay):

- **`consolidatedBalance()` / `accountBalanceBrl()` / `bankingAccounts()` / `openingBalanceTotal()`**
  (`lib/transactions.js`, tested in `transactions.test.js`): sum of `balance_brl` of non-BROKERAGE
  accounts incl. archived. **Endpoint** (the server already computes each balance; add the total).
- **`bankingTransactions()`** (tested): drops rows inside a Corretora; a transfer bank → Corretora
  becomes an EXPENSE "Aporte" (`portfolio_transfer`), back an INCOME "Resgate". **Endpoint**;
  `month_investment_flow()` in `services/monthly_plan.py` is already its SQL twin for one month.
- **`buildMonthlyFlow()`** (`lib/cashFlow.js`, tested only through `sharing.test.js`): per month
  income/expense (owner's part, `ownAmount()`), invested/redeemed, othersPaid/Received, net and
  month-end balance (opening = banking `initial_balance` + earlier rows). Card purchases count in the
  purchase month (refund subtracts), invoice payments (`CC_INVOICE_PAYMENT`, `CC_AUTOPAY`, or
  category starting "Pagamento Fatura") never. **Endpoint**.
- **`attentionRules.js`** (tested, `attentionRules.test.js`): `nextInvoices()` (per card, open
  invoice with the earliest `invoice_due_date` ≥ today), `payableInvoices()` (closed, total ≥ 0),
  `overdueInvoices()` (due date < today, total > 0), `autopayShortfalls()` (autopay invoices due
  within 31 days vs the account's BRL balance; Corretora/archived/no-rate skipped),
  `attentionItems()` (order: overdue; payable only without overdue; shortfalls; recurring; over
  budget; each with a case `key`). **Endpoint** (`GET /api/attention`, shared with the bell); keep
  the `key` format so per-device dismissals keep working.
- **Inline, untested** in `Dashboard.jsx`: `buildSpending()` (by day and by category **name** —
  "Outros" root and "Lazer › Outros" merge), the pace (3-month baseline, months with zero spending
  excluded), `categoryBreakdown` (delta vs previous month), `invoiceProjection` (6 invoice months,
  overdue excluded), `groupedInstallmentExpenses`, `flowSummary` (averages over active months,
  savings rate), next closing date. **Endpoint**; if ported instead, write tests first.

**Stays on the phone (port)**:
- **Pending overlay** — `outboxRules.js` `pendingAccountDeltas()` / `applyPendingToAccounts()` /
  `pendingAsTransactions()` (tested in `outboxRules.test.js`: expense out, income in, transfer moves
  both and leaves the consolidated, card pending touches nothing, missing account → default,
  `needs_attention` excluded, cents exact, foreign account's `balance_brl` untouched). Not in
  `OutboxRules.java` yet: **port** with the same cases; the queue is local, no endpoint can see it.
- **Dismissals** — `lib/attention.js` (localStorage `@financeMVP:attentionDismissed`) +
  `addDismissed()` (keeps the last 200, tested) / `undismissedItems()`. **Port** per device.
- **Budget status of the strip** — `BudgetProgress.jsx` `budgetStatus()` recomputes the overall
  status from totals (≥ 80 % = WARNING); items use the server's `status`. Prefer a server total
  status.

## States
- **Loading**: `DashboardSkeleton` (hero 56, summary, tile, two panels) until movements arrive;
  cards/recurring/budget failing only hide their parts.
- **Empty**: each panel has its empty state (above); the hero shows R$ 0,00.
- **Error**: rose banner; the rest renders from what loaded.
- **Offline**: the persisted cache (≤ 14 days) renders everything; pending items enter balances and
  the month with the "Saldo estimado" banner; pay and "Lançar" fail with the network message.
- **Privacy mode**: masks the hero total, account balances, all of Resumo do mês (and Resultado's
  colour), Evolução do saldo (badge, axis, tooltip), the two shortfall values. Invoices, flow,
  categories, budget, installments and pace stay visible.
- **Light/dark**: tokens only; charts take `CHART`/`FLOW`/`SERIES` colours.

## Conventions that apply
- **"Início is the banking area only, and in reais"**: no portfolio; aportes/resgates apart.
- **"Consolidated balance = sum of `/api/accounts` balances"** (Known sharp edges), with archived.
- **"Investments and banking are separate areas…"**: Corretora balance only in Investimentos.
- **"Investimento is not a category"**: aporte/resgate by origin, never by category name.
- **"Transfers are one row, not two"**: flow skips `TRANSFER`.
- **"Budget spent (decision 1)"**: card purchases in full in the purchase month; invoice payments never.
- **"Whose expense it is"**: only the owner's part counts; "Outras pessoas" apart.
- **"A card refund is a credit row"**: sums go through `cardSignedAmount()`.
- **"The next invoice is per card, by due date, never 'next month's'"** and **"An invoice is paid
  only once it has closed"**: use `invoice_due_date` / `invoice_closed` from the server.
- **"'Precisa de atenção' lives in two places"**: Início's dismissals never hide the bell's items.
- **"'Disponível por dia' lives in Planejar › Orçamento, not Início"**.
- **"A recurrence is a template, not money"**: "Lançar" = `/run`, idempotent.

## Native-only improvements
- Instant open from the last good payload (Room/DataStore), refresh behind.
- Pull to refresh; swipe the attention card to dismiss it (same `key`).
- Home-screen widget (Jetpack Glance): consolidated balance (respecting privacy mode) and the next
  invoice; launcher shortcut to "+ Novo".

## Acceptance
- [ ] The hero equals the sum of the non-Corretora account balances in Ajustes › Contas.
- [ ] A Corretora account never appears in the strip; a transfer to it shows as "Investido".
- [ ] Resumo do mês matches the web Início for the same day, sharing included.
- [ ] A pending (offline) despesa lowers its account and shows the "Saldo estimado" banner.
- [ ] A card that closes on the 3rd and is due on the 10th shows this month's invoice as next.
- [ ] Overdue invoice → card "Fatura vencida", "Pagar" pays it and the card disappears.
- [ ] Dismissing hides the cards on this phone only; the bell still lists them; a new case returns.
- [ ] "Lançar" with an archived-account recurrence shows the blocked message.
- [ ] The eye masks exactly the values listed under "Privacy mode".

## Desktop
Keep and widen: hero + summary + next invoice in one row, then flow/categories and invoices/
installments side by side (as today at `xl`), plus room for analysis (12-month table under the flow,
category drill-down to the Extrato). Drop the horizontal account strip in favour of a grid.
