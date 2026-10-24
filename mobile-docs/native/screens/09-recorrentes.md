# Recorrentes — native spec

| | |
|---|---|
| Migration order | 5 (see `../migration-order.md`) |
| Status | Built 2026-10-24 on `claude/practical-hamilton-e6nxfi` (native-level 7): `ui/recorrentes/` over `GET /api/recurring` and `/forecast?days=90` (the calendar stays on the server), Lançar pendentes (toast with `through`, the archived-account message from `HomeRules.blockedRecurringMessage`), Nova recorrência (comma amounts via `parseMoneyInput`, native date pickers, optional end date), Editar valor e conta (`rules/Recurring.kt`: `recurringEditPatch`/`recurringAccountOptions` ports), pause/resume, delete with the kept count; `frequencyLabel` moved to `lib/recurring.js` with node tests and ported; nothing masked (as today); waiting for the owner's phone check. Not built: swipe to pause, long-press, the overdue notification |
| React source | `frontend/src/pages/Recorrentes.jsx`, `components/ui.jsx` (`SummaryPanel`, `Collapsible`, `Menu`, `Badge`, `ListSkeleton`, `EmptyState`) |
| Route(s) | `/planejamento/recorrentes` (legacy `/recorrentes` redirects); tab "Recorrentes" of "Planejamento" |
| Endpoints | `GET /api/recurring`, `GET /api/recurring/forecast?days=90`, `POST /api/recurring`, `PATCH /api/recurring/<id>`, `DELETE /api/recurring/<id>`, `POST /api/recurring/run`, `GET /api/categories`, `GET /api/accounts` |
| Client rules | `lib/transactions.js` (`blockedRecurringMessage()`), inline in `Recorrentes.jsx` (`frequencyLabel()`, `FREQUENCY_LABELS`, `STATUS_LABELS`, pending sum); `lib/format.js` (`formatSignedCurrency()`, `formatDateBR()`, `getLocalDateString()`) |

## What it is for
Templates for money that repeats — rent, salary, subscriptions. The owner registers each once; when
an occurrence falls due it shows as pending, and "Lançar pendentes" writes the real lançamentos.
The page also projects the next 90 days of recurring cash. On the phone: a quick "launch what is
due" and a glance at what is coming; creating a template is occasional.

## What it shows
1. **Header**: title "Recorrentes", description "Aluguel, salário, mensalidade, assinatura: o molde
   fica aqui e o lançamento é gerado quando vence.", primary button "Lançar N pendente(s)" (N = sum
   of `items[].pending_count`) or "Lançar pendentes" when N = 0 (still enabled).
2. **Summary** (`SummaryPanel`), from `forecast.windows`:
   - Lead "Saldo previsto em 30 dias" = `windows['30'].net`, signed (`formatSignedCurrency`), tone
     `loss` when < 0; hint "Em 90 dias: <windows['90'].net signed>" (or "Recorrências ativas").
   - "Receitas previstas" = `windows['30'].income`, "Saídas previstas" = `windows['30'].expense`
     (hint "Próximos 30 dias"); "Pendentes" = N, hint "Venceram e não foram lançados" / "Tudo em dia"
     (muted when 0).
   - The windows sum every non-settled occurrence from the past-due ones up to today + 30/90 days,
     so overdue pending items are inside the 30-day figure. Not masked in privacy mode today.
3. **"Recorrências"** panel. Description: "Pausar interrompe a geração sem apagar o histórico: ao
   retomar, só o período pausado é pulado — o que já tinha vencido antes continua pendente. Excluir
   mantém os lançamentos já gerados."
   - Collapsible "Nova recorrência" (form, see Actions); intro line "O lançamento só nasce quando a
     data chega — nada é antecipado no extrato."
   - List in server order (`active DESC, next_run_date IS NULL, next_run_date, description`). Row:
     title `description || category` (grey when FINISHED); badge by `status` — `ACTIVE` "Ativa",
     `PAUSED` "Pausada", `FINISHED` "Encerrada" (all neutral); amber badge "N pendente(s)" when
     `pending_count > 0`. Line 2: "Receita|Despesa · <category> · <frequencyLabel> · <when>" where
     when = "pausada desde dd/mm/aaaa" (PAUSED with `paused_at`), "próxima em dd/mm/aaaa"
     (`next_run_date`) or "sem próxima data"; plus " · até dd/mm/aaaa" when `end_date`. Right: amount
     signed (+ emerald for INCOME, − neutral for EXPENSE) and a "⋯" menu.
   - Empty: "Nenhuma recorrência cadastrada" / "Cadastre o aluguel, o salário e as assinaturas uma
     vez — depois é só lançar os pendentes."
4. **"Próximos 90 dias"** panel ("Projeção das recorrências ativas. Nada aqui existe no extrato
   ainda."): `forecast.occurrences[]` in date order — date `dd/mm/aaaa`, `description || category`,
   amber badge "venceu" when `pending`, signed amount (INCOME emerald). Empty: "Nada previsto" /
   "Cadastre uma recorrência ativa para ver a projeção de caixa."

`frequencyLabel(item)`: interval 1 → "Mensal" / "Semanal" / "Anual"; otherwise "A cada N meses",
"A cada N semanas", "A cada N anos".

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Launch pending | header button | `POST /api/recurring/run` `{}` (server today; `through` and `id` exist but the screen sends neither) | toast "N lançamento(s) gerado(s) até dd/mm/aaaa." (success) or "Nada pendente: todos os lançamentos recorrentes já estão em dia." (info); if `blocked[]` non-empty, the error alert shows `blockedRecurringMessage(blocked)` | refused |
| Create | "Nova recorrência" → "Salvar" | `POST /api/recurring` `{description, amount, type, category_id, account_id \| null, frequency, interval_count, start_date, end_date \| null}` | none; form closes and resets | refused |
| Edit amount | "⋯" › "Editar valor" → inline field + ✓ ("Salvar valor") / ✕ | `PATCH /api/recurring/<id>` `{amount}` | none | refused |
| Pause / resume | "⋯" › "Pausar" / "Retomar" | `PATCH /api/recurring/<id>` `{active: false \| true}` | none | refused |
| Delete | "⋯" › "Excluir recorrência" (danger) | `DELETE /api/recurring/<id>` → `{deleted, kept_transactions}` | confirmAction "Excluir a recorrência "<nome>"?" / "Os lançamentos já gerados continuam no extrato." → toast "Recorrência excluída. N lançamento(s) já gerado(s) foram mantidos." or "Recorrência excluída." | refused |

Create form fields, in order: "Descrição" (required, placeholder "Aluguel"), "Valor" (decimal,
required, > 0), "Tipo" (Despesa/Receita, default Despesa), "Categoria" (required; active categories,
"Pai › Filho", not filtered by type), "Conta" (hint "Opcional — usa a conta padrão"; option "Conta
padrão" sends `null`, and the server then stores the *current* default account's id — the template is
pinned to it, it does not follow later default changes), "Frequência" (Mensal default / Semanal /
Anual), "A cada" (1–60, hint "1 = todo período"), "Primeira data" (default today, hint "Define o dia
de ancoragem"), "Até" (optional, hint "Opcional — sem data, não termina").

Server refusals (400 unless noted, unaccented): "Valor …" (must be > 0), "Tipo …" / "Frequencia …"
(choice), "Intervalo …" (integer 1–60), "Data inicial …", "Data final deve ser igual ou posterior a
data inicial.", category errors from `resolve_category()`, "Conta nao encontrada." / "Conta esta
arquivada.", "Informe ao menos um campo para atualizar.", 404 "Recorrencia nao encontrada.".

`blockedRecurringMessage()`: one → `A recorrência "<desc>" (<conta>) está numa conta arquivada e não
foi lançada. Edite a recorrência e escolha outra conta.`; several → `N recorrências estão em contas
arquivadas e não foram lançadas: "<a>" (<x>), "<b>" (<y>). Edite cada uma e escolha outra conta.`
"⋯" › "Editar valor e conta" (2026-10-23) edits the amount and the account inline: active accounts,
the archived current one shown disabled; the PATCH carries only what changed
(`recurringEditPatch()` in `lib/recurring.js`, tested). It is the way out of `blocked`.

## Data
- One query, key `['recorrentes']`, fetching four endpoints in parallel:
  - `GET /api/recurring` (default `include_inactive=1`) → `{items[], pending_count, today}`. Item
    (`serialize_recurring()`): `id`, `description`, `amount`, `type` (`INCOME|EXPENSE`), `category`,
    `category_id`, `account_id`, `frequency` (`WEEKLY|MONTHLY|YEARLY`), `interval_count`,
    `start_date`, `end_date`, `next_run_date`, `last_occurrence_date`, `active`, `paused_at`,
    `pause_gaps` (`[[start, end], …]`), `status` (`ACTIVE|PAUSED|FINISHED`), `pending_count`.
  - `GET /api/recurring/forecast?days=90` (`build_recurring_forecast()`) → `occurrences[]`
    (`recurring_id`, `date`, `type`, `amount`, `category`, `description`, `account_id`, `pending`),
    `pending_count`, `totals`, `windows` (`"30"`, `"60"`, `"90"` → `{income, expense, net}`).
  - `GET /api/categories` (active), `GET /api/accounts` (active) — form selects.
- Início reads `GET /api/recurring` under `['inicio', 'recorrencias']` for its "Precisa de atenção"
  card and also calls `/run` from there (`pages/Dashboard.jsx`).
- Invalidation: any write invalidates every query; the screen awaits `invalidateServerData()`.

## Client rules
- `blockedRecurringMessage()` — `lib/transactions.js`, tested in `lib/transactions.test.js`
  ("blockedRecurringMessage: a recorrencia numa conta arquivada"). **Port** (text only).
- `frequencyLabel()` + label maps — inline in `Recorrentes.jsx`, **no test**. Port with a JVM test.
- Pending total = Σ `pending_count` — inline here; the same sum is `pendingRecurringCount()` in
  `lib/attentionRules.js` (tested). Reuse that port. Note `GET /api/recurring` already returns the
  top-level `pending_count`, so native can just read it.
- The calendar itself (next date, pause gaps, revival, settlements) is **server only**
  (`services/recurring.py`); native must never compute occurrences.

## States
- Loading: `ListSkeleton` (5 rows) in the list; the summary has no skeleton and shows "R$ 0,00" until loaded (native should skeleton it).
- Empty: list and forecast empty states above.
- Error: "Não foi possível carregar os lançamentos recorrentes."; write errors in the top alert with
  the server text, fallbacks "Não foi possível criar a recorrência.", "…gerar os lançamentos.",
  "…atualizar a recorrência.", "…atualizar o valor.", "…excluir a recorrência.".
- Offline: persisted cache shows list and forecast; every action fails with "Sem conexão com o
  servidor. Esta ação só funciona conectado." (`/run` is deliberately not queued).
- Privacy: nothing masked today (forecast values are cash projections; decide with the owner
  whether the lead should mask — not a money rule).
- Light/dark: tokens; emerald only for income amounts, amber for pending/venceu, rose for negative net.

## Conventions that apply
- "A recurrence is a template, not money" — `/run` writes `RECURRING_TRANSACTION` rows with
  `source_id = '<id>:<AAAA-MM-DD>'`; pressing twice is a no-op; deleting keeps the lançamentos;
  pause skips only its own window (`pause_gaps`).
- "An edit keeps the row's own account even when archived" — a recurrence whose account is archived
  does not post: `/run` lists it in `blocked`.
- "Aprovar settles a recurrence's occurrence" — settled dates are not pending, not in the forecast,
  and `/run` skips them; the screen just reads `pending_count` / `occurrences`.
- "Transfers are one row, not two" — recurrences are only INCOME/EXPENSE; no transfer template.
- "Dates and months are stored zero-padded" — send `AAAA-MM-DD`.

## Native-only improvements
- Swipe a row: pause/resume; long-press: menu. Haptic on "Lançar".
- A notification or Início chip "N recorrências vencidas" deep-linking here (the data is already in
  `GET /api/recurring.pending_count`).
- Date pickers native; amount field with the shared `parseMoneyInput()` port (the React form uses
  `type="number"`, which rejects a comma on some keyboards).

## Acceptance
- [ ] With a due rent, the header reads "Lançar 1 pendente(s)"; pressing it shows the success toast
      and the row's badge disappears; pressing again shows "Nada pendente…".
- [ ] A recurrence on an archived account produces the blocked message and no lançamento.
- [ ] Pausing shows "Pausada · pausada desde <hoje>"; resuming later skips only the paused window.
- [ ] Editing the amount changes future occurrences only (past lançamentos unchanged in Extrato).
- [ ] Deleting shows how many lançamentos were kept; they remain in Extrato.
- [ ] Forecast lists the next 90 days with "venceu" on overdue ones; totals match the desktop.
- [ ] Offline: list visible, actions show the offline message.

## Desktop
Keep, widen into a table (descrição, tipo, categoria, conta, frequência, próxima, valor, status) with
inline editing of every field (not just amount — including the account, which closes the `blocked`
gap), and the 90-day forecast as a side panel or a cumulative cash chart.
