# Investimentos › Operações and "Registrar operação" — native spec

| | |
|---|---|
| Migration order | 7 (see `../migration-order.md`) — **second of the area** (7b), right after Posição: the "Registrar operação" sheet is the investments' write path and is opened from Posição, from this screen and from the shell's "+" while inside `/investimentos` |
| Status | **Built** 2026-10-24 (session D, native-level 8): `ui/investimentos/OperacoesScreen.kt` + `OperacoesViewModel.kt`, the sheet `LaunchSheet.kt`, fields `InvestFields.kt` (CashLinkField, AssetPicker, FixedIncomeFields), rules `Operations.kt` (movement reading, edit payload, buy/sell bodies and refusals, corporate-action body; tested). **Salvar compra/venda go through the outbox** (kind `INVESTMENT`, `client_id` before the POST, 6 s, then the worker), shown on the screen as "N operação(ões) guardada(s)"; edit, delete and corporate events are online only (events carry a `client_id`). A typed ticker the catalog cannot be asked about offline is queued, and the server refuses it later if it is not from the B3. **Privacy**: every R$ (summary, list, results, Aportes) is masked natively (decided by the session; the web masks less). Not built: the shell's "+" opening the sheet (`NativeScreens.open("investment-entry")`), remembering the last asset type. |
| React source | `frontend/src/pages/investimentos/Operacoes.jsx` (`describeMovement()`, `MovementCard`/`MovementRow`, `realizedDetail()`, edit sheet), `components/InvestmentLaunchModal.jsx`, `components/CashLinkField.jsx`, `components/AssetPicker.jsx`, `components/TickerAutocomplete.jsx`, `components/ExemptionMeter.jsx` (`SaleExemptionNotice`), `components/FixedIncomeFields.jsx`, `pages/investimentos/CorporateActionsPanel.jsx`, `pages/investimentos/AportesChart.jsx` (spec in `14-…`), `pages/investimentos/useInvestments.js`, `pages/investimentos/helpers.js`, `components/ExportSheet.jsx`, `components/Layout.jsx` (`openInvestment()`) |
| Route(s) | `/investimentos/operacoes`; the sheet has no route |
| Endpoints | `GET /api/investments?order=created_at&ascending=false`, `GET /api/investments/portfolio?refresh_prices=false`, `POST /api/investments`, `PATCH /api/investments/<id>`, `DELETE /api/investments/<id>`, `POST /api/investments/update-prices`, `GET /api/market/tickers?q=&asset_class=&kind=&limit=20`, `GET /api/market/tickers/<ticker>`, `GET /api/tax-report/exemption?month=&planned_sale=&ticker=`, `GET /api/accounts` (and `?include_archived=1`), `GET/POST /api/corporate-actions`, `DELETE /api/corporate-actions/<id>`, `GET /api/investments/export`, `GET /api/investments/contributions` |
| Client rules | `lib/assetSearch.js` (`filterAssetOptions()`, `normalizeSearchText()`), `lib/portfolioAccount.js` (`cashLinkMetadata()`, `cashLinkFromMetadata()`, `emptyCashLink()`, `portfolioAccounts()`, `pickPortfolioAccountId()`), `lib/fixedIncome.js` (`fixedIncomeMetadataFromForm()`, `fixedIncomeFormFromMetadata()`, `FIXED_INCOME_METADATA_KEYS`, `treasuryRateMode()`, `rateModeOf()`, `rateFieldsForMode()`, `TREASURY_TITLES`), `lib/treasury.js` (`parseTreasuryUnits()`), `pages/investimentos/helpers.js` (`movementDateValue()`, `movementUnitPrice()`, `movementTotalValue()`, `movementFees()`, `hasRealizedResult()`, `parseNumberInput()`), inline in `InvestmentLaunchModal.jsx` (`assetTypeOf()`, `movementAssetClass()`, total value, average price, sale validation), inline in `Operacoes.jsx` (`describeMovement()`, realized summary, edit payload) |

## What it is for
The history of buys, sells, aportes and redemptions with the realized result and estimated IR of
each sale, plus the form that records a new operation. On the phone the form is the main use: the
owner records a buy or sale right after doing it at the broker; the list is checked occasionally.

## What it shows
1. **Header** "Operações" / "Compras, vendas, aportes e resgates, com o resultado realizado e o IR
   estimado." Actions "Exportar" (disabled with no movements), "Registrar operação".
2. **Summary** (only when some movement has a realized result): lead "Resultado pós-IR" = Σ
   `realized_net_profit_after_tax` (signed, gain/loss), hint "N venda(s) e resgate(s) com
   resultado"; "Lucro/prejuízo realizado" = Σ `realized_profit` ("Antes do IR", gain/loss); "IR
   estimado" = Σ `realized_tax_amount` ("Parte de cada venda no IR do mês, e o retido na renda
   fixa"); "Base de custo vendida" = Σ `realized_cost_basis` ("Custo médio e títulos
   resgatados"). Today summed on the client; the same sums come from the server as
   `realized_result` {`net_profit_after_tax`, `realized_profit`, `tax_amount`, `cost_basis`,
   `operation_count`} in `GET /api/investments/portfolio` — **native reads that**. Not masked in
   privacy mode today.
3. **Aportes e resgates** chart — see `14-investimentos-rentabilidade.md` § Aportes.
4. **Operações list** (newest first, header badge "N registro(s)"), one card per movement
   (`describeMovement()`):
   - `ticker_or_name`; "<asset_category_label || class label> · <date>": date = `metadata.
     redemption_date || sale_date || purchase_date` (dd/mm/aaaa), or `created_at` with " às hh:mm"
     when no typed date. Right: total = |quantity × unit price| (`formatCurrency`).
   - Kind line: "Compra/Venda de <qty>" (variable) or "Aporte/Resgate" (fixed income; a redemption
     reads "Resgate de R$ x"), "Bonificação" when `metadata.corporate_action_id`; " a <unit
     price>"; "· Custos <fees>" when > 0; "· Líquido <net>" on sales; "· No extrato" when
     `metadata.cash_account_id` is set. Unit price: redemption → `current_price`; sale →
     `metadata.sale_price`; else `average_price`. Fees: `realized_fee_amount ?? fee_amount ??
     metadata.other_costs`. "ajustada por evento" when `metadata.corporate_adjustments` is
     non-empty.
   - Result box (only with `realized_profit` set): "Resultado" `realized_profit` (signed,
     gain/loss), "Base: <realized_cost_basis>", detail "<±realized_profitability_percent> · custo
     médio" (method from `realized_metadata.cost_method`: AVERAGE "custo médio", FIFO "FIFO" + ",
     N lotes", LOT_REDEMPTION "resgate do título"); "IR estimado" `realized_tax_amount`, "Pós-IR:
     <realized_net_profit_after_tax>" (gain/loss), "Alíq.: <realized_tax_rate × 100>%".
   - "⋯" with "Editar operação" and "Excluir só esta operação" — **absent on a Bonificação**.
   - Empty: "Nenhum histórico encontrado." / "As compras, vendas e resgates registrados aparecem
     aqui."
5. **Eventos corporativos** panel: "Desdobramentos, grupamentos e bonificações. As operações
   anteriores à data ex são ajustadas à base nova." Button "Registrar evento" (disabled with no
   STOCKS/REIT asset). Rows "<ticker> · <label> <ratio_from> para <ratio_to>", "Data ex dd/mm/aaaa"
   (+ " · custo atribuído R$ x por cota" for BONUS, + notes) and a delete icon "Desfazer …". Empty:
   "Nenhum evento" / "Registre aqui um desdobramento, grupamento ou bonificação avisado pela
   empresa."

### "Registrar operação" sheet (`InvestmentLaunchModal`)
Description "Compra ou venda. O resgate de renda fixa fica na linha do ativo, em Posição."
Segmented "Compra" / "Venda" (changing mode clears asset, quantity "1", price, costs).

- **Tipo de ativo** (disabled in Venda): Ações, ETFs, Fundos Imobiliários, Renda Fixa, Tesouro
  Direto, Bitcoin, Outros. Screen types map to the stored class (`movementAssetClass()`): ETF →
  STOCKS, TESOURO → FIXED_INCOME, BITCOIN → OTHER with ticker "BTC"; others as is.
- **Ativo**:
  - Compra + Ações/ETFs/FIIs: `TickerAutocomplete` over the B3 catalog (`GET /api/market/tickers`,
    180 ms debounce, limit 20, `asset_class` = stored class, `kind=ETF` for ETFs; Ações exclude
    `kind === 'ETF'`), plus wallet assets of the class not in the result, labelled "Na carteira".
    Placeholder "Digite o ticker (ex: PETR4)" / "(ex: BOVA11)". Typing uppercases; text not chosen
    from the list is not a valid asset (checked on submit).
  - Compra + Bitcoin: fixed text "Bitcoin (BTC) · cotação automática em reais".
  - Compra + Renda Fixa/Tesouro: free name with suggestions = own titles of that kind (+
    `TREASURY_TITLES` for Tesouro); placeholder "Ex: CDB Banco X 2027" / "Ex: Tesouro IPCA+ 2035".
    For Tesouro the name sets the rate mode (`treasuryRateMode()`: Selic → POS, IPCA/Renda+/Educa+
    → IPCA, Prefixado → PRE; resets the rate field when it changes).
  - Compra + Outros: free text with own OTHER assets as suggestions ("Selecionar ou digitar").
  - Venda: `AssetPicker` over positions with `class !== 'FIXED_INCOME'` and quantity > 0, sorted by
    name; option = ticker, line "<category_label> · <qty> cota(s) · <name>", aside `current_value`
    (masked); filtered by `filterAssetOptions()`; empty "Nenhuma posição para vender.".
- **Data da operação** (default today). **Quantidade** (hidden for fixed-income buys; default "1";
  any decimals for Bitcoin, step 0.0001 otherwise). **Preço em R$** / "Valor aplicado em R$"
  (fixed-income buy). **Outros custos (opcional)**.
- Tesouro buy: **"Quantidade de títulos (opcional)"**, hint "Como no extrato da corretora. Sem ela,
  o app usa o preço do Tesouro na data da compra." (`parseTreasuryUnits()`).
- Fixed-income buy: `FixedIncomeFields` — "Tipo de título" (not for Tesouro; Tesouro is excluded
  from the list), "Rentabilidade" (Pós-fixado (CDI) / IPCA+ / Pré-fixado), "Indexador" (% do CDI /
  CDI+), the rate field (`rateFieldLabel()`), "Imposto de renda" (read-only, follows the type).
- Venda with no position: warning "Não há ativos de renda variável disponíveis para venda. Resgates
  de renda fixa continuam na linha do ativo."
- Venda of a STOCKS asset: `SaleExemptionNotice` (debounced 400 ms, `planned_sale` = qty × price):
  ETF/BDR (`eligible === false`) info "ETFs e BDRs não têm a isenção…" or for `kind === 'ETF_RF'`
  "ETF de renda fixa: o IR é retido na fonte…"; `would_exceed` warning "Com esta venda, as vendas
  de ações de <mês> somam <sales_after> e passam de <limit>: o ganho do mês inteiro deixa de ser
  isento (15%). Cabem <remaining> sem perder a isenção."; `!exempt` info "As vendas de ações de
  <mês> já passaram de <limit>: …"; else "Isenção de <mês>: depois desta venda, ainda cabem
  <limit − sales_after> em vendas de ações."
- `CashLinkField` (`movementType` BUY "O valor sai desta conta." / SELL "O valor líquido entra
  nesta conta."): select "Conta da carteira" over active BRL Corretora accounts (default the first
  in list order), checkbox "Não descontar de nenhuma conta" ("A operação entra na carteira sem
  mexer em saldo. Use quando o dinheiro já está no extrato (importado ou lançado à mão)."); with no
  Corretora account the text "Nenhuma conta vinculada à carteira. Cadastre uma conta do tipo
  Corretora, em reais: as operações saem dela." + link "Ajustes › Contas".
- **Valor total** (live): Venda max(qty × price − costs, 0); fixed-income buy price + costs; buy
  qty × price + costs. Buttons "Cancelar" / "Salvar compra" | "Salvar venda".

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Salvar compra | sheet | `POST /api/investments` `[{asset_class, ticker_or_name (uppercased), quantity (1 for fixed income), average_price: round6((gross + costs) / qty) — fixed income: price + costs, current_price: existing asset's current_price or the typed price, metadata: {purchase_date, other_costs, cash_account_id \| null, + fixed income: fixed_income_type, rate_type, indexer, cdi_percentage \| annual_rate, is_tax_free, treasury_units?}}]`; then `POST /api/investments/update-prices {investment_id}` behind | toast "Compra de <TICKER> registrada." | refused |
| Salvar venda | sheet | `POST /api/investments` `[{asset_class, ticker_or_name, quantity: −qty, average_price: position's average (ignored by the server), current_price, metadata: {sale_date, sale_price, other_costs, cash_account_id \| null}}]` | toast "Venda de <TICKER> registrada." | refused |
| Editar operação | card "⋯" → sheet "Editar operação" ("Ativo: <ticker>") | `PATCH /api/investments/<id>` `{quantity (sale/redemption with "−"), average_price, metadata}`; then update-prices behind | toast "Operação atualizada." | refused |
| Excluir só esta operação | card "⋯" | `DELETE /api/investments/<id>` (removes its linked Extrato row) | "Excluir esta operação?" / "Só esta operação sai do histórico; as outras do ativo continuam." / "Excluir"; toast "Operação excluída." | refused |
| Registrar evento | corporate panel → sheet | `POST /api/corporate-actions` `{asset_id, action_type: SPLIT\|REVERSE_SPLIT\|BONUS, ex_date, ratio_from, ratio_to, bonus_unit_cost?, notes?}` | toast "Evento registrado: as operações de <T> antes de <data> foram ajustadas." + " A cotação não foi atualizada: use "Atualizar cotações" em Posição." when `price_refreshed` is false | refused |
| Desfazer evento | row icon | `DELETE /api/corporate-actions/<id>` | "Desfazer o <label> de <ticker>?" / BONUS "As cotas da bonificação saem da carteira." else "As operações anteriores voltam à quantidade e ao preço originais." / "Desfazer"; toast "Evento desfeito." | refused |
| Exportar | header | `GET /api/investments/export?format=&columns=` (`movements` columns) | file | refused |

Edit sheet fields: "Quantidade" (not fixed income, unsigned), "Preço médio/base de custo (R$)" /
"Valor aplicado (R$)" / "Base de custo resgatada (R$)" (hidden on a sale), "Preço de venda (R$)"
(sale; hint "O custo da venda é o preço médio da posição na data, calculado pelo app."), "Outros
custos (R$)", "Data da operação", `CashLinkField` with the saved account (an archived or
non-Corretora saved account stays selectable as "<name> (arquivada)"/"Conta arquivada"),
"Quantidade de títulos (opcional)" (Tesouro buy), `FixedIncomeFields` (fixed income, not a
redemption). The payload drops `purchase_date`/`sale_date`/`redemption_date`, re-sets the one that
applies, writes `other_costs` and the cash key (`cashLinkMetadata(..., {editing: true})` — an old
operation is not blocked by a missing Corretora), and for fixed income clears
`FIXED_INCOME_METADATA_KEYS` before re-adding them. Errors shown inside the sheet, prefixed "Erro
ao guardar edição: ".

Corporate-action sheet: segmented Desdobramento / Grupamento / Bonificação (defaults 1→2, 10→1,
10→1; hint per type in the description), "Ativo" (STOCKS/REIT, one per `asset_id`), "Data ex"
("Operações antes desta data são ajustadas."), "De (cotas antes)", "Para (cotas depois)" / "Para
(cotas novas)", "Custo atribuído por cota" (BONUS), "Observação"; footnote "Depois de registrado,
operações deste ativo com data anterior à data ex ficam bloqueadas; desfaça o evento para lançar
uma."

Client validation: "Informe o ativo do lançamento.", "<T> não está na lista da B3. Selecione um
ativo pela busca." (typed ticker not in wallet and `GET /api/market/tickers/<T>` 404), "Informe um
preço válido.", "Informe uma quantidade válida.", "Selecione o ativo para venda.", "A quantidade
informada é maior do que a posição disponível.", "Informe o preço da venda.", "Informe uma
quantidade de títulos válida.", "Informe um percentual do CDI válido." / "Informe uma taxa
válida.", edit: "Informe um preço/valor válido.", "Informe custos válidos.", "Informe um preço de
venda válido.", plus the cash-link messages.

Server refusals (verbatim, unaccented): "Ativo <T> nao encontrado na lista da B3. Selecione um
papel pela busca.", "<T> e um ativo do tipo <kind>. Selecione o tipo <expected>.", "Venda maior que
a quantidade disponivel na carteira.", "Quantidade deve ser diferente de zero.", the backing
messages (409), "Esta operacao e a bonificacao de um evento corporativo; para mudar ou tirar,
exclua o evento em Operacoes." (409), "O lancamento desta operacao no extrato tem comprovante.
Remova o comprovante no Extrato antes de tirar a operacao de la." (409), "Esta operacao nao tem
valor para lancar no extrato. Corrija o valor ou desmarque 'Lancar no extrato'." (stale
wording: the checkbox is now "Não descontar de nenhuma conta"; fix the server text), "Ha um <label> em <data> neste ativo, e as operacoes anteriores ja estao ajustadas a
ele. Exclua o evento, lance a operacao e registre o evento de novo." (409); corporate actions: "No
desdobramento cada cota vira mais de uma: …", "No grupamento varias cotas viram uma: …", "Nenhuma
posicao em <T> antes de <data>.", "Ja existe um evento em <data>; registre os eventos em ordem de
data.", undo: "Ha um evento mais recente neste ativo (<data>); exclua-o primeiro.", "Ha N
operacao(oes) a partir de <data> feitas na base nova; exclua-as antes de desfazer o evento."

## Data
- `GET /api/investments?order=created_at&ascending=false` → per movement: `id`, `asset_id`,
  `asset_class`, `asset_category`, `asset_category_label`, `ticker_or_name`, `quantity` (signed),
  `average_price`, `current_price`, `fee_amount`, `created_at`, `metadata`, `realized_profit`,
  `realized_tax_amount`, `realized_tax_rate`, `realized_net_profit_after_tax`,
  `realized_net_proceeds`, `realized_cost_basis`, `realized_profitability_percent`,
  `realized_fee_amount`, `realized_metadata`. Key `['investimentos','operacoes']`.
- `GET /api/investments/portfolio?refresh_prices=false` → `assets[]` for the sale picker and
  wallet suggestions, `realized_result` for the summary. Key `['investimentos','carteira']` (the
  shell's "+" fetches it ad hoc).
- `GET /api/market/tickers` → `[{ticker, name, kind, kind_label, asset_class}]` (reference data,
  no user filter); `GET /api/market/tickers/<t>` → the entry or 404.
- `GET /api/tax-report/exemption` → `month`, `limit`, `sales_after`, `remaining`, `exempt`,
  `would_exceed`, `eligible`, `kind`. Key `['investimentos','isencao',month,planned,ticker]`.
- `GET /api/accounts` (`['contas','ativas']`), `?include_archived=1` (`['contas','todas']`, only
  when the saved account is not a current Corretora).
- `GET /api/corporate-actions` → `id`, `asset_id`, `ticker`, `action_type`, `label`, `ex_date`,
  `ratio_from`, `ratio_to`, `bonus_unit_cost`, `notes`. Key `['investimentos','eventos']`.
- Every write invalidates all queries and schedules the proventos sync (`changesPositions()`).

## Client rules
> **Session B (2026-10-24).** Built: the web's realized summary reads `realized_result` of the
> portfolio (no client sum). Ported: `rules/AssetSearch.kt`, `rules/PortfolioAccount.kt`,
> `rules/FixedIncome.kt` (with the form-error cases on both sides). Aportes e resgates can use
> `ui/charts/SignedBarChart`. `client_id` (migration 042) is now accepted by `POST /api/investments` (object or list, one id per request), `POST /api/investments/redemptions`, `POST /api/investment-proceeds` (with `repeat`) and `POST /api/corporate-actions`: a repeat returns the first result (200), so these creations may be queued offline like "+ Novo". The statements below saying "no `client_id`, never queue" are superseded.

- **Asset search** `filterAssetOptions()` (`lib/assetSearch.js`, tested in
  `proceedsRules.test.js` "the search matches ticker or name…"). **Port** (shared with `15-…`).
- **Cash link** (`lib/portfolioAccount.js`, `portfolioAccount.test.js`). **Port**.
- **Fixed-income form ↔ metadata** (`lib/fixedIncome.js`, `fixedIncome.test.js` partial). **Port**
  with extra cases for `fixedIncomeMetadataFromForm()` errors.
- **Average price of a buy** `(gross + costs) / qty`, 6 decimals; fixed income `price + costs`;
  **Valor total** — inline in `InvestmentLaunchModal.jsx`, no test. Port with tests (or let the
  server take `gross` + `other_costs`; it already stores `fee_amount` from `other_costs`).
- **Screen asset type ↔ class** `assetTypeOf()` / `movementAssetClass()` — inline. Port.
- **Movement reading** `describeMovement()` and the helpers `movementUnitPrice()`,
  `movementTotalValue()`, `movementFees()`, `movementDateValue()` — inline / `helpers.js`, no test.
  Port with tests.
- **Realized summary** — inline sum. **Endpoint**: use `realized_result`.
- **Edit payload** (sign by stored type, date keys) — inline. Port; the server keeps the sign
  anyway ("An operation's sign is its type, not the field").

## States
Loading: list skeleton (6). Empty: item 4's empty state; summary hidden. Error: warning banner
("Não foi possível carregar o histórico de operações."). Offline: cached list; the sheet opens but
"Salvar" is refused — `POST /api/investments` has **no `client_id`**, so never queue, never retry
after a timeout (unlike "+ Novo"). Privacy: today only the sale picker's aside is masked; the list
and summary are not, while the Aportes chart is (inconsistent; decide with the owner). Light/dark: tokens only.

## Conventions that apply
- "Cost is the weighted average (custo médio ponderado), never FIFO" — the sale's cost is computed
  by the server; the price stored on a SELL row is never a cost.
- "One monthly tax rule for variable income" / "The exemption meter reads the IR report's own
  apuração" — the sale notice reads `/api/tax-report/exemption`, never a local rule.
- "An operation's sign is its type, not the field" — edit shows quantities unsigned.
- "Investments and banking are separate areas; …portfolio account" — every new operation sends
  `cash_account_id` or `null`; refused with no Corretora account.
- "A corporate action is applied on write" — no movement before the latest event; only the latest
  event undoes.
- "Foreign currency is stored native, calculated in BRL" / "reais-only on screen" — no currency
  field.
- "Investimento is not a category" — the linked Extrato rows are "Aporte"/"Resgate".
- "A save waits only for its own request" — close the sheet on the POST's answer; quotes behind.

## Native-only improvements
The sheet as a native bottom sheet opened by `NativeScreens.open("investment-entry")` from the
shell's "+" inside Investimentos; numeric keyboard with comma; remembers the last asset type;
haptic on save.

## Acceptance
- [ ] A buy of an ação picked from the catalog appears in Operações and Posição, with one "Aporte"
      in the Corretora's Extrato; with "Não descontar de nenhuma conta", none.
- [ ] A typed ticker not in the B3 list is refused with the message.
- [ ] A Tesouro buy with "Quantidade de títulos" shows those units in Posição.
- [ ] A sale over 20 mil in ações in the month shows the warning before saving; an ETF shows the
      no-exemption note.
- [ ] Editing a sale without "−" keeps it a sale; a Bonificação has no "⋯".
- [ ] Registering and undoing a split rescales and restores earlier operations; out-of-order
      events show the server message.
- [ ] Airplane mode: the sheet refuses to save and nothing is duplicated after reconnecting.

## Desktop
Widen into the table (Data, Ativo, Preço, Total, Resultado, IR estimado) with filters by asset,
type and period; the register form as a dialog; corporate events in a side panel.
