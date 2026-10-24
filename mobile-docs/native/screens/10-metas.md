# Metas — native spec

| | |
|---|---|
| Migration order | 5 (see `../migration-order.md`) |
| Status | Built 2026-10-24 on `claude/practical-hamilton-e6nxfi` (native-level 7): `ui/metas/` over `GET /api/goals` (cached copy opens at once), cards with progress, Atual/Faltam/Objetivo masked, the forecast texts and badge from `lib/goals.js` (moved out of `Metas.jsx` with node tests) ported in `rules/Goals.kt`; the sheet clears the fields its kind hides (an income goal sends contribution 0, rate and date null — the web still sends them, harmless); waiting for the owner's phone check. Not built: circular progress, the pinned-goal widget |
| React source | `frontend/src/pages/Metas.jsx` (`GoalSheet`, `Figure`, `forecastText()`, `forecastHint()`, `shortMonthYear()`), `components/BudgetProgress.jsx` (`BudgetProgressBar`), `pages/investimentos/helpers.js` (`getClassLabel()`), `components/ui.jsx` (`Sheet`, `SegmentedControl`, `Menu`, `Badge`) |
| Route(s) | `/planejamento/metas`; tab "Metas" of "Planejamento" |
| Endpoints | `GET /api/goals`, `POST /api/goals`, `PATCH /api/goals/<id>`, `DELETE /api/goals/<id>` (`GET /api/goals/<id>` exists, unused by the screen) |
| Client rules | inline in `Metas.jsx` (`payloadFromForm()`, `formFromGoal()`, `forecastText()`, `forecastHint()`, `shortMonthYear()`, `KINDS`, `KIND_HINTS`, `CLASSES`); `lib/format.js` (`formatCurrency()`, `formatPercent()`, `monthLabel()`); `lib/privacy.js` (`usePrivateFormatter()`) |

## What it is for
Long-range targets — "Primeiros 100 mil", net worth, a class of assets, or a monthly income from
proventos. The owner sets the target, the planned monthly contribution and optionally an expected
return and a date; the server says how far along it is, when it arrives at this pace, and what
contribution the date needs. Goals with a date also feed the monthly plan's flags in Orçamento
(`GOAL_SHORT` / `GOAL_COVERED`). On the phone: an occasional glance, rare edits.

## What it shows
1. **Header**: "Metas", description "Onde você quer chegar, quanto falta e quando chega no ritmo
   atual.", button "Nova meta".
2. **Empty**: "Nenhuma meta ainda" / "Patrimônio, carteira, uma classe de ativo ou renda mensal de
   proventos: diga o alvo e o aporte, e a previsão aparece aqui." + "Nova meta".
3. **One card per goal**, in server order (`target_amount`, then `created_at`):
   - Title `name`; subtitle `kind_label` ("Carteira de investimentos", "Patrimônio total", "Classe de
     ativo", "Renda mensal de proventos") + " · <getClassLabel(asset_class)>" for a class goal.
   - Badges: "Alcançada" (success, `reached`), else "Fora do prazo" (warning, `on_track === false`)
     or "No prazo" (neutral, `on_track === true`); none when `on_track === null` (no date).
   - "⋯" menu: "Editar", "Remover" (danger).
   - Progress bar = `percent` (clamped 0–100, always emerald) + `formatPercent(min(percent, 999), 1)`
     ("45,3%").
   - Four figures (2×2 on the phone): "Atual" = `current`, "Faltam" = `remaining`, "Objetivo" =
     `target_amount` — **these three masked in privacy mode** — and either "Recebido em 12 meses" =
     `income_last_12_months` (income goal; not masked) or "Previsão" = `forecastText(goal)` with
     hint `forecastHint(goal)`.
   - Non-income goals: sentence "Aporte de <monthly_contribution>/mês a <annual_return_percent, 1
     decimal>% ao ano" (or ", sem rentabilidade") + ". Para chegar em <monthLabel(target_month)>:
     <required_contribution>/mês." when there is a date, not reached and `required_contribution` is
     not null; else ".". Not masked today.

`forecastText()`: "Alcançada" if reached; "—" for an income goal; "Sem previsão" when
`estimated_month` is null; else `shortMonthYear(estimated_month)` ("out/2028").
`forecastHint()`: "" for reached/income; "Informe um aporte mensal" when no estimate; else "em N
anos e M meses" (singular "1 ano", "1 mês"; parts omitted when 0; "" when 0 months).

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Create | "Nova meta" → sheet "Nova meta" → "Criar meta" | `POST /api/goals` `{name, kind, asset_class, target_amount, monthly_contribution, annual_return_percent, target_date}` | toast "Meta criada." | refused |
| Edit | "⋯" › "Editar" → sheet "Editar meta" → "Salvar" | `PATCH /api/goals/<id>` same full payload | toast "Meta atualizada." | refused |
| Remove | "⋯" › "Remover" | `DELETE /api/goals/<id>` (real delete, no guard) | confirmAction "Remover a meta "<nome>"?" / "Só o plano sai; nenhum lançamento muda." → toast "Meta removida." | refused |

Sheet: the description is the kind's hint (`KIND_HINTS`): NET_WORTH "Carteira de investimentos +
saldo das contas — o número do Início.", PORTFOLIO "Valor líquido da carteira de investimentos.",
ASSET_CLASS "Valor líquido de uma classe de ativo.", MONTHLY_INCOME "Média mensal dos proventos
líquidos recebidos nos últimos 12 meses.". Fields: segmented kind "Patrimônio | Carteira | Classe |
Renda" (default Patrimônio); "Nome" (required, ≤ 120, placeholder "Ex.: Primeiros 100 mil"); "Classe
de ativo" only for Classe (Ações, Fundos Imobiliários, Renda Fixa, Outros → `STOCKS|REIT|FIXED_INCOME|OTHER`,
default STOCKS); "Valor da meta" / for Renda "Renda mensal desejada" (required, ≥ 0,01); for non-income
kinds also "Aporte mensal" (hint "Quanto você pretende pôr por mês."), "Rentabilidade esperada ao ano
(%)" (−99…100, hint "Opcional. Sem ela, a previsão conta só os aportes."), "Quero chegar até" (date,
hint "Opcional. Mostra o aporte mensal necessário.").

`payloadFromForm()`: comma → dot; empty → `null`; `monthly_contribution` empty → 0; `asset_class` only
for ASSET_CLASS (else `null`); **hidden fields are still sent** — switching a dated goal to "Renda"
keeps sending its old `target_date`, `annual_return_percent` and contribution (harmless: the server
ignores them for MONTHLY_INCOME, but native should clear them).

Server refusals (400, unaccented): "Nome da meta …" (required, ≤ 120), "Tipo da meta …", "Escolha a
classe de ativo da meta.", "Valor da meta deve ser maior que zero." (and `parse_number` messages),
"Aporte mensal …", "Rentabilidade anual esperada …" (−99…100), "Data desejada …", "A data desejada
precisa ser depois deste mes."; 404 "Meta nao encontrada.".

Only a *changed* `target_date` must be after this month (fixed 2026-10-23): a goal whose month has
arrived still takes a rename or a new amount with its stored date sent back.

## Data
- `GET /api/goals` → array, key `['metas']` (`queryFn: goalsApi.list`). Item (`serialize_goal()`,
  `services/goals.py`): `id`, `name`, `kind`, `kind_label`, `asset_class`, `asset_class_label`
  (unaccented, unused), `target_amount`, `monthly_contribution`, `annual_return_percent` (null =
  none), `target_date`, `target_month`, `current`, `remaining`, `percent`, `reached`,
  `estimated_months`, `estimated_month`, `required_contribution`, `on_track` (true/false/null),
  `income_last_12_months` (income goals only).
- Values are computed on read: PORTFOLIO = `build_portfolio_snapshot().current_net_balance`;
  ASSET_CLASS = Σ positions' `net_value` of the class; NET_WORTH = portfolio + every account's
  balance in BRL (`account_balance_rows()`, archived and Corretora included, foreign accounts
  without a rate skipped); MONTHLY_INCOME = net proventos paid in (today − 365 d, today] / 12.
  Forecast: months to target with contribution at month end and the annual rate as an equivalent
  monthly rate, capped at 1 200 months; no contribution and no positive rate → no forecast.
- The read builds the portfolio snapshot, so it is as slow as Posição on a cold cache — keep the
  last copy on the phone and show it immediately.
- Invalidation: any write invalidates every query (including `['plano-do-mes', …]`, whose goal flags
  depend on goals); the sheet awaits `invalidateServerData()` before closing.

## Client rules
- `forecastText()`, `forecastHint()`, `shortMonthYear()`, `plural()` — inline, **no test**. Port
  with JVM tests (pure formatting; `shortMonthYear` uses pt-BR short month without the dot).
- `payloadFromForm()` / `formFromGoal()` — inline, no test; port, and clear hidden fields per kind.
- Badge choice (reached → on_track) — inline; port as a small function with tests.
- All money (current, remaining, forecast, required contribution) is **server only**; never port
  `months_to_reach()` / `required_contribution()`.

## States
- Loading: a panel with `ListSkeleton` (3 rows).
- Empty: the empty state above.
- Error: "Não foi possível carregar as metas." (query) or the write's server message in the alert;
  sheet errors stay inside the sheet ("Não foi possível salvar a meta.").
- Offline: persisted cache shows the cards (values as of the last read; label them as such);
  writes fail with "Sem conexão com o servidor. Esta ação só funciona conectado.".
- Privacy: Atual, Faltam, Objetivo masked; the contribution sentence and "Recebido em 12 meses" are
  not — consider masking them too (not a money rule).
- Light/dark: tokens; green badge only for "Alcançada", amber for "Fora do prazo".

## Conventions that apply
- "Allocation targets and goals are plans, like budgets" — `DELETE` is real with no guard; current
  values, gaps and the forecast are computed on read, never stored.
- "The monthly plan is a plan…" — goal flags in Orçamento are per goal, never summed; a goal edit
  changes them.
- "Money" — the client only formats; `rounded_money()` happens on the server.
- "The app is reais-only on screen" — NET_WORTH converts foreign accounts on the server; never show
  a currency.
- "Privacy mode" — use the private formatter for the sensitive figures.

## Native-only improvements
- Instant open from the cached list while the snapshot recomputes.
- A circular progress per goal; haptic on save.
- Optional widget/shortcut for one pinned goal (masked under privacy).

## Acceptance
- [ ] Creating "Primeiros 100 mil" (Patrimônio, 100.000, aporte 2.000, 8% a.a.) shows the toast, the
      card, a "Previsão" month and the hint "em N anos e M meses" — same values as the desktop.
- [ ] Adding a future date shows "No prazo"/"Fora do prazo" and the "Para chegar em …" sentence.
- [ ] An income goal shows "Recebido em 12 meses" and no forecast.
- [ ] A class goal shows " · Ações" (or the chosen class) in the subtitle.
- [ ] The eye masks Atual, Faltam, Objetivo.
- [ ] Removing asks for confirmation and the goal's flag disappears from Orçamento.
- [ ] Offline: cards visible; saving shows the offline message.

## Desktop
Keep; widen into a two-column grid (already `xl:grid-cols-2`) and add a projection chart per goal
(value over time at the planned contribution vs the target line), computed by a new server endpoint,
not in the browser. Fix the NET_WORTH hint: Início no longer shows the portfolio, so "o número do
Início" is wrong.
