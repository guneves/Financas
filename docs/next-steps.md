# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`. This file holds **only open work**: when a task is finished, remove it from here and
> record it in `docs/done-tasks.md` — no ticked boxes, no "done" sections.

---

## 1. Open work, in priority order

### Browser walk-through (owner) — everything below is backend-tested and `vite build` clean only
The Chrome extension worked on 2026-09-22 (late) for clicks and DOM reads, but its screenshots timed
out; Playwright from the npx cache covers screenshots (see the handoff). None of the items below has
been clicked through by the owner. One pass in the real app covers all of it (what each feature
changed is in `docs/done-tasks.md`):
- [ ] UX reorganization (all six steps), then settle open decisions 7–8 below.
- [ ] Signup with username and Ajustes → Perfil. Existing accounts have `username = NULL` and show
  "Usuário" until they pick one.
- [ ] Eye toggle (reworked 2026-09-22, checked by script only): the page stays put — no reload, no
  skeleton, numbers do not recount. Hidden: Início's four top cards, "Evolução do saldo" (badge, axis,
  tooltip), "Saldo por conta", the autopay-shortfall warning; the balance block on Extrato and
  Cartões; Ajustes → Contas; the balance in Pagar fatura's account picker; all of Posição (the
  summary block — its % stays —, allocation, Evolução do Patrimônio, group totals, quantities,
  values, the fixed-income principal, the value in the Resgate sheet) and the position values in the
  sale picker. Everything else stays visible.
- [ ] Cartões and Início: Pagar opens a sheet with "Debitar da conta" (Cartões preselects the card's
  autopay account, else the default; Início defaults to "Conta de cada cartão"); the sheet warns when
  the chosen account's balance does not cover the invoice.
- [ ] Início "Precisa de você": "Débito automático sem saldo" appears when autopay invoices due in the
  next 31 days exceed the debit account's balance today.
- [ ] Extrato: filters survive a reload and the filter panel opens when the URL carries them.
- [ ] Each screen loads its own chunk now; first visit shows a skeleton in the page area.
- [ ] Lançamentos → Importar: pick a real bank export (CSV and OFX), check the column mapping
  guess, the preview statuses, category overrides, "Criar regra", and that importing the same file
  twice creates nothing the second time.
- [ ] Extrato → "Exportar" and Investimentos → Posição → "Exportar": the file downloads, opens in
  Excel with the columns split, and the statement export respects the active filters.
- [ ] Visual design pass: Início cards show full values at your usual
  window width; Extrato right-aligned signed values, sticky header while scrolling, "Mostrar mais";
  on the phone, tap a lançamento to edit it; Posição rows with the quote dot (hover for source and
  time); every percentage with a comma; no chart axis label on two lines.
- [ ] Início → "Orçamento do mês" (below "Despesas por categoria"): spent of available with a bar
  and "Restam"/"Passou", badge with the month's status, up to four categories that are "Perto do
  limite" or "Estourou" (worst first), or a one-line "todas no plano". Hidden in a month with no
  budget. Not masked by the eye (orçamentos stay visible).
- [ ] Ajustes → Regras de importação: the pencil edits a rule (pattern too); "Aplicar" on a rule and
  "Aplicar ao extrato" list the lançamentos that would change category, all ticked — untick any you
  categorized by hand on purpose, then "Recategorizar N". (Clicked through on scratch data
  2026-09-22 via Chrome + Playwright; not yet on real data.)
- [ ] Extrato → comprovantes: the paperclip on a row (on the phone: inside the edit form, or a tap
  on a row from another screen, e.g. an invoice payment) opens "Comprovantes"; attach a PDF and a
  phone photo (several at once works), "Abrir" shows it in a new tab, "Baixar" keeps the original
  name, a row with receipts shows a clip beside the description. Try a photo straight from the
  phone camera — iPhones may send HEIC, which only Safari can open (elsewhere "Abrir" downloads).
  Clicked through on scratch data 2026-09-23 with Playwright at 1280 and 390 px, not on real data.
- [ ] Tables at 1024–1279 px (Extrato, Posição, Operações, Proventos) now show as cards below `xl`;
  check that this is what you want at your usual window width.
- [ ] UI remodel (2026-09-23), both themes (moon/sun next to the eye) and the phone: Início,
  Extrato (day groups, "⋯" on hover), Cartões (one panel per card, Pagar only on a closed invoice),
  Posição (summary block, "⋯" → Editar cotação opens a sheet, Resgatar opens a sheet), Operações,
  Proventos, Orçamento, Recorrentes (summary blocks, "⋯" menus), Importar (stepper; after
  importing, the green "importado(s)" banner now stays), Ajustes. Success messages now appear as a
  dark toast at the bottom right (above the bottom bar on the phone) and fade after 4 s.
- [ ] Motion pass: every sheet ("+ Novo", Pagar fatura, investimento, editar operação) animates
  out, not just in, and shows its last content while leaving (no "Pagar R$ 0,00" flash). Tab pill
  slides between abas. Início numbers count up on the first visit only; leaving and coming back,
  or toggling the eye, shows them still. Collapsibles and Cartões invoices open and close in height,
  and focus rings inside an open one are not clipped. A lançamento saved by "+ Novo" flashes green
  in Extrato. Paying an invoice shows a green confirmation with a drawn check; a refused payment
  shakes the error. With Windows "animation effects" off, nothing moves (charts included).

### UI remodel leftovers
- [ ] `DemoDataSection` keeps its success banner (it carries a link) instead of a toast.
- [ ] Proventos' form is still a collapsible at the top of the page rather than a sheet.

### Known limits, accepted for now
- Privacy mode hides balances, net worth and the portfolio only — lançamentos, faturas, orçamentos,
  operações and proventos stay visible by the owner's choice. Percentages (allocation shares,
  Conta/Investido split, rentabilidade) stay visible; chart shapes still show relative sizes. A
  sensitive value must go through `usePrivateFormatter()` (`lib/privacy.js`) — the plain formatters
  never mask.
- IPCA+ is an **estimate**: the purchase month is pro rata by calendar days and the current,
  unpublished month is missing until the BCB releases it. Real contracts use pro rata by business
  days and the projected IPCA — revisit if the owner holds IPCA+ papers and sees a gap.
- Lançamentos from before the fixed-income type change have no `fixed_income_type`; the edit sheet
  asks for one on first edit. Validation on save (`validate_fixed_income_metadata`) only checks a
  buy that carries rate keys, so a title without any rate (manual price) is still accepted.
- Autopay still debits into the negative, as a real bank would try to; the Início warning is the
  mitigation. The warning compares against today's balance, not a projected one, and counts a
  not-yet-closed invoice at its current total.
- The provento-on-CDB "backend error" did not reproduce as a 500, neither on current code nor at
  `95f5eea` where it was logged. The one refusal is "no position on the Data com" (title bought after
  it, or already redeemed); the message now names the date. Reopen with the exact steps if seen again.
- The `'str' object has no attribute 'get'` quote failure matches iterating a BCB error object; the
  fetch now rejects non-list payloads with the BCB's message, treats 404 "Value(s) not found" (title
  bought today) as no accrual, and splits windows over BCB's 10-year limit (406).

### Smaller gaps
- [ ] Import rules: amount and account conditions on a rule. Import is capped at 2,000 rows per
  file, and the apply preview at 2,000 rows (the sheet says so when it cuts).
- [ ] Export: .xlsx proper, exporting Operações/Proventos, and a column picker.
- [ ] Receipts: **not in the backup zip** (a year of photos in every daily zip × 7 days of
  retention) — copy `backend/attachments/` alongside the database when moving it; no thumbnails or
  inline preview; no receipts on card purchases (`cc_expenses`) — they reach the statement only as
  the invoice payment, so a purchase receipt goes on that for now.
- Budget strip on Início: an "estourou" entry in "Precisa de você" was left out on purpose (a
  budget is a plan, not a task); open decision 1 still applies to what the strip counts as spent.

### Phase 5 — Backend refactor — in progress (started 2026-09-23)
Split `backend/app.py` one area at a time, code moved verbatim, suite green and one commit per step.
Foundation, services and nine blueprints are out (see `docs/done-tasks.md`); `tests/test_route_map.py`
pins the 60 routes.
- [ ] Investments — everything left in `app.py`. Suggested cut, bottom-up (details in the handoff):
  `services/prices.py` (cache, brapi/yfinance, history), `services/fixed_income.py` (BCB, accrual,
  rate terms), `services/investments.py` (movements, cash sync, FIFO, realized results, tax),
  `services/portfolio.py` (snapshot, materialized positions, evolution), then `routes/investments.py`,
  `routes/proceeds.py`, `routes/market.py`. The tests patch many of these names — retarget each
  patch to the module that *reads* the name.
- [ ] Then `app.py` is only the factory + boot; consider a `create_app()` so tests stop depending
  on import-time side effects.

### Frontend debt
- [ ] Centralized server state (TanStack Query). A small `DataVersionContext` covers "+ Novo" refetch for now.
- [ ] Loading skeletons on heavy screens.

### Operations
- [ ] Integration healthcheck for yfinance.
- [ ] Structured logging.

### Phase 6 — Advanced investments
- [ ] Corporate actions (splits, reverse splits, bonus shares).
- [ ] Real multi-currency (`assets.currency` is not converted today).
- [ ] Annual tax report.
- [ ] Evolução do Patrimônio: fixed income and other non-quoted assets show only their cost in past
  months (the backend marks them to market in the current month only), so their gain appears as a
  step in the last bar. Needs a historical accrual per month (CDI/IPCA series are already fetched).

---

## 2. Open decisions

1. **Credit card purchases vs. budget.** Card purchases only reach the budget when the invoice is
   paid, as one "Pagamento Fatura" lançamento. Options: budget the invoice categories; count open
   `cc_expenses` into their category; or materialize installments as `transactions` on settlement.
2. **Recurring pause/resume** drops an occurrence already overdue before the pause (accepted for now;
   fix would be a `paused_at` column). Related: reviving a finished recurrence by extending its
   `end_date` restarts after the latest *surviving* generated lançamento, so a deleted last one is
   regenerated — a stored cursor would fix both.
3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
4. **Desktop only or phone access?** The layout is now responsive (bottom bar, card lists); hosting
   with HTTPS is still undecided.
5. **Tax: support tool or source of truth?** Filing-grade use needs reconciliation against
   brokerage notes.
7. **Cartões header: Pagar fatura and "Nova compra" side by side.** Kept both: "Nova compra" opens
   the sheet already on the card type, which the global "+ Novo" does not. Revisit if it still
   feels crowded.
8. **Wording and fit.** The Início cash-flow legend still says "Entradas/Saídas" (the glossary allows
   plurals for aggregates) — switch to Receitas/Despesas? The "+ Novo" type selector wraps onto two
   lines so "Investimento" stays visible — acceptable, or shorten the labels?
