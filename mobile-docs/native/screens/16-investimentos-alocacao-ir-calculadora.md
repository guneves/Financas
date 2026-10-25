# Investimentos › Alocação, IR and Calculadora — native spec

| | |
|---|---|
| Migration order | 7 (see `../migration-order.md`) — **last of the area** (7e). Within this file: Calculadora first (pure, offline, a day of work), then a read-only Alocação, then the slim IR |
| Status | **Built** 2026-10-24 (session D, native-level 8), as the table below recommends: **Calculadora** complete (`CalculadoraScreen.kt`, the form kept per device, `CompoundInterest.chartPoints`); **Alocação** read-only plus the aporte split (`AlocacaoScreen.kt`: classes, drift, gaps, concentration, opportunities, sectors read-only; `AllocationRules.kt`), with "Definir metas e setores" opening `/investimentos/alocacao?web=1`; **IR** only the exemption meter and the DARF months of the chosen year (`IrScreen.kt`), with "Relatório completo" opening `/investimentos/ir?web=1`. Not built: the DARF reminder, copying a suggested amount into Registrar operação. |
| React source | `frontend/src/pages/investimentos/Alocacao.jsx`, `pages/investimentos/SectorAllocation.jsx`, `pages/investimentos/ImpostoRenda.jsx`, `components/ExemptionMeter.jsx` (`ExemptionMeter`), `pages/investimentos/Calculadora.jsx`, `lib/compoundInterest.js`, `components/charts.jsx` (`DonutChart`, `LegendDot`, `SERIES`, `FLOW`, `OTHER_COLOR`) |
| Route(s) | `/investimentos/alocacao`, `/investimentos/ir`, `/investimentos/calculadora` |
| Endpoints | `GET /api/allocation?contribution=`, `PUT /api/allocation/targets`, `GET /api/allocation/sectors?asset_class=`, `POST /api/allocation/sectors/refresh`, `PATCH /api/assets/<asset_id>/sector`, `GET /api/tax-report?year=`, `GET /api/tax-report/exemption?month=`, `GET /api/tax-report/export?year=`; Calculadora: none |
| Client rules | `lib/compoundInterest.js` (`readForm()`, `compoundSchedule()`, `futureValue()`, `yearlyRows()`, `calculate()`, `monthlyFromAnnual()`, `annualFromMonthly()`, `realAnnualRate()`, `parseNumber()`, `periodLabel()`, `durationText()`, `DEFAULT_FORM`), inline in `Alocacao.jsx` (`gapText()`, `DriftBadge` + `DRIFT_WARNING`, `sumOf()`, `toNumber()`), inline in `SectorAllocation.jsx` (`withColors()`, `fetchNotice()`), inline in `ImpostoRenda.jsx` (`activeMonths` filter, `hasEtfs`, `hasForeignResult()`, `monthName()`, net of tributação exclusiva) |

**Native or desktop-first.** Step 8 removes the WebView, so each of the three needs a decision:

| Screen | Recommendation | Why |
|---|---|---|
| Calculadora | **Native, complete** | Pure math, works offline, used on the go; `compoundInterest.js` has 12 tests to port |
| Alocação | **Native read-only + the aporte split**; editing targets and sectors desktop-first (native later if the owner asks) | "Where does this month's aporte go?" is asked at the broker, on the phone; typing 20 percentages is a desk task |
| IR | **Desktop-first**; native shows only the exemption meter and the month-by-month DARF list | The declaration is filled on the computer (IRPF program, copy-paste, .xlsx); the phone needs "do I owe a DARF this month?" |

---

## A. Alocação

### What it is for
Target allocation by class (and by asset within a class), how far the portfolio is from it, how
to split the next aporte without selling, buy opportunities, concentration and the sector
breakdown.

### What it shows
1. Header "Alocação" / "Quanto de cada classe e de cada ativo você quer ter, e para onde vai o
   próximo aporte." Action "Definir metas" (disabled until data).
2. No class targets: info "Sem metas por classe ainda. Em “Definir metas”, diga quanto quer em cada
   classe; a tela passa a mostrar o desvio e a sugerir o aporte."
3. Concentration (`concentration.assets_over_threshold`, threshold `threshold_percent` = 10):
   warning "Um ativo passa / N ativos passam de 10% da carteira: TICKER x,x%, …." + "Uma queda forte
   em um deles pesa na carteira inteira." (percentages only, never masked).
4. With class targets: "Quanto vai aportar?" (decimal; debounced 350 ms → refetch with
   `?contribution=`), hint "Divide o valor entre o que está abaixo da meta, sem vender nada."; then
   badges "<Classe>: <suggested>" for classes with `suggested > 0`.
5. "Oportunidades de compra" (`opportunities[]`): "Abaixo da meta dentro da classe e cotados abaixo
   do seu preço médio: comprar agora aproxima da meta e baixa o médio."; row ticker, class, "Atual
   <current_price>", "Médio <average_price>", "<percent_in_class> / meta <target_percent>".
6. "Por classe" ("Carteira de <total> pelo valor líquido. O traço na barra é a meta."): per
   `classes[]` (order from the server) a collapsible row: label (`getClassLabel(asset_class)`),
   `value` (masked), "<percent> / meta <target_percent>", drift badge (`diff_percent`: "Sem meta",
   "Na meta" below 0.01, else "±x,x p.p.", amber at ≥ 5 p.p.), a bar of `percent` (emerald) with a
   tick at `target_percent`, and on the right "Aportar <suggested>" (with a contribution) or
   `gapText(gap_value)` ("Faltam R$ x" / "R$ x acima" / "Na meta"). Expanded: "Sem meta por ativo
   nesta classe: o aporte fica no nível da classe." when `!has_asset_targets` and > 1 asset; table
   Ativo (+ "abaixo do médio" when `below_average_price`), Valor (masked), Na classe
   (`percent_in_class`), Meta, "Aportar"/"Para a meta".
7. "Por setor" (`SectorAllocation`): "Valor líquido agrupado pelo setor de cada ativo. Ações e FIIs
   vêm da brapi; renda fixa e Tesouro, pelo indexador (pré, pós, IPCA+); o resto, e o que estiver
   errado, você define no lápis." Button "Buscar setores". Class chips (Todas + classes with value
   > 0, shown when ≥ 2 classes). Notice from `fetch` when `unassigned_value > 0`: unconfigured →
   info "Sem token da brapi (BRAPI_TOKEN): preencha o setor dos ativos à mão, no lápis de cada um.";
   error → warning `fetch.message`. Donut (no legend, centre "Carteira", ≤ 9 slices, colours
   `SERIES[i]` in server order, "Sem setor" `OTHER_COLOR`). List of `sectors[]`: colour dot,
   `label`, "N ativo(s)", `value` (masked), `percent`; expanded: ticker, "<category_label> ·
   <segment> · manual", value, `percent_in_sector`, `percent_of_total`, pencil "Editar setor de T".
8. Empty portfolio: "Carteira vazia" / "Registre uma compra em Operações para ver a alocação."

### Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Simular aporte | field | `GET /api/allocation?contribution=<n>` | — | refused (cached last value shown) |
| Salvar metas | "Definir metas" sheet | `PUT /api/allocation/targets` `{classes: {STOCKS: n, REIT: n, FIXED_INCOME: n, OTHER: n}, assets: {<asset_id>: n}}` (blank fields omitted; replaces the whole set) | toast "Metas de alocação salvas." | refused |
| Buscar setores | "Por setor" | `POST /api/allocation/sectors/refresh` → body + `fetch` {`status`, `message`, `updated`} | toast "Setor de N ativo(s) atualizado pela brapi." / "Nenhum setor novo na brapi." / skipped "Nenhum ativo de bolsa para consultar: os demais têm setor manual."; else error | refused |
| Editar setor | pencil → sheet "Setor de T" | `PATCH /api/assets/<asset_id>/sector` `{sector, segment}` | toast "Setor de T salvo." | refused |
| Voltar ao automático | sector sheet (only `source === 'MANUAL'`) | same with `{sector: ""}` | toast "T volta ao setor automático." | refused |

Targets sheet: "Classes em % da carteira; ativos em % da própria classe. Deixe em branco o que não
tem meta."; four class fields; per class with assets a box "<Classe> — por ativo" with one field per
asset and the running sum (amber when filled and ≠ 100), note "Com alguma meta preenchida na classe,
as outras contam como 0% e a soma precisa dar 100%."; footer "Classes: x,xx%" (amber when ≠ 100).
Sector sheet: "Setor" (max 60, suggestions = `suggestions[]`), "Segmento (opcional)" ("Só aparece na
lista; a alocação agrupa pelo setor."); client error "Informe o setor.". Server refusals: "<label>:
percentual invalido.", "<label>: o percentual deve ficar entre 0 e 100.", "<label> somam x,xx%;
precisam somar 100%.", "Classe de ativo invalida: X.", "O aporte nao pode ser negativo.", "Setor:
use no maximo 60 caracteres.", "Informe o setor (vazio para voltar ao
automatico).".

### Data
- `GET /api/allocation[?contribution]` → `total`, `has_class_targets`, `classes[]` {`asset_class`,
  `value`, `percent`, `target_percent`, `diff_percent`, `gap_value`, `suggested`,
  `has_asset_targets`, `assets[]` {`asset_id`, `ticker`, `value`, `percent_in_class`,
  `target_percent`, `gap_value`, `suggested`, `below_average_price`}}, `opportunities[]`
  {`asset_id`, `ticker`, `asset_class`, `current_price`, `average_price`, `percent_in_class`,
  `target_percent`}, `concentration` {`threshold_percent`, `assets_over_threshold[]` {`asset_id`,
  `ticker`, `percent`}}. Key `['investimentos','alocacao',contribution]`.
- `GET /api/allocation/sectors[?asset_class]` → `sectors[]` {`sector` (null = none), `label`,
  `value`, `percent`, `assets[]` {`asset_id`, `ticker`, `category_label`, `class_label`,
  `segment`, `source`, `value`, `percent_in_sector`, `percent_of_total`}}, `unassigned_value`,
  `suggestions[]`, `fetch`. Key `['investimentos','alocacao','setores',assetClass]`. The read fills
  sectors from brapi once for never-checked assets (it may be slow the first time).

### Client rules
- `gapText()`, drift badge (`DRIFT_WARNING` = 5 p.p.), sums in the targets sheet (`sumOf()`) —
  inline, no test. **Port** (display and form feedback; the server validates the sums).
- Sector colours `withColors()` and notice `fetchNotice()` — inline. Port.
- The split itself (`suggested`) is the server's — never compute it on the phone.

### States
Skeleton (4 rows); empty as item 8; error "Não foi possível calcular a alocação." / "…por setor.";
offline: cached; privacy: R$ masked, % and prices of opportunities shown (as today); dark: tokens.

### Conventions that apply
"Allocation targets and goals are plans, like budgets" (PUT replaces the set; class targets sum to
100, asset targets 100 within a class; current values computed on read from net values). "The
category refines the class, on read" (fixed income's sector is its indexer). "Privacy mode".

### Native-only improvements
Open with the "Quanto vai aportar?" field focused when coming from a shortcut; copy a suggested
amount into "Registrar operação" (`13-…`) for that class.

### Acceptance
- [ ] Classes, drift badges, gaps and the contribution split equal the web for the same amount.
- [ ] The concentration warning lists the same assets.
- [ ] Sector donut and list match; editing a sector (if built) moves the asset at once.

### Desktop
Primary home of target editing and sectors: a wide table class × asset with editable cells and live
sums, the donut beside it.

---

## B. IR (Imposto de renda)

### What it is for
Support for the yearly declaration (Bens e direitos, renda variável month by month, rendimentos,
the text to paste into the IRPF program, the .xlsx) and the monthly R$ 20 mil exemption meter.

### What it shows
1. Header "Imposto de renda" / "Bens e direitos, renda variável mês a mês e rendimentos — para
   montar a declaração." Year select "Ano-calendário <ano>" (default last year; options =
   `available_years` + chosen + current), "Exportar .xlsx".
2. **Exemption meter** (current month, `monthKey()`): "Isenção de ações — <mês>" / "Vender até R$
   20.000 em ações no mês deixa o ganho isento. ETFs, BDRs e FIIs não têm isenção."; badge "Isento
   até aqui" (green) / "Passou do limite" (red); "<stock_sales> vendidos de <limit>"; "Ainda cabem
   <remaining>" or "IR estimado de ações: <stock_tax>" (rose); bar of `percent` (emerald < 80,
   amber ≥ 80, rose when not exempt); footer "x,x% do limite", "Resultado das vendas: …", "IR de
   ETFs e BDRs: …" (exempt and `stock_tax`), "Prejuízo a compensar: …", "FII vendidos: … (IR …)",
   "DARF do mês: …". Not masked.
3. `disclaimer` (info).
4. **Bens e direitos** ("Situação em 31/12/<y−1> e 31/12/<y>, pelo custo de aquisição (não pelo
   valor de mercado)."): per item `ticker` · "grupo <group>, código <code> — <code_label>",
   `description`, `cost_previous` and `cost` (masked), copy icon (copies `description`, toast
   "Discriminação copiada.").
5. **Renda variável** (badge "DARF no ano <totals.tax_due>", amber when > 0): months with any
   sale/DARF: Mês ("mmm/aaaa", + "isento"), Vendas ações, Resultado ações, ETFs e BDRs (only if any
   ETF sale), Resultado FII, Prejuízo usado (`stocks.loss_used + reits.loss_used`), DARF (or
   "acumula R$ x" from `darf_carried`). Footer "Prejuízo a compensar ao fim de <y>: ações[, ETFs e
   BDRs] … · FII …"; fixed-income ETF sales listed apart.
6. **Rendimentos isentos** (`line`, `amount`) and **Tributação exclusiva** ("declare o valor
   líquido"; value = `gross − withheld` computed on the client, "bruto … · IR retido …").
7. **Aplicações no exterior** — only when `exterior` has a non-zero `result`, `tax`, `loss_used`
   or `loss_balance`.
8. **Para colar no programa do IRPF** (`irpf_text.sections[]`: `title`, `hint`/`empty`, `text`,
   `blocks[]`), "Copiar" per section and per block; Bens text hidden in privacy mode (copy still
   copies). **Ganho de capital (GCAP)** when `ganho_de_capital[]` is non-empty.

### Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Change year | select | `GET /api/tax-report?year=` (2000…current; else "Ano invalido." / "Ano fora do intervalo.") | — | cached years |
| Exportar .xlsx | header | `GET /api/tax-report/export?year=` → `ir-<ano>.xlsx` (share sheet on the phone) | toast "<file> baixado." | refused |
| Copiar | items, sections, blocks | clipboard | toast "Texto copiado." / "<seção>: texto copiado." | works |

### Data
`GET /api/tax-report?year=` → `available_years`, `disclaimer`, `bens_e_direitos[]` {`key`,
`ticker`, `group`, `code`, `code_label`, `description`, `cost_previous`, `cost`},
`renda_variavel` {`months[]` {`month`, `stocks` {`sales`, `result`, `exempt`, `loss_used`},
`etfs` {`sales`, `result`}, `reits` {`sales`, `result`, `loss_used`}, `darf`, `darf_carried`},
`totals` {`tax_due`, `stock_loss_balance`, `reit_loss_balance`}, `fixed_income_etfs[]`},
`rendimentos_isentos[]`, `tributacao_exclusiva[]` {`line`, `gross`, `withheld`}, `exterior`,
`irpf_text`, `ganho_de_capital[]`. Key `['investimentos','ir',year]`.
`GET /api/tax-report/exemption?month=` → see `13-…`. Key `['investimentos','isencao',month]`.

### Client rules
> **Session B (2026-10-24).** Built: each `tributacao_exclusiva[]` item has `net` =
> `rounded_money(gross − withheld)`, as the export; the web reads it. The Calculadora is ported:
> `rules/CompoundInterest.kt` with the 12 cases.

- Net of tributação exclusiva `gross − withheld` — inline, unrounded float. **Endpoint**: add
  `net` per item (the export already computes `rounded_money(gross − withheld)`).
- `activeMonths`, `hasEtfs`, `hasForeignResult()`, `monthName()` — inline. Port (display).
- The exemption numbers are the server's ("The exemption meter reads the IR report's own
  apuração"); never port the rule.

### States
Skeleton (6); empty sections "Nada a declarar em bens", "Nenhuma venda no ano", "Nada no ano.";
error "Não foi possível montar o relatório."; offline cached; privacy masks Bens values and the Bens
paste text only; dark tokens.

### Conventions that apply
"One monthly tax rule for variable income", "The exemption meter reads the IR report's own
apuração", "Cost is the weighted average", "The app is reais-only on screen" (the exterior panel is
the one deliberate exception), Tributação exclusiva declared at the net value.

### Native-only improvements
Native keeps only items 2 and 5 (meter + DARF months, read-only) with "Relatório completo no
computador" as plain text; a reminder on the last business day when `darf` > 0 (owner to confirm).

### Acceptance
- [ ] The meter equals the web's and the sale form's notice for the same month.
- [ ] DARF months and amounts match the web for the chosen year.

### Desktop
The primary home: everything above, wide tables, the paste text beside the sections, export.

---

## C. Calculadora (juros compostos)

### What it is for
A compound-interest simulator: initial value, monthly aporte, rate, period, optional inflation. "É
só uma conta: nada é gravado e a carteira não muda."

### What it shows
1. Header "Calculadora de juros compostos" + the description above; action "Limpar" (back to
   `DEFAULT_FORM`: 1000, 500, 10% a.a., 10 anos, fim do mês, no inflation).
2. Form: "Valor inicial", "Aporte mensal", "Aporte feito no" (Fim de cada mês / Início de cada
   mês), "Taxa de juros (%)" + unit (ao ano / ao mês; hint "Equivale a x,xxxx% ao mês." or
   "Equivale a x,xx% ao ano."; no decimal keyboard because the rate may be negative), "Período" +
   unit (anos / meses), "Inflação anual (%)" ("Opcional: mostra o valor final em reais de hoje.").
   Last form kept per device (`@financeMVP:calculadoraJuros`); results debounce 250 ms.
3. Error (warning) from `readForm()`: "Valor inicial e aporte não podem ser negativos.", "A taxa
   precisa ser maior que −100%.", "A taxa pode ir até 1000%.", "Inflação fora do intervalo
   aceito.", "Informe o período.", "O período em meses precisa ser inteiro.", "Esse período não
   fecha em meses inteiros: informe em meses.", "O período pode ir até 100 anos."
4. Summary: lead "Valor final" (`final`, "Depois de <durationText(months)>"); "Total investido",
   "Juros" (gain/loss tone), and either "Em reais de hoje" (`real`, "Taxa real x,xx% a.a.") or
   "Rende por mês no fim" (`monthlyIncomeAtEnd`, "Saldo final × taxa mensal").
5. "Evolução": stacked areas investido (`FLOW.investment`) + juros (`SERIES[2]`), dashed line "Em
   reais de hoje" (`SERIES[3]`) with inflation; one point per month up to 60 months, else per year
   (+ the last); X labels `periodLabel()` ("Hoje", "Mês 7", "Ano 3"); tooltip footer "Saldo: …".
6. "Ano a ano": per `yearlyRows()` "Ano N" (or "Ano N (k meses)"), "Juros no ano … · investido …",
   right `balance` and "hoje <real>".

### Actions
| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Edit any field | form | none (local) | — | works |
| Limpar | header | none | — | works |

### Data
None. No endpoint, no query key.

### Client rules
All of `lib/compoundInterest.js` — equivalent (never proportional) monthly rate, Fisher real rate,
end/start-of-month timing, schedule, closed form, yearly rows, labels — tested in
`compoundInterest.test.js` (12 tests). **Port** with the same cases; it is a simulation, not a money
rule of record, so no endpoint. Use `Double` like the web (results are displayed, never stored).

### States
No loading or server error; invalid input shows the warning and hides results. Privacy: nothing
masked (not the owner's data). Light/dark: chart tokens.

### Conventions that apply
"Visual rules" (green/red only for the gain/loss of Juros), "Theme and tokens"; touch targets and
`inputMode` (decimal for money, none for the rate).

### Native-only improvements
Instant, fully offline; a slider for the period; share the result as text.

### Acceptance
- [ ] For the default form and three owner-chosen cases, final value, juros and the yearly table
      equal the web to the cent.
- [ ] Each validation message appears for its input; the last form survives reopening the app.

### Desktop
Keep as is, with the form and the chart side by side.
