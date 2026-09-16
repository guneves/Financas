# Handoff

> Rolling handoff between working sessions. The **most recent session is at the top.**
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

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
