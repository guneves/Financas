# CLAUDE.md

Guidance for Claude Code in this repository.

**This file is static.** A session never adds to it: a new or changed finance rule goes in
`docs/domain-rules.md` (the section of its area, with the owner's date), a test trick in the test's
docstring, a lesson in the handoff. Only the owner changes this file, or a session the owner asks to.

## Where things are (read on demand, never whole)

| File | Holds | Read |
|---|---|---|
| `docs/handoff.md` | the last session only | at the start, whole (it is short) |
| `docs/next-steps.md` | what to do next, priority order, ≤ ~60 lines | at the start, whole |
| `docs/domain-rules.md` | finance rules and owner decisions, by area | the section you touch |
| `docs/backlog.md` | bugs, limits, owner decisions, ideas; one line each | grep the area |
| `docs/done-tasks.md` | finished work, one line each | grep, to know whether something exists |
| `DEPLOY.md`, `mobile-docs/native/` | the server setup and runbook; the APK architecture and conventions | when the task is there |

`session-scout` (`.claude/agents/`) can brief a cold start (if `subagent_type` is "not found":
`general-purpose` with "Read .claude/agents/session-scout.md and follow it").

## Ending a session

1. Finished tasks leave `next-steps.md` for a one-line row in `done-tasks.md`; what was left undone stays in
   the plan, rewritten. Keep `next-steps.md` under ~60 lines: the least urgent go to `backlog.md`, one line each.
   Never let a doc grow into a log: history is in git.
2. **Replace** `docs/handoff.md` with this shape, **at most ~25 lines**, one line per bullet, no detail the
   commit or the code already says:
   ```
   ## Session — <date> · <topic>, branch <name>
   **Done:** what changed, where it was checked (server, tests).
   **Not done, and why:** the partial work, explicitly.
   **Next:** the first thing the next session should do.
   **Lessons:** only what would cost the next session time (skip if none).
   ```
3. Commit.

## What this is

A single-user personal finance manager used daily by the owner: accounts, cards and invoices,
budget and plan, investments (average cost, tax, proventos, quotes), fed by phone notifications and
Pluggy (Open Finance). Prefer what makes daily use better over prettier architecture.

**Stack:** React 18 + Vite + Tailwind (browser) · Kotlin + Compose (the APK, no WebView) · Flask 3 ·
SQLite with versioned migrations · hand-rolled HS256 JWT · yfinance/brapi/BCB/Tesouro/StatusInvest.

## Server and deploy

The home server is the only real backend; `backend\finance.db` on the PC is a stale dev copy full of
test users. Production is the Docker image `ghcr.io/guneves/financas-app`, deployed by
`.github/workflows/deploy.yml` on every push to `main` (tests → GHCR → Tailscale SSH → `docker compose
pull/up`); data in the `financas_data` volume. `DEPLOY.md` has setup, manual deploy and rollback.
Off the VPN, Funnel publishes only :8443 (Caddy → oauth2-proxy for browsers, `X-Device-Key` for the
APK; the app's JWT still applies, and a proxy 401 never clears it); 443 is tailnet-only.

## Testing on the server (the norm, owner 2026-11-26)

**A change is proven on the server, with the real data, not on a local backend or an emulator.**

- **Access:** `ssh -o BatchMode=yes guilherme@guilhermeserver`, then `cd /srv/apps/financas && sudo -n
  docker compose exec -T -w /app/backend app python ...`; logs with `sudo -n docker compose logs --since 1h app`.
- **Reading is free; writing needs the owner.** Open SQLite as `file:/data/finance.db?mode=ro`; never
  import `app`/`db`/`services` in an ad-hoc script (the import runs migrations). A script not in the
  image: pipe it in (`... exec -T app sh -c 'cat > /tmp/x.py' < local.py`), run with
  `-e PYTHONPATH=/app/backend`, `rm` it after. Anything that writes (a rebuild `--apply`, a fix-up) only
  when the owner says so. The owner's user is the one with real transactions; the others are tests.
  Window by a row's own date, never `auto_recorded_at` (the 2026-10-27 rebuild re-recorded a year).
- **Before merging a rule that changes recorded data:** replay it on a copy of the server's database
  (`sqlite3.connect('file:/data/finance.db?mode=ro').backup(...)` to `/tmp`, copy it to the scratchpad,
  `rm` the server copy), run the engine inside one transaction, diff, ROLLBACK.
- **After the push deploys:** check the change on the server (the endpoint, the logs, the read-only
  scripts in `backend/scripts/`, e.g. `check_identity.py --email X`) and say what the owner should look
  at on the phone. Report what was and wasn't checked there.
- Unit tests still run before every commit (CI runs them too). Backend: `cd backend;
  ..\.venv\Scripts\python.exe -m pytest` (~2700 tests; on this PC run the files in 4 chunks, one
  process OOMs). Frontend: `cd frontend; npm test`. APK: `cd frontend/android; ./gradlew.bat --offline
  testDebugUnitTest` with `JAVA_HOME` = Android Studio's `jbr`.

## Unit tests (backend)

Named for what they cover (`test_invoice_month.py`, `test_route_map.py` lists every route and its
`@token_required`, …); they run on a throwaway SQLite built by the real migrations.

- `conftest.py` sets the environment at import, before anything imports `db`/`app` (`config.py`
  reads it once; `app.py` runs `init_db()` at import). Different config goes there, not in a test. It
  blanks the providers (brapi, Pluggy, Tesouro, history cache), turns the threads off and sets
  `AUTO_RECORD_DEFAULT=0`, `REVIEW_AUTO_DAYS_DEFAULT=0`, `ALLOW_SIGNUP=1`; tests that need them on set
  them per user. Pluggy is faked with `open_finance.set_client(FakePluggy())` (`tests/open_finance_world.py`).
- **One clock**: `dates.local_now()`/`local_today()` (`test_architecture.py` refuses a bare
  `datetime.now()`/`date.today()`); freeze with `monkeypatch.setattr(dates, "now_source", ...)`. SQLite's
  `created_at` is never frozen.
- A test never imports `db`, `routes.*` or `services.*` at the top (fixture or `importlib` inside).
- **Patch where the name is read, not where it is defined** — a wrong target silently does nothing
  (e.g. `services.invoices` *and* `routes.cards` for `local_today`; both `services.prices` and
  `routes.investments` for `yf`). A name a test replaces on `services.inbox` (`notification_wanted`,
  `BANK_NOTIFICATIONS_DEFAULT`) must be read in `inbox.py`, not in the modules it re-exports.
- Fixtures: `client`, `user`, `other_user`, `auth`, `*_module`; shared setup in `tests/finance_world.py`.
- **Add tests for every financial rule you touch.** A frontend rule tested with node imports nothing
  from the browser, React or `lib/api.js`.

## Layout

```
backend/   app.py (blueprints, boot) · config.py (env, read once) · db.py (migrations, backups)
           money.py / dates.py / validators.py / auth.py · services/ (domain rules) · routes/ (one
           blueprint per area) · scripts/ (server tools) · tests/
database/migrations/   versioned, append-only, applied on boot
frontend/src/          pages/ · components/ (ui.jsx is the UI kit) · lib/ (pure rules have *.test.js)
frontend/android/      the APK, native Kotlin/Compose (read mobile-docs/native/ before touching it)
docs/                  handoff.md, next-steps.md, done-tasks.md, domain-rules.md
```

## Rules that hold everywhere

- **Money** rounds only through `rounded_money()` (never `round()`); request amounts go through
  `parse_money()`. **Dates** are 1900–2199, stored zero-padded, compared as text.
- **`user_id` on every table and every query.** **Migrations are append-only.** Destructive endpoints
  take a confirmation guard. Accounts, categories and cards are archived, never deleted.
- **Idempotency**: materialized rows carry `source_type` + `source_id` (unique index); "+ Novo"
  creations are idempotent by `client_id`.
- **The app is reais-only on screen** (the one exception: the Conta global screen, in US$).
- Text the user sees is Portuguese; `docs/` is English; comments/identifiers match the file.
- **Strict layering**: `config` ← `applog` ← `db` ← `validators`/`money`/`dates`/`auth` ← `services/*`
  ← `routes/*` ← `app`; a blueprint never imports another; a new blueprint goes in `app.py`'s list.
  `test_architecture.py` enforces it, plus no import cycles (never "fix" one with a function-level
  import) and a shrinking list of `_private` cross-module uses (`tests/architecture_private_uses.txt`).
- Pluggy is **GET only**: never `PATCH /items` (it spends the owner's monthly CPF quota).

## Frontend (web and APK)

- Pages use only `ui.jsx` pieces; tabs come from the URL; data via `useQuery`; `apiFetch` invalidates
  after every write. Success is `toast()`, errors `AlertMessage`, destructive confirms
  `confirmAction()` — never `window.confirm`/`prompt`/`alert`.
- **Privacy mode** via `usePrivateFormatter()` / `MetricCard sensitive` (`lib/privacy.js`).
- **Visual rules**: green/red/amber/sky only for gain/loss/warning/info; signed amounts via
  `formatSignedCurrency`; numeric cells `.num`; 44 px touch targets below `lg`; `inputMode` on numeric
  fields; big values in `FitValue`, never `truncate`; no `overflow-hidden` around sticky tables.
- **Theme**: only `zinc`, `emerald` (the one accent), `rose`, `amber`, `sky`, `white`, `brand` (CSS
  variables in `index.css`); dark mode swaps the variables — never `dark:` classes. Charts use the
  colors from `charts.jsx`. Font: Plus Jakarta Sans from `public/fonts`.
