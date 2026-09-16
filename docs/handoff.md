# Handoff

> Rolling handoff between working sessions. The **most recent session is at the top.**
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

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
