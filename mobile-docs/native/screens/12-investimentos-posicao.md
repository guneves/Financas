# Investimentos › Posição — native spec

| | |
|---|---|
| Migration order | 7 (see `../migration-order.md`) — **first of the Investimentos area** (7a): the most opened investments screen, read-heavy, and the host of "Resgatar" and of the "Registrar operação" sheet (`13-investimentos-operacoes.md`) |
| Status | Not started |
| React source | `frontend/src/pages/Investments.jsx` (route wrapper), `pages/investimentos/Posicao.jsx` (`PortfolioSummary`, `QuoteSheet`, `RedeemSheet`, `QuoteUpdateResult`, `QuoteValue`, `NetValue`, `Profit`, `PositionCard`/`PositionRow`, `TreasuryCard`/`TreasuryRow`/`TreasuryTable`, `TreasurySourceNote`, `TreasuryDetailSheet`, `GroupToggle`), `pages/investimentos/PortfolioOverview.jsx`, `pages/investimentos/useInvestments.js`, `pages/investimentos/helpers.js`, `components/CashLinkField.jsx`, `components/InvestmentLaunchModal.jsx`, `components/ExportSheet.jsx`, `components/charts.jsx` (`DonutChart`, `ChartTooltip`, `LegendDot`, `FLOW`, `CHART`) |
| Route(s) | `/investimentos/posicao` (`/investimentos` and legacy `/investments` redirect here); tab "Posição" of section "Investimentos" ("Investir" in the bottom bar) |
| Endpoints | `GET /api/investments/portfolio?refresh_prices=false`, `GET /api/investments?order=created_at&ascending=false` (shared hook), `GET /api/investments/history?months=`, `GET /api/accounts`, `POST /api/investments/update-prices`, `PATCH /api/investments/price-by-asset/<asset_id>`, `POST /api/investments` (redemption), `DELETE /api/investments/<id>`, `DELETE /api/investments/by-asset/<asset_id>?asset_class=`, `GET /api/investments/portfolio/export`, `GET /api/exports/columns`, `POST /api/investment-proceeds/sync` |
| Client rules | `lib/treasury.js` (`allocateTreasuryRedemption()`, `treasuryRateText()`, `treasuryRateLabel()`, `treasuryMarketRateText()`, `isMarketValued()`), `lib/fixedIncome.js` (`describeFixedIncome()`, `FIXED_INCOME_TYPES`), `lib/portfolioAccount.js` (`emptyCashLink()`, `cashLinkMetadata()`, `portfolioAccounts()`, `pickPortfolioAccountId()`), `lib/transactions.js` (`isPortfolioAccount()`, `portfolioCashBalance()`, `accountBalanceBrl()`), `pages/investimentos/helpers.js` (`quoteSourceLabel()`, `quoteStatusLabel()`, `formatDateTime()`, `parseNumberInput()`, `getClassLabel()`), inline in `Posicao.jsx` (`groupAssets()`, `groupKeyAndLabel()`, `variableGroupKey()`, `positionMenuItems()`), inline in `PortfolioOverview.jsx` (allocation by category, bar stacking), `lib/proceedsSync.js` (`useProceedsSync()`) |

## What it is for
What the owner holds, what it is worth and how it is doing: the portfolio total, the cash still in
the Corretora, each position with its quote and return, Tesouro Direto marked to market. On the
phone it is opened a few times a month to check the portfolio and, less often, to sell or redeem.

## What it shows
Top to bottom (phone layout = the `xl:hidden` branch of the React page).

1. **Header** "Posição" / "O que você tem, quanto vale e como está rendendo." Actions: "Atualizar
   cotações" (spinner while running), "Exportar" (disabled with no assets), "Registrar operação"
   (primary).
2. **Error banner** (warning, dismissible): `dataError` from either query or an action.
3. **Quote update result** (only after "Atualizar cotações", closable): "Atualização de cotações" /
   "N atualizada(s), N falha(s), N desatualizada(s)/sem cotação." from `updated_assets`,
   `failed_assets`, `stale_assets`; lines "Atualizados: …" (emerald), "Usando cache: …"
   (`cached_assets`, amber), "Falharam: TICKER (error)" (rose), "Desatualizada/sem cotação: …"
   (neutral). Names = `ticker || name`.
4. **Summary** (`PortfolioSummary`, only when there are assets): lead "Carteira" = `current_balance`
   ("Valor de mercado bruto"); figures "Valor aplicado" = `total_invested` ("Custo das posições
   abertas"); "Resultado" = `current_balance − total_invested`, signed, tone gain/loss, hint
   "<±x,xx%> bruto" (% = result / invested × 100; the server already returns the same number as
   `gross_portfolio_profitability`); "Líquido estimado" = `current_net_balance` ("Após IR e custódia
   da renda fixa"); **"Saldo na corretora"** = `portfolioCashBalance()` over the active accounts of
   type `BROKERAGE` (`GET /api/accounts`, each `balance_brl ?? balance`), hint = the account name or
   "N contas Corretora"; the figure is absent with no Corretora account. All R$ masked in privacy
   mode; the % stays. This is the **only** place the Corretora balance appears (Início skips it).
5. **Alocação** donut (`PortfolioOverview`): "Valor de mercado bruto por categoria de ativo." Slices
   = sum of `current_value` per `category_label` (fallback `getClassLabel(class)`), centre label
   "Carteira", sorted desc, max 6 slices (rest "Outros"/"Demais" in `OTHER_COLOR`), colours
   `SERIES[i]` by rank. Legend below with % and R$ (R$ masked).
6. **Evolução do Patrimônio** (`GET /api/investments/history?months=`): period chips 6M/1A/2A/3A/5A
   (6/12/24/36/60; default 12, remembered per device under `@financeMVP:patrimonioPeriod`). Stacked
   monthly bars from `evolution[]`: `base` = `valorAplicado` when `ganhoCapitalBruto ≥ 0`, else
   `patrimonioBruto`; on top `ganho` = max(gain, 0) in `FLOW.income` or `perda` = max(−gain, 0) in
   `FLOW.expense`; base in `FLOW.investment`. Legend "Valor aplicado", "Ganho de capital",
   "Perda de capital" (only if a month has a loss). Tooltip: month, Valor aplicado, Ganho/Perda de
   capital (absolute), footer "Patrimônio bruto: …" and, when different, "Líquido de IR estimado:
   …" (`patrimonio`). X = `month` via `shortMonthLabel()`; Y compact (`compactAxis`, masked in
   privacy). Previous period stays visible while the new one loads.
7. **Tabs** (segmented): "Variável" (`class !== 'FIXED_INCOME'`), "Renda fixa" (fixed income with
   `category !== 'TESOURO'`), "Tesouro Direto" (`category === 'TESOURO'`). Local state, default
   Variável.
8. **Groups** (collapsible, all start closed): header "LABEL" + "N posição(ões) · R$ total"
   (total = Σ `current_value`, masked). Grouping (`groupKeyAndLabel()`):
   - Variável: STOCKS by `market_kind` (ACAO "Ações", ETF "ETFs", BDR "BDRs"), REIT "Fundos
     Imobiliários", OTHER with `market_kind === 'CRIPTO'` "Cripto", else the class label. Order
     ACAO, ETF, BDR, FII, CRIPTO, OTHER.
   - Renda fixa: `metadata.fixed_income_type` with `FIXED_INCOME_TYPES` labels (CDB, LCI, …), in
     that list's order; none → "Sem tipo" last.
   - Tesouro: `rate_kind` POS "Pós-fixado (Selic)", PRE "Pré-fixado", IPCA "IPCA+"; none → "Sem
     indexador".
9. **Position card** (non-Tesouro): `name` (wraps, never truncated); sub-line fixed income
   `describeFixedIncome(metadata)` ("CDB · 110% do CDI") or class label, else "<quantity> un."
   (masked) + " · PM <average_price>" (PM masked only for fixed income). Right: `current_value`
   (masked) and `profitability_percent` (signed, gain/loss/neutral). Row "Proventos
   <proceeds_net>" (masked) · "c/ proventos <total_return_percent>". Quote line (`QuoteValue`): a
   dot (emerald when `quote.status === 'fresh'`, else amber; spinner while this asset updates) +
   `current_price` (masked only for fixed income not market-valued); accessible text "<status> ·
   <source> · <dd/mm/aa hh:mm>" (`quoteStatusLabel`, `quoteSourceLabel`, `formatDateTime`). Buttons
   "Vender" (variable) / "Resgatar" (fixed) and "⋯". Note: for fixed income
   `profitability_percent` is **net** of IR, for variable income it is gross.
10. **Tesouro card**: `name`; "Venc. dd/mm/aaaa · x,xx títulos" (`treasury.maturity_date`,
    `treasury.units`, two decimals, units masked); rate line `treasuryRateLabel()` ("Taxa média
    IPCA + 6,23% a.a." when `treasury.lot_count > 1`) or `describeFixedIncome()`. Right:
    `net_value` (bold), "bruto <current_value>", `profitability_percent`. Quote = PU (public, not
    masked when `treasury.valuation === 'MARKET'`).
11. **Tesouro source note** (Tesouro tab only): "Marcação a mercado pelo PU de venda do Tesouro
    Nacional (Tesouro Transparente), data base <latest treasury.price_date>. Saldo líquido = bruto
    − custódia da B3 (0,20% a.a.) − IOF − IR, como se vendido hoje." Plus an info alert listing the
    titles on the curve (`valuation !== 'MARKET'`): "Sem o preço do Tesouro para …: o valor segue a
    curva da taxa contratada. Confira se o nome traz o tipo e o ano do título (ex.: Tesouro IPCA+
    2045)."
12. **Empty tab**: "Nenhum ativo cadastrado nesta categoria." / "Registre uma compra ou um aporte
    para acompanhar a posição aqui." + "Registrar operação".

**"Detalhes do título"** sheet (Tesouro only, `TreasuryDetailSheet`): title = name, "Vence em
dd/mm/aaaa"; info alert when not MARKET; list Saldo bruto (+ "N títulos"), Custódia da B3
(`treasury.custody`, "0,20% a.a., provisionada"), IOF (only > 0), IR (`treasury.income_tax`,
"Tabela regressiva, compra a compra"), Saldo líquido (`net_value`), Valor aplicado
(`total_invested`); then PU de venda (`treasury.market_pu`, "Data base …"), "Taxa de mercado hoje"
(`treasuryMarketRateText()`, never for Selic), "Sua taxa"/"Sua taxa média"
(`treasuryRateText(treasury.average_rate, metadata)`); then "Compra"/"N compras" from `lots[]`:
`purchase_date`, `net`, rate (`treasuryRateText(lot.rate)`), units, "aplicado <invested> · bruto
<gross>". R$ and units masked; PU and rates not.

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Atualizar cotações | header | `POST /api/investments/update-prices` `{}`; refresh screens only when `updated_count > 0` (`refreshQuotes()`) | result panel (item 3) | refused (needs the providers) |
| Atualizar cotação / "Atualizar valor" (fixed) | card "⋯" | same, `{asset_id, asset_class}` | result panel | refused |
| Editar cotação (not fixed income) | card "⋯" → sheet "Editar cotação", field "Cotação (R$)", hint "Um ativo com fonte de mercado volta ao preço da fonte na próxima atualização." | `PATCH /api/investments/price-by-asset/<asset_id \|\| id>` `{asset_class, current_price}` | toast "Cotação de <name> salva." | refused |
| Vender | card button | opens "Registrar operação" in Venda mode with the asset (`13-…`) | — | refused |
| Resgatar (fixed income, Tesouro) | card button → sheet "Resgate parcial" | `POST /api/investments` with a **list**: one item per part, `{asset_class, ticker_or_name, quantity: -1, average_price: <cost>, current_price: <amount>, metadata: {is_redemption: true, affects_position: true, related_id: <lot id>, redemption_date, cash_account_id}}` | toast "Resgate de R$ x registrado nas operações." | refused |
| Detalhes do título | Tesouro "⋯" | none (data already loaded) | — | works from cache |
| Excluir este aporte (fixed income, ≤ 1 lot) | "⋯" | `DELETE /api/investments/<id>` | "Excluir este aporte de <name>?" / "O aporte sai das operações." / "Excluir" | refused |
| Excluir toda a posição | "⋯" | variable: `DELETE /api/investments/by-asset/<asset_id>?asset_class=<class>`; grouped Tesouro: one such DELETE per `asset_ids[]`, sequentially | "Excluir toda a posição de <name>?" / "Todas as operações deste ativo saem do histórico." | refused |
| Exportar | header → `ExportSheet` ("Exportar carteira") | `GET /api/investments/portfolio/export?format=csv\|xlsx&columns=` (columns from `GET /api/exports/columns` → `portfolio`) | file | refused |
| Registrar operação | header / empty state | see `13-…` | — | refused |

Resgate parcial sheet: "Valor bruto a resgatar (R$)" (decimal, comma accepted), "Data do resgate"
(default today), `CashLinkField` with `movementType="REDEMPTION"` (hint "O valor resgatado, menos
os custos, entra nesta conta. O IR retido na fonte não é descontado."). Hint for grouped Tesouro
(> 1 lot): "Sai primeiro das compras mais antigas, como no Tesouro; o custo resgatado é proporcional
ao valor."; else "O custo resgatado é proporcional a este valor.". Client validation: "Informe um
valor entre R$ 0,01 e <current_value>.", "Informe a data do resgate.", `cashLinkMetadata()` errors
("Vincule uma conta à carteira antes: …", "Escolha a conta da carteira, ou marque …"), and from
`allocateTreasuryRedemption()` "O valor passa do saldo bruto do título.". Cost per part: grouped →
PEPS parts; single → `average_price × amount / current_value`, `related_id = asset.id`.

Server refusals to show verbatim (unaccented, as the API writes them): "Venda maior que a
quantidade disponivel na carteira.", "Nao e possivel alterar ou excluir essa compra: ela possui
resgate vinculado." / "…ficaria com venda sem lastro de compra anterior." (409), "Classe do ativo
nao confere com o ativo informado." (409), "Ativo nao encontrado." (404), "Conta do extrato
esta arquivada.", "O lancamento no extrato e em reais: escolha uma conta em reais.", and
`CASH_WITHOUT_AMOUNT_MESSAGE`.

## Data
- `GET /api/investments/portfolio?refresh_prices=false` → `total_invested`, `current_balance`,
  `current_net_balance`, `gross_portfolio_profitability`, `assets[]`: `id`, `asset_id`,
  `asset_ids` (Tesouro grouped), `ticker`, `name`, `class`, `market_kind`, `category`,
  `category_label`, `rate_kind`, `fixed_income_type`, `quantity`, `average_price`, `current_price`,
  `total_invested`, `current_value`, `net_value`, `is_tax_free`, `profitability_percent`,
  `proceeds_net`, `dividend_yield_12m`, `total_return_percent`, `quote` {`status`, `source`,
  `quoted_at`}, `metadata`, `lots[]` and `treasury` {`title_type`, `maturity_date`, `units`,
  `average_rate`, `market_pu`, `market_rate`, `price_date`, `valuation`, `custody`, `iof`,
  `income_tax`, `lot_count`} (Tesouro). Query key `['investimentos','carteira']`. Also returns
  `realized_result` (used by `13-…`).
- `GET /api/investments?order=created_at&ascending=false` — loaded by the shared hook
  (`['investimentos','operacoes']`); Posição itself does not render it.
- `GET /api/investments/history?months=N` (1–60) → `evolution[]` {`month`, `month_key`,
  `patrimonio`, `patrimonioBruto`, `valorAplicado`, `ganhoCapitalBruto`, `ganhoCapitalReal`}. Key
  `['investimentos','historico',months]`. The response also carries `historical_prices`, unused.
- `GET /api/accounts` → `type`, `name`, `balance`/`balance_brl`, `archived_at`. Key
  `['contas','ativas']` (shared with `CashLinkField`).
- `POST /api/investment-proceeds/sync` on open (at most every 10 min) and 1.5 s after any
  position-changing write; see `15-…`.
- Invalidation: every write invalidates all queries; the quote refresh invalidates only when it
  changed something.

## Client rules
- **PEPS redemption split** — `allocateTreasuryRedemption()` (`lib/treasury.js`, tested in
  `treasury.test.js`). **Endpoint** recommended: it decides cost basis (money). A proposed
  `POST /api/investments/redemptions {position id, amount, date, cash_account_id}` does not exist
  today; until then port with the same cases.
- **Single-title redemption cost** `average_price × amount / current_value` — inline in
  `Posicao.jsx` `handlePartialSale`, no test. **Endpoint** (same proposal) or port with a new test.
- **Rate texts** `treasuryRateText()`, `treasuryRateLabel()`, `treasuryMarketRateText()`,
  `isMarketValued()` and `describeFixedIncome()` — tested (`treasury.test.js`,
  `fixedIncome.test.js` covers part). **Port** (display only).
- **Grouping into tabs and groups** `groupAssets()` / `groupKeyAndLabel()` / `variableGroupKey()`
  — inline, no test. **Port** with new tests (order, "Sem tipo", "Sem indexador").
- **Menu items** `positionMenuItems()` — inline. Port.
- **Saldo na corretora** `portfolioCashBalance()` (`transactions.test.js`). Port (or an endpoint
  field; it is a sum of balances).
- **Resultado %** — inline. Use `gross_portfolio_profitability` from the server instead.
- **Allocation donut** (Σ `current_value` by `category_label`) and **bar stacking** (base/ganho/
  perda) — inline in `PortfolioOverview.jsx`, no test. Port with tests.
- **Cash link** `cashLinkMetadata()` etc. — tested (`portfolioAccount.test.js`). Port (shared with
  `13-…`).
- **Labels** `quoteSourceLabel()`, `quoteStatusLabel()`, `formatDateTime()` — inline helpers, no
  test. Port.

## States
- Loading: list skeleton (6 rows) in the positions panel; chart skeleton only when no previous
  period is cached.
- Empty portfolio: no summary/donut/chart; each tab shows the empty state of item 12.
- Error: warning banner ("Não foi possível carregar os investimentos." / "…o histórico de
  operações."); chart error inside its card ("Não foi possível carregar a evolução do
  patrimônio.").
- Offline: last cached portfolio (the web persists every successful query for 14 days); all writes
  and the quote refresh refused with a clear message — `POST /api/investments` has **no
  `client_id`**, so a redemption must never be queued or retried after a timeout.
- Privacy: R$ values, quantities, titles' units and fixed-income principal/PM masked; quotes of
  variable income, the Tesouro PU, rates and every % stay.
- Light/dark: chart colours from the chart tokens (see `14-…`, "Charts").

## Conventions that apply
- "Investments and banking are separate areas; a movement's cash goes through the portfolio
  account" — Saldo na corretora shows here only; the redemption carries `cash_account_id` or
  `null`.
- "Tesouro Direto is marked to market and grouped by title" — one row per title with `lots`; a
  grouped redemption is one row per purchase, oldest first.
- "The category refines the class, on read" — tabs and labels read `category`/`category_label`.
- "Destructive endpoints take a confirmation guard" — by-asset delete sends the matching
  `asset_class`.
- "A save waits only for its own request" — the quote refresh after a write runs behind.
- "Renda variável quotes refresh every hour on their own" — the button is a manual force.
- "Privacy mode" (Known sharp edges) — as in States.
- "The app is reais-only on screen" — never show `native_current_price`/currency.

## Native-only improvements
Instant open from the cached portfolio; pull-to-refresh = "Atualizar cotações"; swipe on a card
for Vender/Resgatar; the detail sheet as a full-height bottom sheet; haptic on a finished refresh.

## Acceptance
- [ ] Carteira, Valor aplicado, Resultado, Líquido estimado and Saldo na corretora equal the web's.
- [ ] Each tab groups exactly as the web (same order, same counts and totals).
- [ ] A Tesouro title with two purchases is one card; "Detalhes do título" lists both purchases.
- [ ] A partial redemption of a grouped title creates one Resgate per purchase, oldest first, and
      one Extrato row each in the Corretora (or none with "Não descontar de nenhuma conta").
- [ ] "Editar cotação" changes the value at once; "Atualizar cotações" shows the result panel.
- [ ] Deleting a position asks first; a refused delete (sale without backing) shows the message.
- [ ] Privacy hides the values listed above and nothing else; airplane mode shows the last data
      and refuses writes.

## Desktop
Keep and widen: the full table (Ativo, Qtd, Preço médio, Cotação, Valor, Rentab., Proventos,
Rentab. c/ proventos) with groups as `tbody` sections, the Tesouro table (Vencimento, Quantidade,
PU, Saldo líquido, Saldo bruto), donut and evolution side by side, summary always visible.
