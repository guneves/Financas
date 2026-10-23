# Aprovar — native spec

| | |
|---|---|
| Migration order | 2 (see `../migration-order.md`) |
| Status | Built 2026-10-22 on `claude/native-aprovar` (native-level 4): NativeActivity + NavHost, ui/inbox/, data/InboxRepository, "Novo para aprovar" notification; local JVM tests + assembleDebug green; waiting for the owner's phone check (Acceptance). Not built: swipe gestures, quick-settings tile |
| React source | `frontend/src/pages/lancamentos/Aprovar.jsx` (ItemCard, Decisions, TargetLine, CandidateRow, EditSheet, DecidedRow inline), `pages/lancamentos/helpers.js` (`buildCategoryOptions`, `filterCategoryOptions`), `pages/ajustes/AprovarSection.jsx` (the "Sempre perguntar" switch), `components/Layout.jsx` (tab badge) |
| Route(s) | `/lancamentos/aprovar` (`APROVAR_PATH` in `lib/navigation.js`; `/aprovar` redirects there) |
| Endpoints | `GET /api/inbox?view=pending\|decided`, `GET /api/inbox/count`, `GET /api/inbox/<id>`, `PATCH /api/inbox/<id>`, `POST /api/inbox/<id>/approve`, `POST /api/inbox/<id>/deny`, `POST /api/inbox/<id>/restore`, `POST /api/inbox/<id>/split`, `POST /api/inbox/approve-ready`, `GET /api/inbox/hints`, `DELETE /api/inbox/hints/<id>`, `GET/PATCH /api/inbox/settings`, `GET /api/accounts`, `GET /api/credit-cards`, `GET /api/categories` |
| Client rules | `lib/inboxRules.js` (all texts and request bodies), `lib/inboxCount.js` (`useInboxCount()`), `lib/cardFunctions.js` (`creditCards()`), `lib/monthlyPlan.js` (`parseMoneyInput()`) |

## What it is for
Every money notification the phone hears (bank apps, Samsung Wallet fallback, Flash) becomes a pending
item here; nothing reaches the Extrato or a card invoice until the owner approves it. Day to day the
owner opens it from the notification, confirms the account/card, and taps "Aprovar" — on the phone,
seconds after paying. Native lets this open instantly without loading the WebView.

## What it shows
Top to bottom:

1. **Header** "Aprovar", description "O que o celular encontrou. Nada entra no extrato até você aprovar, e a
   mesma compra aparece uma vez só." Action **"Aprovar prontos (n)"** only on the pending view and only
   when `readyIds(items)` (items with `ready: true`) is non-empty.
2. **Segmented control** "Pendentes (n)" / "Decididos". `n` = `pending_count` from `GET /api/inbox`
   (omitted when 0).
3. **Error banner**: action error, or the 409 text `CONFLICT_MESSAGE` = "Este item mudou em outro aparelho. A
   lista foi atualizada: confira antes de decidir.", or the query error "Não foi possível ler o que espera
   aprovação."
4. **Pending list** — one card per item (server order: `occurred_at DESC, created_at DESC`, max 200):
   - Title `item.description` or `entryTypeLabel(entry_type)`; under it `whenText(occurred_at)`
     ("17/10/2026 às 22:30", the source's local time — never convert the time zone; date only when the
     source had no time).
   - Amount right-aligned: `formatSignedCurrency(amount, amountSign(item))` — TRANSFER unsigned,
     `direction === 'IN'` → "+", else "−". Neutral colour (not masked by privacy mode: privacy covers
     balances only).
   - Badges: entry type (`ENTRY_TYPE_LABELS`: Despesa / Receita / Transferência / Cartão de crédito; no type
     → "Crédito ou débito?" in warning tone), category (not for TRANSFER), "via Samsung Wallet" (info) when
     `onlySamsung(item)`, "corrigido" (info) when `edited.length`.
   - Source lines, one per `sources[]`: `sourceLabel(source)` ("Notificação Itaú · compra no crédito · final
     1234 · <counterparty>") + `whenText(source.occurred_at)` + " · mesma compra" when `role === 'PAIRED'`.
   - Reason paragraph `reasonText(item)` for `reason` in several_candidates / possible_duplicate /
     installments_differ / out_of_reach / own_transfer / external_transfer.
   - **Target line**: arrow + `targetText(item)` ("Itaú Visa · 3x", "Itaú → BTG", account name) and a
     "Trocar"/"Fechar" toggle, hidden when every picker of the type is already open.
   - **Decisions box** (amber when something is needed or guessed, neutral after "Trocar"): `needs` contains
     `method` → two-button choice "Crédito (cartão)" / "Débito (conta)"; pickers for card / account
     ("De qual conta?" for TRANSFER) / destination account, shown when in `needs`, in `confirm`, or after
     "Trocar" (`openPickers()` + `targetFields()`). A guessed field shows hint `CONFIRM_TEXTS[field]`
     ("Cartão preenchido por palpite: confirme."). `ambiguousText(item)` under it when `item.ambiguous`.
     Card picker lists **credit cards only** (`creditCards()`); account picker lists active accounts;
     destination excludes the origin.
   - **Recurring row** when `item.recurring`: `recurringText(item)` and a "Não é esta" / "Desfazer" button.
   - **Candidates** (`item.candidates[]`): "<description|category|kind label>" and "<kind label> · dd/mm/aaaa ·
     R$ · parcela x/y · <card or account> → <transfer account>", each with "É este".
   - Buttons: "Aprovar" (label "Aprovar como novo" when there are candidates), "Editar", "Recusar"; checkbox
     "Lembrar a escolha" (default on) only when `offersRemember(item)`; a "⋯" menu with "Editar antes de
     aprovar" and, per `splittableSources(item)`, "Não é a mesma: separar <sourceLabel>" (menu shown only
     when there is at least one split option).
5. **Decided list** (`view=decided`, latest 200 by `decided_at`): description, `decisionText(item)` ·
   when · amount, " · lançado em dd/mm/aaaa" when `target.date` differs from the occurred date, the
   recurring text, and "Voltar para aprovar" only for `state === 'DENIED'`.
6. **"Escolhas lembradas (n)"** collapsible (from `GET /api/inbox/hints`, hidden when empty): `hintText(hint)`,
   "Usada N vez(es) · desde dd/mm/aaaa" (`created_at`), X to forget.

**Edit sheet** "Corrigir antes de aprovar", description "Hora original: <whenText(source_occurred_at)>. Ela fica
guardada mesmo se você mudar a data." Fields: type segmented (Despesa / Receita / Transferência / Cartão),
"Valor (R$)" (text, decimal keyboard, accepts "45,90" / "1.234,56"), "Data", "Hora" (hint "A notificação não
disse a hora." when empty), "Descrição", "Categoria" (not for TRANSFER; first option "Sugerida pelas regras";
the item's own category kept as an option when not in the list), CARD → "Cartão" + "Parcelas" (1–72),
EXPENSE/INCOME → "Conta", TRANSFER → "De" + "Para" and the note "Entre suas contas: não conta como entrada
nem saída." Footer: "Salvar e decidir depois", "Salvar e aprovar".

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Approve | card button | `POST /api/inbox/<id>/approve` `{version, remember}` | toast "Aprovado: já está no extrato." | refused (needs server) |
| It's this one | candidate "É este" | `POST /api/inbox/<id>/approve` `{version, remember, candidate:{table,id}}` | toast "Conferido: ficou um lançamento só." | refused |
| Deny | "Recusar" | `POST /api/inbox/<id>/deny` `{version}` | none; toast "Recusado. Não entra no extrato." | refused |
| Restore | decided row "Voltar para aprovar" | `POST /api/inbox/<id>/restore` `{version}` | toast "De volta para aprovar." | refused |
| Quick choice (method / card / account / destination) | decisions box | `PATCH /api/inbox/<id>` body from `quickChoice()`: `{version, entry_type?, card_id?, account_id?, transfer_account_id?}` | none; the returned item replaces the one in the list (new `version`) and the pickers close | refused |
| "Não é esta" / "Desfazer" | recurring row | `PATCH /api/inbox/<id>` `{version, recurring: false\|true}` (`recurringToggle()`) | none | refused |
| Edit and save | edit sheet | `PATCH /api/inbox/<id>` with `changesFromDraft()` (only changed fields + `version`) | toast "Correção salva. O item continua esperando você." | refused |
| Edit and approve | edit sheet | `POST /api/inbox/<id>/approve` with the same body | toast "Aprovado com a correção." | refused |
| Split a source | "⋯" menu | `POST /api/inbox/<id>/split` `{version, source:'notification', source_id}` | confirmAction "Não é a mesma?" / "\"<source>\" vira um item separado, para aprovar ou recusar sozinho." / "Separar"; toast "Separado em dois itens." | refused |
| Approve ready | header | `POST /api/inbox/approve-ready` `{ids}` | toast `approveReadySummary()` ("2 aprovados, 1 ficou para você decidir.") | refused |
| Forget a hint | hints list X | `DELETE /api/inbox/hints/<id>` | confirmAction "Esquecer esta escolha?" / "<hintText>\nO próximo aviso assim volta a perguntar. Nenhum lançamento muda." / "Esquecer"; toast "Escolha esquecida." | refused |
| "Sempre perguntar a conta/cartão" | Ajustes › Aprovar (today) | `PATCH /api/inbox/settings` `{always_ask: bool}` | toast "Aprovar vai pedir a conta/cartão de todo item." / "Aprovar volta a usar as escolhas lembradas." | refused |

Server refusals to surface verbatim (400 unless noted): any 409 (`Conflict`: "Este item ja foi decidido
(talvez em outro aparelho)." / "Este item mudou em outro aparelho. Confira antes de decidir.") → show
`CONFLICT_MESSAGE` and reload; approve with `needs` → `NEED_MESSAGES` ("Diga se foi no crédito (cartão) ou no
débito (conta).", "Escolha o cartão.", "Escolha a conta.", "Escolha a conta de destino.", "Confira o valor em
reais (a compra foi em outra moeda)."); "Origem e destino devem ser contas diferentes."; "Conta nao
encontrada." / "Conta esta arquivada." / "Conta nao e em reais."; archived or debit-only card
(`require_active_card()`): "O cartao X foi excluido; ele nao recebe lancamentos novos." / "O cartao X so tem a
funcao debito: …"; "Parcelas invalidas."; "Escolha um dos lancamentos parecidos."; "Este lancamento nao existe
mais."; recurring: "Recorrencia nao encontrada.", "Esta ocorrencia da recorrencia ja foi lancada."; 404 "Item
nao encontrado.". Client-side, "Não foi possível concluir." is the fallback.

## Data
- `GET /api/inbox?view=pending|decided` → `{items, pending_count}`. Query key `['aprovar', view]`;
  pending refetches every 20 s and on window focus. Item fields used: `id, version, state, reason,
  entry_type, direction, amount, currency, installments, occurred_at, source_occurred_at, description,
  category, category_id, account_id, account_name, card_id, card_name, transfer_account_id,
  transfer_account_name, needs[], confirm[], guessed[], edited[], ready, ambiguous, recurring
  {recurring_id, date, description, category, category_id, amount, type, frequency, exact_amount,
  settled}, recurring_off, candidates[] {table, id, kind, date, amount, description, category,
  installment_info, card_name, account_name, transfer_account_name}, sources[] {source, id, role, app,
  app_label, kind, amount, occurred_at, card_last4, card_name, counterparty, counterparty_bank}`;
  decided items add `target` (the full `transactions`/`cc_expenses` row + `table`). Built by
  `serialize_item()` in `backend/services/inbox.py`.
- Every decision endpoint returns the serialized item + `pending_count`; split returns `{item, new_item,
  pending_count}`; approve-ready returns `{approved:[ids], skipped:[{id, reason: decided|needs_decision|refused,
  error?}], pending_count}`.
- `GET /api/inbox/count` → `{pending_count}`; key `['aprovar','contagem']`, every 60 s + focus, `retry: 0`
  (0 when offline). Feeds the tab badge, the header and the Extrato notice (`pendingNoticeText()`).
- `GET /api/inbox/hints` → rows `{id, hint_key, label, entry_type, account_id, card_id,
  transfer_account_id, uses, created_at, updated_at, account_name, card_name, transfer_account_name}`; key
  `['aprovar','lembradas']`.
- `GET /api/inbox/settings` → `{always_ask}`; key `['aprovar','ajustes']`.
- Pickers: `GET /api/accounts` (key `['contas','ativas']`, filtered `!archived_at`), `GET /api/credit-cards`
  (`['cartoes']`, then `creditCards()`), `GET /api/categories` (`['categorias','ativas']`).
- Any successful write invalidates every query (`lib/queries.js`); a 409 awaits `invalidateServerData()`.

## Client rules
All in `lib/inboxRules.js`, tested by `inboxRules.test.js` (13 tests). The decisions themselves (pairing,
`needs`, `confirm`, `ready`, `ambiguous`, recurring suggestion, hints) are already server-side.
- `whenText()` / `splitOccurredAt()` / `composeOccurredAt()` — local-time display and the PATCH value.
  **Port.**
- `amountSign()`, `entryTypeLabel()`, `sourceLabel()`, `onlySamsung()`, `reasonText()`, `needText()`,
  `CONFIRM_TEXTS`, `decisionText()`, `candidateKindLabel()`, `hintText()`, `recurringText()`,
  `ambiguousText()`, `targetText()`, `approveReadySummary()` — Portuguese texts. **Port** with the same cases.
- `targetFields()`, `offersRemember()`, `splittableSources()`, `readyIds()` — UI gating. **Port.**
- `draftFromItem()` / `changesFromDraft()` — the edit diff; amount through `parseMoneyInput()`; empty
  category sends `{category: null, category_id: null}` ("sugerida pelas regras"); `ITEM_CATEGORY` keeps a
  name-only category untouched. **Port** (money parsing must match `parseMoneyInput` exactly).
- `quickChoice()` — method DEBIT maps to INCOME when `direction === 'IN'`, else EXPENSE. **Port.**
- `recurringToggle()`. **Port.**
- Inline in `Aprovar.jsx`, untested: `openPickers()` (which pickers show), the
  "alreadyOpen" rule for the "Trocar" button, the category fallback option in the edit sheet. Port and add
  JVM tests.

## States
- Loading: 3-row skeleton (`ListSkeleton rows={3}`).
- Empty pending: "Nada esperando" / "Compras e Pix avisados pelo celular aparecem aqui para você aprovar.";
  empty decided: "Nada decidido ainda".
- Busy: the pressed button shows a spinner (`busyKey` = `<id>:<action>`); other items stay usable.
- Offline: no queue — every action needs the server. Show the last cached list read-only with a clear
  "sem conexão" state; never queue an approval (the 409/version model assumes a live answer).
- Privacy mode: amounts are not masked today. Light/dark from tokens; amber box = warning (something to
  decide), info badges = Samsung / corrigido.

## Conventions that apply
- "Every money notification goes to Aprovar, as parsed fields only" — nothing is recorded without approval;
  a candidate is never a silent match.
- "Aprovar never remembers an ambiguous target" — no "Lembrar a escolha" when `ambiguous`; the text says why.
- "Aprovar settles a recurrence's occurrence" — approve with no `recurring` key uses the suggestion unless
  `recurring_off`; "Não é esta" holds for "Aprovar prontos" too.
- "Own-account transfer vs someone else is the counterparty" — `own_transfer` / `external_transfer` reasons;
  switching type to TRANSFER is learned by the server.
- "A card has functions: crédito, débito or both" — only `creditCards()` in the card picker.
- "Transactions.category still holds the category name, but the id decides" — the edit sends `category_id`.
- "A + Novo creation is idempotent by client_id" — the server absorbs a typed entry that matches a pending
  item (`absorb_created`), shown as "Lançado pelo \"+ Novo\"".
- "Bank notifications are read on the phone and stay there" — the screen never shows notification text.

## Native-only improvements
- Open straight from a local notification ("Novo para aprovar") posted by `DetectionSender` when a result is
  `new`/`merged`, deep-linking to `GET /api/inbox/<id>`.
- Swipe right = Aprovar (only when `ready`), swipe left = Recusar; haptic on success.
- A quick-settings tile / app shortcut with the pending count.
- Optimistic replacement of the item from the PATCH response (already the React behaviour) — keep it.

## Acceptance
- [ ] A test notification (debug APK, `adb` shell notification) appears as a pending item within one refresh
      (≤ 20 s with the screen open).
- [ ] An item missing the method shows "Foi no crédito ou no débito?"; choosing "Crédito (cartão)" opens the
      card picker without a reload and "Aprovar" works immediately (no 409).
- [ ] A guessed card shows "Cartão preenchido por palpite: confirme." and the item is not counted in
      "Aprovar prontos" until confirmed.
- [ ] With "Sempre perguntar a conta/cartão" on, "Aprovar prontos" does not appear (or approves nothing).
- [ ] "É este" on a candidate leaves one lançamento in the Extrato; the decided list says "Já estava lançado".
- [ ] "Não é esta" on a recurring suggestion changes the text to "Não marca …" and survives a reload.
- [ ] Deciding the same item on the desktop first and then on the phone shows the conflict message and a fresh
      list.
- [ ] "Recusar" then "Voltar para aprovar" brings the item back with its data intact.
- [ ] Editing the amount to "1.234,56" approves R$ 1.234,56; the original time stays in the sheet description.
- [ ] A forgotten hint disappears from "Escolhas lembradas" and the next similar notification asks again.

## Desktop
Keep, widened: a two-pane layout (pending list left, the selected item's details, candidates and edit form
right), keyboard shortcuts (A approve, R deny). Move "Sempre perguntar" next to the list as well as Ajustes.
The decided list becomes a table with filters by state.
