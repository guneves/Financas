# Cartões — native spec

| | |
|---|---|
| Migration order | 4 (see `../migration-order.md`; same step as Extrato) |
| Status | Built 2026-10-24 on `claude/native-session-a` (native-level 6): `ui/cartoes/` over `GET /api/cc-invoices` (totals, closed/past-due/payable/nearest/future from the server), pay-invoice (suggested account = autopay, else default), refund with `client_id` per sheet open and the installments' prefill, "De quem é?" (`CardRules.shareStart`, comma accepted), delete purchase/refund through `DELETE /api/cc-expenses/purchases/<id>`, receipts; `rules/CardRules.kt` (cardPurchase.js port + the inline rules); CI green; waiting for the owner's phone check (Acceptance) and the merge. Not built: card carousel, haptic confirm on Pagar, the home-screen widget, refunds queued offline (a decision) |
| React source | `frontend/src/pages/lancamentos/Cartoes.jsx`, `pages/lancamentos/CardRefundSheet.jsx`, `pages/lancamentos/CardShareSheet.jsx`, `pages/lancamentos/useLancamentos.js`, `pages/lancamentos/ProjectionHeader.jsx`, `pages/lancamentos/helpers.js`, `components/PayInvoiceSheet.jsx`, `components/AttachmentsSheet.jsx` (purchase mode), `components/ShareFields.jsx` |
| Route(s) | `/lancamentos/cartoes` |
| Endpoints | `GET /api/cc-expenses?status=OPEN`, `GET /api/credit-cards`, `GET /api/accounts?include_archived=1`, `GET /api/transactions`, `GET /api/categories` (shared load), `POST /api/cc-expenses/pay-invoice`, `POST /api/cc-expenses/refunds`, `GET /api/cc-expenses/candidates?id=`, `PATCH /api/cc-expenses/<id>/share`, `DELETE /api/cc-expenses` (`{ids}`), `GET/POST /api/cc-expenses/<id>/attachments`, `GET /api/cc-expenses/<id>/attachments/<aid>/file`, `DELETE /api/cc-expenses/<id>/attachments/<aid>` |
| Client rules | `lib/attentionRules.js` (`nearestOpenInvoice()`, `isPastDue()`), `lib/transactions.js` (`cardSignedAmount()`, `isCardRefund()`, `cardPurchaseKey()`, `accountBalanceBrl()`, `isPortfolioAccount()`), `lib/cardFunctions.js` (`creditCards()`), `lib/sharing.js`, `lib/outboxRules.js` (`newClientId()`), `lib/monthlyPlan.js` (`parseMoneyInput()`), `helpers.js` (`parseInstallmentInfo()`, `formatInvoiceLabel()`, `getPurchaseGroupKey()`), inline grouping in `Cartoes.jsx` |

## What it is for
Open credit-card invoices by card: what is on the current invoice, when it closes and is due, and the
"Pagar" button once it has closed. The owner also registers a refund (estorno), marks a purchase as someone
else's, attaches a receipt or deletes a wrong purchase. On the phone this is checked before paying the
invoice and after a refund shows up in the bank app.

## What it shows
1. **Header** "Cartões"; description = "Próxima fatura: <card> MM/AAAA · R$ total · R$ X em aberto nos
   cartões" when `nearestOpenInvoice()` finds one, else "Faturas em aberto por cartão.". Actions: "Nova
   compra" (opens "+ Novo" on Cartão), "Estorno" (when there are credit cards), "Pagar fatura" only when the
   nearest invoice is closed.
2. **Warning banner** for errors.
3. **Projection header** (same component and numbers as the Extrato: "Saldo em contas", "Projeção próximo
   mês", "Projeção global"; masked in privacy mode). It never shows the "estimate" hint here.
4. **One panel per credit card that has open items** (sorted by card name), built client-side from
   `GET /api/cc-expenses?status=OPEN`:
   - Title card name; subtitle "Fecha dia N · vence dia M" (+ " · débito automático em <account>" when
     `autopay_account_id`). Right: "Em aberto" + total of every open invoice of the card.
   - **Current invoices**: every invoice up to and including the first not-yet-closed one (overdue and closed
     ones first, in date order). **Future invoices** after it are folded into one row "Fatura seguinte" /
     "Próximas N faturas · até MM/AAAA" with their total, expandable (grey background).
   - **Invoice row** (tap toggles; by default only the nearest invoice is expanded): "MM/AAAA"; badges —
     total < 0 → "Crédito" (green); else (not future) "Em atraso" (danger, `isPastDue(invoice_due_date,
     today)`: after the due day), "Fechada" (warning, `invoice_closed`), or "Aberta"; "Próxima" on the nearest
     one. Total `formatCurrency(Σ cardSignedAmount)`. Hint line (`paymentHint()`): "O crédito do estorno abate a
     próxima fatura" (total < 0); not closed → "Fecha em dd/mm/aaaa · pagamento liberado depois" ("Fecha em
     dd/mm/aaaa" for future ones; "Pagamento liberado após o fechamento" without a date); closed with autopay →
     "Débito automático em dd/mm/aaaa". "Pagar" button when `invoice_closed && total >= 0` (primary on the
     nearest).
   - **Purchase rows** inside an expanded invoice, one per purchase (`cardPurchaseKey()`: `compra:<client_id>`,
     fallback card+description+date+category), sorted by description: description + paperclip when
     `attachment_count > 0` (count covers every installment of the purchase); "Estorno · " + category ·
     dd/mm/aaaa · "parcela x/y"; `shareSummary()` line; amount = this invoice's installment — refunds green with
     sign (`formatSignedCurrency`), purchases neutral. Not masked by privacy mode.
   - Row "⋯": purchase → "Registrar estorno", "De quem é?", "Comprovantes (n)", "Excluir compra" / "Excluir
     compra e parcelas"; refund → "Comprovantes (n)", "Excluir estorno".
5. **Sheets**: "Pagar fatura" (`PayInvoiceSheet`: description "<card> · MM/AAAA", select "Debitar da conta" with
   active accounts as "<name> (padrão) · R$ saldo" — no balance for a Corretora, with no FX, or in privacy mode;
   warning "O saldo de X (R$) não cobre a fatura; a conta ficará negativa." when the chosen non-Corretora
   balance < total; button "Pagar R$ total"). "Registrar estorno" (fields "Valor do estorno", "Descrição",
   "Cartão" — locked when opened from a purchase —, "Data do estorno" with hint "Entra na fatura desta data; se
   ela já foi paga, na próxima em aberto."; button "Lançar estorno"). "De quem é esta compra?" (description
   "<desc> · R$ total em N parcelas", `ShareFields`, note "A fatura não muda. A parte da outra pessoa fica fora de
   Despesas por categoria e do orçamento, aparece à parte no Fluxo de caixa e fica em A receber até você marcar
   que ela pagou."). "Comprovantes" (purchase mode: description "<desc> · dd/mm/aaaa · Nx de R$ / R$").

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Pay invoice | invoice "Pagar" / header "Pagar fatura" | `POST /api/cc-expenses/pay-invoice` `{card_id, invoice_month, invoice_year, account_id}` (`account_id` omitted → server uses autopay account, else default) | sheet confirm; toast "Fatura <card> MM/AAAA paga — R$ total saiu de <account>." | refused |
| Register refund | header "Estorno" / purchase "⋯" | `POST /api/cc-expenses/refunds` `{card_id, amount, purchase_date, description, category?, refund_of?, client_id}` (`client_id` = `newClientId()` per sheet open) | toast "Estorno de R$ X lançado na fatura MM/AAAA." | refused today (idempotent by `client_id`, so it could be queued) |
| Who it belongs to | purchase "⋯" › "De quem é?" | loads `GET /api/cc-expenses/candidates?id=<id>`, saves `PATCH /api/cc-expenses/<id>/share` with `sharePayload()` (`{share_mode:null}` or `{share_mode, share_person, share_others_amount?}`) for the whole purchase | toast "Compra marcada." / "Compra voltou a ser só sua." | refused |
| Delete purchase | purchase "⋯" | `GET /api/cc-expenses/candidates?id=` → keep rows within 1 cent of this installment and the same installment total → `DELETE /api/cc-expenses` `{ids: open ones}` | confirmAction "Excluir a compra \"<desc>\"?" / "Todas as parcelas dela saem das faturas." or "A parcela em aberto sai da fatura. / As N parcelas em aberto saem das faturas." + paid-installment note ("…Para tirá-la também, desfaça esse pagamento no Extrato.") / "Excluir compra" | refused |
| Delete refund | refund "⋯" | `DELETE /api/cc-expenses` `{ids:[id]}` | confirmAction "Excluir o estorno \"<desc>\"?" / "O crédito sai da fatura." / "Excluir estorno" | refused |
| Receipts | "⋯" › "Comprovantes" | `/api/cc-expenses/<id>/attachments…` (listed across all installments) | delete: "Excluir o comprovante?" | refused |
| New purchase | header "Nova compra" | "+ Novo" card form (`POST /api/cc-expenses/purchases`) | — | queued (outbox) |

Client validation: refund "Informe o valor do estorno."; share via `shareFormError()`; delete with no open
installment → "Nenhuma parcela em aberto foi encontrada para essa compra.".

Server refusals (verbatim): pay-invoice 409 "A fatura MM/AAAA ainda esta aberta. O pagamento so e liberado
depois do fechamento, em dd/mm/aaaa." (`ensure_invoice_closed()`), 409 "A fatura MM/AAAA ficou com credito de
estorno; ele abate a proxima fatura.", 409 "Nao ha itens em aberto nesta fatura.", 404 "Cartao nao
encontrado."; a zeroed invoice answers 200 `{transaction: null}` (settled without a lançamento). Delete 409
"N item(ns) ja foram pagos com a fatura e nao se excluem. Para tira-los, desfaca o pagamento da fatura no
Extrato.". Refund: "Compra estornada nao encontrada neste cartao.", archived/debit-only card messages from
`require_active_card()`. Share: "Um estorno nao se divide.", 404 "Compra nao encontrada.".

## Data
- Shared load `useLancamentos()` (key `['lancamentos']`, see `04-extrato.md`). Cartões reads `ccExpenses`
  (`GET /api/cc-expenses?status=OPEN`, ordered by invoice year, month, created_at), `cards`
  (`creditCards(GET /api/credit-cards)` — debit-only cards dropped), `accounts`, the balance and projections.
- cc-expense fields used (`serialize_cc_expense()` in `services/invoices.py`): `id, card_id, client_id, kind,
  status, description, category, purchase_date, amount, installment_info, invoice_month, invoice_year,
  invoice_closed, invoice_closing_date, invoice_due_date, credit_cards{name, due_day, closing_day},
  attachment_count, share_mode, share_person, share_others_amount`. The GET materializes due autopay first
  (`apply_due_autopay()`).
- Card fields: `id, name, due_day, closing_day, autopay_account_id` (`credit_enabled`, `debit_account_id`
  through `creditCards()`). Archived cards are absent from the GET.
- `GET /api/cc-expenses/candidates?id=` → every installment of that purchase: `id, amount, installment_info,
  status, share_mode, share_others_amount, share_person, share_settled_at`.
- pay-invoice → `{transaction}` (201) or `{transaction: null}` (200); refund → the created row (201, or 200
  on a repeated `client_id`) with `invoice_month/invoice_year`; share → the purchase's rows.
- Every write invalidates all queries.

## Client rules
`GET /api/cc-invoices` and `DELETE /api/cc-expenses/purchases/<id>` are built (session 6) and both the
web and native read them; the grouping, the current/future split, `nearest` and the delete filter below
are the server's now. What stays on the client is listed as ported in `rules/CardRules.kt`.

- **Invoice grouping** (inline `openInvoicesByCard` in `Cartoes.jsx`, **untested**): groups open items by
  card → invoice (`YYYY-MM`) → purchase, sums with `cardSignedAmount()` in float, sorts. **Endpoint**
  recommended: `GET /api/cc-invoices` returning per card the invoices with `total` (cents-correct),
  `closed`, `closing_date`, `due_date`, `overdue`, `payable`, purchases. That also removes float sums of money.
- `nearestOpenInvoice()` / `nextInvoices()` / `overdueInvoices()` / `isPastDue()` (`lib/attentionRules.js`,
  `attentionRules.test.js`) — the same choice Início and the bell make. **Endpoint** (flag `nearest` in the
  invoice list) or port with the same cases; must stay identical across screens.
- Current/future split (inline): invoices up to the first not-closed one are "current". **Port** with tests.
- `paymentHint()` and `getInvoiceStatus()` (inline, **untested**). **Port** with tests.
- Pay button gating: `invoice_closed === true && total >= 0` (server re-checks). **Port.**
- Suggested pay account (inline): the card's autopay account if active, else the default, else the first
  active — same as the server's omitted-`account_id` rule. **Port**, or simply omit `account_id` when the owner
  keeps the suggestion.
- Delete-purchase filter (inline): installments within 1 cent and same total count, only `OPEN` ones.
  **Endpoint** preferred: a `DELETE /api/cc-expenses/purchases/<id>` that deletes the purchase's open
  installments server-side.
- Refund prefill: the sum of the purchase's installments in cents from `GET /api/cc-expenses/candidates`
  (`refundPrefillAmount()` in `lib/cardPurchase.js`, tested; installment × count was off by the split's
  cent), the estimate until the answer, comma decimal; description "Estorno · <desc>". The delete's
  installment filter is `purchaseInstallments()` in the same module. **Port.**
- `parseInstallmentInfo()`, `formatInvoiceLabel()` (`helpers.js`, untested). **Port.**
- `shareFormFrom()` / `shareFormError()` / `sharePayload()` / `othersAmount()` (`lib/sharing.js`, tested).
  **Port.** The share sheet sums installments in cents.
- PayInvoiceSheet shortfall warning (inline): selected non-Corretora `accountBalanceBrl()` < total. **Port.**

## States
- Loading: panel with `ListSkeleton rows={4}`.
- No credit card: "Nenhum cartão cadastrado" / "Os cartões ficam em Ajustes. Depois disso, registre compras
  pelo botão Novo." + link "Cadastrar cartão em Ajustes" (`/ajustes#cartoes`).
- Cards but nothing open: "Nenhuma fatura aberta" / "As compras no crédito aparecerão agrupadas por cartão.".
- Offline: cached invoices shown; pay, refund, share and delete refused with the error.
- Privacy mode: only the projection header is masked; invoice and purchase totals stay visible; the pay sheet
  hides account balances.
- Colours: "Em atraso" danger, "Fechada" warning, "Crédito"/refund amounts green; everything else neutral.

## Conventions that apply
- "An invoice is paid only once it has closed" — trust `invoice_closed`/`invoice_closing_date`; never compute
  the closing day on the phone.
- "Only pay-invoice marks an invoice paid" — one `POST /api/cc-expenses/pay-invoice`, never an EXPENSE + status.
- "The next invoice is per card, by due date, never 'next month's'" — `nearestOpenInvoice()`; overdue means
  after the due day.
- "A paid invoice is history" — paid installments are never deleted here; the confirmation points to
  "Desfazer pagamento" in the Extrato.
- "A card refund is a credit row" — sums go through `cardSignedAmount()`; an invoice in credit is not
  payable; a zeroed one settles without a lançamento.
- "A card purchase is its client_id" — group, delete, share and receipts by purchase, not by description.
- "A card has functions: crédito, débito or both" — only credit cards appear.
- "Débito automático" — the hint shows the autopay date; autopay is materialized by the server on read.
- "Whose expense it is" — the share covers every installment; the invoice total never changes.
- "Budget spent (decision 1)" — not shown here, but a refund subtracts in its month elsewhere.

## Native-only improvements
- Card carousel at the top (one card per page) with the nearest invoice expanded.
- "Pagar" with a bottom sheet and haptic confirmation; a home-screen widget "Próxima fatura" (shared with
  Início).
- Queue refunds offline (they already carry `client_id`), if the owner wants it — a decision, not a default.

## Acceptance
- [ ] Each credit card with open items shows its invoices; a debit-only card (Flash) never appears.
- [ ] An invoice before its closing day shows "Fecha em dd/mm/aaaa · pagamento liberado depois" and no "Pagar".
- [ ] After the closing day "Fechada" + "Pagar"; after the due day "Em atraso".
- [ ] The header's "Próxima fatura" matches Início's "Próxima fatura" for the same day.
- [ ] Paying debits the chosen account (Extrato shows "Fatura MM/AAAA", category "Pagamento Fatura <card>") and the invoice leaves the list.
- [ ] A refund dated in a paid invoice lands in the next open one (toast names it) and shows green with "+".
- [ ] An invoice zeroed by a refund is settled without a lançamento; one in credit shows "Crédito" and no "Pagar".
- [ ] "De quem é?" → Dividida, Ana, R$ 30 on a 3x purchase shows "Dividida com Ana · sua parte …" on each
      installment and the purchase appears once in A receber.
- [ ] "Excluir compra e parcelas" on a purchase with one paid installment removes only the open ones and says so.
- [ ] Two identical Uber rides on the same day stay two purchases.

## Desktop
Keep, widened: cards side by side (already two columns at `xl`), each invoice as a table (date, description,
category, installment, share, amount), and a timeline of future invoices per card. Add a per-card history view
(paid invoices, `?include_archived=1` for archived cards) — today only open items are listed.
