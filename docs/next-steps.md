# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`. This file holds **only open work**: when a task is finished, remove it from here and
> record it in `docs/done-tasks.md` — no ticked boxes, no "done" sections.

---

## 1. Open work, in priority order

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

### Proventos per asset (requested 2026-09-26)
Today proventos are only seen as a flat list and a portfolio-wide summary
(`build_investment_proceeds_summary()` in `routes/proceeds.py`: totals, `by_type`, `by_month`,
yield on cost). Nothing groups them by asset, and Posição's "Rentab." ignores them entirely:
`profitability_percent` in `build_portfolio_snapshot()` is `(net_value − total_invested) /
total_invested` — price only, no proventos, no realized result. Build this first; the weighted
return below reuses it.
- [ ] **Move the proceeds read into a service.** `fetch_investment_proceeds()`,
  `serialize_investment_proceed()`, `investment_position_at_date()` and the summary live in the
  `routes/proceeds.py` blueprint, and a service may not import a route (layering). Create
  `services/proceeds.py`, move them there, keep the blueprint thin. `services/goals.py` and
  `services/tax_report.py` each carry their own proceeds SQL — fold them onto it only if trivial.
- [ ] **`by_asset` in the summary** (`GET /api/investment-proceeds/summary`, honours the existing
  `date_from`/`date_to`/`proceeds_type` filters): per asset — ticker, class, event count, gross,
  tax, net, share of the total, yield on cost (net ÷ `cost_basis_at_record_date`, already computed
  per event), and the last 12 months' net. Money through `rounded_money()`; percentages may stay
  `round()` (not currency).
- [ ] **Per-asset proventos in the portfolio snapshot.** Add to each `processed_assets` entry:
  `proceeds_net` (all paid proventos of the asset, `payment_date <= today`), `proceeds_12m_net`,
  `dividend_yield_12m` (12-month net ÷ current net value) and `total_return_percent` =
  (net value − invested + proventos received + realized net profit of the asset) ÷ invested.
  Realized profit per asset comes from `investment_realized_results` (it has `asset_id`). Decide
  and document which base "invested" is for a partly sold asset (current cost only, or all money
  ever put in) — current cost overstates the return of an asset that paid back most of its capital.
  Fixed-income positions group by title id, not asset id: they get proventos only if an
  `AMORTIZATION` points at the title's asset.
- [ ] **Frontend.** Proventos: a "Por ativo" block (table, sorted by net, with the 12-month total
  and YoC; bar chart optional), the record date next to the payment date in the list, a
  monthly/annual toggle for the `by_month` chart. Posição: "Proventos" and "Rentab. c/ proventos"
  columns (the latter replacing or next to "Rentab." — owner's call) and both in the phone card.
  Proventos values are sensitive (`usePrivateFormatter()`), percentages are not.
- [ ] **Tests** (`test_proceeds_by_asset.py`): grouping and totals by asset, filters applied,
  another user's proventos never counted, a scheduled provento excluded from "received", total
  return with a partial sale plus proventos, foreign-asset proventos taken as BRL (current rule).

### Weighted return — time-weighted, portfolio and per asset (requested 2026-09-26)
Nothing computes a return that is independent of when money went in: the only figures are the
simple `profitability_percent` above and `ganhoCapital` in the evolution. **Owner decision first:**
"weighted return" is read here as **time-weighted return (TWR)** — the Investidor10
"Rentabilidade" figure and the only one comparable with CDI/IBOV. The alternative is a
money-weighted return (XIRR on the actual cash flows), which answers "how did *my* money do" and
is cheap to add per asset once the flows below exist. Build TWR; offer XIRR as a second column if
the owner wants it.
- [ ] **Method: monthly Modified Dietz, chained.** For each month: V₀ = value at the previous month
  end, V₁ = value at this month end, F = net external flow (buys − sells/redemptions, BRL, from
  `fetch_investments()`), each flow weighted by the fraction of the month it was invested, and
  proventos paid in the month added to the gain (income, not a flow). r = (V₁ − V₀ − F + D) ÷
  (V₀ + Σ wᵢFᵢ); TWR = Π(1 + r) − 1. Monthly is the resolution the data allows: past prices come
  from `get_monthly_history()` (month-end closes, **`auto_adjust=False`, so not dividend-adjusted —
  proventos must be added, and must not be added twice if that ever changes**).
- [ ] **Refactor `build_portfolio_evolution()`** (`services/portfolio.py`) so the month loop yields
  the value of *each* position (its `group_key`) per month, not just totals; the current output is
  a sum over that. Portfolio TWR and per-asset TWR then share one valuation. Keep the existing
  output byte-identical (the evolution tests must pass unchanged). Put the return maths in a new
  `services/returns.py` (above `portfolio` in the layering) as pure functions over (values, flows,
  income) so they are unit-testable without prices.
- [ ] **Which value:** gross or net of the estimated fixed-income IR? The evolution's `patrimonio`
  is net. Gross is what brokers and Investidor10 show; pick one, label it, and use it for both V₀
  and V₁. Known distortions to document: past months of unquoted classes (CATTLE, manual prices)
  sit at cost; a missing yfinance month falls back to today's price (`historical_price_for_month`);
  corporate actions are already rescaled in the stored movements, so they need no handling; a
  foreign asset's month uses that month's PTAX (already done in `/api/investments/history`).
- [ ] **Endpoint** `GET /api/investments/returns?months=&asset_class=` (in `routes/investments.py`,
  reusing the history fetch — extract it from `get_historical_portfolio()` rather than copying):
  portfolio TWR over the period and year-to-date, the monthly series (return and accumulated), the
  year × month table, and per asset: TWR since first purchase (capped at the fetched window, say
  so in the response), plus the simple and total return from the proventos task. `months` capped
  at 60 like the history. Consider caching per user/day — it is a yfinance round-trip.
- [ ] **Frontend.** Investimentos → Posição (or a new "Rentabilidade" tab — owner's call): the
  portfolio TWR in the `SummaryPanel`, an accumulated-return line chart (colours from `CHART`),
  the year × month table (`.num` cells, gain/loss colours only), and a TWR column per asset. "% do
  CDI" is one division away (CDI is already fetched by `index_history()`); IBOV/IFIX lines are the
  benchmark idea below.
- [ ] **Tests** (`test_returns.py`): single buy and hold equals the price change; a contribution
  mid-period does not move TWR; a month with a provento adds it; a full sale and re-buy;
  zero-value months (before the first buy, after a full sale) are skipped rather than dividing by
  zero; `user_id` isolation on the endpoint; route map entry.

### Ideas from the Investidor10 survey (2026-09-26, not prioritized)
Seen in the owner's Investidor10 PRO wallet and not built; each needs the owner's call first.
- Returns vs benchmarks: a CDI/IPCA/IBOV/IFIX/IDIV line chart next to the TWR from the task above.
  CDI/IPCA are already fetched; the indices would come from brapi/yfinance.
- Contributions chart: monthly buys vs sells (the operations are already stored — cheap).
- Concentration alerts: an asset above 10% of the portfolio, no exposure abroad.
- Allocation by sector/segment: needs a sector per ticker (brapi returns one; store it in the catalog).
- Harder, external data: fundamentals columns (Bazin ceiling price, P/L, P/VP, 5-year DY), a B3
  import of trades and proventos (the investor-area spreadsheet, via the existing import), and
  IRPF copy-paste text per section.

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
  currencies is refused (register an expense and an income); fixed income, FII and cattle are BRL.
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
- Exemption meter: stocks in BRL only (FII has no exemption, foreign assets are annual); it reads
  realized results, so a sale shows up once recorded — the form's warning covers the sale being typed.

---

## 2. Open decisions

3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
4. **Desktop only or phone access?** The layout is responsive; hosting with HTTPS is undecided.
