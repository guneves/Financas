# Orçamento — native spec

| | |
|---|---|
| Migration order | 5 (see `../migration-order.md`) |
| Status | Built 2026-10-24 on `claude/practical-hamilton-e6nxfi` (native-level 7): `ui/orcamento/` over `GET /api/monthly-plan` (every R$ from the server; a pre-038 copy without `invest` is ignored), the "Plano do mês" sheet with `ui/components/PercentSlider.kt` and the live preview (`rules/MonthlyPlan.kt`, the input side of `lib/monthlyPlan.js` with its node cases), flags dismissed per device (`PlanFlagDismissals`, SharedPreferences, separate from the WebView's list), categories (add with the slider bounded by `percentRoom`, edit %, Acumula, remove, lines per category, copy the previous month); only Saldo do plano / Disponível por dia masked, as on the web; CI to be confirmed in the PR; waiting for the owner's phone check (Acceptance). Not built: month swipe, long-press menu, pull to refresh, the widget |
| React source | `frontend/src/pages/Orcamento.jsx`, `components/MonthlyPlanPanel.jsx` (`MonthlyPlanPanel`, `MonthlyPlanSheet`), `components/BudgetLines.jsx`, `components/BudgetProgress.jsx`, `components/ui.jsx` (`PercentSlider`, `SummaryPanel`, `Menu`, `Collapsible`, `Expand`) |
| Route(s) | `/planejamento/orcamento` (legacy `/orcamento` redirects); tab "Orçamento" of section "Planejamento" ("Planejar" in the bottom bar) |
| Endpoints | `GET/PUT/DELETE /api/monthly-plan`, `POST /api/budgets`, `PATCH/DELETE /api/budgets/<id>?month=`, `GET /api/budgets/<id>/lines?month=`, `POST /api/budgets/copy`, `GET /api/categories?include_archived=1` |
| Client rules | `lib/monthlyPlan.js` (`percentRoom()`, `clampPercent()`, `stepPercent()`, `percentOf()`, `categoryAmountPreview()`, `livePlanTotals()`, `livePlanText()`, `parseMoneyInput()`, `moneyInputValue()`, `formatPlanPercent()`, `flagText()`, `sortFlags()`, `spendStatus()`, `planFlagKey()`, `visibleFlags()`, `incomeReceivedText()`), `lib/planFlags.js` (`dismissPlanFlag()`, `useDismissedPlanFlags()`), `components/BudgetProgress.jsx` (`BUDGET_STATUS_LABELS`, `BUDGET_STATUS_TONES`) |

## What it is for
The month's plan: the owner types the expected income once, slides how much of it goes to Investir
and Gastar, then splits Gastar across categories. Day to day the screen answers "how much can I
still spend" (Saldo do plano, Disponível por dia) and which category is about to blow. On the
phone it is checked several times a week, typed into rarely (start of month, copy last month).

## What it shows
Top to bottom. Every R$ comes from the server; the client computes only previews while typing.

1. **Header**: title "Orçamento", month switcher (`‹ outubro de 2026 ›`, `monthLabel()`, first letter
   uppercase; "Mês anterior"/"Próximo mês" step with `shiftMonth()`). Default month = `monthKey()`
   (local today). The previous month's data stays on screen while the new one loads
   (`keepPreviousData`).
2. **Empty states** (instead of 3–4):
   - `plan === null`: "Comece pelo plano do mês" / "Informe a renda do mês e quanto dela vai investir
     e gastar. Depois, divida o Gastar entre as categorias." + button "Definir plano" (opens the
     sheet).
   - `plan.needs_income` (a pre-038 plan with no income): "O plano precisa da renda" / "Informe a
     renda para converter o plano em porcentagens." + "Informar renda".
3. **Summary** (`SummaryPanel`): lead "Saldo do plano" = `plan_balance`, hint "Do que você planejou
   gastar, quanto ainda pode"; figure "Disponível por dia" = `daily_available`, hint "Mês encerrado"
   when `period === 'PAST'`, else "Até o fim do mês". `null` → "—". Both **masked in privacy mode**
   (`usePrivateFormatter`). Tone `loss` (rose) when negative, else neutral.
4. **"Renda do mês"** panel (`MonthlyPlanPanel`), action "Editar plano":
   - `incomeReceivedText(income.received, income.planned)` → "Recebido R$ 3.200,00 de R$ 5.000,00
     esperados". If `plan.inherited`: "Plano definido em <Mês de AAAA>." (`plan.source_month`).
   - Row **Investir · <invest.percent>%** — `invest.amount` bold right; "<actual.invested>
     investidos até agora"; bar = `progress.invest_percent` (always emerald, status OK); footer
     "Falta investir <progress.invest_remaining>" or "Aporte do mês feito" when ≤ 0; link "Como
     dividir →" to `/investimentos/alocacao` only when `invest.amount > 0`.
   - Row **Gastar · <spend.percent>%** — `spend.amount`; "<actual.spent> gastos até agora"; bar =
     `progress.spend_percent` (if null: 100 when spent > 0, else 0), colour by `spendStatus(flags)`
     (OVER rose, WARNING amber, OK emerald).
   - Row **Sem destino** only when `unallocated.percent > 0`.
   - **Flags** list: `sortFlags(flags)` (loss → warning → info → gain), minus those dismissed on this
     device (`visibleFlags(flags, month, dismissed)`); each an alert with the tone map
     `FLAG_TONES` (loss→danger, warning, gain→success, info) and text `flagText(flag)`; X =
     "Dispensar". The Gastar bar keeps reading *all* flags, dismissed or not.
   - Footnote: "Gasto: saídas das contas e compras no cartão (inteiras, no mês da compra), sem
     transferências, pagamento de fatura e aportes. Investido: aportes menos resgates das operações da
     carteira no mês."
   - Percentages print with `formatPlanPercent()` (max two decimals, comma: "33,33%").
   None of these R$ are masked in privacy mode today (only item 3 is).
5. **"Categorias do mês"** panel, only when the plan has figures (`plan && !plan.needs_income`).
   Description cites `spend.amount`.
   - Collapsible "Adicionar categoria ao mês": select "Categoria" (active categories not yet in the
     month, label "Pai › Filho"), `PercentSlider` "% do Gastar" with `room = percentRoom(totals.assigned_percent)`,
     R$ preview beside it (`categoryAmountPreview(spend.amount, value)`, "R$ —" when null), hint
     "Livre: <room>% do Gastar"; "Observação" (optional, ≤ 255 chars server side); checkbox
     "Acumular sobra do mês anterior"; "Salvar" (disabled with no category left). Helper text:
     "Juntas, as categorias levam no máximo 100% do Gastar. Subcategoria sem orçamento próprio soma no
     orçamento do pai." or "Todas as categorias ativas já têm orçamento neste mês.". The form stays
     open after saving (several categories in a row).
   - Buttons "Copiar mês anterior" and "Gerenciar categorias" (→ `/ajustes#categorias`).
   - Empty: "Nenhuma categoria neste mês" / "Adicione uma categoria ao mês, ou copie as do mês
     anterior."
   - One row per `categories.items[]`: name (`parent_name › category_name`), line 2
     "`<planned_percent>% · <planned_amount>`" or, when `needs_income`, "antes <legacy_amount> · falta
     a renda do plano" / "<planned_percent>% do Gastar · falta a renda do plano"; badge by `status`
     (`OK` "No plano" neutral, `WARNING` "Perto do limite" amber, `OVER` "Estourou" rose,
     `NEEDS_INCOME` "Falta a renda" amber); progress bar `percent` (clamped 0–100) coloured by status;
     `remaining` right (rose when < 0, "—" when null); "<spent> gastos de <available> (inclui
     <carryover> acumulado)"; `note`; "Ver lançamentos"/"Ocultar lançamentos" toggle; "Acumula" pill
     (pressed = emerald) and a "⋯" menu ("Editar % do Gastar", "Remover do mês").
   - Expanded lines (`BudgetLines`, fetched on open): description (or category), date `dd/mm/aaaa`,
     card name + "· Nx" + "· estorno" for card rows or account name, the subcategory name when it
     differs, "sua parte de <total_amount>" for shared rows; amount signed (`formatSignedCurrency`;
     an expense category shows outflows as "−", a refund "+"). Footer "<n> lançamento(s)" / "Total
     <spent>". Empty: "Nenhum lançamento neste mês."; error "Não foi possível carregar os lançamentos.".
   - Footer row **Sem categoria**: `categories.unassigned.percent` · `.amount` ("O resto do Gastar,
     para o que não tem categoria no mês"), rose when negative.
   - `totals.over_count > 0`: "1 categoria estourou neste mês." / "N categorias estouraram neste mês."

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Define / edit plan | "Definir plano", "Informar renda", "Editar plano" → sheet "Plano do mês" | `PUT /api/monthly-plan` `{month, income_amount, invest_percent, spend_percent}`; conversion of an old plan sends only `{month, income_amount}` | toast "Plano salvo a partir de <Mês de AAAA>." | refused (error) |
| Remove month's plan | sheet footer "Remover deste mês" (only when `!plan.inherited`) | `DELETE /api/monthly-plan?month=` | confirmAction "Remover o plano de <mês>?" / "O mês volta a usar o plano anterior, com as categorias dele, se houver. Nenhum lançamento muda." → toast "Plano removido." | refused |
| Add category | "Adicionar categoria ao mês" | `POST /api/budgets` `{category_id, month, planned_percent, rollover, note?}` | none (row appears) | refused |
| Edit % | "⋯" › "Editar % do Gastar" → inline slider + ✓/✕ | `PATCH /api/budgets/<id>?month=<shown>` `{planned_percent}` | none | refused |
| Toggle rollover | "Acumula" pill | `PATCH /api/budgets/<id>?month=` `{rollover: !rollover}` | none | refused |
| Remove category | "⋯" › "Remover do mês" | `DELETE /api/budgets/<id>?month=` | confirmAction "Remover o orçamento de "<nome>"?" / "Só o plano de <mês> sai; nenhum lançamento muda." | refused |
| Copy previous month | "Copiar mês anterior" | `POST /api/budgets/copy` `{to_month}` (from = previous month; `overwrite` not sent) | if `created === 0 && skipped === 0`: error "Nenhum orçamento em <mês anterior> para copiar." | refused |
| See lines | "Ver lançamentos" | `GET /api/budgets/<id>/lines?month=` | — | cached copy |
| Dismiss flag | X on a flag | none (device only) | — | works |

Sheet "Plano do mês" (description "Vale a partir de <mês>, até você salvar outro."): field "Renda do
mês (R$)" (large, focused, decimal keyboard, `parseMoneyInput()`), sliders "Investir (% da renda)"
(`room = percentRoom(spend)`) and "Gastar (% da renda)" (`room = percentRoom(invest)`), each with its
live R$; live line `livePlanText(totals)` ("Investir R$ 1.000,00 · Gastar R$ 3.500,00 · Sem destino
10%", rose when over). "Salvar plano" is disabled while `livePlanTotals().blocked`: "Informe a renda
do mês.", "Informe quanto da renda investir e gastar, em %.", "Investir e Gastar passam de 100% da
renda.". For a `needs_income` plan: warning "Informe a renda para converter o plano em porcentagens."
+ "O plano antigo era investir <legacy.invest_amount> e gastar <legacy.spend_amount>…"; both sliders
start blank (`null`, "—", hint "Em branco: converte o valor antigo"); "Converter os valores antigos"
blanks them again once touched. Reopening the sheet resets the form from the shown plan.

Server refusals (400, unaccented): "Informe a renda do mes: o plano parte dela.", "A renda do mes deve
ser maior que zero.", "Investir (%) e obrigatorio." / "Gastar (%) e obrigatorio.", "… deve estar entre
0 e 100.", "Investir e Gastar somam N%: passam de 100% da renda.", "As categorias passam de 100% do
Gastar (N%). Reduza alguma antes.", "Informe a categoria do orcamento.", "Categoria nao encontrada.",
"Categoria esta arquivada.", "Os meses de origem e destino sao iguais."; 409 "Ja existe um orcamento
para esta categoria neste mes."; 404 "Orcamento nao encontrado." / "Orcamento nao encontrado neste
mes." (the `?month=` does not use that row) / "Nenhum plano gravado neste mes." (DELETE plan).

## Data
- `GET /api/monthly-plan?month=AAAA-MM` (`build_monthly_plan()`, `services/monthly_plan.py`). Key
  `['plano-do-mes', month]`. Fields used: `month`, `period` (`PAST|CURRENT|FUTURE`), `plan`
  (`null` | `{id, source_month, inherited, needs_income, income_amount, invest_percent,
  spend_percent, legacy: {invest_amount, spend_amount} | null}`), `income.{planned, received}`,
  `invest.{percent, amount}`, `spend.{percent, amount}`, `unallocated.{percent, amount}`,
  `categories.{items, totals, unassigned}`, `plan_balance`, `daily_available`,
  `actual.{spent, invested}`, `progress.{spend_percent, invest_percent, invest_remaining}` (null
  without figures), `flags[]` (`{code, tone, amount, …}`: `over` for SPEND_PACE, `days_left` for
  INVEST_PENDING, `percent` for CATEGORIES_OVER_SPEND, `goal_id/goal_name/target_month/missing` for
  GOAL_*). A response with no `invest` key is a pre-038 persisted copy and is ignored.
- `categories.items[]` (`serialize_budget()`, `services/budgets.py`): `id`, `category_id`,
  `category_name`, `parent_name`, `category_kind`, `planned_percent` (float | null), `planned_amount`,
  `legacy_amount`, `rollover`, `note`, `spent`, `carryover`, `available`, `remaining`, `percent`,
  `status`, `needs_income`, `inherited`, `source_month`. `totals`: `assigned_percent`,
  `unassigned_percent`, `unassigned_amount`, `over_count`, `spend_amount`, `planned`, `spent`,
  `remaining`.
- `GET /api/budgets/<id>/lines?month=` → `{spent, lines[]}`; line: `id`, `source`
  (`TRANSACTION|CARD`), `type`, `category`, `date`, `description`, `amount` (owner's part),
  `total_amount`, `shared`, `account_name` | `card_name`, `installments`, `refund`, `subcategory`.
  Key `['orcamento', 'linhas', budgetId, month]`.
- `GET /api/categories?include_archived=1`, key `['categorias', 'todas']` (`id`, `name`,
  `parent_name`, `archived_at`) — for the add select.
- Invalidation: every successful write through `apiFetch` invalidates every query; the screen then
  awaits `invalidateServerData()`. `POST /api/budgets/copy` returns the `GET /api/budgets` view plus
  `{from_month, created, updated, skipped}`.
- Note: the code comment says `['plano-do-mes', month]` is "the same key as Início"; it is not —
  Início reads `GET /api/budgets?month=` under `['inicio', 'orcamento', month]` (`lib/attention.js`).

## Client rules
- **Slider bounds** — `percentRoom(others, total=100)` (100 − others, ≥ 0, six decimals),
  `clampPercent(value, room)` ([0, room]), `stepPercent(value, dir, room)` (next whole point:
  33,33 + 1 → 34, 33,33 − 1 → 33, capped at room). Edit room for an existing category =
  `max(own %, percentRoom(assigned − own))` (inline in `Orcamento.jsx`: a month already over 100% may
  lower, never raise). `lib/monthlyPlan.test.js` ("percentRoom…", "clampPercent…",
  "stepPercent…"). **Port** with the same cases (UI bounds only; the server re-checks).
- **R$ previews** — `percentOf()` (cents × micro-percent in BigInt, ROUND_HALF_UP, mirrors
  `money.percent_of()`), `categoryAmountPreview()`, `livePlanTotals()` (incl. legacy conversion
  preview and `blocked` reasons), `livePlanText()`, `unallocatedText()`. Tested. **Port** (preview
  only; the saved values come back from the server). Use `BigDecimal`, never `Double`.
- **Money input** — `parseMoneyInput()` / `moneyInputValue()`, tested; the same parser "+ Novo"
  needs (step 1) — share the Kotlin port.
- **Flag texts** — `flagText()`, `sortFlags()`, `spendStatus()`, `FLAG_TONES`; tested. **Port**
  (pure text; codes stay on the server).
- **Flag dismissal** — `planFlagKey(flag, month)` = `plan:<month>:<code>[:<goal_id>]`,
  `visibleFlags()`; store = `lib/planFlags.js` (localStorage `@financeMVP:planFlagsDismissed`, via
  `addDismissed()` from `attentionRules.js`). Tested ("planFlagKey…", "visibleFlags…"). **Port** to
  DataStore; nothing goes to the server.
- **Status labels/tones** — `BUDGET_STATUS_LABELS/TONES` (inline constants, no test). Port as an enum.
- `formatPlanPercent()` tested; port with pt-BR formatting.
- Inline, untested: the "nothing to copy" check (`created === 0 && skipped === 0`), the available
  categories filter (active and not budgeted), the progress fallback for Gastar.

## States
- Loading: two skeleton blocks (summary + panel) only on first load; month switches keep the old data.
- Empty: "no plan" and "needs income" states above; categories empty state.
- Error: query errors → "Não foi possível carregar o plano do mês." / "Não foi possível carregar as
  categorias."; write errors in the alert at the top (server message as is).
- Offline: persisted cache (`lib/queryPersist.js`, ≤ 14 days) shows the last plan; every write fails
  with "Sem conexão com o servidor. Esta ação só funciona conectado." (no outbox for plans).
- Privacy: only Saldo do plano and Disponível por dia are masked today.
- Light/dark: tokens only; rose = negative/over, amber = warning, emerald = progress fill.

## Conventions that apply
- "A budget is a plan, not a record" — category %s of Gastar, R$ computed on read, inheritance via
  `category_source_month()`, writes in an inherited month go through `materialize_month()` (send
  `?month=` = the month shown on every PATCH/DELETE/lines call).
- "The monthly plan is a plan, like budgets, and starts from income" — income is the only typed R$;
  Saldo do plano = Gastar R$ − month's spent; `needs_income` plans compute nothing.
- "Orçamento's percentages slide, they are not typed" — sliders of 1 point with − / +, capped at room.
- "The plan's flags can be dismissed per device" — key = code + month (+ goal).
- ""Disponível por dia" lives in Planejar › Orçamento, not Início" — read `daily_available`, never
  compute it.
- "Budget spent (decision 1)" — card purchases in full in the purchase month; invoice payments never.
- "Whose expense it is" — spent counts only the owner's part (lines show "sua parte de").
- "Money" — no float rounding on the previews.

## Native-only improvements
- Swipe a month left/right; haptic tick on each slider point and at the room limit.
- Long-press a category row for the menu; pull to refresh.
- A Glance widget showing Saldo do plano / Disponível por dia (masked when privacy is on).

## Acceptance
- [ ] Opening shows the current month; ‹ › change months with the previous data kept until loaded.
- [ ] No plan → "Comece pelo plano do mês"; saving income 5.000, Investir 20, Gastar 70 shows
      Investir R$ 1.000,00, Gastar R$ 3.500,00, Sem destino 10% and the toast.
- [ ] Investir slider cannot pass 100 − Gastar; − / + step whole points and stop at the limit.
- [ ] Adding a category: slider stops at "Livre"; R$ preview matches the saved `planned_amount`.
- [ ] Editing a category in an inherited month leaves earlier months unchanged.
- [ ] Saldo do plano and Disponível por dia match the desktop; masked with the eye.
- [ ] Dismissing a flag hides it this month on this phone only; next month it comes back.
- [ ] "Ver lançamentos" total equals the row's "gastos".
- [ ] Copy with nothing in the previous month shows "Nenhum orçamento em … para copiar."
- [ ] Airplane mode: last plan visible; saving shows the offline message.

## Desktop
Keep, widen: plan panel and summary side by side, categories as a table (category, %, planned,
carry-over, spent, remaining, status) with lines expanding inline; add a month-over-month view of
spent per category (analysis). The sliders can stay; a numeric field beside them is fine on desktop
as long as it clamps with the same `percentRoom()`.
