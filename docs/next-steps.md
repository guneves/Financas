# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`; this file only tracks *what* is done and *what* is next.

---

## 1. Done

| Area | When |
|---|---|
| Local auth (signup/login/JWT) | before 2026-09-15 |
| Income and expenses | before 2026-09-15 |
| Credit cards, installment purchases, invoice settlement | before 2026-09-15 |
| Normalized investments, FIFO cost basis, realized results, estimated tax | before 2026-09-15 |
| Investment ↔ cash linkage | before 2026-09-15 |
| Proceeds (dividends/JCP/amortization) with calendar and summary | before 2026-09-15 |
| Quotes with freshness status and per-asset refresh | before 2026-09-15 |
| Dashboard (net worth, balance, expenses by category, installments, next invoice) | before 2026-09-15 |
| Housekeeping: stray DBs/logs, `.gitignore`, `JWT_SECRET`, seed scripts moved to `backend/scripts/` | 2026-09-15 |
| `CATTLE` asset class — decided to keep (live, not dead code) | 2026-09-15 |
| Backend test suite (pytest, throwaway DB) | 2026-09-15 |
| Single start script `start.ps1` | 2026-09-15 |
| Automatic backup on boot with retention | 2026-09-15 |
| Invoice-month rule moved to the backend | 2026-09-15 |
| Bank accounts and transfers (§3.1) — migration 007 | 2026-09-16 |
| Categories as a table, with subcategories and management screen (§3.2) — migration 008 | 2026-09-16 |
| Editing a transaction | 2026-09-16 |
| Monthly budget by category, with rollover (§3.3) — migration 009 | 2026-09-16 |
| Recurring entries with cash-flow forecast (§3.4) — migration 010 | 2026-09-16 |
| Shared `frontend/src/lib/format.js` | 2026-09-16 |
| B3 ticker catalog, autocomplete, and guard on buys | 2026-09-16 |
| Statement search and filters (§3.7) — closes Phase 3 | 2026-09-21 |
| UX reorganization: 4 sections + Ajustes, "+ Novo" sheet, Carteira merged away, phone layout (spec in git at `9c186fe:docs/ux-reorganization.md`, file removed) | 2026-09-21 |
| Invoice payment only after closing, server-side; "Débito automático" per card — migration 011 | 2026-09-22 |
| Investimentos: "Evolução do Patrimônio" (monthly valor aplicado + ganho de capital, 6M–5A) replaces "Rentabilidade por ativo" | 2026-09-22 |
| Username (display name) on signup, editable in Ajustes → Perfil; email no longer shown as the name; privacy toggle (eye) masks money and name — migration 012 | 2026-09-22 |
| BCB fetch hardened (404 = no data yet, >10-year windows split, error payloads reported); fixed-income rate metadata validated on save; clearer provento error without a position | 2026-09-22 |
| Invoice payment: account picker (card's autopay account, else default); Início warns when an autopay account will not cover upcoming debits | 2026-09-22 |
| Statement filters in the URL; favicon; route-level `lazy()` (largest chunk 386 kB, was 737 kB) | 2026-09-22 |
| Phase 4: CSV/OFX statement import with preview and dedupe, auto-categorization rules — migration 013 | 2026-09-22 |
| Export to CSV (Excel pt-BR) of the filtered statement and of the portfolio | 2026-09-22 |
| brapi as the primary quote provider (batch + 5-min cache + dedupe + market-hours TTL), yfinance as fallback | 2026-09-22 |
| Motion pass: sheet/collapsible exit animations, sliding tab pill, count-up and chart draw-in once per page per session, reduced motion honoured in JS, new-row flash in Extrato, invoice-paid confirmation — zero new dependencies | 2026-09-22 |
| Privacy mode rework: the eye no longer remounts the page (no refetch, no empty-state flash) and hides only account balances, net worth and the investment portfolio; name and e-mail stay visible — `lib/privacy.js` | 2026-09-22 |

---

## 2. Open work, in priority order

### Browser walk-through (owner) — everything below is backend-tested and `vite build` clean only
The Chrome extension was offline again on 2026-09-22. Playwright turned out to be usable from the npx
cache (see the handoff), so screenshots are possible now, but none of the items below has been
clicked through by the owner. One pass in the real app covers all of it:
- [ ] UX reorganization (all six steps), then settle open decisions 6–8 below.
- [ ] Signup with username and Ajustes → Perfil. Existing accounts have `username = NULL` and show
  "Usuário" until they pick one.
- [ ] Eye toggle (reworked 2026-09-22, checked by script only): the page stays put — no reload, no
  skeleton, numbers do not recount. Hidden: Início's four top cards, "Evolução do saldo" (badge, axis,
  tooltip), "Saldo por conta", the autopay-shortfall warning; the three balance cards on Extrato and
  Cartões plus Cartões' two "Saldo…" cards; Ajustes → Contas; the balance in Pagar fatura's account
  picker; all of Posição (allocation, Evolução do Patrimônio, group totals, quantities, values, the
  fixed-income principal) and the position values in the sale picker. Everything else stays visible.
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
- [ ] Motion pass: every sheet ("+ Novo", Pagar fatura, investimento, editar operação) animates
  out, not just in, and shows its last content while leaving (no "Pagar R$ 0,00" flash). Tab pill
  slides between abas. Início numbers count up on the first visit only; leaving and coming back,
  or toggling the eye, shows them still. Collapsibles and Cartões invoices open and close in height,
  and focus rings inside an open one are not clipped. A lançamento saved by "+ Novo" flashes green
  in Extrato. Paying an invoice shows a green confirmation with a drawn check; a refused payment
  shakes the error. With Windows "animation effects" off, nothing moves (charts included).

### Visual design pass — audit done, plan waiting for the owner's approval
A full screen-by-screen audit (1280 px and 390 px, before-screenshots in the 2026-09-22 session
scratchpad) found, in order of daily-use cost: MetricCard values truncated at 1280 px ("R$ 1.99…" on
Início, Operações, Recorrentes, Proventos, Orçamento); money left-aligned and not tabular in every
table, the sign wrapping onto its own line in Extrato, three sign styles, `formatPercent` printing
"1.29%"; colour used without meaning (red "Despesa" on every Extrato row, every open invoice in red,
green/red Compra/Venda, amber JCP); 65–120 px rows (Extrato, Posição, Cartões); horizontal overflow
in Posição and Proventos; three header layers plus a duplicate "+ Novo"; chart axes wrapping
("R$ 900 / mil") at ~3.4:1 contrast; `text-zinc-400` text at 2.6:1. Proposed, one commit each:
- [ ] 1. Tokens and money type — `index.css`, `tailwind.config.js`, `lib/format.js`: tabular-nums
  everywhere, zinc-500 as the lightest text, pt-BR `formatPercent`, `formatSignedCurrency` (real minus,
  non-breaking space).
- [ ] 2. `MetricCard` never truncates money — inline icon, one type step down at 4 columns,
  shrink-to-fit, no hover lift.
- [ ] 3. Tables — right-aligned numbers, sticky header, ~44 px rows, truncated descriptions; Posição
  inline quote; Cartões purchases as rows; overflow fixed.
- [ ] 4. Colour meaning — green/red/amber/sky only for gain/loss/warning/info.
- [ ] 5. Charts — one-line axes, AA ticks, one month-label format. (Privacy axes: done.)
- [ ] 6. Phone density — Extrato rows, Cartões invoice row, metric cards two across.
- [ ] 7. States and leftovers — real disabled button, hand-built alert → `AlertMessage`, Ajustes
  sub-nav → `Tabs` look, `SegmentedControl` sliding pill.
Decisions for the owner: **A** drop the background gradients; **B** drop the eyebrow and the
page-level "+ Novo" (see decision 6 below); **C** sidebar 288 → 256 px; **D** Extrato shows ~100
rows + "Mostrar mais" (it renders all 804 today); **E** dark mode, separately scoped, optional.

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

### Phase 4 — Reduce friction — done, not yet clicked through
- [x] **CSV statement import** — `backend/statement_import.py` parses the file (delimiter sniffing,
  pt-BR and en-US numbers, the usual date shapes), `POST /api/import/preview` shows what would enter
  without writing, `POST /api/import/commit` writes it. Dedupe is `source_type='STATEMENT_IMPORT'`
  plus a hash of account + date + amount + normalized description, so the unique index from 007
  makes a re-import a no-op; identical rows inside one file get an occurrence suffix and survive.
- [x] **Auto-categorization rules** — `import_rules` (migration 013), `/api/import-rules`, applied
  in the preview only. Managed in Ajustes → Regras de importação, or created straight from a preview
  row.
- [x] **OFX import** — hand-rolled SGML reader in the same module (no `ofxparse` dependency); the
  bank's `FITID` becomes the dedupe key when the file carries one.
- [ ] Not built: applying rules to lançamentos already recorded (rules only run on import), amount
  and account conditions on a rule, and editing a rule's pattern after creation (toggle + delete
  only). Import is capped at 2,000 rows per file.

### Smaller gaps
- [x] **Export to CSV** — `GET /api/transactions/export` (the same filters as the statement list) and
  `GET /api/investments/portfolio/export`. The file is what Excel in pt-BR opens on a double click:
  BOM UTF-8, `;` as the separator, comma as the decimal mark. Formatting lives in
  `backend/export_csv.py` (pure functions, no DB — the `statement_import.py` shape). The statement
  has both `Valor` (magnitude) and `Valor com sinal`, and a TRANSFER leaves the signed column empty
  so summing it cannot turn moving money between your own accounts into an expense. Buttons:
  Extrato → "Exportar" (exports exactly what the filters show) and Investimentos → Posição →
  "Exportar". Not built: .xlsx proper, exporting Operações/Proventos, and a column picker.
- [ ] Attachments/receipts per transaction (file stored locally, path in `metadata`).
- [ ] Dashboard strip for the budget (overdue recurrences and the open invoice are now on Início).

### Phase 5 — Backend refactor
- [ ] Split `backend/app.py` into blueprints (config, db, auth, validators, services/portfolio,
  prices, invoices, routes/*), one at a time, suite green between steps.

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

## 3. Open decisions

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
6. **"+ Novo" twice on Início and Extrato.** The page header has one and so do the sidebar
   (desktop) and the bottom bar (phone). Keep both, or drop the header one?
7. **Cartões header: Pagar fatura and "+ Novo" side by side.** Pagar fatura is primary while the
   nearest invoice is closed (disabled before that). Keep both, or rely on the global "+ Novo" only?
8. **Wording and fit.** The Início cash-flow legend still says "Entradas/Saídas" (the glossary allows
   plurals for aggregates) — switch to Receitas/Despesas? The "+ Novo" type selector wraps onto two
   lines so "Investimento" stays visible — acceptable, or shorten the labels?
