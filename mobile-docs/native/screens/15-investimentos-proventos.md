# Investimentos › Proventos — native spec

| | |
|---|---|
| Migration order | 7 (see `../migration-order.md`) — **third of the area** (7c), after Posição and Operações: the calendar of upcoming payments is a frequent phone glance; the typed coupons of fixed income are its only regular write |
| Status | **Built** 2026-10-24 (session D, native-level 8): `ui/investimentos/ProventosScreen.kt` + `ProventosViewModel.kt`, rules `ProceedsForm.kt` (FIXED/MARKET bodies, refusals, edit form, texts; tested). Calendar first, filters collapsed (status always visible). **Registrar provento goes through the outbox** (kind `PROCEED`, with `repeat` too: a resend returns the series already written); edit, delete and "Atualizar" are online only. The automatic sync runs on open (≤ every 10 min per process) and 1.5 s after a position write (`ProceedsSync` in `InvestimentosUi.kt`). **Privacy**: every R$ masked (summary, calendar, chart axis, history), % kept, natively and on the web (owner, 2026-10-24). Not built: the "próximos 30 dias" total, the local notification on payment day, swipe to edit. |
| React source | `frontend/src/pages/Proventos.jsx` (`Proventos`, `ProventoForm`, `ProceedsByAsset`, `receiptsChartData()`, `blankForm()`, `buildPayload` inline), `components/AssetPicker.jsx`, `components/ExportSheet.jsx`, `components/charts.jsx` (`ChartTooltip`, `FLOW`, `CHART`, `compactAxis()`), `lib/proceedsRules.js`, `lib/proceedsSync.js`, `lib/assetSearch.js` |
| Route(s) | `/investimentos/proventos` (legacy `/proventos` redirects) |
| Endpoints | `GET /api/assets`, `GET /api/investment-proceeds`, `GET /api/investment-proceeds/summary`, `GET /api/investment-proceeds/calendar`, `POST /api/investment-proceeds`, `PATCH /api/investment-proceeds/<id>`, `DELETE /api/investment-proceeds/<id>`, `POST /api/investment-proceeds/sync`, `GET /api/investment-proceeds/export`, `GET /api/exports/columns` |
| Client rules | `lib/proceedsRules.js` (`PROCEEDS_TYPES`, `TYPE_HINTS`, `CATEGORY_LABELS`, `assetCategory()`, `categoryLabel()`, `treasuryProduct()`, `proceedsTypeFitsAsset()`, `assetsForProceedsType()`, `proceedsLayout()`, `proceedsTaxField()`, `typeLabel()`, `typeForAsset()`, `changesPositions()`), `lib/proceedsSync.js` (`syncProceeds()`, `scheduleProceedsSync()`, `useProceedsSync()`), `lib/assetSearch.js` (`filterAssetOptions()`), inline in `Proventos.jsx` (`receiptsChartData()`, `buildPayload`, `isFixedIncomeEvent()`, `parseNumberInput`) |

## What it is for
Dividends, JCP, amortizations and coupons: what was received in a period, what is scheduled, per
asset and per month. Proventos of ações/FIIs arrive on their own (computed by the server from
StatusInvest × the position on the data com); the owner types only fixed-income coupons and
amortizations, ahead, and occasionally corrects an automatic one.

## What it shows
1. **Header** "Proventos" / "Calculados pela sua posição na data com de cada provento; os de ações e
   FIIs entram sozinhos. Cupons e amortizações de renda fixa: registre os pagamentos futuros, que
   entram na conta da carteira no dia." Actions "Atualizar" (spinner while fetching or syncing),
   "Exportar" (disabled when the list is empty), "Registrar provento".
2. **Error banner** (danger, dismissible).
3. **Summary** (for the filtered period): lead "Líquido no período" = `summary.net_amount`, hint "N
   evento(s) · bruto <gross_amount>"; "Yield on cost" = `yield_on_cost_percent` ("Líquido / custo
   elegível"); "Agendado" = `scheduled_net_amount` ("Pagamentos futuros"); "Imposto retido" =
   `tax_amount` ("Retido na fonte"). Not masked today.
4. **Calendário** ("Proventos registrados com pagamento nos próximos 180 dias.", badge "N
   evento(s)"): up to 8 rows from `/calendar` (status SCHEDULED, today → +180 days, ascending,
   respecting the asset and type filters): "dd/mm/aaaa <Tipo>" / "<ticker> - <net_amount>". Empty:
   "Nenhum pagamento agendado" + message (filtered: "Nenhum provento futuro para o ativo ou tipo
   filtrado. …"; else "A agenda mostra os proventos registrados com data de pagamento futura.
   Quando um provento for anunciado, registre-o com a data de pagamento.") + "Registrar provento".
5. **Recebimentos por mês / por ano** (only when `summary.by_month` is non-empty): chips "Mensal" /
   "Anual". Bars of net (`FLOW.income`): monthly = `by_month[].net_amount` by `month`
   (`shortMonthLabel`); annual = the months summed per year on the client (rounded to cents).
   Tooltip "Líquido <R$>", footer "N evento(s)"; Y = `compactAxis` (not masked today).
6. **Por ativo** (when `summary.by_asset` is non-empty; server order = net desc): "Líquido no
   período, últimos 12 meses e yield on cost de cada ativo.", badge "N ativo(s)". Row: `ticker`,
   "N evento(s) · 12m <net_12m> · YOC <yield_on_cost_percent>"; right `net_amount` and
   "<share_percent> do total". R$ **masked**, % not. ("12 meses" is the rolling window to today,
   independent of the filter.)
7. **Filtros** ("Período, status, ativo e tipo de provento. Valem ao mudar."): "Início" (default
   1 Jan of the current year), "Fim" (31 Dec), "Ativo" (all `/api/assets`, by ticker), "Tipo"
   (Dividendos, JCP, Amortização, Juros (cupom)), "Status" segmented Todos / Pagos / Agendados.
   Badge "Atualizando..." while fetching. On the phone this panel should collapse into a filter
   chip row above the list.
8. **Histórico de proventos** (badge "N registro(s)"; server order = payment date desc): `ticker`;
   "dd/mm/aaaa[ · com dd/mm/aaaa] · <categoria>" (data com hidden for fixed-income events,
   `asset.asset_class === 'FIXED_INCOME'`; category = `categoryLabel()` from `/api/assets`); right
   `net_amount` (emerald). "<Tipo>[ · agendado]" (sky when `status !== 'PAID'`). Detail line
   "<amount_per_unit>/cota · <eligible_quantity> cotas · " (not for fixed income) + "Bruto … ·
   Imposto … · YOC <yield_on_cost_percent, 4 decimals>". "⋯" → "Editar provento", "Excluir
   provento". Empty: "Nenhum provento" / "Registre dividendos, JCP ou amortizações para acompanhar
   o calendário."

### "Registrar provento" / "Editar provento" sheet
Description "Escolha o tipo e depois o ativo: a busca só mostra os ativos que recebem aquele
provento." **Type first**, then the asset:
- "Tipo de provento" with hint `TYPE_HINTS[type]`. Changing the type clears an asset that no longer
  fits (`proceedsTypeFitsAsset()`), except the one being edited.
- "Ativo" = `AssetPicker` over `assetsForProceedsType(assets, type, editingAssetId)`; option =
  ticker, line "<categoria> · <name>"; empty "Nenhum ativo da carteira recebe este tipo de
  provento.". Without an asset only "Escolha o ativo para ver os campos deste provento."
- **Layout FIXED** (`proceedsLayout()`: fixed-income or Tesouro asset with INTEREST/AMORTIZATION):
  "Pagamento" ("Primeiro pagamento" when repeating), "Valor bruto (R$)" (AMORTIZATION hint
  "Capital devolvido: sem IR."), the tax field (`proceedsTaxField()`; none for AMORTIZATION),
  and on create only "Repetir" (Não repetir / Todo mês / A cada 3 meses / A cada 6 meses / Todo
  ano → 1/3/6/12) + "Nº de pagamentos" (1–120; hint "Contando o primeiro. Cada um entra na conta da
  carteira no seu dia; ajuste o valor de cada um depois, se mudar."), "Observações".
- **Layout MARKET**: "Data com" (hint "A quantidade elegível é a sua posição nesta data."), "Data
  ex", "Pagamento", "Declaração", "Valor por cota (R$)", "Qtd. elegível" (placeholder "auto"),
  "Valor bruto (R$)" (hint "Em branco: valor por cota × quantidade."), tax field, "Observações".
- Tax field label "IR retido (R$)", placeholder "auto", hints: INTEREST "Em branco: tabela
  regressiva desde a aplicação (22,5% a 15%), zero em título isento."; JCP "Em branco: 15% retido
  na fonte (17,5% com data com desde 2026)."; DIVIDEND "Em branco: sem IR (dividendos e
  rendimentos de FII). Preencha só se houve retenção na fonte."

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Atualizar | header | `POST /api/investment-proceeds/sync` `{force: true}` (bypasses the server's 6 h cache), then refetch | toast "Proventos atualizados: N novo(s), N corrigido(s), N removido(s)." or "Proventos já estavam em dia."; `result.message` (e.g. "Nao foi possivel consultar os proventos na StatusInvest agora.", "Proventos nao atualizados para: …") goes to the error banner; no answer → "Não foi possível buscar os proventos agora." | refused |
| Automatic sync | screen open (≤ every 10 min per session) and 1.5 s after any write to `/api/investments*` or `/api/corporate-actions*` (not quote writes) | `POST /api/investment-proceeds/sync` `{}`; refetch **only** if `created + updated + removed > 0` | silent | skipped silently |
| Registrar (FIXED) | sheet | `POST /api/investment-proceeds` `{asset_id, proceeds_type, declared_date: null, record_date: payment_date, ex_date: null, payment_date, amount_per_unit: null, eligible_quantity: null, gross_amount, tax_amount (null = auto), notes, repeat?: {every_months, count}}` → one object, or a list with `repeat` (all or none) | toast "Provento registrado." / "N pagamentos registrados." | refused |
| Registrar (MARKET) | sheet | same endpoint `{asset_id, proceeds_type, declared_date, record_date, ex_date, payment_date, amount_per_unit, eligible_quantity, gross_amount, tax_amount, notes}` (blank → null; the server fills quantity from the position on the data com and gross = per unit × quantity) | toast "Provento registrado." | refused |
| Editar | "⋯" | `PATCH /api/investment-proceeds/<id>` with the same body (no `repeat`); an edited automatic provento becomes `sync_locked` | toast "Provento atualizado." | refused |
| Excluir | "⋯" | `DELETE /api/investment-proceeds/<id>` | "Excluir este provento?" / "<ticker>, pago em dd/mm/aaaa." + for an automatic one (`sync_key`) " Ele foi calculado automaticamente e não volta nas próximas atualizações." / "Excluir"; toast "Provento excluído." | refused |
| Exportar | header | `GET /api/investment-proceeds/export?<filters>&format=&columns=` (`proceeds` columns) | file | refused |
| Change filters | filter panel | refetch with the new params | — | cached combos only |

Client validation: "Selecione o ativo na lista.", FIXED: "Informe a data de pagamento.", "Informe o
valor bruto do pagamento.", "Informe um IR válido.", "Informe quantos pagamentos (de 1 a 120).";
MARKET: "Informe a data com.", "Informe a data de pagamento.", "Informe valores numéricos
válidos.". Server refusals (verbatim): "Juros (cupom) sao de renda fixa ou Tesouro Direto.", "Renda
fixa nao paga dividendos: use juros (cupom) ou amortizacao.", "Renda fixa nao paga JCP: use juros
(cupom) ou amortizacao.", "FII nao paga JCP: use dividendos (rendimentos) ou amortizacao.", "Informe
valor por cota ou valor bruto.", "Nenhuma posicao neste ativo na data com (dd/mm/aaaa). Confira a
data com, informe o valor bruto ou a quantidade elegivel.", "Imposto nao pode ser maior que o valor
bruto.", "Frequencia invalida: a cada 1, 2, 3, 6 ou 12 meses.", "Numero de pagamentos deve ficar
entre 1 e 120.", "Provento nao encontrado." (404).

## Data
One query today, key `['proventos', filters]`, `keepPreviousData`, four requests in parallel:
- `GET /api/assets` → `id`, `ticker`, `name`, `asset_class`, `category`, `category_label` (the
  picker and the category labels).
- `GET /api/investment-proceeds?date_from&date_to&proceeds_type&asset_id&status=ALL|PAID|SCHEDULED`
  → `id`, `asset_id`, `asset` {`ticker`, `asset_class`, `name`}, `proceeds_type`, `declared_date`,
  `record_date`, `ex_date`, `payment_date`, `amount_per_unit`, `eligible_quantity`,
  `gross_amount`, `tax_amount`, `net_amount`, `notes`, `status` (PAID/SCHEDULED by payment date vs
  today), `sync_key`, `yield_on_cost_percent`, `effective_tax_rate_percent`,
  `cost_basis_at_record_date`.
- `GET /api/investment-proceeds/summary` (same filters) → `event_count`, `gross_amount`,
  `tax_amount`, `net_amount`, `yield_on_cost_percent`, `scheduled_net_amount`, `by_month[]`
  {`month`, `net_amount`, `event_count`}, `by_asset[]` {`asset_id`, `ticker`, `asset_class`,
  `event_count`, `net_amount`, `net_12m`, `yield_on_cost_percent`, `share_percent`, `cost_basis`}.
- `GET /api/investment-proceeds/calendar?asset_id&proceeds_type&status=SCHEDULED` (server fills
  today → +180 days).
- `POST /api/investment-proceeds/sync` → `status` (ok/partial/error/skipped), `message`, `created`,
  `updated`, `removed`, `failed[]`.
Native can split these into separate cached requests; the assets list rarely changes.

## Client rules
> **Session B (2026-10-24).** Built: `GET /api/investment-proceeds/summary` has `by_year[]`
> {`year`, `event_count`, `gross_amount`, `tax_amount`, `net_amount`} (summed per event, rounded
> once); the web's annual chart reads it. Ported: `rules/ProceedsRules.kt` (types, layout, tax
> field, `typeForAsset`, `changesPositions`), `rules/AssetSearch.kt`. `client_id` (migration 042) is now accepted by `POST /api/investments` (object or list, one id per request), `POST /api/investments/redemptions`, `POST /api/investment-proceeds` (with `repeat`) and `POST /api/corporate-actions`: a repeat returns the first result (200), so these creations may be queued offline like "+ Novo". The statements below saying "no `client_id`, never queue" are superseded.

- **Which asset receives which type** `proceedsTypeFitsAsset()`, `assetsForProceedsType()`,
  `treasuryProduct()` (Tesouro by name: Renda+/Educa+ INSTALLMENTS, juros semestrais/NTN-F/NTN-B
  COUPON, Selic/Prefixado/IPCA+ BULLET, else null = both) — `proceedsRules.test.js`. **Port** with
  the same cases (form filter only; the server refuses by class).
- **Form layout and tax field** `proceedsLayout()`, `proceedsTaxField()` — tested. **Port**.
- **Category label** `assetCategory()`/`categoryLabel()` — tested. Port.
- **`typeForAsset()`** — tested but not used by the page (the page clears the asset instead). Port
  only if the native form uses it.
- **When to sync** `changesPositions()` (tested) and the 10 min / 1.5 s timing (`proceedsSync.js`,
  untested). **Port**; in native, trigger after the investments writes of `12-…`/`13-…`.
- **Annual totals** `receiptsChartData()` — inline, no test; sums money on the client with
  `Math.round`. **Endpoint** preferred (`by_year` in the summary); else port with a test.
- **Payload building** (FIXED vs MARKET, `record_date = payment_date`, `repeat`) — inline, no test.
  Port with tests.
- **Asset search** `filterAssetOptions()` — tested. Port (shared with `13-…`).

## States
Loading: list skeleton (5) for the history; previous filter's data kept while refetching. Empty:
calendar, by-asset and history empty states above. Error: danger banner "Não foi possível carregar
os proventos.". Offline: cached data for the last filters; sync skipped; writes refused —
`POST /api/investment-proceeds` has **no `client_id`** (a retried `repeat` would write the series
twice). Privacy: only "Por ativo" R$ are masked today; summary, calendar, chart and history are not
— inconsistent with "Por ativo"; decide with the owner before building. Light/dark: tokens.

## Conventions that apply
- "Proventos of ações/FIIs are computed, not typed" — sync on open and after writes; a typed
  provento stands in for the automatic one; a deleted automatic one stays gone (say so in the
  confirmation).
- "Coupons and amortizations of fixed income are typed proventos" — FIXED layout, `repeat`, the
  coupon's regressive IR when blank; amortization does not reduce the title's value in Posição.
- "Registrar provento: the type first, then only the assets that can pay it".
- "Investments and banking are separate areas; …" — paid proventos land in the Corretora by
  themselves ("Provento"/"Juros: <título>"), locked in the Extrato; nothing to do here.
- "Privacy mode" — see States.

## Native-only improvements
Calendar as the top section with a "próximos 30 dias" total; a local notification on a
provento's payment day (computed from the cached calendar, never from the server pushing); filters
as chips; swipe to edit/delete.

## Acceptance
- [ ] Opening the screen syncs at most every 10 min and refreshes only when something changed.
- [ ] A coupon typed with "A cada 6 meses" × 4 creates four scheduled rows; each shows in the
      calendar and, on its day, in the Corretora's Extrato.
- [ ] JCP lists only ações; Juros (cupom) lists only fixed income and coupon-paying Tesouro titles.
- [ ] Deleting an automatic provento warns it will not come back, and it does not after
      "Atualizar".
- [ ] Summary, by-asset and history match the web for the same filters.
- [ ] Airplane mode: cached data shown, writes refused, nothing duplicated later.

## Desktop
Keep the table history (Pagamento, Ativo, Valor/cota, Qtd., Bruto, Imposto, Líquido, YOC) with the
filters always visible; calendar and chart side by side; per-asset table sortable.
