# Extrato — native spec

| | |
|---|---|
| Migration order | 4 (see `../migration-order.md`; same step as Cartões) |
| Status | Not started |
| React source | `frontend/src/pages/lancamentos/Extrato.jsx` (`Extrato`, `ExtratoContas`), `pages/lancamentos/ExtratoInvestimentos.jsx`, `pages/lancamentos/useLancamentos.js`, `pages/lancamentos/ProjectionHeader.jsx`, `pages/lancamentos/helpers.js`, `components/AttachmentsSheet.jsx`, `components/ExportSheet.jsx`, `components/ShareFields.jsx` |
| Route(s) | `/lancamentos/extrato` (`?ver=contas\|investimentos`, filters `?q=&from=&to=&type=&account_id=&category_id=&min_amount=&max_amount=`); `/transactions` and `/carteira` redirect here |
| Endpoints | `GET /api/transactions` (+ filters), `PATCH /api/transactions/<id>`, `DELETE /api/transactions/<id>`, `GET /api/transactions/export`, `DELETE /api/cc-expenses/payments/<id>`, `DELETE /api/investments/<id>`, `GET /api/accounts?include_archived=1`, `GET /api/categories`, `GET /api/credit-cards`, `GET /api/cc-expenses?status=OPEN`, `GET/POST /api/transactions/<id>/attachments`, `GET /api/transactions/<id>/attachments/<aid>/file`, `DELETE /api/transactions/<id>/attachments/<aid>`, `GET /api/exports/columns`, `GET /api/inbox/count`, `GET /api/investments?order=created_at&ascending=false`, `GET /api/investment-proceeds`, `POST /api/investment-proceeds/sync` |
| Client rules | `lib/transactions.js` (`consolidatedBalance()`, `isInvestmentOutflow()`, `isInvestmentInflow()`, `INVESTMENT_SOURCE_TYPES`, `cardSignedAmount()`, `activeAccounts()`), `lib/outboxRules.js` (`pendingAsTransactions()`, `applyPendingToAccounts()`), `lib/sharing.js` (`shareSummary()`, `shareFormFrom()`, `shareFormError()`, `sharePayload()`), `lib/investmentStatement.js`, `lib/inboxRules.js` (`pendingNoticeText()`), `lib/monthlyPlan.js` (`parseMoneyInput()`), inline rules in `Extrato.jsx` and `useLancamentos.js` |

## What it is for
The list of every lançamento in the accounts, newest first, grouped by day: the owner checks what went out,
searches a merchant, fixes a wrong amount or category, attaches a receipt, undoes an invoice payment. A
second view lists investment operations and proventos. It is the longest list in the app — where native
scrolling and instant open pay off most.

## What it shows
A segmented switch "Contas" / "Investimentos" sits under the header; the choice is in the URL (`?ver=`) and
the last one is kept on the device (`localStorage` key `financas.extrato.view`). Switching clears the other
view's filters.

### View "Contas"
1. **Header** "Extrato" / "Entradas, saídas e transferências das suas contas.", action "Exportar" (disabled
   when the list is empty).
2. **Warning banner** for load/save errors; **info banner** when `GET /api/inbox/count` > 0:
   `pendingNoticeText(n)` ("1 movimento do celular ou do banco espera sua aprovação.") + link "Aprovar".
3. **Projection header** (`ProjectionHeader`, shared with Cartões): lead "Saldo em contas" =
   `consolidatedBalance(accounts with include_archived)` (sum of `balance_brl ?? balance`, **Corretora
   accounts excluded**), hint "Movimentações confirmadas" or "Estimativa: conta os lançamentos pendentes de
   envio" when the outbox has a pending non-card, non-transfer item. Figures "Projeção próximo mês" (hint
   "Inclui faturas próximas") = balance − open card items whose invoice is ≤ next month, and "Projeção
   global" ("Inclui parcelamentos futuros") = balance − every open card item, both via `cardSignedAmount()`
   (refunds subtract). All three masked in privacy mode; red (`loss`) only when negative and not hidden.
4. **Statement panel** "Extrato da conta" ("Últimas movimentações registradas." / "Movimentações que atendem
   aos filtros."). With filters active: badges income (+, green), expense (−), and "Investido"/"Resgatado"
   net when |investment| ≥ 0,005; always a count badge "N registro(s)" or "Filtrando…".
5. **Search + filters**: search box "Buscar por descrição ou categoria" (`q`, max 100 chars server-side);
   "Filtros" button with a count of hidden active filters; "Limpar filtros". Filter panel: "De", "Até",
   "Tipo" (Todos / Entradas / Saídas / Transferências), "Conta" (active accounts), "Categoria" (all, label
   "Pai > Filho"; the server includes subcategories), "Valor mín.", "Valor máx.". Filters live in the URL;
   requests are debounced 250 ms.
6. **Day groups**: header `dayLabel(date)` ("Hoje", "Ontem", "ter., 22 de set.", year only when not the
   current one) and the day total = Σ INCOME − Σ EXPENSE of the shown rows (TRANSFER skipped; investment cash
   rows *are* counted here), `formatSignedCurrency`.
7. **Row** (phone layout): line 1 `description || category`; line 2 category (or "Origem → Destino" for a
   transfer) + " · <originLabel>" when not editable here + paperclip with count when `attachment_count > 0`;
   line 3 `shareSummary()` when `share_mode` ("Dividida com Ana · sua parte R$ 40,00", "De Ana"). Right:
   amount `formatSignedCurrency(amount, sign)` — TRANSFER unsigned grey, INCOME green "+", else "−" in ink
   colour; under it a badge only for "Transferência", "Investimento" (`isInvestmentOutflow`) or "Resgate"
   (`isInvestmentInflow`). Amounts are not masked by privacy mode.
   - `originLabel()`: pending outbox row → "Pendente de envio" / "Recusado pelo servidor"; source_type
     INVESTMENT_TRANSACTION → "Pela carteira", INVESTMENT_PROCEED → "Provento", CC_AUTOPAY → "Débito
     automático", CC_INVOICE_PAYMENT → "Pela fatura".
   - Rows just written flash (`useArrivals`).
8. **Pagination**: 100 rows at a time; "Mostrando X de Y" + "Mostrar mais N". The data itself is the whole list
   (no server paging).
9. **Inline edit** (tap an editable row): "Data", "Valor", "Descrição", "Categoria", "Tipo" (Despesa/Receita;
   a transfer shows the badge only), "Conta" (archived current account kept as "<name> (arquivada)"),
   "De quem é?" (`ShareFields`: "Só minha" / "Dividida" / "De outra pessoa", "Nome da pessoa", "Parte dela
   (R$)") except for transfers and investment rows; buttons "Excluir", paperclip, save ✓, cancel ✕.

### View "Investimentos" (`ExtratoInvestimentos.jsx`)
1. Header "Extrato" / "Operações da carteira e proventos recebidos."; runs `useProceedsSync()` on open.
2. **Summary**: lead "Proventos recebidos" (gain tone; hint "R$ X agendados" when scheduled > 0), figures
   "Aportes e compras", "Vendas e resgates" — all masked in privacy mode (`usePrivateFormatter`).
3. Panel "Extrato de investimentos" / "Operações da carteira e proventos. Não altera o saldo das contas.",
   count badge; search "Buscar por ativo ou tipo" (matches title + kind); segmented "Tudo" / "Operações" /
   "Proventos".
4. Day groups (total masked, scheduled excluded); row: title (ticker or name), kind badge (Compra / Venda /
   Aporte / Resgate / Bonificação / Dividendo / JCP / Juros / Amortização), "Agendado" (info) when payment date
   > today; detail "10 un. · R$ 20,00 · IR R$ 1,75" / "cotas", " · no extrato da conta" when the movement has
   `metadata.cash_account_id`; amount masked, "sem custo" for 0, green when > 0, grey when scheduled; "⋯" →
   "Excluir operação" for deletable movements (not bonificações, not proventos).
5. Empty: "Nada por aqui" + link "Ir para Operações".

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Edit lançamento | tap row (phone) / "⋯" › "Editar lançamento" | `PATCH /api/transactions/<id>` `{amount, date, description}` + `type` and `category_id` (only when changed; not for transfers) + `account_id` and, for a transfer, `transfer_account_id` (each only when changed; `transactionEditPayload()` in `lib/transactionEdit.js`, tested — a transfer's edit shows De/Para since 2026-10-23) + `share_mode/share_person/share_others_amount` (only when the share form changed; `sharePayload()`) | none (list refreshes) | refused (edits are never queued) |
| Delete lançamento | edit form "Excluir" / "⋯" | `DELETE /api/transactions/<id>` | confirmAction "Excluir este lançamento?" / "O saldo da conta é recalculado." / "Excluir" | refused |
| Undo invoice payment | "⋯" on a CC_INVOICE_PAYMENT / CC_AUTOPAY row | `DELETE /api/cc-expenses/payments/<transaction id>` | confirmAction "Desfazer \"<desc>\"?" / "O pagamento sai do extrato, o valor volta para o saldo da conta e a fatura fica em aberto de novo em Cartões. O débito automático não a paga outra vez: pague-a pelo botão Pagar." / "Desfazer pagamento"; toast "Pagamento desfeito. A fatura está em aberto em Cartões." | refused |
| Delete operation (Contas) | "⋯" on an INVESTMENT_TRANSACTION row with `source_id` | `DELETE /api/investments/<source_id>` | confirmAction "Excluir \"<desc>\"?" / "A operação sai da carteira e este lançamento sai do extrato; o saldo da conta é recalculado." / "Excluir operação"; toast "Operação excluída." | refused |
| Delete operation (Investimentos) | "⋯" | `DELETE /api/investments/<movementId>` | confirmAction "Excluir <kind> de <title>?" / with link: "A operação sai da carteira e o lançamento dela sai do extrato da conta; o saldo é recalculado." / without: "Só esta operação sai do histórico; as outras do ativo continuam." / "Excluir"; toast "Operação excluída." | refused |
| Receipts | paperclip / tap a derived row | list/upload/download/delete under `/api/transactions/<id>/attachments` (multipart field `file`) | delete: confirmAction "Excluir o comprovante?" / "“<name>” será apagado." / "Excluir" | refused |
| Export | header "Exportar" | `GET /api/transactions/export?<filters>&format=xlsx\|csv&columns=a,b` (columns omitted when all) | toast "<file> baixado." | refused |
| New lançamento | empty state "Novo lançamento" | opens "+ Novo" | — | queued (outbox) |

Client validation: "Informe um valor valido." (amount ≤ 0 or not a number); share errors from
`shareFormError()`: "Informe o nome da pessoa.", "Informe a parte da outra pessoa.", "A parte da outra pessoa
deve ser menor que o valor. Se é tudo dela, escolha \"De outra pessoa\"." Attachments: files > 10 MB are
refused before upload ("<name>: passa de 10 MB.").

Server refusals (verbatim): 409 for investment cash ("Este lancamento de caixa esta vinculado a uma
movimentacao de investimento. Edite/Exclua a movimentacao…"), proventos (`PROCEED_LOCKED_MESSAGE`) and invoice
payments (`INVOICE_PAYMENT_LOCKED_MESSAGE`); 400 "Nao e possivel converter um lancamento comum em
transferencia.", "Informe ao menos um campo para atualizar.", "Origem e destino devem ser contas diferentes.",
`TRANSFER_CURRENCY_MESSAGE`, "O valor ficou menor que a parte da outra pessoa. Ajuste a divisao junto.",
"Transferencia entre contas nao se divide com outra pessoa."; filters: "Data inicial deve ser anterior ou igual
a data final.", "Valor minimo deve ser menor ou igual ao valor maximo.", "Categoria nao encontrada.". Undo
payment 409 "Este pagamento tem comprovante. Remova o comprovante antes de desfazer o pagamento.", 404
"Pagamento de fatura nao encontrado.". Attachments: 413 too big, 415 type, limit of 20 per lançamento.

## Data
- **Shared load** `useLancamentos()` (query key `['lancamentos']`, also used by Cartões): in parallel
  `GET /api/transactions` (no filters: everything, ordered `date DESC, created_at DESC`, each row with
  `attachment_count`; the GET first materializes due autopay and paid proventos), `GET /api/credit-cards`
  (→ `creditCards()`), `GET /api/cc-expenses?status=OPEN`, `GET /api/accounts?include_archived=1`,
  `GET /api/categories`. Transaction fields used: `id, type, amount, date, description, category,
  category_id, account_id, transfer_account_id, source_type, source_id, attachment_count, share_mode,
  share_person, share_others_amount, pending, pending_status`. Account fields: `id, name, type,
  is_default, archived_at, balance, balance_brl`.
- **Filtered list**: `GET /api/transactions?<filters>`, key `['lancamentos','filtrado', filters]`, enabled
  only with an active filter, `keepPreviousData`. The balance header never reads it.
- Outbox items (`useOutbox()`) are prepended as pending rows (`pendingAsTransactions()`) and folded into
  account balances (`applyPendingToAccounts()`).
- Investments view: `GET /api/investments?order=created_at&ascending=false` (key
  `['investimentos','operacoes']`; fields `id, asset_class, ticker_or_name, quantity, average_price,
  current_price, fee_amount, realized_fee_amount, realized_net_proceeds, created_at, metadata{purchase_date,
  sale_date, redemption_date, sale_price, is_redemption, other_costs, corporate_action_id,
  cash_account_id}`) and `GET /api/investment-proceeds` (key `['proventos','extrato']`; fields `id,
  proceeds_type, payment_date, net_amount, tax_amount, eligible_quantity, amount_per_unit, sync_key,
  asset{ticker,name}`).
- Attachments: `GET …/attachments` → `[{id, original_name, content_type, size_bytes, sha256, created_at,
  transaction_id}]`; file bytes from `…/file` (token in header, no public URL).
- Export catalog: `GET /api/exports/columns` → `{transactions: [{key, label}], …}`; format and columns are
  remembered per screen (`financeMVP:export:transactions`).
- Every write invalidates all queries.

## Client rules
- `consolidatedBalance()` / `accountBalanceBrl()` / `bankingAccounts()` (`lib/transactions.js`,
  `transactions.test.js`) — **endpoint** preferred (the same number Início shows; a `GET /api/balance-summary`
  would serve both), else port.
- `projections()` (inline in `useLancamentos.js`, **untested**) — balance minus open card items by invoice
  month, with `cardSignedAmount()`. Money: **endpoint** (return `projected_next_month` / `projected_global`
  with the summary above).
- `isInvestmentOutflow()` / `isInvestmentInflow()` — badge and totals. **Port** (tested).
- `statementTotals` and `groupByDay()` (inline in `Extrato.jsx`, **untested**) — income/expense/investment
  sums and day totals in float. **Endpoint** (totals with the filtered response) or port with tests in cents.
- `isEditableHere()`, `isInvoicePayment()`, `isInvestmentCash()`, `canShare()`, `originLabel()`, `dayLabel()`
  (inline, **untested**) — row gating and labels. **Port** with new tests.
- `shareSummary()`, `shareFormFrom()`, `shareFormError()`, `sharePayload()` (`lib/sharing.js`,
  `sharing.test.js`). **Port.**
- `buildInvestmentStatement()`, `movementEntry()`, `proceedEntry()`, `statementTotals()`,
  `groupEntriesByDay()` (`lib/investmentStatement.js`, `investmentStatement.test.js`, 8 tests; same day, operações before proventos) — computes
  each movement's cash amount (quantity × price ± fees, float). **Endpoint** preferred (money); else port.
- `pendingAsTransactions()` / `applyPendingToAccounts()` (`lib/outboxRules.js`, mirrored in
  `OutboxRules.java`). Reuse the Java port.
- `filterCategoryOptions()` / `categoryLabel()` (`helpers.js`) — EXPENSE lists non-INCOME categories and vice
  versa. **Port.**

## States
- Loading: `ListSkeleton rows={8}` (also while the first filtered fetch runs).
- Empty: "Nenhuma movimentação" / "Os lançamentos bancários aparecerão no extrato." + "Novo lançamento"; with
  filters "Nenhum lançamento atende aos filtros.". Filter error in red under the filters.
- Offline: the saved cache (`lib/queryPersist.js`, 14 days) shows the last list; pending outbox rows appear
  marked, and the balance hint becomes the estimate text. Edits/deletes refused with the error message.
- Privacy mode: the three header values and the investments summary/amounts are masked; Contas row amounts
  are not.
- Light/dark: green only for income/gain, red only for a negative balance.

## Conventions that apply
- "Transfers are one row, not two" — a transfer is one row shown "Origem → Destino", unsigned, skipped by
  every total.
- "Consolidated balance = sum of /api/accounts balances" — never sum transactions for the header.
- "Investments and banking are separate areas…" — Corretora balance is not in "Saldo em contas"; investment
  cash rows are locked here (409) but deletable through their movement.
- "Investimento is not a category" — aporte/resgate by `source_type`, not by category name.
- "Only pay-invoice marks an invoice paid" / "A paid invoice is history" — the payment row is locked;
  "Desfazer pagamento" is the only way back, refused while it has a receipt.
- "An edit keeps the row's own account even when archived" — send `account_id` only when it changed.
- "Transactions.category still holds the category name, but the id decides" — send `category_id`, never the
  name.
- "A receipt is a file on disk, referenced by a row" — attach works on any row, derived ones included.
- "Whose expense it is" — share fields only on despesa/receita; balances never change.
- "The outbox holds creations only…" — an edit or delete is never queued.
- "The Extrato has two views" — Investimentos view deletes operations, editing stays in Operações/Proventos.

## Native-only improvements
- `LazyColumn` with sticky day headers over the whole list (no "Mostrar mais").
- Swipe-to-delete on editable rows (with the same confirmation), long-press for the "⋯" actions.
- Camera capture straight into "Comprovantes"; share-sheet to attach a PDF from another app.
- Export through Android's share sheet instead of a browser download.

## Acceptance
- [ ] "Saldo em contas" equals Início's balance and excludes the Corretora account.
- [ ] A search for a merchant filters within ~250 ms of typing and the URL-equivalent state survives leaving
      and returning to the screen.
- [ ] Editing an amount to "45,90" saves R$ 45,90; editing a lançamento of an archived account keeps that
      account.
- [ ] Changing the category of "Alimentação › Outros" to another and back keeps the subcategory (by id).
- [ ] An invoice payment row shows "Pela fatura", cannot be edited, and "Desfazer pagamento" reopens the
      invoice in Cartões.
- [ ] An "Aporte" row shows "Pela carteira"; "Excluir operação" removes it and the movement.
- [ ] A lançamento typed offline appears as "Pendente de envio" and the balance hint says "Estimativa…".
- [ ] A photo attached from the camera shows in the list with its size and opens full screen.
- [ ] Investimentos view: a future provento shows "Agendado" and is not in the day total; a bonificação has
      no delete option.
- [ ] Privacy mode masks the header values and the investments amounts.

## Desktop
Keep and widen: full table (Conta, Categoria, Descrição, Valor, Ações) with inline edit, filters always
visible in a side panel, multi-select for bulk delete/recategorize (with `POST /api/import-rules/apply`-style
confirmation), and the export dialog. The investments view becomes a sortable table.
