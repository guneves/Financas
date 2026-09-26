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

### Ideas from the Investidor10 survey (2026-09-26, not prioritized)
Seen in the owner's Investidor10 PRO wallet and not built; each needs the owner's call first.
- Returns vs benchmarks: time-weighted return, a CDI/IPCA/IBOV/IFIX/IDIV line chart, a year × month
  return table, "% do CDI". CDI/IPCA are already fetched; the indices would come from brapi/yfinance.
- Contributions chart: monthly buys vs sells (the operations are already stored — cheap).
- Concentration alerts: an asset above 10% of the portfolio, no exposure abroad.
- Allocation by sector/segment: needs a sector per ticker (brapi returns one; store it in the catalog).
- Proventos screen: split by asset over 12 months, monthly/annual toggle, record date next to the
  payment date.
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
