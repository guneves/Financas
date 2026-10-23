# Início — native spec

| | |
|---|---|
| Migration order | 3 (see `../migration-order.md`) |
| Status | Built 2026-10-23 on `claude/wizardly-faraday-cbx3mb` (native-level 5, PR #38): `ui/home/`, the bell, privacy mirrored both ways, `ui/charts/`; CI green, parity review clean after two fix rounds; waiting for the owner's phone check and the merge. Out of scope natively: Despesas por categoria, Ritmo de gastos, Próximas faturas (projection) and Parcelamentos abertos — one row "Categorias, ritmo e parcelamentos" opens the web Início (`/inicio?web=1`) |
| React source | `frontend/src/pages/Dashboard.jsx` (with its inline `BalanceHero`, `MonthSummary`, `NextInvoiceTile`, `NeedsAttention`, `CategoryList`, `BudgetStrip`, `FlowTooltip`, `InlineStat`, `DashboardSkeleton`, `buildSpending()`), `components/Attention.jsx` (`AttentionCards`), `components/PayInvoiceSheet.jsx`, `components/BudgetProgress.jsx`, `components/charts.jsx` (`DonutChart`, `CHART`, `FLOW`, `SERIES`, `OTHER_COLOR`), `lib/attention.js`, `lib/attentionRules.js`, `lib/transactions.js`, `lib/cashFlow.js`, `lib/sharing.js` (`ownAmount()`, `othersAmount()`), `lib/outboxRules.js` (`applyPendingToAccounts()`, `pendingAsTransactions()`), `lib/format.js`, `lib/privacy.js` |
| Route(s) | `/inicio` (also `/dashboard` → redirect) |
| Endpoints | Native: `GET /api/home?months=12`, `GET /api/attention`, `GET /api/budgets?month=AAAA-MM`, `GET /api/inbox/count` (the Aprovar pill), `POST /api/cc-expenses/pay-invoice`, `POST /api/recurring/run`. The web Início (`?web=1`, and the browser) also reads `GET /api/transactions`, `GET /api/cc-expenses`, `GET /api/accounts?include_archived=1` for the history panels |
| Client rules | Ported (Kotlin, JVM-tested with the node cases): `lib/homeFlow.js` → `rules/HomeFlow.kt` (flowPoint, flowSummary, savingsRateText; moved out of `Dashboard.jsx` in this step), `lib/chartFormat.js` → `HomeFlow.compactAxis`, `lib/attentionRules.js` → `rules/AttentionRules.kt` (overdueDetail, attentionText, attentionLink, bellBadge/bellLabel, undismissedItems, addDismissed; the texts moved out of `Attention.jsx`), `applyPendingToHome` (`rules/OutboxPending.kt`) fed by `rules/OutboxItems.kt` (OutboxStore JSON → PendingItem), `blockedRecurringMessage` and `budgetStatus` → `rules/HomeRules.kt`. The rest of the old list moved to the server in session 6 |

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
Native (`ui/home/HomeViewModel.kt`, `data/HomeRepository.kt`): three independent reads through
`CachedReader` (cache first, then the network; one failing hides nothing else; "atualizado às HH:MM"
while the copy shown is the stored one), re-read on every resume of the screen and by pull to refresh:

| Read | Request | Fields used |
|---|---|---|
| home | `GET /api/home?months=12` (as `useHome()`) | `consolidated_balance`, `accounts[]` (`id`, `name`, `type`, `archived_at`, `is_default`, `currency`, `balance`, `balance_brl`), `summary` (`income`, `expense`, `invested`, `redeemed`, `others_net`), `flow[]` (every field), `next_invoices[]` (`card_id`, `invoice_month`, `invoice_year`, `payable`, `total`), `next_invoices_total`, `next_closing_date` |
| attention | `GET /api/attention` | `items[]`: `key`, `kind`, `tone`, `total`, `item_count`, `invoices[]` (`card_id`, `card_name`, `invoice_month`, `invoice_year`, `due_date`, `total`), `account_name`, `balance`, `missing`, `first_due`, `count`, `category_name`, `spent`, `available` |
| budget | `GET /api/budgets?month=<device month>` | `items[]` (`id`, `category_name`, `parent_name`, `spent`, `available`, `percent`, `status`), `totals` (`available`, `spent`, `remaining`) |
| outbox | `OutboxStore.all()` → `OutboxItems.forUser(…, session user)` | `pending` non-`CARD` items → `applyPendingToHome()` (accounts, Saldo em contas, every month of the flow, `summary`); the "Saldo estimado" banner counts them |

Dismissals: native keeps its own list in SharedPreferences (`financas_attention`, `dismissed`, the
same keys, last 200); the web's stays in localStorage. They are separate stores on purpose: hiding a
card in the native Início does not hide it in the web Início (`?web=1`) and vice versa. The bell
always lists every item.

Privacy: `ShellPrefs.valuesHidden` (`financas_shell`, `values_hidden`). The web pushes each toggle
(`Shell.setValuesHidden`) and, on start and on every `resume`, adopts what native stored
(`Shell.getValuesHidden`, `lib/nativeApp.js`); native's eye writes the same key. An older APK
rejects both calls and the web keeps its own mode.

Navigation: the web route `/inicio` is `NativePage stay`: it opens the native page and the WebView
stays on `/inicio` drawing nothing; native links (Cartões, Extrato, A receber, Orçamento,
Recorrentes, Ajustes, the bottom tabs) finish the Activity with `navigate`; `/inicio?web=1` is the
React page (also what "Entrar novamente" opens after a 401). With no WebView listening (the
process was recreated with native Início on top) the link's route is stored
(`NativeScreens.takePendingRoute`, valid 2 min) and the web goes straight to it on start. Native back on Início minimizes; "+"
opens the native "+ Novo"; the Aprovar pill opens native Aprovar on top.

## Client rules
See the header row. All money (balances, the month, next invoices, attention items, budget totals)
comes from the server; the phone only overlays its own pending items and formats. Two deliberate
differences from the web, both privacy fixes: a negative account in the hero strip and the Evolução
do saldo badge are not coloured rose while values are hidden (the web leaks the sign there).

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

### Comparing native and web on the same data
Both read the same server, so the same account at the same minute must show the same numbers.

1. Get the APK with native Início: before the merge, build this branch on the PC
   (`.\mobile\build-apk.ps1`, installs over the real app and keeps its data); after the merge, the
   debug APK from `/apk/financas-debug.apk` (installs beside it, log in once).
2. Send or discard every pending item first (Pendentes pill on the web), and open the eye on both:
   a pending item or a hidden value is a legitimate difference.
3. On the PC, print the server's numbers with the screen's labels:
   `.\.venv\Scripts\python.exe mobile\inicio-snapshot.py --url https://<server>.<tailnet>.ts.net --email <email>`
   (GETs only; the password is asked, or `FINANCAS_PASSWORD`). It lists Saldo em conta and each
   account, Resumo do mês, the next invoice(s), every attention item (the bell's count), the
   Orçamento strip and the 12 months of the flow with each month-end balance.
4. Open the native Início on the phone and the web Início in a browser
   (`https://<server>…/inicio`, the desktop or the phone's browser). Tick each value against the
   printout: hero, each account chip, the four or five Resumo lines, the invoice tile (label, total,
   "Fechada"/"fecha dd/mm"), the attention cards and the bell's count, the Orçamento strip, the
   flow's averages and taxa de poupança, and a few months of Evolução do saldo (tap a bar/point).
5. Then the overlay: airplane mode, one despesa through "+ Novo" on the phone → the account and the
   hero drop by it and "Saldo estimado: 1 lançamento…" appears; reconnect, it is sent, the banner
   goes and the numbers equal the printout again (run it again).

## Desktop
Keep and widen: hero + summary + next invoice in one row, then flow/categories and invoices/
installments side by side (as today at `xl`), plus room for analysis (12-month table under the flow,
category drill-down to the Extrato). Drop the horizontal account strip in favour of a grid.
