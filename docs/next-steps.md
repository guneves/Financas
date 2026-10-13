# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`. This file holds **only open work**: when a task is finished, remove it from here and
> record it in `docs/done-tasks.md` — no ticked boxes, no "done" sections.

---

## 1. Open work, in priority order

### Separate the investments area from the banking area
Plan approved by the owner on 2026-10-12; design, decisions and traps in `docs/areas-separation.md`
— read it before starting a phase. Today every buy, sale and redemption mirrors a lançamento into
the Extrato, always in the default account. The rule to build: an operation touches the banking
area only when the owner asks for it (`metadata.cash_account_id` on the movement, replacing
`skip_cash`). Nothing is built yet. One phase per commit, in this order:
- [ ] **Phase 1 — backend.** The link becomes opt-in and takes an account
  (`sync_investment_cash_transaction()`, validation in `routes/investments.py`); migration 024
  converts the flags without moving any balance (rows linked today stay linked);
  `test_investment_cash_link.py` rewritten, the six test files that read linked rows pass the key,
  a migration test. Rewrite the cash-link convention in `CLAUDE.md` with it.
- [ ] **Phase 2 — forms and bulk unlink.** "Lançar no extrato" (off by default) with an account
  picker in "Registrar operação", the Operações edit form and the Posição redemption sheet,
  replacing "Operação anterior ao app"; Operações tags linked rows; `GET /api/investments/cash-links`
  (preview) and `POST /api/investments/cash-links/unlink` (ids only, rows with receipts skipped),
  behind "Desvincular do extrato…".
- [ ] **Phase 3 — banking read side.** A linked or typed-in-"Investimento" INCOME is a resgate,
  not a receita (Início cash flow and month result, Extrato totals); "+ Novo" becomes banking-only
  and opens "Registrar operação" inside Investimentos. Then fold the lasting rules into `CLAUDE.md`
  and delete `docs/areas-separation.md`.
- [ ] Owner's call, outside the phases: the same opt-in for proventos (they never reach an account
  today); moving Metas from Planejamento to Investimentos; remembering the checkbox's last choice.

### Owner walk-through on real data
Everything below was built and clicked through on a seeded scratch database (Chrome + Playwright,
2026-09-23); none of it has been used on the owner's real data yet. Restart the backend first: the
running `:5000` process predates migrations 015–018 and the brapi fix. What each item does is in
`docs/done-tasks.md`.
- [ ] Signup with a username (typed in the browser — Claude only checked it through the API), then
  Ajustes → Perfil.
- [ ] Open an exported `.xlsx` and a `.csv` in Excel (no Excel on the dev machine; the `.xlsx` was
  validated with openpyxl): extrato with filters, operações, proventos, IR. Carteira `.xlsx` was
  checked by the owner 2026-09-26 and its fixes are in; re-export it once to see whole quantities
  without the trailing comma.
- [ ] Budgets under decision 1: card purchases now count in the purchase month and the invoice
  payment no longer counts, so card-heavy categories may read as overrun — re-plan them.
- [ ] Import rules with amount/account conditions on a real bank file.
- [ ] Receipts: a phone photo (HEIC only opens in Safari), a receipt on a card purchase, and after
  the next backup check that `backend/backups/attachments/` holds the files.
- [ ] Ajustes → Integrações: all green? (`BRAPI_TOKEN` is set in `backend/.env`.)
- [ ] Corporate actions: register one real past event (if any) and compare quantities and average
  price with the broker.
- [ ] Multi-currency: if you hold anything abroad, one purchase with the broker's exchange rate, and
  a USD account.
- [ ] IR tab for the last year against the broker's informe de rendimentos.
- [ ] Motion and phone layout by eye (scripted checks passed: sheets animate out, count-up only on
  first visit, reduced motion, tab pill).
- [ ] Recorrentes after migration 019 (2026-09-26): pause one, check "pausada desde", resume it
  later — only the paused weeks/months are skipped; anything due before the pause stays pending.
  A recurrence paused *before* 019 still resumes the old way (skips everything up to today).
- [ ] Allocation, goals and the exemption meter (2026-09-26, migrations 020–021): in Investimentos →
  Alocação, set the class targets (and per-asset ones where you have them) and try "Quanto vai
  aportar?" with the next contribution — does the split match what you would do? In Planejamento →
  Metas, recreate the Investidor10 goals (patrimônio 100 mil…5 mi, renda R$ 500) and compare the
  estimated dates (theirs seem to assume a return; set "Rentabilidade esperada"). On the IR tab,
  the current month's meter should match Investidor10's "isentômetro" once the same sales are
  recorded here. Open "Registrar operação" → Venda on a stock to see the warning.
- [ ] Proventos por ativo, Rentabilidade (TWR) and Aportes (2026-09-26, built in parallel by three
  subagents, **none opened in a browser yet**): Investimentos → Proventos "Por ativo" table and the
  Mensal/Anual toggle; Posição's new "Proventos" and "Rentab. c/ proventos" columns (9 columns now —
  check the 1280px layout and decide whether "Rentab. c/ proventos" should replace "Rentab.");
  the new Investimentos → Rentabilidade tab (TWR vs Investidor10's "Rentabilidade" and "% do CDI");
  Operações' "Aportes e resgates" chart; Alocação's concentration warning (asset > 10%, no
  exposure abroad). Also: Rentabilidade's class filter, and the four new provento
  columns in the carteira export (open the `.xlsx`).

### Benchmarks, sectors and IRPF text (2026-09-26 night) — owner checks
Built by three subagents, tested with mocks and one live provider run, **not opened in a browser**.
- [ ] Rentabilidade: the benchmark cards and lines (CDI, IPCA, Ibovespa on by default); compare
  Ibovespa's period total with Investidor10.
- [ ] Alocação → "Por setor": press "Buscar setores" once (needs `BRAPI_TOKEN`), check the stock
  sectors and FII segments, fix the wrong ones with the pencil (brapi files MXRF11 as Logística).
- [ ] IR tab → "Para colar no programa do IRPF": paste each section into the 2026 program and check
  two codes: FII payouts under isentos **99** "Outros", and whether tributação exclusiva (JCP 10,
  aplicações 06) wants the **net** value (what the text gives) or gross + IR retido (what the tab's
  older caption says). Fill the "(preencher)" CNPJs.

### brapi plan allows 1 ticker per request
Found 2026-09-26: a 2-ticker quote call returns 400 `QUOTES_PER_REQUEST_EXCEEDED`, while
`MAX_SYMBOLS_PER_REQUEST = 20` in `backend/brapi_client.py`, so any multi-ticker quote refresh fails
and silently falls back to yfinance. Owner's call: set it to 1 (one credit per ticker) or leave
yfinance as the de facto source and keep brapi for single quotes/sectors.

### Found while fixing the walk-through inconsistencies (2026-09-27)
- **Budgets on income categories.** Orçamento offers income categories when adding a budget and the
  backend accepts them; their "spent" is the category's income, and `build_budget_month()` adds it
  to `totals.spent`, so the "Realizado" tile and the Início budget strip mix income into "gasto".
  Owner's call: refuse income categories in budgets, or keep them out of the totals.
- **A position with applied value ≤ 0 drops out of the monthly valuation.** `portfolio_month_positions()`
  skips it; that happens to a stock after a large profitable partial sale (sales subtract the sale
  value, not the cost). Posição keeps it, so Rentabilidade/Evolução and Posição can still disagree
  for such an asset. Not in the seed; fixing it puts a jump into that asset's TWR — decide first.

### Fixed-income form (2026-09-27 night) — leftovers
Exemption by title type, IPCA+ in Rentabilidade and the removal of Gado are built (see
`docs/done-tasks.md`); what it left open:
- [ ] Owner check in the browser: Registrar operação → Renda Fixa, pick LCA / CDB / IPCA+.

### Ritmo de gastos against the 3-month average (2026-10-12) — leftovers
The Início panel now compares the month so far with the average of the 3 previous months at the same
day (see `docs/done-tasks.md`); what it left open:
- [ ] Owner check on real data: Início → Ritmo de gastos. Do the three months' figures look right?
- [ ] "Despesas por categoria" still compares each category with last month's **whole** total, so
  its arrows and the pace panel answer different questions. Owner's call: move the category arrows
  to the same 3-month, same-day average (it would say *where* the overspending is).
- [ ] A month only partly recorded (the app started mid-month) still enters the average and pulls
  it down; only a month with no spending at all is left out.

### Ideas from the Investidor10 survey (2026-09-26, not prioritized)
Seen in the owner's Investidor10 PRO wallet and not built; each needs the owner's call first.
- Fundamentals columns (Bazin ceiling price, P/L, P/VP, 5-year DY) — external data.
- B3 import of trades and proventos (the investor-area spreadsheet, via the existing import).
- Sector targets/rebalancing (today the sector view is a breakdown only).

### Known limits, accepted for now
- Privacy mode hides balances, net worth and the portfolio only — lançamentos, faturas, orçamentos,
  operações and proventos stay visible by the owner's choice. Percentages stay visible; chart
  shapes still show relative sizes. A sensitive value must go through `usePrivateFormatter()`.
- IPCA+ is an **estimate**: purchase month pro rata by calendar days, the unpublished month missing.
- Lançamentos from before the fixed-income type change have no `fixed_income_type`; a title without
  any rate (manual price) is still accepted on save.
- Autopay still debits into the negative; the Início warning is the mitigation (today's balance,
  not a projection).
- No `create_app()` factory: only worth it together with moving config into the app object.
- Import is capped at 2,000 rows per file, and the rules apply-preview at 2,000 rows.
- IR report: day trade is not separated (no time of day stored); the R$ 20 mil exemption and loss
  pools follow the simplified rules in `services/tax_report.py`; proventos of foreign assets are
  taken as BRL.
- Multi-currency: USD, EUR and GBP only (BCB PTAX); a transfer between accounts in different
  currencies is refused (register an expense and an income); fixed income and FII are BRL.
- Corporate actions: nothing can be entered before an asset's latest event — undo the event, enter
  the movement, register the event again.
- Receipts: no server-side thumbnails (the browser scales the file); the backup mirror copies each
  receipt once, deleted ones are kept for the backup retention.
- Allocation: the contribution split is proportional to each shortfall (not "fill the furthest
  behind first") and never sells. A class without per-asset targets gets its share at class level
  only. Values are net (after estimated IR on fixed income), like the Posição distribution.
- Goals: the forecast is deterministic (constant monthly contribution and return, compounded
  monthly); monthly income has no forecast. Income counts net proventos paid in the last 365 days,
  foreign ones taken as BRL like the IR report.
- Rentabilidade (TWR): monthly Modified Dietz on **gross** values with month-end closes; past months
  of unquoted classes (OTHER, manual prices) sit at cost, so their gain lands in the current month;
  a missing yfinance month reuses the previous close; the current month runs to today at the
  stored quotes, like Posição (a fixed-income title never refreshed from the BCB dips in that month
  until "Atualizar cotações"); a provento
  paid while the portfolio is empty is dropped. The response's `notes[]` lists these.
- Total return per asset ("Rentab. c/ proventos"): base is all money ever put in (current cost +
  cost of shares sold), so an asset that paid back most of its capital isn't overstated.
- Benchmarks: IFIX and IDIV have no free monthly history — they accumulate from the closes the app
  stores when the screen is opened (stale if not opened near month-end); IPCA lacks the current
  month; brapi fallback covers 3 months only.
- Sectors: brapi data is imperfect (244 tickers without sector, ETFs as "Miscellaneous"); a FII
  segment and a stock sector with the same name merge; fixed income, foreign assets are
  "Sem setor" until filled by hand.
- IRPF text: no CNPJ/custodian/country stored ("(preencher)"); no paste text for foreign assets
  (Lei 14.754) or GCAP; imposto pago is the app's estimate.
- Exemption meter: stocks in BRL only (FII has no exemption, foreign assets are annual); it reads
  realized results, so a sale shows up once recorded — the form's warning covers the sale being typed.

---

## 2. Open decisions

3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
4. **Desktop only or phone access?** The layout is responsive; hosting with HTTPS is undecided.
