# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (night) · Investments check: average cost, ETF/BDR tax, per-sale IR

The owner asked first for a prompt to check the investments area, then, mid-task, to do the check
now, fix every error found and open a PR. Cloud session, no providers reachable (brapi, yfinance,
BCB and StatusInvest are all blocked from the container). Branch `claude/sweet-rubin-un057n`,
restarted from `main` after PR guneves/financas#1 (Phase 6) was merged; it also carries the
docs-only commit that marked Phase 6 as merged.

### How the check was done
Read every investment service and route; seeded a scratch database (`seed_three_years_mock.py`,
scale 1) through the real API; ran the backend with a built frontend and walked Posição,
Rentabilidade, Operações, Alocação, Proventos, IR, Metas and Extrato › Investimentos in Chromium at
360 and 1280 px (no overflow, no console or API errors); compared the numbers between screens;
checked each tax rule against the law (WebSearch only — gov.br and planalto are blocked here).

### Errors found and fixed (each with tests)
1. **Cost basis.** Realized results and Bens e Direitos used FIFO lots; Posição and the evolution
   subtracted whatever price the SELL row stored. The Receita's rule is the weighted average
   (Lei 8.981/1995 art. 72 §2º; IN RFB 1.585/2015 art. 58). Seed example: WEGE3 showed a R$ 77,11
   FIFO loss (carried into the loss pool) that is a R$ 12,89 exempt gain, and three different
   remaining costs; PETR4's preço médio read 44,79 instead of 46,10. Now
   `apply_average_cost()` (in `fetch_investments()`) gives one cost to everything; the stored
   price of a sale is never read. This also fixes the old next-steps item "a position with
   applied value ≤ 0 drops out of the monthly valuation".
2. **ETFs and BDRs** were taxed as ações: counted in the R$ 20 mil and exempt below it. Now 15%
   with no exemption, outside the limit, in the stocks' loss pool; fixed-income ETFs out of the
   DARF (IR withheld at source); Bens codes 07.09 (ETF) and 04.04 (BDR); the sale form and the
   meter say so.
3. **Per-sale IR in Operações** ignored the exemption and the loss pool (PETR4's exempt sale
   showed IR R$ 20,58; a loss-making sale showed IR). One rule now, `variable_income_tax.py`:
   each sale stores its share of the month's tax.
4. **Tributação exclusiva** (códigos 06 e 10) is declared net; the IR tab said "informe o bruto"
   and showed gross. Tab and export now show net (with bruto and IR retido beside it).
5. Proventos' yield-on-cost cost counted the buy fees twice (`accumulate_position`).
6. Posição printed quantities raw ("1022"; a fraction would read "62.7"); now `formatQuantity`.
7. Rentabilidade's notes and benchmark messages had no accents on screen.
8. brapi batch size is `BRAPI_MAX_SYMBOLS_PER_REQUEST` (default 20 as before); a plan error
   now tells the owner what to set.
9. Operações: "FIFO, N lotes" → "custo médio"; the sale's edit form no longer offers a cost
   field that did nothing.

Tests: backend 1031 (was 1002; `test_fifo.py` became `test_average_cost.py`, new
`test_variable_income_tax.py`), node 46 (was 45).

### Later, separate request: Posição › Variável split by kind
Posição's Variável tab groups by kind of paper (Ações, ETFs, BDRs, Fundos Imobiliários, Outros).
The asset class is unchanged; each position carries `market_kind`, which is the IR's own
`market_listing.tax_kind()` (fixed-income ETFs shown with the ETFs), so the screen and the tax
rule can never disagree on what a ticker is. `test_portfolio_market_kind.py`.

### What was not done and why
- **The prompt itself** — superseded by the owner's second message (do the check now).
- **No live check against the owner's data**: it is on the home server, unreachable from here.
  After the deploy the owner should open IR 2025 again (next-steps, "Investments check").
- Decisions left to the owner, in next-steps: brapi at 1 ticker per request (credits), the ETF
  Bens code 07.09 (2022 source), units as ações, the isentos line 18 for bonificações.
- Foreign assets and "outros" keep the per-sale 15% estimate; fixed-income ETFs show 15% though
  the withheld rate depends on the fund's term.
- No native change: no APK, no native-level bump. The screens reach the phone as a bundle — but
  the phone still has APK 10011 (level 1) and the server's screens need level 2 since Phase 6, so
  the new screens arrive only after APK 10013 is installed.

### Carried from the previous session (Phase 6, still open)
1. Phone: "Nova versão disponível" → install APK 10013; Ajustes › Notificações dos bancos → grant
   access ("Configuração restrita" steps are on the screen).
2. Test APK from the PC: `curl -fLO https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`,
   `adb install -r financas-debug.apk`, grant access, capture on, run the adb command on its
   screen; the notification must show under "Teste (adb)" there and not in the real app. Then
   `adb uninstall br.financas.app.debug`.
3. Capture on in the real app for about a week (Samsung Pay on each card, debit, Pix both ways,
   estorno, a declined purchase), then "Exportar JSON". Decide first whether fixtures may go into
   the repo verbatim. Next coding session: Phase 6 step 4 against that export, with the
   one-source-per-purchase rule (Samsung Wallet + bank).

### Carried from earlier sessions (still open)
- After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
- Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
- The remaining self-update cases (offline queue across a switch, the native-level bump of
  `e340d1c`, the 30 s fallback). The rclone backup, if the owner wants help.
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, on the server.
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.

### Learned
- The seed (`seed_three_years_mock.py`) and the API store a sale with the **sale price** in the
  price column; the screen stores the position's average there. Any cost read from that column
  was wrong for one of them — hence the server-side average cost.
- A full-page screenshot scaled down can turn "0,00" into "0.00": read the cell text before
  calling it a formatting bug.
- From the cloud container: gov.br, planalto, Receita's normas site, Play Store and dl.google.com
  are blocked (WebFetch fails to resolve them too); WebSearch works for citations.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
