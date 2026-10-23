# Findings from specifying the screens (2026-10-22)

Writing the specs meant reading every screen against the backend. These are the cross-cutting
findings: endpoints that would make native simpler, inconsistencies and possible bugs in today's
app, and decisions to put to the owner. The possible bugs and the stale texts were fixed on 2026-10-23 (below); the rest is still open,
each its own task. Details and file references are in the
spec named on each line.

## Endpoints that would simplify native (and the web)

| Proposal | Replaces | Spec |
|---|---|---|
| `GET /api/home`: consolidated balance, accounts, the month's flow (Entrou, Saiu, Investido, Resultado, others' net), next invoices | Início and the bell downloading every transaction and card row and running ~1000 lines of client money logic (`transactions.js`, `cashFlow.js`) | `03-inicio.md` |
| `GET /api/attention`: the attention items with their keys | `attentionRules.js` on the client (dismissal stays on the device) | `03-inicio.md`, `00-shell.md` |
| A balance summary with the Extrato's projections | An untested inline function in `useLancamentos.js` | `04-extrato.md` |
| `GET /api/cc-invoices`: invoices grouped per card with totals and the nearest one flagged | Cartões grouping invoices and summing money as floats on the client; Início, the bell and Cartões would agree by construction | `05-cartoes.md` |
| `DELETE /api/cc-expenses/purchases/<id>` | The client filtering a purchase's open installments to delete them | `05-cartoes.md` |
| Paging on `GET /api/transactions` | Returning the whole history on every read | `04-extrato.md` |

`rules-port.md` holds the port-or-endpoint decision per module; these are the concrete shapes.

## Rules that must be ported anyway

- **Pending-balance rules** (`outboxRules.js`: `pendingAccountDeltas`, `applyPendingToAccounts`,
  `pendingAsTransactions`): `OutboxRules.java` has only the send rules. The queue lives on the phone,
  so no endpoint can replace them. Needed by native Início (step 3).
- `parseMoneyInput()` (shared by "+ Novo", Orçamento and others), `percentRoom` / `clampPercent` /
  `stepPercent`, the plan's flag texts and `planFlagKey()`, `cardFunctions.js`.

## Untested money arithmetic on the client

- Extrato's filtered totals and day totals, Cartões' invoice totals and `movementEntry()` in
  `investmentStatement.js` add money as floats (`04-extrato.md`, `05-cartoes.md`).
- Inline rules with no test: `frequencyLabel` (Recorrentes), the goal forecast texts (Metas),
  `parseBalanceInput` (Contas), the rules' own `parseAmountInput` (Regras), the closing-day auto-fill
  (Cartões) (`08`–`11`).

## Inconsistencies

- The Extrato never calls `bankingTransactions()`, so a typed transfer to the Corretora is a
  "Transferência" there and "Investido" on Início; its day total counts aporte/resgate rows while its
  filtered totals keep them apart; "Saldo em contas" leaves the Corretora out but the list shows its
  rows (`04-extrato.md`).
- Corretora accounts appear in banking forms: the "+ Novo" account selects, the pay-invoice sheet and
  the autopay select (the server accepts them). A despesa recorded there vanishes from Início
  (`01-novo.md`, `11-ajustes.md`).
- A débito purchase is queued as kind `EXPENSE`, so Pendentes › Corrigir reopens it as a Despesa
  (`01-novo.md`).
- Installments: the client allows up to 48, the server up to 72. The description is required on the
  client, optional on the server for despesa/receita (`01-novo.md`).
- "Despesas por categoria" on Início groups by name, so root "Outros" and "Lazer › Outros" merge —
  against CLAUDE.md's "the id decides" (`03-inicio.md`).
- Privacy mode masks Entrou/Saiu but the cash-flow chart shows the same numbers (`03-inicio.md`).
  Aprovar, Cartões' totals and A receber are not masked — consistent with "balances only", to confirm
  with the owner.
- `/api/credit-cards` is fetched under two cache keys, `['cartoes']` and `['inicio','cartoes']`
  (`03-inicio.md`).
- Cards have no bank field, so Aprovar's ambiguous-target check (`ambiguous_target()`) never runs for
  cards (`11-ajustes.md`).

## Possible bugs

Triaged 2026-10-23 (branch `claude/mobile-docs-bugs-stale-text-u8ylzb`): each got a test that
reproduced it first; every one reproduced, so every one is fixed, with the test kept in the suite.

| Finding | Outcome |
|---|---|
| **Metas**: the stored `target_date` re-checked on every edit, so once its month arrived even a rename was refused (`10-metas.md`) | **Real, fixed.** Only a *new* date must be after this month (`normalize_goal_payload()`); `test_goals.py::test_an_edit_keeps_a_target_date_that_has_since_arrived` |
| **Recorrentes**: "Edite a recorrência e escolha outra conta", but the edit could change only the amount (`09-recorrentes.md`) | **Real, fixed.** "Editar valor e conta" has an account select; the PATCH is `recurringEditPatch()` in `lib/recurring.js` (`recurring.test.js`). The server side was already tested (`test_recurring.py`, archived account) |
| **Extrato**: the edit could not change a transfer's destination (`04-extrato.md`) | **Real, fixed.** De/Para selects; the form and the PATCH moved to `lib/transactionEdit.js` (`transactionEdit.test.js`). The server already accepted `transfer_account_id` |
| **`investmentStatement.js`**: same day, the comment says operações first, the code put proventos first (`04-extrato.md`) | **Real, fixed** (the code, to match the comment); `investmentStatement.test.js` same-day case |
| **Card refund prefill**: one installment × count off by the split's cent (`05-cartoes.md`) | **Real, fixed.** R$ 100 in 3x opened from 2/3 prefilled 99,99. The sheet sums the purchase's installments in cents (`refundPrefillAmount()` in `lib/cardPurchase.js`, `cardPurchase.test.js`); the estimate stays until the answer, and a typed value is kept |
| **A receber**: "pago em" cut from a UTC timestamp (`06-a-receber.md`) | **Real, fixed.** `localDateOfTimestamp()` in `lib/format.js`, tested under `America/Sao_Paulo` (01:30Z is the previous local day) |
| **401**: the native sender never clears `Session` on a 401; no refresh token (`00-shell.md`) | **Not in this session's scope (native).** Correction: the server default is 30 days (`JWT_EXP_DAYS` in `config.py`); 180 is the value `.env.example` sets for the owner's server. Open for the native shell |

## Investimentos

- **No idempotent creation**: `POST /api/investments`, `/api/investment-proceeds` and
  `/api/corporate-actions` take no `client_id`. Native must refuse them offline and never resend
  after a timeout (unlike "+ Novo"). Adding `client_id` (as migration 024 did for "+ Novo") would
  allow queueing (`13-investimentos-operacoes.md`).
- **Money computed on the client** that belongs on the server: the redemption cost split across
  Tesouro purchases (`allocateTreasuryRedemption()`, PEPS) and the proportional cost of a single
  title (a redemption endpoint would own it); Operações' summary summing floats while
  `portfolio.realized_result` already holds the totals; Proventos' yearly totals; the IR tab's
  tributação exclusiva net (`gross − withheld`, unrounded); the CDI comparison card, which belongs in
  `benchmarks[]` (`12`–`16`).
- No tests: position grouping and `describeMovement()`; `typeForAsset()` is tested but unused.
- Privacy mode masks Aportes and "Por ativo" but not Operações' list and summary or Proventos'
  summary and history.
- Deleting a grouped Tesouro position sends several separate DELETEs; a failure halfway leaves it
  half-deleted (a grouped delete endpoint would make it atomic).
- `/api/investments/history` returns `historical_prices`, which nothing reads.
- `profitability_percent` is net of IR for fixed income and gross for variable income.
- Chart colours: `SERIES` (and part of `FLOW`) in `components/charts.jsx` are hex literals, not CSS
  variables as CLAUDE.md says; native needs them in `Tokens.kt` (`14-investimentos-rentabilidade.md`).

## Stale texts

All fixed 2026-10-23: the login says "Finanças" and offers "Criar acesso" only when the server's
signup is open (new public `GET /api/auth/signup` → `{open}`); Metas' Patrimônio hint, Integrações
(the Tesouro prices, no bank API), Notificações (what goes to Aprovar, what capture keeps),
`CASH_WITHOUT_AMOUNT_MESSAGE` ("Não descontar de nenhuma conta") and the `Orcamento.jsx` comment
(no other screen reads `['plano-do-mes', month]`).

## Notes for building native

- "+ Novo" should try the server first with the 6 s timeout, like `createEntry()`, and queue only when
  the request never arrived — queue-only would lose the "registrada" and `matched_inbox` toasts
  (`01-novo.md`).
- `OutboxEvents.changed()` is package-private and fired only by the sender; the WebView needs a new
  event to refresh after a native save (`architecture.md`, "Keeping data fresh").
- `GET /api/accounts` and `GET /api/credit-cards` write before answering (due autopay, paid
  proventos): treat them as reads with side effects, never prefetch them speculatively in a loop.
- Plans, budgets, recurrences, goals and settings are never queued offline; they fail with "Sem
  conexão…", as on the web.
- While WebView screens remain, a native theme change or "Sair" must update both sides.
- `DetectionSender` could post a local "Novo para aprovar" notification that opens the native
  Aprovar item (`02-aprovar.md`).
- Importar: desktop-only recommended; Aprovar replaced file import on the phone (`07-importar.md`).
