# Findings from specifying the screens (2026-10-22)

Writing the specs meant reading every screen against the backend. These are the cross-cutting
findings: endpoints that would make native simpler, inconsistencies and possible bugs in today's
app, and decisions to put to the owner. **None of them was changed** — each needs its own task
(and, for the bugs, a test that reproduces it first). Details and file references are in the
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

- **Metas**: the server re-checks the stored `target_date` on every edit, so once the target month
  arrives even a rename is refused ("A data desejada precisa ser depois deste mes.") (`10-metas.md`).
- **Recorrentes**: a recurrence blocked by an archived account says "Edite a recorrência e escolha
  outra conta", but the edit form cannot change the account (the API accepts `account_id`)
  (`09-recorrentes.md`).
- **Extrato**: the edit form cannot change a transfer's destination account (`04-extrato.md`).
- **`investmentStatement.js`**: its comment says operações sort before proventos on the same day; the
  code does the opposite, and no test covers it (`04-extrato.md`).
- **Card refund prefill** (one installment × count) can be off by the rounding cents
  (`05-cartoes.md`).
- **A receber**: "pago em" is cut from a UTC timestamp, so late at night it can show the next day
  (`06-a-receber.md`).
- **401**: the native sender never clears `Session` on a 401; there is no refresh token (30-day JWT
  — CLAUDE.md says 180 days are configured on the server). A native login must also write the
  WebView's stored auth while both exist (`00-shell.md`).

## Stale texts

- Login says "FinanceMVP" and offers "Cadastrar", but signup is closed (`00-shell.md`).
- Metas' NET_WORTH hint says "o número do Início", which no longer shows the portfolio; Integrações
  mentions "extrato dos bancos" (there is no bank API); Notificações says it "só guarda os textos",
  though the parsers and Aprovar exist; a comment in `Orcamento.jsx` names the wrong query key
  (`08`, `10`, `11`).

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
