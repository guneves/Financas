# A receber — native spec

| | |
|---|---|
| Migration order | 5 (see `../migration-order.md`) |
| Status | Not started |
| React source | `frontend/src/pages/lancamentos/AReceber.jsx` |
| Route(s) | `/lancamentos/a-receber` |
| Endpoints | `GET /api/receivables` (`?include_settled=1`), `POST /api/receivables/settle` |
| Client rules | `lib/sharing.js` (`groupReceivables()`, `settlePayload()`) |

## What it is for
What the owner paid for other people and expects back: the others' part of each despesa or card purchase
marked "Dividida" or "De outra pessoa", grouped by person. After the friend sends the Pix, the owner taps
"Pago" — usually right after seeing the Pix notification, on the phone. Marking writes no money: the Pix that
arrives is its own lançamento.

## What it shows
1. **Header** "A receber", description "O que você pagou por outras pessoas. Marque um lançamento ou uma compra
   como de outra pessoa ao editá-lo no Extrato ou em Cartões; ele fica aqui até você marcar que ela pagou."
   Segmented control "Pendentes" / "Todos" (header action).
2. **Error banner** (danger): action error or "Não foi possível carregar o que você tem a receber.".
3. **Summary** (only when something is pending, in either view): lead "Pendente" = Σ pending `others_amount`
   (`groupReceivables(pending)` totals, in cents), figures "Pessoas" (number of person groups with pending
   items) and "Itens" (pending count). `formatCurrency`, **not masked** in privacy mode.
4. **One panel per person** (`groupReceivables()`: name trimmed, case-insensitive grouping, "Sem nome" when
   empty; sorted by total desc, then name). In "Pendentes" the groups hold pending items only; in "Todos" every
   item, settled included, with the group total still computed over the list passed in.
   - Title "<person> · R$ <open total>" when something is open, else just "<person>"; description "N itens
     pendentes" (N > 1) or "Tudo pago" (none open).
   - Action "Tudo pago" when more than one item is open.
   - **Item row**: card icon for `kind === 'CARD_PURCHASE'`; description (server falls back to the category);
     detail "dd/mm/aaaa" + " · <card_name>" + " · dividida, total R$ <amount>" for `share_mode === 'SPLIT'` +
     " · pago em dd/mm/aaaa" (from `settled_at`, a UTC timestamp, read as the local day by
     `localDateOfTimestamp()` in `lib/format.js`, 2026-10-23). Amount `others_amount` (struck through and grey when
     settled). Button "Pago" (pending) or an undo icon "Voltar para pendente" (settled).

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Mark one paid | row "Pago" | `POST /api/receivables/settle` `{transaction_ids:[id]}` or `{cc_expense_ids:[id]}`, `settled: true` (`settlePayload()`) | toast "Marcado como pago." | refused |
| Back to pending | row undo icon | same with `settled: false` | toast "Voltou para pendente." | refused |
| Everything from a person | panel "Tudo pago" | `settlePayload(openItems, true)` → both id lists | toast "Marcado como pago." | refused |
| Go to Extrato | empty state | navigation `/lancamentos/extrato` | — | n.a. |

No confirmation dialog: the action is reversible and writes no money. Errors shown verbatim; server 400s:
"Informe ao menos um item.", "Informe uma lista de ids.", "settled deve ser verdadeiro ou falso.". A
`cc_expense_ids` entry settles every installment of that purchase (`cc_purchase_expense_ids()`); the response
`{updated}` counts a purchase once. Client fallback "Não foi possível atualizar.".

## Data
- `GET /api/receivables` (pending only) or `GET /api/receivables?include_settled=1` ("Todos"). Query key
  `['lancamentos', 'a-receber', view]` — it starts with `'lancamentos'`, and any write invalidates every query
  anyway. Response: list ordered by `date` desc, `id` desc, each
  `{kind: 'TRANSACTION' | 'CARD_PURCHASE', id, date, description, category, amount, share_mode, others_amount,
  person, settled_at}` plus `card_name` for card purchases. Built by `list_receivables()` in
  `backend/services/sharing.py`:
  - TRANSACTION: only `type = 'EXPENSE'` with `share_mode` set (a shared **receita** never appears here).
  - CARD_PURCHASE: one item per purchase (`client_id`, fallback card+description+date+category), `id` = the
    first installment's, `amount` and `others_amount` summed over the installments with `rounded_money()`,
    `settled_at` of the first installment.
  - `others_amount`: OTHERS → the full amount, SPLIT → `share_others_amount`.
- `POST /api/receivables/settle` → `{updated}`.

## Client rules
- `groupReceivables(items)` (`lib/sharing.js`, `sharing.test.js`) — group by normalized person, sum in cents,
  sort. **Port** (or ask the server for `?group=person`; small enough to port).
- `settlePayload(items, settled)` — splits items into `transaction_ids` / `cc_expense_ids` by `kind`.
  **Port.**
- Inline in `AReceber.jsx`, **untested**: the pending filter (`!settled_at`), the per-group open total
  (re-running `groupReceivables(open)`), "Tudo pago" shown only with > 1 open item, the summary counts. Port and
  add JVM tests.
- The others' amount itself is computed on the server — keep it that way.

## States
- Loading: panel with `ListSkeleton rows={4}`.
- Empty: "Nada a receber" / "Ao editar uma despesa no Extrato ou uma compra em Cartões, escolha De quem é? ›
  Dividida ou De outra pessoa e informe o nome." + "Abrir o Extrato".
- Busy: the pressed button spins (`savingKey` = `item:<id>` or `person:<name>`).
- Offline: cached list shown; settle refused (could be queued safely since it is idempotent per state, but that
  would be a new outbox kind — not today).
- Privacy mode: nothing masked today (the screen uses `formatCurrency` directly). Decide with the owner
  whether amounts owed count as "balances".
- Colours: neutral throughout; settled rows grey with a strike-through (a state, not a gain/loss colour).

## Conventions that apply
- "Whose expense it is" — balances never change; marking paid sets `share_settled_at` only; transfers and
  investment cash are never shared; a card purchase's share covers every installment.
- "A card purchase is its client_id" — the purchase is one item, settled as a whole.
- "user_id on everything" — both endpoints filter by the session user (server side).
- "The outbox holds creations only…" — a settle is never queued.

## Native-only improvements
- From an incoming Pix in Aprovar whose counterparty matches a person here, offer "Marcar <pessoa> como pago"
  (UI suggestion only; still the owner's tap, and still a separate lançamento for the Pix).
- Swipe right on a row = "Pago", with undo in a snackbar instead of the icon.
- Share a reminder text ("Você me deve R$ X: …") through the Android share sheet — text built on the phone
  from the list, nothing sent to the server.

## Acceptance
- [ ] A despesa marked "De outra pessoa · Ana" in the Extrato appears under "Ana" with its full amount.
- [ ] A 3x card purchase "Dividida com Ana, R$ 30" appears once, with "dividida, total R$ …" and R$ 30,00.
- [ ] "Ana" and "ana " are one group.
- [ ] "Pago" removes the item from "Pendentes"; in "Todos" it shows struck through with "pago em dd/mm/aaaa"; the
      undo icon brings it back.
- [ ] "Tudo pago" appears only for a person with two or more open items and settles all of them.
- [ ] Marking paid does not change any account balance or the Extrato.
- [ ] A shared receita does not appear here (by design).

## Desktop
Keep, as a table per person (date, description, card, total, others' part, status) with multi-select settle,
and a filter by person. Low priority for redesign: the current layout already reads well at desk width.
