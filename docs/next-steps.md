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

---

## 2. Open work, in priority order

### UX reorganization — follow-ups
All six steps done (summary at `5faa425:docs/ux-reorganization.md`). Tested only on a scratch database so far.
- [ ] **Owner walk-through in the real app**, then settle open decisions 6–8 below.
- [ ] Keep statement filters in the URL — today a reload clears them.
- [ ] Add a favicon to `frontend/index.html` — every first load logs a 404.
- [ ] Split the bundle (737 kB, over Vite's 500 kB warning) with route-level `lazy()`.

### Username and privacy mode (done 2026-09-22, follow-ups)
- [ ] Not checked in a browser yet (the Chrome extension was offline). Walk through signup, the
  eye toggle on every page (charts, tooltips, "+ Novo" sheet) and Ajustes → Perfil.
- [ ] Existing accounts have `username = NULL` and show "Usuário" until they pick one.
- [ ] Masking covers values formatted through `lib/format.js` / `compactCurrency`. Percentages and
  share quantities stay visible on purpose; chart shapes still show relative sizes.

### Bugs found during the UX work (pre-existing, backend)
- [ ] Registering a provento against a fixed-income asset (CDB) returns a backend error.
- [ ] Quote update on fixed-income assets fails with `'str' object has no attribute 'get'` (not
  reproduced on 2026-09-22 against a scratch DB; the missing-rate case now reports "Taxa do titulo
  nao informada").

### Fixed income — type and indexer (done 2026-09-22, follow-ups)
Buys carry `fixed_income_type`, `rate_type` (POS/PRE), `indexer` (CDI/CDI_PLUS/IPCA) and
`cdi_percentage` or `annual_rate`; the quantity field is gone for fixed-income buys. Valuation in
`refresh_fixed_income_prices` handles all four forms (tests: `test_fixed_income_indexers.py`).
- [ ] IPCA+ is an **estimate**: the purchase month is pro rata by calendar days and the current,
  unpublished month is missing until the BCB releases it. Real contracts use pro rata by business
  days and the projected IPCA — revisit if the owner holds IPCA+ papers and sees a gap.
- [ ] The backend does not validate the new metadata keys on `POST /api/investments`; a bad
  indexer surfaces only as a failed refresh.
- [ ] Lancamentos from before this change have no `fixed_income_type`; the edit sheet asks for
  one on first edit.

### Credit card payment — closed-only + Débito automático (done 2026-09-22, follow-ups)
Payment goes through `POST /api/cc-expenses/pay-invoice` (EXPENSE + PAID in one DB transaction),
refused with 409 before the closing day; the status PATCHes refuse PAID the same way. A card with
`autopay_account_id` is paid on its due date by `apply_due_autopay()`, which runs at the start of
the GETs for transactions, accounts, cards and cc-expenses (tests: `test_invoice_payment.py`).
- [ ] Manual payment always debits the **default account**; there is no account picker in the
  Pagar confirmation. Use the card's autopay account when set, or ask?
- [ ] Autopay does not check the balance — it debits even into the negative, as a real bank's
  débito automático would try to. Warn on Início when the debit account will not cover it?
- [ ] Not clicked through in a browser; verified by backend tests and `vite build`.

### Phase 4 — Reduce friction
- [ ] **CSV statement import** with configurable column mapping; dedupe by hash (date + amount +
  normalized description) so re-imports are idempotent.
- [ ] **Auto-categorization rules** (`import_rules`: description contains X → category).
- [ ] **OFX import** (`ofxparse`).

### Smaller gaps
- [ ] Attachments/receipts per transaction (file stored locally, path in `metadata`).
- [ ] Export to CSV/Excel for the statement and the portfolio.
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
