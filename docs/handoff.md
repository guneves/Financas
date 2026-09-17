# Handoff

> Rolling handoff between working sessions. The **most recent session is at the top.**
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-16 (later) · Phase 3 opened: monthly budget, categories screen, format.js

### Where things stand

**§3.3 (monthly budget) is complete**, and with it Phase 3 is underway. The categories management
screen that the last session flagged as "the most obvious loose end" is also done, and §4.3's
`formatCurrency` duplication is closed. 205 tests → **249**. Migration count 8 → **9**. Recurring
entries (§3.4) is the next Phase 3 item.

There is also a second subagent now: **`session-scout`**, which reads the three state documents at
the *start* of a session and hands back a one-page briefing. `CLAUDE.md` describes both agents as one
routine that brackets a session — scout opens it, guard closes it.

### What was done

**1. Monthly budget by category — migration `009_budgets.sql`**

`budgets` (id, user_id, category_id, month `YYYY-MM`, planned_amount, rollover, note), with
`UNIQUE(user_id, category_id, month)`. Endpoints: `GET /api/budgets?month=`,
`POST /api/budgets`, `PATCH/DELETE /api/budgets/<id>`, `POST /api/budgets/copy`.

`GET` returns the month already computed — per category: planned, carryover, available, spent,
remaining, percent, and a `OK | WARNING (≥80%) | OVER` status — plus totals and an `over_count`.

Three design decisions worth knowing:

- **The realized amount is never stored.** It is read from `transactions` each time: a category whose
  `kind` is `INCOME` realizes income, every other kind realizes expense, and `TRANSFER` is excluded —
  the same rule §3.1 imposed on everything that sums `transactions`. Lançamentos carrying only the
  category *text* (free text, or older than migration 008) are matched by name, so historical months
  still add up.
- **A subcategory without its own budget counts against its parent's.** Budgeting "Alimentação" has
  to cover "Alimentação › Delivery" or the planned figure never reconciles with the statement. Give
  the subcategory its own budget and it stops counting against the parent — two tests pin both halves.
- **`rollover` carries only the leftover, floored at zero, and only one month back.** Computed on
  read. Storing it would mean recalculating a chain of months every time a retroactive lançamento
  lands; and letting an overrun become next month's debt makes the plan punitive rather than useful.

`DELETE /api/budgets/<id>` is a **real delete with no confirmation guard**, unlike accounts and
categories. That is deliberate and is the one place the "destructive endpoints take a guard"
convention does not apply: a budget is a plan, and removing one destroys no lançamento.
`test_delete_removes_the_budget_and_keeps_the_transactions` pins it.

**2. `Orcamento.jsx` — new page, two tabs**

- *Orçamento*: four metric cards, month navigation (‹ setembro de 2026 ›), a bar per category over
  planned × spent × remaining with the status colour, inline edit of the planned value, an "Acumula"
  toggle for rollover, and "Copiar mês anterior".
- *Categorias*: **this closes §3.2's loose end.** Create (with a parent), rename, change kind,
  archive, reactivate. Until now the API could do five things and the UI could only list them.

Registered at `/orcamento` and added to the sidebar between Movimentações and Carteira.

**3. `frontend/src/lib/format.js` — §4.3's duplication, closed**

`formatCurrency`, `formatUnitCurrency`, `formatPercent`, `parseLocalDate`, `formatDateBR`,
`getLocalDateString`, `monthKey`, `monthLabel`, `shiftMonth`. Six files that had their own copies now
import them.

**Two local copies survive on purpose.** `Carteira.jsx` and `Transactions.jsx` default their
`getLocalDateString` to a `getNow()` clock hook rather than to `new Date()`, and
`Transactions.jsx`'s `formatDateBR` returns `''` where the shared one returns `'-'`. Collapsing those
would be a behaviour change dressed up as a cleanup. `npm run build` passes.

**4. Tests: 205 → 249**

`tests/test_budgets.py` (44): creation and the seven invalid payloads, actuals from transactions,
months not bleeding into each other, free-text categories counted by name, transfers excluded,
income categories realizing income, the subcategory rollup in both directions, the OK→WARNING→OVER
walk, totals and `over_count`, rollover (carries, floors at zero, crosses the year, no-op without a
previous month), partial PATCH, copy (default source month, skip vs. overwrite, same-month refusal),
and five isolation tests.

**5. The `session-scout` subagent**

`.claude/agents/session-scout.md`. Reads `docs/handoff.md`, `docs/next-steps.md`, the git log, the
migration directory and the test suite, and returns ≤500 words: where things stand, what is genuinely
open, the next task **and the concrete files it touches**, the traps from the handoff that apply to
*that* task, and any drift between the docs and the repository. The arithmetic is the point — this
handoff file grows by a full entry per session and most of it is history the current task does not
need.

### The audit caught a real bug — read this one

`finance-guard` (via the fallback below) found that **`rollover` was transporting money that had
already been spent.** The screen computed a parent category's `spent` *including* its unbudgeted
subcategories, but `budget_carryover()` computed the previous month's leftover from the parent's own
spending only. Alimentação budgeted 900, R$300 spent on it and R$200 on an unbudgeted
"Delivery": August correctly showed 400 left, and September's carry-over came out as **600**.

Fixed by giving both callers one definition of "realized": `budget_month_spent()`
(`backend/app.py`), which the screen, the carry-over, `POST` and `PATCH` all call.
`test_rollover_uses_the_same_spent_the_screen_shows` pins it — verified by reverting the fix and
watching it fail with exactly `600 != 400`.

The lesson generalizes: two code paths that both answer "how much was spent" will drift, and the one
the user does not see on screen is the one that drifts silently.

Also from the audit, and applied: a deterministic tiebreaker when two subcategories share a name
(`ORDER BY parent_id IS NOT NULL, created_at, id`), and `window.confirm` on the two destructive
actions in `Orcamento.jsx` — every other page in the project already prompts.

### Things to know

- **`.claude/agents/*.md` are still not discoverable.** `Agent(subagent_type="finance-guard")`
  returned *"Agent type not found"* again this session, listing only the built-in types — and the
  definition has been committed since the session before. So this is **not** the "written this
  session, visible next session" problem the last handoff guessed at; discovery of project agent
  files simply is not happening in this environment. The audit was run through the documented
  fallback instead (`general-purpose` told to read `.claude/agents/finance-guard.md` and follow it),
  which works and gives the same report. `CLAUDE.md` now documents that fallback for both agents.
  Try the real `subagent_type` first next session; if it still fails, don't spend time on it.
- **A rounding test of mine was wrong, and the code was right.** I asserted that two lançamentos of
  `0.125` should show `0.25` of spending. They show `0.26`: `POST /api/transactions` already rounds
  each lançamento half-up on the way in (`0.125 → 0.13`), and the budget sums the *stored* values,
  not the typed ones. The test now states that explicitly. Worth remembering before "fixing" a
  similar off-by-a-cent elsewhere — with banker's rounding it would have been `0.24`.
- **Month arithmetic lives in two places now** and must agree: `shift_month()` in `backend/app.py`
  and `shiftMonth()` in `frontend/src/lib/format.js`. Both are integer arithmetic on
  `year * 12 + month`, which is why the year rollover is not a special case.
- **Credit card purchases do not count as budget spending, and that is now a recorded open
  decision** (§3.3 of the plan lists the three ways out). Spending on the card lives in `cc_expenses`
  until the invoice is settled, and then enters as one lançamento in a `Pagamento Fatura <cartão>`
  category rather than under what was actually bought. For a card-heavy household the budget
  under-reports all month and then over-reports one category. The page says so in its subtitle rather
  than leaving it to be discovered. **Decide this before §3.4** — recurring entries raise the same
  question about where spending lives.
- **The real `backend/finance.db` has not been migrated yet.** Migration 009 will apply on the next
  boot, after the automatic backup. It only creates a table and two indexes — no backfill, no table
  rebuild, nothing to verify on a copy first.

### What was NOT done, and why

- **Recurring entries (§3.4) and statement search (§3.7)** — the rest of Phase 3. Deliberate: §3.3
  plus 44 tests plus the categories screen was the session's scope.
- **The credit-card question above was recorded, not answered.** Answering it well means choosing
  between three designs and probably a migration; doing that badly at the end of a session would put
  wrong numbers in front of the person using this daily.
- **The Dashboard does not show the budget.** A "orçamento do mês" strip on the Dashboard is the
  obvious next small win — the data is one `GET /api/budgets` away and the page already has the card
  layout for it. Left out to keep the diff to one new page.
- **A budget cannot be created from the Movimentações page**, where you notice you need one. Minor.
- **No frontend tests.** There still is no frontend test harness at all; `Orcamento.jsx` was verified
  by `npm run build` and by reading, like every page before it.
- **`backend/app.py` is now ~5,344 lines.** The §4.1 split got further away again. The budget block
  (helpers + four routes, `backend/app.py:2675-3050`) is self-contained and, together with the
  accounts/categories block, would make a sensible first blueprint to extract.

### Recommended next steps, in order

1. **A budget strip on the Dashboard.** Small, visible, and it is what makes the budget actually get
   looked at daily.
2. **Recurring entries (§3.4).** Rent, salary, subscriptions — the largest remaining source of manual
   typing, and a 30/60/90-day forecast falls out of it for free.
3. **Statement search and filters (§3.7).** By period, category, account, amount range, free text.
4. If you want a quick win between two of those: extract the first blueprint from `app.py` (§4.1),
   starting with accounts + categories + budgets.

---

## Session — 2026-09-16 · Phase 2 closed: bank accounts, transfers, categories, editing

### Where things stand

**Phase 2 is complete.** All three items — §3.1 bank accounts, §3.2 categories as a table, §3.7 edit a
transaction — landed together, because they are all migrations against `transactions` and doing them
in one pass meant rebuilding that table once instead of twice. 127 tests → **205**. Phase 3 (monthly
budget, recurring entries, statement filters) is next.

There is also now a **`finance-guard` subagent** (`.claude/agents/finance-guard.md`) and a step in
`CLAUDE.md`'s end-of-session ritual that says to run it before committing.

### What was done

**1. Bank accounts and transfers — migration `007_accounts_and_transfers.sql`**

`accounts` table, `transactions.account_id` backfilled to an auto-created "Conta Principal" per user,
and `TRANSFER` as a real transaction type. Endpoints: `GET/POST /api/accounts`,
`PATCH/DELETE /api/accounts/<id>`, `POST /api/transfers`.

**The design decision worth knowing: a transfer is ONE row, not two.** `type='TRANSFER'` leaves
`account_id` and arrives at `transfer_account_id`. Two sibling rows would have to be kept in sync on
every edit and delete, and every query would have to know how to pair them. One row of a distinct
type means the consolidated balance ignores transfers for free.

The cost of that choice: **anything summing `transactions` must skip `type = 'TRANSFER'`**, or moving
money between your own accounts reads as an expense. Two callers did exactly that and were fixed
(`Dashboard.jsx:~130`, `Transactions.jsx` in `fetchData`). If you add a third summation anywhere,
that is the thing to remember. The `CHECK` constraints on the table keep the *columns* coherent
(a TRANSFER must have both accounts and they must differ; a non-TRANSFER must have no destination)
but they cannot protect a naive `SUM`.

**The migration rebuilds `transactions`**, because SQLite cannot `ALTER` a `CHECK` constraint and
`type` had to start accepting `TRANSFER`. That means `DROP TABLE` — which takes the table's indexes
with it. All four existing indexes are recreated at the bottom of the migration, plus two new ones.
If you ever rebuild a table again, check the index list; it is the easy thing to lose silently.

**2. Categories as a table — migration `008_categories_table.sql`**

`categories` (with `parent_id` for one level of subcategory, and `kind` extended to `INCOME|EXPENSE|BOTH`),
`transactions.category_id`, and the 10 original categories seeded per user. Endpoints:
`GET/POST /api/categories`, `PATCH/DELETE /api/categories/<id>`.

**`transactions.category` (the text) stays and is still the value.** `category_id` is a link
alongside it, not a replacement. The text is what the Dashboard groups on and what survives a
category being archived — so `PATCH /api/categories/<id>` rewrites the linked lançamentos' text in
the same transaction when the name changes, or the grouping would split in two. Free-text categories
are still accepted on `POST /api/transactions` and come back with `category_id: null`; rejecting them
would break `backend/scripts/`.

The backfill promotes any category that only ever existed as free text into a real row. On the real
database that picked up **"Freelance", "Salário", "Salario" (both spellings), "Mercado" and
"Pagamento Fatura do Mês"** — 25 category rows across the two users. "Salario" and "Salário" existing
side by side is real duplication in the data, not a migration bug; it is now visible and mergeable in
the UI, which it was not before.

**3. Edit a transaction — `PATCH /api/transactions/<id>`**

Partial: it only touches fields present in the payload. Inline editing in the statement table on the
Movimentações page (pencil → edit in place → check/cancel). Two refusals: a lançamento mirrored from
an investment (`source_type = 'INVESTMENT_TRANSACTION'`) returns 409, the same rule `DELETE` already
had; and a plain lançamento cannot be converted into a transfer or back, in either direction.

**4. Frontend**

- `Movimentações`: a "Contas" panel with per-account balance and an inline create form, a
  "Transferência" panel, an account selector on the lançamento form, categories fetched from
  `/api/categories` instead of the hardcoded array, and a Conta column plus inline editing in the
  statement.
- `Dashboard`: a "Saldo por conta" panel below the metric cards.
- `CATEGORY_OPTIONS` survives in `Transactions.jsx` **as a first-render fallback only**, used until
  `/api/categories` answers. It is no longer the source of truth.

**5. Tests: 127 → 205**

| File | Tests | What it pins |
|---|---|---|
| `test_accounts_and_transfers.py` | 31 | Default account on signup, CRUD, archiving rules, transfer arithmetic, `user_id` isolation |
| `test_categories.py` | 23 | Seeding, subcategory depth, rename propagation to lançamentos, archiving, isolation |
| `test_transaction_edit.py` | 24 | Partial PATCH, rounding, the two refusals, balance effects of moving/retyping a lançamento |

The transfer arithmetic test is the one that matters most:
`test_transfer_moves_money_without_changing_the_consolidated_total`.

**6. The `finance-guard` subagent**

`.claude/agents/finance-guard.md` — a read-only auditor that reads the diff and checks `user_id`
scoping, `rounded_money()` vs bare `round()`, migrations staying append-only (and a rebuilt table
getting its indexes back), destructive-endpoint guards, test coverage for touched financial rules,
and the Portuguese/English split. `CLAUDE.md` now has a section describing it and a line in the
end-of-session checklist saying to run it before committing.

### Things to know

- **The agent file could not be exercised this session.** Claude Code discovers `.claude/agents/*.md`
  at startup, so `Agent(subagent_type="finance-guard")` returned *"Agent type not found"* right after
  the file was written. Its checklist was run by hand instead (that is how the readback in
  `POST /api/transfers` got its missing `user_id` filter). **Next session should run it for real
  once**, early, to confirm the definition works before relying on it.
- **The audit flagged pre-existing `round()` calls that are correct.** `backend/app.py` rounds share
  quantities to 6 places, `amount_per_unit` to 8, and yield percentages to 2–4. Those are not
  currency and the `rounded_money()` rule does not apply to them. The guard's own definition now
  warns about this; do not "fix" them.
- **The real `backend/finance.db` has NOT been migrated yet.** Migrations 007 and 008 will apply on
  the next boot, after the automatic backup runs. They were verified on an exact copy: 49
  transactions in, 49 out, zero rows with a null `account_id` or `category_id`, and both
  `PRAGMA foreign_key_check` and `PRAGMA integrity_check` clean. Nothing needs doing — just expect
  the first `.\start.ps1` to take a moment longer and to write a backup first.
- **Two users exist in the real database**, so the backfill created two "Conta Principal" rows and two
  copies of the 10 seed categories. That is correct — `UNIQUE(user_id, name)` is per user.
- **`UNIQUE(user_id, name, parent_id)` does not constrain root categories**, because SQLite treats two
  NULLs as distinct. Migration 008 adds a partial unique index
  (`... WHERE parent_id IS NULL`) to cover that. Worth remembering for any future nullable-column
  uniqueness.

### What was NOT done, and why

- **Nothing from Phase 3** (monthly budget §3.3, recurring entries §3.4, statement search §3.7).
  Deliberate — Phase 2 plus its 78 tests was the session's scope, and §3.3 wants the categories work
  to settle first anyway.
- **No categories management screen.** The API is complete (create, rename, re-parent, archive) but
  the UI only *reads* the list. You can pick a category and a subcategory when entering a lançamento;
  you cannot yet create one without calling the API. This is the most obvious loose end.
- **`formatCurrency`/`formatDateBR` are still duplicated** across five and three files (§4.3). Still
  a ~30-minute mechanical win and still not taken.
- **Transfers cannot be edited across the origin/destination pair in the UI.** The API accepts
  `transfer_account_id` on PATCH and there is a test for it, but the inline editor only exposes the
  origin account. Small gap, deliberate — the row layout was already dense.
- **`backend/app.py` grew to ~4,950 lines.** The §4.1 split did not get smaller this session; it got
  bigger. The accounts/categories/transfers routes are a clean, self-contained block and would make a
  reasonable first blueprint to extract.

### Recommended next steps, in order

1. **Run `finance-guard` once** to confirm the agent definition loads and behaves. Two minutes, and
   everything after this depends on it being real.
2. **A categories screen** (§3.2's loose end). Small, and it closes the gap between an API that can do
   five things and a UI that can do one.
3. **Phase 3 — monthly budget (§3.3).** `budgets` table keyed by `(category_id, month)`, which is
   only now possible because categories have stable ids. This is the biggest remaining win for daily
   use.
4. Then **recurring entries (§3.4)** and **statement search/filters (§3.7)**.
5. If you want a quick win between two of those: extract `frontend/src/lib/format.js` (§4.3).

---

## Session — 2026-09-15 (later) · Phase 1 closed + invoice rule moved server-side

### Where things stand

**Phase 1 is complete.** The two items the previous session recommended are both done: automatic
backup on boot, and the credit card invoice-month rule moved out of the frontend. 88 tests → **127**.
Phase 2 (bank accounts) is now the next thing.

### What was done

**1. Automatic backup on boot with retention — Phase 1's last item**

`run_startup_backup()` runs immediately after `init_db()` (`backend/app.py`, bottom of file). It:

- skips entirely when `AUTO_BACKUP_ON_BOOT` is off, or when there is no database file yet;
- skips when a backup already ran inside `AUTO_BACKUP_MIN_INTERVAL_HOURS` (default **12**) — restarting
  the app a dozen times in a day must not fill the backup directory;
- otherwise writes the usual `.db` + `.sql` + `.zip` trio via the existing `create_database_backup()`;
- then calls `prune_database_backups()`, which deletes anything past `BACKUP_RETENTION_DAYS` (default **7**).

`POST /api/database/backups` prunes too, and now returns a `pruned` list. New env vars are documented
in `backend/.env.example`. Verified against the real database: first boot wrote
`backups/finance-20260915-225038.*`; second boot correctly did nothing.

**2. ⚠️ I deleted six old backup files while testing this — read this before trusting retention**

Running the real app to verify the feature pruned `backend/backups/` down to the fresh backup. Six
files from July 2026 went, and **three of them were hand-named milestones**:
`finance-before-normalized-investments-20260702-234230.db`,
`finance-before-investment-cash-links-20260702-235107.db`, and
`finance-before-realized-results-20260703-000733.db`. They were not in git (`backend/backups/` is
gitignored) and `os.remove` does not use the Recycle Bin, so they are **gone**.

Nothing live was lost — a complete backup of the current `finance.db` was written moments earlier, and
the database itself was never touched. What was lost is three pre-migration snapshots from July.

The cause was my matching rule: I pruned on the prefix `finance-`, which swallowed `finance-before-*`.
**Fixed:** retention now matches `BACKUP_FILE_PATTERN = ^finance-\d{8}-\d{6}\.(db|sql|zip)$` — only the
timestamped files the app generates itself. Any hand-named backup is permanently out of the rotation,
and `test_prune_never_touches_a_hand_named_milestone_backup` pins that. If you ever want a snapshot to
survive retention, give it a name (`finance-before-<thing>-*.db`) and it will.

**3. The invoice-month rule moved from React to Flask**

This was the previous session's #2 recommendation, and the reason axis 3 could not be fully tested.
New in `backend/app.py`:

| Function | What it does |
|---|---|
| `default_closing_day(due_day)` | The `due_day - 7` fallback, wrapping to the previous month |
| `compute_invoice_start(purchase_date, due_day, closing_day)` | Which invoice a purchase lands in |
| `add_invoice_months(month, year, n)` | Month arithmetic with year rollover |
| `split_installments(total, count)` | Cent-exact split; remainder to the first installments |
| `build_installment_rows(purchase, card)` | The rows for one purchase |

Exposed as **`POST /api/cc-expenses/purchases`**, which takes the *purchase* (`total_amount`,
`installments`) rather than pre-computed rows, looks the card's `closing_day`/`due_day` up itself, and
inserts one `cc_expenses` row per installment. The old `POST /api/cc-expenses` is untouched — it still
takes explicit `invoice_month`/`invoice_year`, and its tests still pass.

The behaviour is a faithful port of the JS, including the odd branch: when `closing_day >= due_day`
the cycle is already displaced, so *every* purchase moves at least one month forward (and two if it is
on or after the closing day). I kept it rather than "fixing" it — changing it would silently reassign
existing invoices, and it is the rule the data was entered under. If it is wrong, it should be changed
deliberately, as its own task, with a data migration.

Frontend (`Carteira.jsx`): `getInvoiceStart`, `splitInstallments` and `addMonths` are gone; both the
purchase form and the demo-seed path call `ccExpensesApi.createPurchase()`. The demo seed now
deduplicates per *purchase* (`isSamePurchase`, on card + description + date + category) instead of per
installment, because the server decides the installments. `npm run build` passes.

**4. Tests: 88 → 127**

- `tests/test_invoice_month.py` (22) — the rule itself: before/on/after closing, closing-after-due,
  December→January rollover, the `due_day - 7` fallback, cent-exact splits, plus the endpoint end to
  end (installment rows, year rollover, another user's card, auth, seven invalid payloads).
- `tests/test_backups.py` (17) — retention boundaries, the milestone-name exclusion, boot behaviour
  (creates / skips when recent / skips when disabled / skips with no database), endpoint pruning.
- `tests/conftest.py` sets `AUTO_BACKUP_ON_BOOT=0` so importing `app` in tests does not back up as a
  side effect; `test_backups.py` re-enables it with monkeypatch where it means to.

### Things to know

- **Don't use pytest's `tmp_path` in this environment.** Its base directory
  (`%TEMP%\pytest-of-<user>`) raised `PermissionError: [WinError 5]` on every test that requested it.
  `test_backups.py` uses a `test_dir` fixture built with `tempfile.mkdtemp(dir=...)` next to the test
  database instead. Anything needing a scratch directory should copy that.
- The three backup config values read the environment **at import time** into module globals, so tests
  override them with `monkeypatch.setattr(app_module, ...)`, not by setting env vars mid-run.

### What was NOT done, and why

- **Nothing from Phase 2.** Deliberate: the two recommended items plus their tests were the session's
  scope, and starting a migration with backfill on the remaining budget would have left the schema
  half-changed.
- **`Dashboard.jsx` still derives its own "next invoice"** (`Dashboard.jsx:173,269-281`). It is not the
  rollover rule though — it only picks the nearest `invoice_month`/`invoice_year` among stored rows, so
  there is no duplicated rule left. Worth folding into a shared helper eventually, not urgent.
- **`formatCurrency`/`formatDateBR` are still duplicated** across five and three files (§4.3).

### Recommended next steps, in order

1. **Phase 2 — bank accounts (§3.1).** The `accounts` table, `transactions.account_id` backfilled to an
   auto-created "Primary" account, and `TRANSFER` as its own type. This is the largest remaining gap
   between the app and daily use, and the test suite now makes the migration safe.
2. **Categories as a table (§3.2)**, then **edit a transaction (§3.7)** — both small next to §3.1.
3. If you want a quick win first: extract `frontend/src/lib/format.js` (§4.3). Mechanical, ~30 minutes.

---

## Session — 2026-09-15 · Phase 0 (cleanup) + most of Phase 1 (safety net)

### Where things stand

Phase 0 is **complete**. Phase 1 is **complete except automatic backup**. The project went from
0 to 88 backend tests, and from a two-terminal startup to one command.

### What was done

**1. Phase 0 housekeeping — all items closed**

Most of the file-level cleanup (test databases, loose logs, `venv/`, `frontend/dist/`) had already
landed in commit `7e17371`; this session verified that and closed the three items that remained:

- **`backend/.env` had no `JWT_SECRET` at all.** The app was silently running on the
  `dev-secret-change-me` default (`backend/app.py:56`). It now has a 48-byte random secret. The file
  also still carried three dead `SUPABASE_*` keys from the pre-Flask stack — removed.
  ⚠️ **This invalidated existing sessions. Log in again.**
- **Seed scripts moved** to `backend/scripts/` with a `README.md`. Their `BASE_DIR` was walked up one
  level so `DATABASE_PATH` still resolves to `backend/` rather than to `backend/scripts/`.
- **`CATTLE` stays** — decided, with the reasoning written into `docs/next-steps.md` §2. Short version:
  commit `7f9de03` removed the *screen*, not the asset class, which is still wired end to end
  (tax rate, mortality-rate adjustment, launch modal, labels). The `CHECK` constraints that mention it
  are correct, not stale.

**2. Bug found and fixed: `backend/.env.example` could not boot the app**

It shipped `DATABASE_MIGRATIONS_DIR=../database/migrations`. That value is resolved against the
**project** root, not `backend/` (`backend/app.py:48-51`), so it pointed one directory *above* the repo:

```
RuntimeError: Diretorio de migrations nao encontrado:
C:\Users\User\Documents\Financas\../database/migrations
```

The built-in default is correct, which is why this was never hit — but anyone copying `.env.example`
to `.env` (which `start.ps1` now does automatically) would have been stopped cold. Fixed in both files.
Found by actually launching the app, not by reading it.

**3. Phase 1 — 88 backend tests, in `backend/tests/`**

| File | Tests | Axis |
|---|---|---|
| `test_tax_rules.py` | 27 | Regressive fixed-income brackets, realized rates, `rounded_money` half-up |
| `test_user_isolation.py` | 22 | `user_id` scoping on reads and writes; auth required; tampered tokens |
| `test_credit_card_invoices.py` | 16 | Invoice settlement state machine, installments, payload validation |
| `test_fifo.py` | 14 | FIFO lot consumption — partial, exact, spanning, full exit, unmatched excess |
| `test_investment_cash_link.py` | 9 | Buy → expense, sell → income, delete → cash entry removed, destructive guards |

All 88 pass in about 5 seconds. They run against a throwaway SQLite file built by the **real**
migrations, so the schema under test is the schema that ships.

**4. Phase 1 — `start.ps1`**

One command instead of two terminals. Starts Flask and Vite as jobs, waits for `/api/health` and for
Vite to answer, opens the browser, streams both logs, and stops both on Ctrl+C. Creates `backend/.env`
from the example if missing, and runs `npm install` if `node_modules` is absent.

```powershell
.\start.ps1              # start both
.\start.ps1 -Tests       # run the test suite instead
.\start.ps1 -NoBrowser   # start without opening the browser
```

Verified end to end: `/api/health` returned `200 {"status":"ok","journal_mode":"wal"}` and Vite
returned `200`.

**5. Supporting files**

- `backend/pytest.ini` — testpaths, strict markers, warning filters.
- `backend/requirements-dev.txt` — pins `pytest==9.1.1` on top of `requirements.txt`.
- `docs/next-steps.md` — §2 rewritten as done, §4.2 rewritten with the coverage table, §4.4 and the
  Phase 0/1 entries updated.

### What was NOT done, and why

- **Automatic backup on boot with 7-day retention** — the one Phase 1 item still open. It was left
  deliberately: it is a change to `app.py`'s boot path, and this session's remaining budget was better
  spent proving the test harness works than half-landing a boot-path change. It is small and
  self-contained — `create_database_backup()` already exists at `backend/app.py:253`; it needs a call
  at startup plus retention pruning.
- **The credit card rollover rule is still untested** — and this is worth understanding before
  trusting the "axis 3 covered" line. Which invoice a purchase lands in (closing day, month rollover)
  is computed in the **frontend** (`frontend/src/pages/Carteira.jsx:190`), not the backend. The
  backend stores whatever `invoice_month`/`invoice_year` it is handed. So no backend test can cover
  it. See the recommendation below.

### Recommended next steps, in order

1. **Automatic backup on boot** (finishes Phase 1). Small, and the safety net is not really a safety
   net until the data is backed up too.
2. **Move the invoice-month computation from `Carteira.jsx` into the backend.** This is the highest
   value item not currently on the plan. It is a financial rule sitting in a React component where it
   cannot be tested and cannot be reused by the Dashboard, which currently re-derives its own version
   of the same idea (`Dashboard.jsx:173,269-278`). Moving it server-side makes axis 3 fully testable
   and removes a duplicated rule.
3. **Then Phase 2** — bank accounts (§3.1) → categories as a table (§3.2) → edit transaction (§3.7).
   The tests now exist to make those migrations safe, which was the whole point of Phase 1.

### Things to know before touching the tests

`app.py` reads its configuration and calls `init_db()` **at import time**. `backend/tests/conftest.py`
therefore sets `DATABASE_PATH`, `DATABASE_MIGRATIONS_DIR`, `DATABASE_BACKUP_DIR` and `JWT_SECRET` in
`os.environ` *before* importing the module. `load_dotenv()` does not override variables that are
already set, which is what keeps the real `backend/finance.db` untouched — verified: its mtime did
not change across the whole session.

Fixtures: `client` (Flask test client), `user` and `other_user` (signed-up users with
`["headers"]` ready to pass as `headers=`), and `auth` (shorthand for `user["headers"]`).

Two tests are deliberately written to accept a range of status codes
(`assert response.status_code in (400, 403, 404)`) because the codebase is not consistent about
which one it returns for "not yours". That inconsistency is real and worth standardizing — §4.3 of
`next-steps.md` already flags error-message inconsistency as debt.
