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
| UX reorganization: 4 sections + Ajustes, "+ Novo" sheet, Carteira merged away, phone layout (`docs/ux-reorganization.md`) | 2026-09-21 |

---

## 2. Open work, in priority order

### UX reorganization — follow-ups
All six steps done (`docs/ux-reorganization.md`). Tested only on a scratch database so far.
- [ ] **Owner walk-through in the real app**, then settle open decisions 6–8 below.
- [ ] Keep statement filters in the URL — today a reload clears them.
- [ ] Add a favicon to `frontend/index.html` — every first load logs a 404.
- [ ] Split the bundle (737 kB, over Vite's 500 kB warning) with route-level `lazy()`.

### Bugs found during the UX work (pre-existing, backend)
- [ ] Registering a provento against a fixed-income asset (CDB) returns a backend error.
- [ ] Quote update on fixed-income assets fails with `'str' object has no attribute 'get'` (and
  "Percentual do CDI nao informado" when the CDI % is missing).

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

---

## 3. Open decisions

1. **Credit card purchases vs. budget.** Card purchases only reach the budget when the invoice is
   paid, as one "Pagamento Fatura" lançamento. Options: budget the invoice categories; count open
   `cc_expenses` into their category; or materialize installments as `transactions` on settlement.
2. **Recurring pause/resume** drops an occurrence already overdue before the pause (accepted for now;
   fix would be a `paused_at` column).
3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
4. **Desktop only or phone access?** The layout is now responsive (bottom bar, card lists); hosting
   with HTTPS is still undecided.
5. **Tax: support tool or source of truth?** Filing-grade use needs reconciliation against
   brokerage notes.
6. **"+ Novo" twice on Início and Extrato.** The page header has one and so do the sidebar
   (desktop) and the bottom bar (phone). Keep both, or drop the header one?
7. **Cartões header: Pagar fatura and "+ Novo" side by side.** Pagar fatura is primary while an
   invoice is open. Keep both, or rely on the global "+ Novo" only?
8. **Wording and fit.** The Início cash-flow legend still says "Entradas/Saídas" (the glossary allows
   plurals for aggregates) — switch to Receitas/Despesas? The "+ Novo" type selector wraps onto two
   lines so "Investimento" stays visible — acceptable, or shorten the labels?
