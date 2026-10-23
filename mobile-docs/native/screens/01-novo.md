# "+ Novo" — native spec

| | |
|---|---|
| Migration order | 1 (see `../migration-order.md`) |
| Status | Not started |
| React source | `frontend/src/components/NewEntrySheet.jsx`, `components/Layout.jsx` (host, `openNewEntry()`, edit from Pendentes), `components/PendingSheet.jsx` ("Corrigir"), `lib/newEntry.js`, `lib/outbox.js`, `lib/outboxRules.js`, `lib/cardFunctions.js`, `lib/api.js` (`ApiNetworkError`, timeouts), `lib/nativeApp.js` (native outbox backend), `lib/inboxRules.js` (`matchedInboxNotice()`), `lib/monthlyPlan.js` (`parseMoneyInput()`), `pages/lancamentos/helpers.js` (`buildCategoryOptions`, `categoryLabel`, `categoryIdForName`, `categoryNameOf`, `filterCategoryOptions`, `pickDefaultAccountId`, `getLocalDateString`, `parseLocalDate`); Java `outbox/OutboxStore.java`, `OutboxRules.java`, `OutboxSender.java`, `OutboxWorker.java`, `OutboxPlugin.java`, `OutboxEvents.java`, `Session.java` |
| Route(s) | none — a sheet over any banking route; opened by the bottom **+**, Extrato's empty state ("Novo lançamento") and Cartões' "Nova compra" (`openNewEntry('CARD')`). Inside `/investimentos` the **+** opens "Registrar operação" instead (out of scope) |
| Endpoints | `GET /api/accounts`, `GET /api/categories`, `GET /api/credit-cards`, `POST /api/transactions`, `POST /api/transfers`, `POST /api/cc-expenses/purchases` |
| Client rules | `lib/cardFunctions.js` (`cardMethods()`, `resolveCardMethod()`, `hasCredit()`, `debitPurchasePayload()`), `lib/outboxRules.js` (`endpointFor()`, `newClientId()`, `buildItem()`, `outcomeOf()`, `deliveredDiffers()`), `lib/monthlyPlan.js` (`parseMoneyInput()`), `pages/lancamentos/helpers.js` (category options, default account) |

## What it is for
Recording a despesa, receita, transferência or card purchase the moment it happens — the most used
action in the app, often with weak signal. It must open instantly, accept the amount first, work
offline (the outbox sends later, even with the app closed) and never create a duplicate.

## What it shows
A bottom sheet. Title "Novo lançamento" (editing a pending item: "Corrigir lançamento pendente").
Footer: "Cancelar" (secondary) and "Salvar" (primary, spinner while saving; disabled while lists
load, on Transferência with fewer than 2 accounts, on Cartão with no card).

1. **Type picker**: four equal 56 px buttons, icon over label — "Despesa", "Receita", "Transferir",
   "Cartão" (accessible labels "Despesa", "Receita", "Transferência", "Compra no cartão"). Initial
   type = the one asked (`openNewEntry('CARD')`) or `EXPENSE`. Each type keeps its own form state
   while switching; Despesa ↔ Receita share one form and only clear the category.
2. **Error box** (rose, dismissible) for client validation and server refusals.
3. **The form of the type**, in typing order, amount first, large (`text-2xl` bold), focused,
   `inputMode="decimal"`, placeholder "0,00". No value is masked (privacy mode does not apply here).

**Despesa / Receita** (two-column grid):
- "Valor" (full width).
- "Categoria" (full width, required): "Selecione..." + options from `GET /api/categories` filtered
  by `filterCategoryOptions()` (despesa: kind `EXPENSE` or `BOTH`; receita: `INCOME` or `BOTH`),
  label `categoryLabel()` = "Pai > Nome" for a subcategory, value = **id**. Server order (parent
  name, then children).
- "Descrição" (full width, required on the client; placeholder "Ex: Mercado" / "Ex: Salário").
- "Data" (date, default today local) | "Conta" (select of active accounts, default
  `pickDefaultAccountId()` = `is_default` else the first). No accounts → "Nenhuma conta. Cadastre em
  Ajustes." (link `/ajustes#contas`).

**Transferência**:
- "Valor"; "De" | "Para" (both "Selecione..." + active accounts; "Para" excludes the chosen "De";
  "De" pre-filled with the default account); "Data"; "Descrição" (hint "Opcional", placeholder "Ex:
  Reserva do mês"). Fewer than 2 accounts → "Cadastre uma segunda conta em Ajustes › Contas para
  transferir.".

**Cartão** (no card → empty state "Cadastre um cartão primeiro" / "Os cartões ficam em Ajustes.
Depois disso, a compra no cartão fica disponível aqui." / link "Cadastrar cartão em Ajustes" →
`/ajustes#cartoes`):
- "Valor total" | "Parcelas" (number, `inputMode="numeric"`, 1–48 on the client, default "1"). On
  the débito method the amount is labelled "Valor", full width, and Parcelas disappears.
- "Categoria" (expense categories only), "Descrição" (required, placeholder "O que você comprou?").
- "Cartão": "Selecione..." + **every active card** from `GET /api/credit-cards` (ordered by name),
  each "<name> (vence dia <due_day>)" or "<name> (débito)" for a debit-only card; default the first
  card. Under it, when the card has both functions (`cardMethods(card).length > 1`), a segmented
  control "Crédito" / "Débito". On débito, the hint "Sai de <debit account name>, sem fatura."
  (fallback "a conta do cartão").
- "Data da compra" (default today).

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Save despesa/receita | Salvar | `POST /api/transactions` (payload below) | toast "Despesa de R$ X registrada." / "Receita de R$ X registrada." | queued |
| Save transferência | Salvar | `POST /api/transfers` | toast "Transferência de R$ X registrada." | queued |
| Save compra no crédito | Salvar | `POST /api/cc-expenses/purchases` | toast "Compra no cartão de R$ X registrada." or "… de R$ X em Nx registrada." | queued |
| Save compra no débito | Salvar (card method Débito) | `POST /api/transactions` as an EXPENSE in `card.debit_account_id` | toast "Compra no débito de R$ X registrada." | queued (as kind `EXPENSE`) |
| Save, queued | Salvar without server | outbox `put` | info toast, 6 s: "Sem conexão: despesa de R$ X guardada neste aparelho. Ela é enviada quando o servidor responder." (label lower-cased: "transferência de…", "compra no cartão de…", "compra no débito de…") | — |
| Save, matched an Aprovar item | Salvar | response has `matched_inbox: true` | info toast, 6 s: "<label>: já esperava em Aprovar (do celular ou do banco). Ficou um lançamento só." | n.a. |
| Save a corrected pending item | Salvar (edit mode) | outbox `updateItem()` (same `client_id`, `edited: true`, `status: pending`, `last_error: ''`) then `flush()` | info toast "<label> pendente atualizada." | works |
| Cancel | Cancelar / back / scrim | none | none | — |

Client validation (exact strings, accents as in code):
- despesa/receita: amount not parsed or ≤ 0 → "Informe um valor bancario valido."
- transferência: "Informe um valor valido para a transferencia."; same account →
  "Origem e destino devem ser contas diferentes."
- cartão: no card, bad date, amount ≤ 0 or installments not a positive integer → "Preencha a
  compra no cartão com valores válidos."
- lists failed and nothing cached → "Não foi possível carregar contas, cartões e categorias."
- fallbacks when an error has no message: "Não foi possível criar o lançamento.", "Não foi
  possível registrar a transferência.", "Não foi possível registrar a compra no débito.", "Não foi
  possível criar a compra no cartão."

Server refusals (HTTP 400 unless noted, body `{"error": "..."}`; shown in the error box, the form
stays filled, **nothing is queued**):
- all: "Identificador do envio (client_id) invalido."; "Valor deve ser um numero valido." /
  "Valor deve ser maior que zero."; "Data deve estar no formato AAAA-MM-DD."; "description deve ter
  no maximo 500 caracteres.".
- `/api/transactions`: "Tipo invalido."; "Categoria e obrigatorio." / "Categoria nao encontrada." /
  "Categoria esta arquivada."; "Conta nao encontrada." / "Conta esta arquivada."; 409 "Este envio
  ja foi gravado como outro tipo de lancamento. Confira o extrato." (the `client_id` already belongs
  to a transfer).
- `/api/transfers`: "Conta de origem nao encontrada." / "Conta de origem esta arquivada." (same for
  "Conta de destino"); "Origem e destino devem ser contas diferentes."; "Contas em moedas
  diferentes: lance uma despesa na origem e uma receita no destino, cada uma na moeda da conta.";
  409 the other-kind message.
- `/api/cc-expenses/purchases`: "Informe uma compra valida."; "Cartao e obrigatorio."; "Descricao
  e obrigatorio."; "Valor total deve ser maior que zero."; "Data da compra deve estar no formato
  AAAA-MM-DD."; "Parcelas deve ser um numero inteiro." / "Parcelas deve ser menor ou igual a 72.";
  "Cartao nao encontrado."; "O cartao <nome> foi excluido; ele nao recebe lancamentos novos.";
  "O cartao <nome> so tem a funcao debito: lance a compra como despesa na conta dele."; the category
  messages; "Nao foi possivel criar a compra no cartao.".
- 401 (`{"message": ...}`): the session is gone; the WebView signs out. Do not queue.

## Data

### Lists (read)
| Endpoint | Fields used | Query key today |
|---|---|---|
| `GET /api/accounts` (active only; no `include_archived`) | `id`, `name`, `is_default`, `type`, `currency`, `balance`, `balance_brl` (the last three for the estimate, not the form) | `['contas','ativas']` |
| `GET /api/categories` (active; seeds defaults) | `id`, `name`, `kind` (`INCOME`/`EXPENSE`/`BOTH`), `parent_id`, `parent_name` | `['categorias','ativas']` |
| `GET /api/credit-cards` (active) | `id`, `name`, `due_day`, `credit_enabled` (0/1), `debit_account_id` | `['cartoes']` |

The web fetches the three with the app open (not only with the sheet) so the form works offline from
the persisted cache; any write invalidates them. Native: fetch with `Session`'s token, keep the last
good copy on the phone, refresh on open.

### The outbox item (identical in IndexedDB and in `OutboxStore`)
`outboxRules.js` `buildItem()`; stored whole as JSON in table `outbox(client_id PK, user_id,
status, created_at, item)` of `financas_outbox.db`:

```json
{
  "client_id": "3f1c9a52-6b0e-4d1f-9a7e-0c2d4b8e1f37",
  "user_id": "<Session.userId>",
  "kind": "EXPENSE",
  "payload": { "...": "exactly the POST body below, client_id included" },
  "status": "pending",
  "last_error": "",
  "created_at": "2026-10-22T14:03:11.512Z",
  "edited": true
}
```
- `client_id`: UUID v4 (`crypto.randomUUID()`); server pattern `^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$`.
  It is also `payload.client_id`. Generated **once per Salvar**, before the first try, and reused for
  every resend.
- `kind`: `EXPENSE` | `INCOME` | `TRANSFER` | `CARD` (`endpointFor()` / `OutboxRules.endpointFor()`).
  A débito purchase is kind `EXPENSE`.
- `status`: `pending` | `needs_attention` (then `last_error` holds the server's message).
- `edited` appears only after "Corrigir" (absent on a fresh item).
- `user_id` must equal `Session.userId`: the sender only sends the current user's items.

### The four payloads (the outbox `payload` = the POST body)
Amounts are JSON numbers in reais (`parseMoneyInput()` result, e.g. `1234.5`); the server rounds
with `rounded_money()`. Dates are local `AAAA-MM-DD`. `category` (the name) travels beside
`category_id` only so the pending row in the Extrato can show it (`pendingAsTransactions()`); the
server decides by the id.

**EXPENSE / INCOME → `POST /api/transactions`**
```json
{ "amount": 42.9, "date": "2026-10-22", "category_id": "<id>", "category": "Mercado",
  "description": "Pão de Açúcar", "type": "EXPENSE", "account_id": "<id>", "client_id": "<uuid>" }
```
`type` repeats the kind (`INCOME` for a receita). `account_id` is the chosen account, else the
default; it is omitted only when no account list exists at all, and the server then uses its
default (`resolve_account_id()` → `ensure_default_account()`). `TRANSFER` here is refused ("Use POST
/api/transfers…").

**Débito purchase → `POST /api/transactions`** (`debitPurchasePayload(card, …)`)
```json
{ "amount": 46.81, "date": "2026-10-21", "category_id": "<id>", "category": "Alimentação",
  "description": "Padaria", "type": "EXPENSE", "account_id": "<card.debit_account_id>", "client_id": "<uuid>" }
```
Never a `cc_expenses` row; installments forced to 1. The server does not know it came from a card.

**TRANSFER → `POST /api/transfers`**
```json
{ "amount": 500, "date": "2026-10-22", "account_id": "<origem>", "transfer_account_id": "<destino>",
  "description": "", "client_id": "<uuid>" }
```
No category from the form; the server stores category "Transferencia" and, with an empty
description, "<Origem> -> <Destino>". One row, `type = 'TRANSFER'`. A transfer into a Corretora
account reads as an aporte in the banking view.

**CARD (crédito) → `POST /api/cc-expenses/purchases`**
```json
{ "card_id": "<id>", "category_id": "<id>", "category": "Lazer", "description": "Cinema",
  "total_amount": 120, "purchase_date": "2026-10-22", "installments": 3, "client_id": "<uuid>" }
```
The server splits `total_amount` into whole-cent installments (remainder on the first ones,
`split_installments()`), picks each installment's invoice (`purchase_invoice_start()` — never a paid
invoice) and stores every installment with `client_id` = the purchase id. The card must be active
and have the credit function.

**Sharing fields** (`share_mode`, `share_person`, `share_others_amount`) are **not** part of any
creation: the three POSTs ignore them; sharing is set later by `PATCH /api/transactions/<id>` or
`PATCH /api/cc-expenses/<id>/share`. Do not add them to "+ Novo" without a server change.

### Responses
- `/api/transactions`, `/api/transfers`: **201** with the row (`id`, `account_id`,
  `transfer_account_id`, `amount`, `date`, `category`, `category_id`, `description`, `type`,
  `client_id`, `created_at`, …) plus `"matched_inbox": true` when a pending Aprovar item was absorbed
  (`absorb_created()`); **200** with the row already created for that `client_id` (a replay; checked
  *before* validation, so it succeeds even if the account was archived since).
- `/api/cc-expenses/purchases`: **201** with an **array** of installment rows (`id`, `card_id`,
  `amount`, `purchase_date`, `invoice_month`, `invoice_year`, `installment_info` "1/3", `status`
  "OPEN", `client_id`, …), each with `matched_inbox: true` when absorbed; **200** with the existing
  array on a replay.

### How a save travels (`createEntry()` in `lib/outbox.js`)
1. Build the body with a new `client_id`.
2. No real network (`Outbox.hasNetwork()`: any non-VPN network with internet; the Tailscale VPN
   alone does not count) → queue at once, no request.
3. Else POST with a **6 s** timeout. A network error or timeout → queue (`ApiNetworkError`).
4. Any HTTP response that is an error → shown, **never queued or retried**.
5. Queue = `Outbox.put({item})` → `OutboxStore.put()` + `OutboxWorker.schedule()` (WorkManager,
   requires network, exponential backoff from 30 s). The worker posts with
   `OutboxSender` (one at a time, in `created_at` order): 2xx → removed (or `needs_attention` when the
   2xx body is not the creation shape, `isCreationResponse()`, or when an edited item came back
   different, `deliveredDiffers()` → `ALREADY_DELIVERED_MESSAGE`); network/5xx/408/429 → stop and
   retry later; 401 → stop all, "Sessão expirada" notification; other 4xx → `needs_attention` with the
   server message, next item continues.

## Client rules
- **Card methods** — `cardFunctions.js` `hasCredit()` (`credit_enabled !== 0/false`; a card without
  the column is credit), `hasDebit()` (`debit_account_id` set), `cardMethods()`,
  `resolveCardMethod(card, chosen)` (chosen if the card has it, else its first, else `CREDIT`),
  `debitPurchasePayload()`. Tested in `cardFunctions.test.js` ("the purchase method follows the
  card", "a debit purchase is an expense in the card account"). **Port** with the same cases.
- **Amount parser** — `monthlyPlan.js` `parseMoneyInput()`: strips spaces and "R$"; the last
  separator is the decimal; "1.234" with dot groups is thousands; a lone comma is decimal; `null` for
  empty, `NaN` for invalid. Tested (`monthlyPlan.test.js`: "1.234,56"→1234.56, "1234,5", "1234.56",
  "R$ 3.000"→3000, "1.234.567", "1.5"→1.5, "  "→null, "12a"→NaN). **Port** — keep it a `BigDecimal`.
- **Category options** — `helpers.js` `buildCategoryOptions()`, `categoryLabel()`,
  `filterCategoryOptions()`, `categoryNameOf()`, `categoryIdForName()` (a bare name → the root first,
  then the first match: for old outbox items without an id). **No tests** (inline helpers). Port with
  new tests.
- **Default account** — `helpers.js` `pickDefaultAccountId()` (`is_default`, else first). No test.
  Port; the server guarantees one default (`ensure_default_account()`).
- **Item and send rules** — `outboxRules.js` `buildItem()`, `newClientId()`, `outcomeOf()`,
  `deliveredDiffers()`, `sendOrder()`; tested in `outboxRules.test.js`; already ported to
  `OutboxRules.java` (`endpointFor`, `outcomeOf`, `isCreationResponse`, `deliveredDiffers`, `cents`)
  with `OutboxRulesTest`. `buildItem`/`newClientId` have no Java twin yet — add them (trivial) with
  the "client_id format" and "keeps an existing client_id" cases. Change one side, change the other.
- **Validation** — inline in `NewEntrySheet.jsx` handlers. No test. Port as a pure function
  `validate(kind, form) → message?` with tests.
- **Labels for toasts** — inline (`"Despesa de " + formatCurrency(amount)` …). Port.

## States
- **Opening**: forms reset to empty with today's date on every open; default account and first card
  filled as soon as the lists exist (cached copy first).
- **Loading lists**: Salvar disabled; no skeleton (fields render immediately).
- **Offline**: the form works from the cached lists; Salvar queues (toast above). If no list was
  ever cached: error box, Salvar still enabled for a despesa/receita without account (server picks
  the default) — but the category select is empty, so in practice the form can't be completed.
- **Edit mode** (from Pendentes › Corrigir): the sheet opens on the item's kind with its payload;
  an item without `category_id` resolves it from the name (`categoryIdForName()`). A débito purchase
  reopens as a **Despesa** (it is stored as kind `EXPENSE`).
- **Privacy / theme**: nothing masked; follows the theme (`FinancasTheme`, `ShellPrefs`).

## Conventions that apply
- **"A '+ Novo' creation is idempotent by `client_id`"**: one id per Salvar, reused on every resend;
  a replay answers 200 with the first result.
- **"The outbox holds creations only, and only when the request never reached the server"**: queue
  only on no-network/timeout; a server answer is never queued.
- **"Transfers are one row, not two"**: TRANSFER goes to `/api/transfers`, never as two rows.
- **"A card purchase is its `client_id`"**: every installment shares it.
- **"A card has functions: crédito, débito or both"**: débito = EXPENSE in `debit_account_id`; a
  debit-only card never reaches `/api/cc-expenses/purchases`.
- **"The credit card invoice-month rule now lives in the backend"** (Known sharp edges): send the
  purchase, never compute invoices on the phone.
- **"`transactions.category` still holds the category name, but the id decides"**: send
  `category_id` (value = id); the name only for display.
- **"Investimento is not a category"** and **"'+ Novo' is banking-only"**: no investment kind here.
- **"Dates and months are stored zero-padded"**: always send `AAAA-MM-DD`.
- **"Money"**: no float arithmetic on amounts beyond the parse; cents via `OutboxRules.cents()`.
- In the APK the queue is Java: `OutboxRules.java` ↔ `outboxRules.js`, a test on each side.

## Native-only improvements
- `NewEntryActivity` (Compose bottom sheet over the WebView), opened from the WebView by a new plugin
  method (`NativeScreens.open("new-entry", {type})` per `native-app.md`; **bump
  `native-level.txt`**). Pendentes › Corrigir should open it too with the item's `client_id`.
- Save path: do what `createEntry()` does — `hasNetwork()` false → `OutboxStore.put()` +
  `OutboxWorker.schedule()`; else POST with `Session` (6 s, no redirects, like `OutboxSender.post`);
  on `IOException`/timeout or a 2xx that fails `isCreationResponse()` → queue (safe thanks to the
  `client_id`). Writing to the queue and waiting for the worker would lose the `matched_inbox` toast
  and the immediate "registrada".
- After saving or closing, notify the WebView so it reloads the outbox and invalidates its cache
  (today `OutboxEvents.changed()` is package-private and only the sender fires it; add an event).
- Haptic on save; keep the keyboard up between saves ("Salvar e novo" is optional, not in the web).
- Launcher shortcut "Novo lançamento"; later a Quick Settings tile.

## Acceptance
- [ ] Tapping **+** opens the sheet in under 300 ms with the keyboard on "Valor".
- [ ] "12,50" and "1.234,56" save as R$ 12,50 and R$ 1.234,56.
- [ ] A despesa appears in the Extrato and Início with toast "Despesa de R$ … registrada.".
- [ ] A transfer between two accounts changes both balances and leaves the consolidated balance.
- [ ] A 3x card purchase creates three installments in Cartões with the right invoices.
- [ ] On a card with both functions, Débito hides Parcelas, says "Sai de <conta>, sem fatura." and
      creates a despesa in that account (not in Cartões).
- [ ] A debit-only card (Flash) shows "(débito)" and saves only as despesa.
- [ ] In airplane mode Salvar queues at once (no 6 s wait) with the "Sem conexão…" toast; the pill
      shows 1 pendente; turning the network on sends it with the app closed.
- [ ] Killing the app mid-save and saving again never produces two lançamentos.
- [ ] A notification waiting in Aprovar for the same amount/day disappears after saving, with the
      "já esperava em Aprovar" toast.
- [ ] A refused item (e.g. archived category) shows "Recusado" in Pendentes with the server text;
      Corrigir reopens it and Salvar sends it.

## Desktop
Keep the four forms but as a dialog or an inline row at the top of the Extrato (no bottom sheet,
no 44 px targets); allow keyboard-only entry (Enter saves, type shortcuts). The offline queue matters
less on the desktop but stays (same `lib/outbox.js`).
