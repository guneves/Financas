# Investimentos › Rentabilidade (and the investments' charts) — native spec

| | |
|---|---|
| Migration order | 7 (see `../migration-order.md`) — **fourth of the area** (7d), after Posição, Operações and Proventos: read-only, but it needs the chart kit decided here (also used by Posição's evolution, Operações' Aportes, Proventos' receipts and the Calculadora) |
| Status | **Built** 2026-10-24 (session D, native-level 8): `ui/investimentos/RentabilidadeScreen.kt` + `RentabilidadeViewModel.kt`, rules `ReturnsRules.kt` (the CDI card built on the client as on the web, with the difference rounded to 2; hints, tones, axis, colours; tested). Aportes e resgates lives in Operações (`StackedBarChart`, signed). Chart kit used: `DonutChart`, `StackedBarChart`, `GapLineChart` (now with a line width), new `StackedAreaChart` (Calculadora). Tap selects a column (no press-and-drag crosshair yet); no landscape full-screen. The class filter is not remembered (as on the web). |
| React source | `frontend/src/pages/investimentos/Rentabilidade.jsx` (`BenchmarkToggles`, `ReturnsChart`, `YearMonthTable`, `AssetsTable`, `comparisonItems()`, `comparisonHint()`), `pages/investimentos/AportesChart.jsx`, `components/charts.jsx` (`SERIES`, `FLOW`, `CHART`, `OTHER_COLOR`, `ChartTooltip`, `LegendDot`, `DonutChart`, `compactAxis()`, `axisProps`, `useChartAnimation()`), `pages/investimentos/helpers.js` (`ASSET_CLASSES`, `getClassLabel()`), `frontend/src/index.css` (`--chart-*`) |
| Route(s) | `/investimentos/rentabilidade` (Aportes lives on `/investimentos/operacoes`) |
| Endpoints | `GET /api/investments/returns?months=6\|12\|24\|36\|60\|all&asset_class=`, `GET /api/investments/contributions?months=&asset_class=` |
| Client rules | inline in `Rentabilidade.jsx` (`comparisonItems()` — the CDI's `difference_pp`, `toneOf()`, `signedPercent()`, `percentAxis()`, `BENCHMARK_COLORS`, `DEFAULT_VISIBLE`), inline in `AportesChart.jsx` (resgates drawn negative), `components/charts.jsx` (`compactAxis()`, `DonutChart` slicing) |

## What it is for
"Am I doing better than the CDI?": the time-weighted return (TWR) of the portfolio, or of one
class, against CDI, IPCA, Ibovespa, IFIX and IDIV from the same 0% start, month by month and per
asset. A few times a month on the phone; it is the screen where the chart matters most.

## What it shows
1. **Header** "Rentabilidade" / "Retorno ponderado no tempo (TWR): aportes e resgates não distorcem
   o percentual, então dá para comparar com o CDI, a inflação e os índices da bolsa." Controls:
   class select ("Todas as classes", Ações, Fundos Imobiliários, Renda Fixa, Outros — values
   `STOCKS`, `REIT`, `FIXED_INCOME`, `OTHER`) and period chips 6M/1A/2A/3A/5A/"Tudo" (`all`;
   default 12, remembered per device under `@financeMVP:rentabilidadePeriod`; class not
   remembered).
2. **Summary**: lead "Rentabilidade no período" / "Rentabilidade de <classe> no período" =
   `twr_percent` (signed, gain/loss/neutral, "—" when null); hint "<mmm/aa> a <mmm/aa>[ (desde a 1ª
   operação)] · TWR, valor bruto" from `comparison.start`/`end` (fallback `period`), the suffix when
   `comparison.starts_after_window`. Figures "No ano" = `ytd_percent`; "% do CDI" =
   `percent_of_cdi` (0 decimals), hint "CDI no período: <cdi_percent>" or "CDI indisponível";
   "Carteira hoje"/"<classe> hoje" = last `series[].value` (R$, **masked** in privacy), "Valor
   bruto".
3. **Rentabilidade acumulada** card: description "Carteira e índices partem de 0% no mesmo ponto
   (fim de <base_month>): a linha mais alta no fim rendeu mais no período. Toque em um índice para
   mostrar ou esconder a linha."
   - **Toggle cards** (2 per row on the phone), CDI first then `benchmarks[]` in server order: line
     swatch (index colour when on, `CHART.axis` when off), label, `period_percent` (signed,
     coloured), hint: "indisponível" / "<months_covered> de <months_total> meses" (incomplete) /
     "carteira +x,xx p.p." (`difference_pp`) / "no período". Disabled when `available` is false.
     Visible set remembered per device (`@financeMVP:rentabilidadeBenchmarks`, default CDI, IPCA,
     IBOV). CDI's card is built on the client: `available = cdi_available`, `period_percent =
     cdi_percent`, `difference_pp = round2(twr_percent − cdi_percent)`, note "O BCB não respondeu o
     CDI.".
   - **Line chart**: X = `series[].month_key` (`shortMonthLabel`), Y = % ("1,5%"), reference line
     at 0. Lines: carteira = `accumulated_percent` (`SERIES[0]`, 2.5 px, drawn last, on top); CDI =
     `cdi_accumulated_percent` (`OTHER_COLOR`, 2 px); each shown benchmark =
     `series[].benchmarks[code].accumulated_percent` (1.75 px; IPCA dashed 5/4). Null points break
     the line. The first point (`base: true`) is 0% for all. Legend "<Carteira|classe> (TWR)" +
     shown indices. Tooltip: month, each line's signed %.
   - Notes under the chart for benchmarks with a `note`: "<label>: <note>".
4. **Mês a mês** ("Retorno de cada mês e o acumulado no ano. O mês atual vai até hoje."): newest
   year first; per year a header "<year>" + `total_percent`, then a 4-column grid jan…dez of
   `years[].months[i]` (signed, coloured, "—" for null).
5. **Por ativo** ("TWR de cada ativo desde a primeira compra, limitado à janela escolhida.", badge
   "N ativo(s)"): `ticker`; "<class label> · desde <mmm/aa>[*][ · encerrado]" (`since`, `capped`,
   `open`); right `twr_percent` and `current_value` (masked) or "—" when closed. Footnote when any
   `capped`: "* Comprado antes da janela: o retorno conta a partir do início dela (<period.start>).
   Escolha um período maior para ver mais." Empty: "Nenhum ativo no período".
6. **Como é calculado**: description `basis_label`; bullets `notes[]` (server text).

### Aportes e resgates (on Operações, `AportesChart.jsx`)
Collapsible card ("Ocultar"/"Mostrar", open by default; no fetch while closed). "Por mês, em
reais: compras contra vendas e resgates (valores brutos, sem custos). Bonificações não entram."
Period chips 6m/12m/24m/5a (6/12/24/60, default 12, not remembered) and class select. Totals
"Aportes" `totals.aportes`, "Resgates" `totals.resgates`, "Líquido" `totals.liquido` (signed); all
masked. Bars per `months[].month`: aportes up in `FLOW.investment`, resgates **down** (negated) in
`SERIES[1]`, stacked around a zero line; tooltip shows absolute values and footer "Líquido
<±liquido>". Empty (`totals.count === 0`): "Nenhuma operação no período." / "Compras, vendas e
resgates registrados aparecem aqui, mês a mês."

### Charts used across Investimentos (for the native kit)

| Screen | Chart | Series → colour |
|---|---|---|
| Posição | donut, ≤ 6 slices + "Outros"/"Demais" | `SERIES[i]` by rank, rest `OTHER_COLOR` |
| Posição | stacked monthly bars, loss variant | base `FLOW.investment`, ganho `FLOW.income`, perda `FLOW.expense` |
| Operações | bars above/below zero | aportes `FLOW.investment`, resgates `SERIES[1]` |
| Rentabilidade | multi-line, dashed IPCA, nulls break | carteira `SERIES[0]`, CDI `OTHER_COLOR`, IPCA `SERIES[3]`, IBOV `SERIES[1]`, IFIX `SERIES[2]`, IDIV `SERIES[6]` |
| Proventos | monthly/annual bars | `FLOW.income` |
| Alocação › setor | donut, no legend, ≤ 9 slices | `SERIES[i]` in server order, "Sem setor" `OTHER_COLOR` |
| Calculadora | stacked areas + dashed line | investido `FLOW.investment`, juros `SERIES[2]`, real `SERIES[3]` |

Colours: `SERIES` (`#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948`) and `FLOW`
(income `#1baf7a`, expense `#e34948`, investment `#2a78d6`, others `#eda100`) are **hex literals in
`charts.jsx`**, the same in light and dark; only grid/axis/tick/ink/other are CSS variables
(`--chart-grid` zinc-100, `--chart-axis` zinc-300, `--chart-tick` zinc-500, `--chart-ink`
zinc-900, `--chart-other` zinc-400 in `index.css`). `Tokens.kt` has no chart entries today
(unverified beyond a grep): add `ChartColors` (SERIES, FLOW) plus the five chart tokens, with a JVM
test that reads `charts.jsx`/`index.css` like `TokensTest`. Axis money labels use `compactAxis()`
("900", "1,5 mil", "12 mil", "1,2 mi", minus sign U+2212, no "R$"). Animation: draw once per
screen per session, none with reduced motion.

**Library decision for Compose (to settle before 7a ships the evolution chart):** two of the seven
are donuts and one needs mixed-sign stacking; both are a few lines of `Canvas` (`drawArc`,
`drawRect`). Recommendation: a small in-house kit in `ui/charts/` (bars with stack and negative
values, lines with nulls and dash, stacked areas, donut, a press-and-hold tooltip, compact axis)
with JVM tests for the scale/tick maths — no dependency, exact colours, privacy-aware axes. The
alternative is Vico for the cartesian charts plus a custom donut (Vico has no pie chart; its support
for mixed-sign stacked columns is unverified). Either way the tooltip must be touch-driven
(press-drag), since there is no hover on the phone.

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Change period | chips | `GET /api/investments/returns?months=` | — | cached periods only |
| Change class | select | `…&asset_class=` | — | cached only |
| Toggle an index | toggle card | none (local, remembered) | — | works |
| Aportes period/class | Operações card | `GET /api/investments/contributions?months=&asset_class=` | — | cached only |

No writes on this screen.

## Data
- `GET /api/investments/returns` (`months` 1–60 or `all` = since the first operation, capped at
  60) → `twr_percent`, `ytd_percent`, `cdi_available`, `cdi_percent`, `percent_of_cdi`,
  `period` {`start`, `end`}, `comparison` {`base_month`, `start`, `end`, `months`,
  `starts_after_window`}, `benchmarks[]` {`code`, `label`, `available`, `complete`,
  `months_covered`, `months_total`, `period_percent`, `difference_pp`, `note`}, `series[]`
  {`base`, `month_key`, `accumulated_percent`, `cdi_accumulated_percent`, `value`, `benchmarks`
  {code: {`accumulated_percent`}}}, `years[]` {`year`, `months[12]`, `total_percent`}, `assets[]`
  {`key`, `ticker`, `class`, `twr_percent`, `since`, `capped`, `open`, `current_value`},
  `basis_label`, `notes[]`. Query key `['investimentos','rentabilidade',months,assetClass]`,
  previous data kept while loading. Slow (network fetches on the server, stale-while-revalidate
  caches): show the cached value at once.
- `GET /api/investments/contributions` → `months[]` {`month`, `aportes`, `resgates`, `liquido`},
  `totals` {`aportes`, `resgates`, `liquido`, `count`}. Key
  `['investimentos','aportes',months,assetClass]`.
- Invalidated by any write.

## Client rules
- **CDI comparison card** (`comparisonItems()`: `difference_pp` = twr − cdi rounded to 2) — inline,
  no test. **Endpoint** preferred: add the CDI to `benchmarks[]` on the server (it already computes
  `difference_pp` for the others); else port with a test.
- **Tone/sign/percent formatting** `toneOf()`, `signedPercent()`, `percentAxis()` — inline. Port.
- **Index colours and default visible set** — inline constants. Port as constants.
- **Resgates negated for drawing** — inline in `AportesChart.jsx`. Port (display only).
- **`compactAxis()`** — `charts.jsx`, no test. Port with tests.

## States
Loading: list skeleton (5) in a card; chart skeleton only with no series. Empty (`twr_percent` null
and no assets): "Sem rentabilidade no período" / "A rentabilidade aparece depois da primeira compra
registrada em Operações." (with a class: "Sem rentabilidade em <classe> no período" / "Nenhuma
posição ou operação desta classe na janela escolhida. Escolha outra classe ou um período maior.").
Error: warning "Não foi possível calcular a rentabilidade.". Offline: last cached response per
period × class. Privacy: only R$ (Carteira hoje, per-asset value, Aportes totals and axis) masked;
every % visible. Light/dark: chart tokens.

## Conventions that apply
- "Rentabilidade compares from the same 0%" — draw `series[0]` (base) at 0% for every line; never
  rebase on the client.
- "TWR is daily and the closes are in the basis of the stored quantities" — all numbers are the
  server's; nothing recomputed.
- "The chart history is served stale and refreshed behind" — show what comes, do not poll.
- "Visual rules" / "Theme and tokens" (Known sharp edges) — green/red only for gain/loss; chart
  colours from the kit, never ad-hoc.
- "Privacy mode" — values hidden, percentages kept.

## Native-only improvements
Press-and-drag crosshair with a floating tooltip; tap a toggle card for haptic feedback;
landscape shows the chart full-screen; remember the class filter too (owner to confirm).

## Acceptance
- [ ] For each period and class, the summary, toggle cards, year grid and per-asset list match
      the web on the same data.
- [ ] All lines start at 0% at the base month; IPCA is dashed; toggling an index persists after
      reopening.
- [ ] "Tudo" says "(desde a 1ª operação)" when the first operation is inside the window.
- [ ] Aportes bars go below zero for resgates and the tooltip shows absolute values.
- [ ] Privacy hides only R$; dark mode keeps the index colours.

## Desktop
Keep and widen: summary + toggles + chart in a wide row, the year × month table as a real table,
per-asset table sortable; add a selectable comparison range (desktop-only analysis).
