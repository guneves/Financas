# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (late night) · Chart loading speed

Owner: "Optimize graphs, they seem to be a bit slow at times, investigate and fix, create a PR".
Cloud session; read the docs directly (single, concrete ask).

### Investigation
- Seeded a throwaway DB (`scripts/seed_three_years_mock.py`), faked the network at 1 s per call,
  and timed the chart endpoints. **Rentabilidade cold: 6.07 s; every period or class switch after
  that: ~4 s.** Compute was 40–250 ms; the rest was waiting on the network, for two reasons:
  1. `GET /api/investments/returns` made its fetches **one after another**: Yahoo daily closes,
     then BCB CDI for fixed income, then BCB CDI for the window, then BCB IPCA, then the index
     closes — each with its own 6 s timeout (worst case ~30 s).
  2. Every cache was keyed by the exact start date (and the ticker set), so 6M/1A/2A/Tudo or a
     class filter was a cache miss and a new download each time.
- Frontend: Playwright at 390 px with 4× CPU throttle — every chart page paints its first chart
  in < 1 s (Início ~2 s with 5 charts); a CPU profile shows Dashboard's own JS at ~7 ms, the rest
  is Recharts layout. Recharts is already its own lazy chunk. Nothing worth changing there.

### Done
- **Per-ticker daily-history cache with coverage** (`get_daily_history()`, `services/prices.py`):
  `_daily_history_cache[ticker] = {from, prices, splits, updated_at}`; a request starting on or
  after `from` is served sliced at its start (the same rows a download from that start returns,
  splits included); only missing tickers go to Yahoo, from `history_fetch_floor()` (day 1, 63
  months back — covers every chart window), so one download serves all periods and classes.
- **BCB series the same way** (`services/fixed_income.py`): `cdi_since()` / `ipca_since()` over
  `_index_history_cache["cdi" | "ipca"] = (instant, from, series)`; `index_history()` is built on
  them, and the benchmarks' IPCA now reads the same cache (`start_ipca_fetch()`; the old
  `fetch_ipca()` / `_ipca_cache` are gone).
- **Index closes** (`refresh_benchmark_closes()`): fetch from the floor, throttle key on it — one
  Yahoo trip per TTL for every period.
- **Parallel fetches** (`routes/investments.py`): `start_index_history()` / `wait_index_history()`
  with a deadline counted from the start; `load_history_inputs()` starts the fixed-income BCB
  fetch before the Yahoo download; the returns route starts the window CDI and `load_benchmarks()`
  (`_benchmarks_executor`) before `load_history_inputs()`; inside `load_benchmarks()` the IPCA runs
  during the closes fetch. `_index_history_executor` went from 1 to 2 workers.
- Result, same harness: **cold 6.07 s → 1.08 s; switches ~4 s → 36–87 ms; history 1 s → 14–34
  ms** after the first load. All 46 responses (6 periods × 4 classes × both endpoints) are
  identical to before except the benchmarks' `source` label, which says `"cache"` instead of
  `"yfinance"` when the closes were stored by an earlier period's fetch (not shown on screen).
- `tests/test_history_fetch.py` (11 tests): cache coverage, slicing, missing tickers, expiry,
  caller isolation, BCB/IPCA sharing, a narrower BCB fetch finishing last never shrinking the
  cache, one download across periods and classes via the routes, and a `threading.Barrier`
  proving prices and CDI are in flight at once. The two route tests fail on the old code (6
  downloads instead of 1; barrier broken). pytest **1234 passed**, node tests 94 passed.

### Not done, and why
- **Stale-while-revalidate.** Once the 15-min TTL expires, the next open pays one (now parallel)
  round trip. Past closes and CDI days never change and today's value comes from the stored quote
  (`position_value_today()`), so serving the stale cache while refreshing in the background would
  be safe — but it needs the same treatment in three places (daily history, BCB, index closes) to
  help, and a background refresh must never overwrite good data with an empty failed download.
  Left as an open item in `next-steps.md`.
- No in-flight dedupe: two cold requests at the same moment (e.g. the window CDI and the
  fixed-income CDI) both download. Parallel, so no latency cost; serializing them would add one.
  The BCB cache keeps the wider of the two (`_bcb_series_since()`), so it settles after one round.
- Not measured against the real yfinance/BCB (no outbound access to them here) nor on the phone.

### Learned / decided
- The `POST /api/investment-proceeds/sync` that investments screens fire takes 6 s here
  (StatusInvest unreachable); it is background and no chart waits on it.
- The bench harness (fake latency, response dump, Playwright render/profile) lived in the
  scratchpad; recreate from this description if needed: patch `services.prices.download_daily_history`,
  `services.fixed_income.fetch_bcb_series` (it returns **datetimes**) and
  `services.benchmarks.download_monthly_history`.

### Carried from the Aprovar session (2026-10-18 night), still open
- "Prompt 1's bank field" does not exist; the ambiguity rule reads `accounts.institution`
  (`issuer_of_institution()`), a `bank` column first if one lands. Cards have no bank field.
  Institution is editable only at account creation, so for existing accounts the rule is dormant.
- Migration **036** (`user_settings`) is claimed; if another branch adds a 036, whichever merges
  second renumbers before the server applies it.
- Not tried on the phone. Starting the app for screenshots: signup wants a username of 2+
  characters, and the auth goes in localStorage `@financeMVP:auth` (the signup body, JSON). Global
  Playwright is at `/opt/node22/lib/node_modules/playwright`.

### Carried from the five-bugs session (2026-10-18 evening), still open
- Owner checks in `next-steps.md` ("Bug fixes of 2026-10-18"): Cartões after 035, the next invoice
  per card, orphaned card categories, split shares, Início's categories by name, the 5xx outbox
  cap, the old list `POST /api/cc-expenses`.
- In a fresh cloud container: `python3 -m venv .venv && .venv/bin/pip install -r
  backend/requirements-dev.txt`, `npm ci` in `frontend/`. Importing `app` outside pytest writes a
  boot backup into `backend/backups/` (gitignored) — delete it.

### Carried from the phone layout session (2026-10-18), still open
- Other money fields are still `type="number"` (Metas, Orçamento, Recorrentes, Ajustes › Contas'
  initial balance, ShareFields, Extrato's min/max filter, the investment forms): the same
  `parseMoneyInput()` swap applies.
- Seen but left: Início's attention cards ~170 px each; "indisponível" benchmark cards take a full
  card; charts 286 px wide at 360 px.
- Driving the phone: throwaway `DATABASE_PATH` + `scripts/seed_three_years_mock.py`, `vite build` +
  `python app.py`, `adb reverse tcp:5000 tcp:5000`, DevTools over `adb forward tcp:9222
  localabstract:chrome_devtools_remote` (screenshot the viewport, not a clip beyond it). Git Bash
  needs `MSYS_NO_PATHCONV=1` for `/path` arguments.

### Carried from the Orçamento lines session, still open
- Not clicked through in a browser; lines are read-only (no deep link to a single lançamento).

### Carried from the 034 session (Aprovar × Recorrentes), still open
- Not clicked through. An occurrence `/run` already wrote is matched only at the exact amount; a
  recurrence's amount is not updated after a price change; a deleted approved lançamento does not
  reopen the occurrence.
- After the deploy: open A receber, Aprovar, Ajustes, Cartões and Recorrentes once to confirm
  029–035 ran. Owner walk-throughs: Aprovar × Recorrentes, card refund, Início's daily tile,
  sharing. Install the new APK, then one Pix between own accounts, one to someone else, one card
  purchase → check Aprovar.

### From the notification session (2026-10-17), still open
- Not tried end to end on the phone; Samsung Wallet's purchase text never captured (its parser is
  a guess), same for credit/debit "final", declined, estorno, boleto, BTG Investimentos.
- Mapping screen (Phase 6 step 5) and raw-text-to-inbox (step 6): not built, on purpose.
- `schema.sql` still lacks the 028 tables and 031's columns (032, 033 and 035 are in it).
- TWR: Tesouro mark-to-market, the 12-month window definition (owner to decide), AMER3 not added.
- `adb` is at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`; the installed app is the
  release build, so `run-as` can't read `financas_notify.db` — captures come from the owner's
  export.
- Learned from the capture: BTG puts the message in `android.infoText` and posts each purchase
  twice (24 ms apart, same `when`; `_repeated_posting()` handles it); BB's Pix is a group summary;
  Pix texts carry the counterparty's masked CPF (Itaú, BTG) or institution (BB); the phone's time
  zone is `America/Bahia`.

### Carried, still open
- Test APK from the PC (`/apk/financas-debug.apk`, `adb install -r`, capture, the adb command),
  then `adb uninstall br.financas.app.debug`.
- IR 2025 on the server (next-steps, "Investments check"); the first Ubuntu 26 workflow run after
  2026-10-19; Mobile Phase 5's last phone checks; the remaining self-update cases; Extrato →
  Investimentos and Proventos → Atualizar walk-through. Nothing enforces the native-level bump.

### Learned earlier, still true
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
- In PowerShell 5.1 a javac "deprecated API" note on stderr shows as an error; check the exit code
  from bash.
- Several Claude sessions share this tree: claim migration numbers by message before creating
  the file (030 collided once), stage explicit paths, one committer.
