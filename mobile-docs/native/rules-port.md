# Client rules: port or endpoint

The React app computes some things itself, in `frontend/src/lib/` (pure modules, most with
`node --test` files) and a few inline in components. A native screen needs the same answers. For
each rule there are two ways:

- **Port**: rewrite it in Kotlin (`core/` or `rules/`) with **the same test cases** as its
  `*.test.js` (agent `rule-porter`). Both copies then live on; a change to one is a change to the
  other, with a test on each side — the pattern `OutboxRules.java` already follows.
- **Endpoint**: move it to the server, so web and native both read the answer. One copy, tested by
  pytest. Costs a backend change and, for the web, switching the screen to the new field.

**Default: endpoint when the rule is about money** (a balance, a total, what is overdue, what was
spent), **port when it is about presentation or input** (formatting, parsing, which form fields
show, labels). The server already owns every heavy money rule (invoices, plan, budgets, tax,
portfolio); the client rules below are the remaining ones.

## The modules

| Module | Tests | Used by (screens) | Decision | Notes |
|---|---|---|---|---|
| `format.js` | yes | every screen | **Port** (step 1) — `core/` | `formatCurrency`, `formatSignedCurrency`, `formatPercent`, `formatQuantity`, dates (`parseLocalDate`, `formatDateBR`, `getLocalDateString`, `monthKey`, `monthLabel`, `shiftMonth`). pt-BR. |
| money input parsing (`parseMoneyInput` / `moneyInputValue` in `monthlyPlan.js`) | yes | every form | **Port** (step 1) — `core/` | Comma decimal, dot thousands; CLAUDE.md "An import is idempotent by construction" describes the same convention on the server. |
| `outboxRules.js` | yes | "+ Novo", balances with pending items | **Ported** — send rules in `outbox/OutboxRules.java`; the pending-balance rules (`pendingAccountDeltas`, `applyPendingToAccounts`, `pendingAsTransactions`, `countByStatus`) in `rules/OutboxPending.kt` (2026-10-23, the node cases) | No endpoint can do the pending overlay: the queue lives on the phone. Still to add, both sides: `applyPendingToHome()` once `/api/home` exists (`proposals/home-attention-invoices.md` §1). `OutboxPending.kt` rounds HALF_UP from the decimal text; JS `Math.round` on floats can differ on a third decimal (1.005), which form input never has. |
| `cardFunctions.js` | yes | "+ Novo", Ajustes › Cartões, Cartões | **Port** (step 1) — `rules/` | Which methods a card offers (crédito/débito), the débito payload. |
| `transactions.js` | yes | Início, Extrato, Ajustes › Contas, Posição | **Endpoint** for the money (`consolidatedBalance`, `openingBalanceTotal`, `portfolioCashBalance`, `bankingTransactions` + the investment in/outflow classification); **port** the small predicates (`isCardRefund`, `cardSignedAmount`, `cardPurchaseKey`, `isPortfolioAccount`, `activeAccounts`) | Proposed: `GET /api/home` (`proposals/home-attention-invoices.md`), waiting for the owner. |
| `cashFlow.js` | **no** | Início (Resumo do mês, cash flow) | **Endpoint** | Proposed: `GET /api/home` with 18 new pytest cases (`proposals/home-attention-invoices.md`). The plan's `month_investment_flow()` is already its SQL twin for "Investido". |
| `attentionRules.js` | yes | Início, the bell, Cartões (`nearestOpenInvoice`) | **Endpoint** for the items (`attentionItems`, overdue/next invoices, autopay shortfalls, over budget); **port** `isPastDue`, `nextInvoices`, `nearestOpenInvoice` only if Cartões needs them before the endpoint exists | Proposed: `GET /api/attention` (items + keys) and `GET /api/cc-invoices` (`next`/`nearest` flags), `proposals/home-attention-invoices.md`. Dismissal (`undismissedItems`, `addDismissed`) and the texts (`overdueDetail`) stay on the device: port them. |
| `monthlyPlan.js` | yes | Orçamento | **Port** the input side (`percentRoom`, `clampPercent`, `stepPercent`, `PERCENT_STEP`, `percentOf` preview, `categoryAmountPreview`, `livePlanTotals`), the flag texts (`flagText`, `sortFlags`, `planFlagKey`, `visibleFlags`) | The plan's money (Saldo, daily available, spent) already comes from the server. |
| `planFlags.js` | no | Orçamento | **Port** (device-local dismissal) | Trivial; a preference. |
| `inboxRules.js` | yes | Aprovar | **Port** (step 2) | Texts, labels, the draft ↔ request mapping (`draftFromItem`, `changesFromDraft`), `readyIds`. The decisions themselves are on the server. |
| `sharing.js` | yes | "+ Novo" (share fields), Cartões, A receber | **Port** `shareFormFrom`, `shareFormError`, `sharePayload`, `settlePayload`, `shareSummary`; **endpoint** for totals if a screen needs them (`groupReceivables` sums — check `routes/receivables.py` first) | |
| `investmentStatement.js` | yes | Extrato › Investimentos | **Port** (step 4) or endpoint | Merges operações and proventos into one dated list; presentation. Port unless the Extrato endpoint can return it ready. |
| `portfolioAccount.js` | yes | "Registrar operação", Ajustes › Contas, Posição | **Port** (step 7) | Which account is the Corretora, the cash-link metadata. |
| `proceedsRules.js` | yes | Proventos | **Port** (step 7) | Which types fit which assets, the form layout. |
| `fixedIncome.js` | yes | "Registrar operação" (renda fixa), Posição | **Port** (step 7) | Form ↔ metadata mapping, labels. |
| `treasury.js` | yes | Posição (Tesouro), Operações | **Port** the labels (`treasuryRateText`, `treasuryRateLabel`, `isMarketValued`, `parseTreasuryUnits`); **endpoint** for `allocateTreasuryRedemption` (PEPS split of a grouped redemption — money; a redemption endpoint would own it with the proportional cost of a single title) | Until the endpoint exists, a port must keep the same test cases exactly. |
| Operações / Proventos / IR summaries (inline) | no | Operações, Proventos, IR | **Endpoint** | Float sums of totals the server already has (`portfolio.realized_result`) or can return (yearly proventos, tributação exclusiva net). `findings.md`, Investimentos. |
| `compoundInterest.js` | yes | Calculadora | **Port** if the Calculadora goes native | Pure math; no server data. |
| `assetSearch.js` | no | asset pickers | **Port** with new tests | Text normalization + filter. |
| `notifyRules.js` | yes | Ajustes › Notificações | **Port** when that section goes native | Texts about the listener's state; the rules themselves are in Java already. |
| `appBundleRules.js` | yes | Ajustes › Versão do app | **Drop** | The screen bundle goes away with the WebView. `update/ApkUpdateRules.java` already covers the APK. |
| `outbox.js`, `api.js`, `queries.js`, `queryPersist.js`, `offlineStore.js`, `connection.js` | — | infrastructure | **Replace** | Native equivalents are `data/` (client, cache) and the Java outbox — not ports. |
| `privacy.js`, `theme.js`, `attention.js`, `layers.js`, `scroll.js`, `toast.js`, `confirm.js` | — | shell | **Replace** | Native settings and UI kit (`architecture.md`, `conventions.md`). |

## Rules that live inline in components

Some screens compute things inside the `.jsx` with no test. The screen specs mark each one
("Client rules" section, "inline, no test"). Before porting such a rule, write its test cases from
the React behaviour (or move it to a `lib/` module with a node test first), so both sides start from
the same cases.

## Order

1. Step 1: `format.js` (+ money input parsing), `cardFunctions.js`, the needed parts of `sharing.js`.
2. Step 2: `inboxRules.js`.
3. Before step 3: the endpoints for `transactions.js` / `cashFlow.js` / `attentionRules.js` are
   proposed in `proposals/home-attention-invoices.md`; the owner reviews it (merging its PR approves it), then
   they are built one PR each, the web switched in the same PR.
4. Steps 4–7: the rest as each screen needs it.
