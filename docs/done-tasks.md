# Done Tasks — FinanceMVP

> Record of completed work, moved out of `docs/next-steps.md` so the plan holds only what is still
> open. When a task is finished, remove it from `next-steps.md` and add it here — newest at the
> bottom of the table, with any detail worth keeping in the notes below it. Anything left over from
> a finished task (a "not built", an owner walk-through) stays in `next-steps.md` as an open item.

---

## Completed work

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
| Visual design pass (audit + items 1–7, decisions A–D): tabular figures and a real minus, pt-BR percentages, MetricCard that never truncates money, ~44 px table rows with right-aligned values and sticky headers, colour only with meaning, one-line chart axes, phone density, grey disabled buttons | 2026-09-22 |
| Decision 6 settled: "+ Novo" twice on Início and Extrato — the header one is gone (visual pass decision B) | 2026-09-22 |
| Início "Orçamento do mês" strip: month total spent vs. available and the categories near or over their limit; shared `components/BudgetProgress.jsx` with Orçamento | 2026-09-22 |
| Tables switch to cards below `xl` so they fit without sideways scroll; Proventos' empty calendar explains itself and opens the form | 2026-09-22 |
| Import rules: edit a rule (pattern included) and apply rules to lançamentos already recorded, with a preview and per-row confirmation | 2026-09-22 |
| Receipts per lançamento (PDF/image, several per row) from Extrato — migration 014 | 2026-09-23 |
| UI remodel, direction C, with dark mode: tokens, shell, Início, Extrato, Cartões, then Posição/Operações/Proventos, Orçamento/Recorrentes, Importar (stepper), Ajustes; kit `SummaryPanel`, `Menu`, `Toast` | 2026-09-23 |
| Phase 5 started: foundation modules, services and nine blueprints out of `app.py` (7,692 → 3,603 lines); URL-map test | 2026-09-23 |
| Phase 5 finished: investments out of `app.py` into five services and three blueprints; `app.py` is 60 lines of boot | 2026-09-23 |

---

## Notes on completed work

Detail that used to sit in `next-steps.md` and is still useful as reference — mostly for the owner
walk-through, which remains open there.

### Visual design pass — 2026-09-22
The audit and plan from the same day were approved with decisions A–D; all seven items shipped as
one commit per theme (`a9d2422`..`d3a20be`), checked with Playwright screenshots at 1280 px and
390 px on scratch data. What changed:
- **Numbers:** tabular figures app-wide; `formatCurrency` prints a real minus (U+2212);
  `formatSignedCurrency` for lists of entradas/saídas (sign glued to the value); `formatPercent` in
  pt-BR ("1,29%") and the only copy; `shortMonthLabel` ("out/25") on every chart axis.
- **MetricCard:** icon beside the label, value on one line that shrinks to fit (`FitValue` in
  `ui.jsx`), no hover lift. Two across on phone.
- **Tables** (Extrato, Posição, Operações, Proventos; Cartões purchases as a list): right-aligned
  values, ~44 px rows, truncation with a title, sticky header (no `overflow-x` wrapper — keep it that
  way), `IconButton size="sm"` for row actions. Extrato dropped the Tipo column (only transfer and
  investment keep a neutral tag) and shows 100 rows + "Mostrar mais" (D). On phone an Extrato row
  opens the edit form on tap; Excluir lives inside it.
- **Colour:** green/red/amber/sky only for gain/loss/warning/info; labels, counts, statuses that are
  the normal state, and open invoices are neutral. Archive buttons are neutral, delete stays red.
- **Chrome:** flat background (A), no eyebrow and no page-level "+ Novo" on Início/Extrato (B;
  Cartões keeps "Nova compra", which preselects the card type), 256 px sidebar (C).
- **Kit:** grey disabled `Button`, lighter `Badge`, `SegmentedControl` with the `Tabs` sliding pill
  (shared `useSlidingPill`), `Expand` with a `minmax(0,1fr)` column, `.app-table` rules under
  `:where()` so utilities win.
- **E** (dark mode) shipped with the UI remodel below.

### UI remodel — direction C "Cartões" + dark mode — 2026-09-23
Owner picked **C with dark mode** on 2026-09-23 (audit and mocks:
`git show 36e0164:docs/ui-remodel-audit.md`; canvas https://claude.ai/artifact/DPSbd7JxFULWe4r9z36tto).
- **Tokens + dark mode + font**, **shell + kit**, **balance bug** (consolidated balance includes
  opening balances), **Início**, **Extrato**, **Cartões** — see the handoffs of 2026-09-23 in git.
- **Kit:** `SummaryPanel` (one headline figure and up to three beside it — replaces rows of
  `MetricCard`s; `ProjectionHeader` uses it), `Menu` (the "⋯" row menu), `Toaster` + `toast()` in
  `lib/toast.js` (short success notices; errors stay in `AlertMessage`).
- **Posição:** summary panel (carteira, aplicado, resultado with %, líquido estimado — from the
  backend's totals, masked by the eye). The per-row quote input is gone: the quote is read-only with
  its status dot; "Editar cotação" and "Atualizar cotação" are in the row `Menu` and editing opens a
  sheet. Fixed-income partial redemption is a sheet instead of two `window.prompt`s and an `alert`
  (same payload). Ticker and title names wrap instead of truncating.
- **Operações / Proventos:** summary panel instead of four cards; row actions in `Menu`; success
  notices are toasts; the `alert()` on a failed delete is now the page's warning banner.
- **Orçamento / Recorrentes:** summary panel; Editar/Remover (and Pausar/Retomar) in `Menu`, the
  Acumula toggle stays on the row; Recorrentes' notices are toasts.
- **Importar:** three-step stepper (Arquivo → Conferir → Importado) above the two panels, the
  preview rows run edge to edge. Fixed along the way: the "N lançamento(s) importado(s)" banner was
  cleared by the preview reload the instant it appeared — it had never shown until then.
- **Ajustes:** section chips in the pill style; Categorias and Regras row actions in `Menu` (Regras
  keeps "Aplicar" as a button); Contas and Cartões keep their single icon button (one action is not
  worth a menu); notices are toasts; inner boxes rounded like the rest.
- **Extrato:** Editar/Excluir in `Menu`; the paperclip stays visible beside it.

### Phase 4 — Reduce friction — 2026-09-22
- **CSV statement import** — `backend/statement_import.py` parses the file (delimiter sniffing,
  pt-BR and en-US numbers, the usual date shapes), `POST /api/import/preview` shows what would enter
  without writing, `POST /api/import/commit` writes it. Dedupe is `source_type='STATEMENT_IMPORT'`
  plus a hash of account + date + amount + normalized description, so the unique index from 007
  makes a re-import a no-op; identical rows inside one file get an occurrence suffix and survive.
- **Auto-categorization rules** — `import_rules` (migration 013), `/api/import-rules`, applied in
  the preview only. Managed in Ajustes → Regras de importação, or created straight from a preview row.
- **OFX import** — hand-rolled SGML reader in the same module (no `ofxparse` dependency); the bank's
  `FITID` becomes the dedupe key when the file carries one.
- **Rules on lançamentos already recorded** — `POST /api/import-rules/apply/preview` lists what
  would change category (never writes); `POST /api/import-rules/apply` rewrites `category` and
  `category_id` only for the confirmed `transaction_ids`, re-checking each against the rule, and adds
  to the rule's `hits`. With `rule_id` it runs just that rule (even inactive); without, all active
  rules in import priority. TRANSFER, investment cash and invoice payments are never touched.
  Ajustes → Regras: "Aplicar ao extrato" (all rules) and "Aplicar" per rule open a sheet with every
  row ticked; the pencil edits a rule in the same form as "Nova regra". Tests in
  `backend/tests/test_rule_apply.py`.

### Export to CSV — 2026-09-22
`GET /api/transactions/export` (the same filters as the statement list) and
`GET /api/investments/portfolio/export`. The file is what Excel in pt-BR opens on a double click:
BOM UTF-8, `;` as the separator, comma as the decimal mark. Formatting lives in
`backend/export_csv.py` (pure functions, no DB — the `statement_import.py` shape). The statement has
both `Valor` (magnitude) and `Valor com sinal`, and a TRANSFER leaves the signed column empty so
summing it cannot turn moving money between your own accounts into an expense. Buttons: Extrato →
"Exportar" (exports exactly what the filters show) and Investimentos → Posição → "Exportar".

### Receipts per lançamento — 2026-09-23
Table `transaction_attachments` (migration 014) rather than a path in `metadata`: several files per
row, and `metadata` is rewritten by the investment cash sync. Files live in
`ATTACHMENTS_DIR/<user_id>/<generated name>` (default `backend/attachments/`, gitignored); the type
is sniffed from the bytes (PDF, JPG, PNG, GIF, WEBP, HEIC), 10 MB and 20 files per lançamento.
Routes are nested under the lançamento (`/api/transactions/<id>/attachments`, `.../<aid>/file`,
`DELETE .../<aid>`), so the ids must match. Deleting a lançamento removes its files; files orphaned
by other paths (an investment movement deleted takes its cash row) are swept at boot.
`GET /api/transactions` carries `attachment_count`. Any row takes receipts, including investment
cash and invoice payments. Tests in `backend/tests/test_attachments.py`.

### Budget strip on Início — 2026-09-22
"Orçamento do mês" panel reading `GET /api/budgets` for the current month; status rule mirrors
`serialize_budget()` (`budgetStatus()` in `components/BudgetProgress.jsx`).

### Phase 5 — Backend refactor, first part — 2026-09-23
Code moved verbatim, suite green and one commit per step. `tests/test_route_map.py` pins the 60
routes (rule, methods, token) from before the split.
- Foundation: `config.py`, `db.py`, `validators.py`, `auth.py`, `money.py`, `dates.py`,
  `source_types.py`.
- Services: `services/accounts.py`, `services/invoices.py`, `services/attachments.py`.
- Blueprints: system, auth, accounts (+ transfers, categories), transactions (+ CSV export),
  attachments, budgets, recurring, imports (+ rules), cards (+ cc-expenses, pay-invoice).
  `app.py` 7,692 → 3,603 lines.

### Phase 5 — Backend refactor, investments — 2026-09-23
Same rules: 133 definitions moved byte-identical (checked by script against `363e518`), the only
edit `@app.route` → `@bp.route`; suite green and one commit per step (`93fe66a`..`a06b3f1`).
- `asset_classes.py` (the class constants and `parse_asset_class_filter`), `responses.py`
  (`csv_response`, out of `routes/transactions.py` so no blueprint imports another).
- `services/prices.py` (caches, executor, brapi/yfinance, `record_price_quote`),
  `services/fixed_income.py` (indexers, BCB, accrual, the two-half refresh),
  `services/investments.py` (movements, assets, cash link, backing validation),
  `services/realized_results.py` (tax rates, FIFO, realized results — split out of investments,
  which would otherwise have been ~1,000 lines), `services/portfolio.py` (snapshot, materialized
  positions, market refresh, evolution). Import order: prices ← fixed_income ← investments ←
  realized_results / portfolio.
- Blueprints `routes/investments.py`, `routes/proceeds.py` (proceeds helpers live in the blueprint,
  their only caller), `routes/market.py`.
- Tests reach moved code through fixtures `prices_module`, `fixed_income_module`,
  `realized_results_module`, `portfolio_module`; `yf` is patched in `services.prices` *and*
  `routes.investments` (the history route reads it too).
