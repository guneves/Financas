# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 · Investir charts fast + fair index comparison

Cloud session, owner request: "updating every Investir chart (Posição, Rentabilidade) takes 5 s or
more — optimize, it must be very fast", and "the comparison of the indices with the portfolio is
unfair: over the observed period both must start at 0%". Docs read directly (no scout: the task was
given in full).

### Done
- **Measured first** on a synthetic portfolio (27 tickers, 59 fixed-income titles, 354 operations
  since 2021) with the network patched and 2–3 s of latency. Four causes: (a) the index closes
  (yfinance) blocked `/returns` every 15 min; (b) the history caches lived only in memory, so every
  deploy made the first chart wait for the whole download; (c) opening Investimentos runs the
  proventos sync, a POST, which invalidated the whole cache — every chart computed twice; (d) CPU:
  `accrual_factor_until()` looping the CDI per title × month, the per-asset TWR walking all days
  once per asset, date parsing per day.
- (a) `load_benchmarks()` reads `benchmark_closes` and refreshes in the background when closes were
  stored < 7 days ago (`stored_closes_are_recent()`); waits only without them.
- (b) `backend/history_store.py`: sections "daily" (Yahoo) and "bcb" (CDI/IPCA) in
  `HISTORY_CACHE_FILE` (`history_cache.json` next to the DB → `/data` on the server), written off
  the request, read once per process keeping each entry's age. In `.gitignore`/`.dockerignore`.
- (c) `apiFetch(..., { invalidate: false })` + `notifyMutation()`; the sync notifies only when
  `created + updated + removed > 0`.
- (d) `cdi_products()` (cumulative products, bisect), `group_monthly_returns()`, segment memo in
  `FixedIncomeCurve`, dates parsed once (`daily_group_values`, `iter_portfolio_months`). Outputs
  compared field by field with the old code: identical. 1A 312 → ~100 ms, 5A 900 → ~300 ms,
  Evolução 5A 300 → ~90 ms; first Rentabilidade after a restart with a 3 s network: ~150 ms.
- Fair comparison: `series[0]` is a base point (`base: true`) at 0% for the portfolio, the CDI and
  every index; months before the first operação leave the series; CDI and index totals,
  `percent_of_cdi` and `months_total` cover the compared months only; a late index starts at 0% at
  its own start. New `comparison` block in the response; the screen's hint and description say it.
- 11 new tests (`TestDiskCopy` ×5, two benchmark route tests for background/old closes, a portfolio
  started inside the window, two pure ones, the accrual equivalence); 3 tests updated for the base
  point. 1392 pytest, 122 node, `vite build`. Screenshots in Chromium (1A and 5A, 1280 px).

### Not done, and why
- Not measured against real yfinance/BCB or the owner's data (sandbox network is blocked) —
  owner check in `next-steps.md` ("Chart speed and the fair comparison").
- The first compared month counts the whole month for the index but the portfolio from the
  purchase day (only month-end index closes exist). In `next-steps.md`.
- No server-side cache of the computed response; ~0.3 s for 5A is pure CPU. In `next-steps.md`.
- Not tried on the phone.

### Learned
- `pkill -f serve.py` from the Bash tool kills the tool's own shell (the pattern is in its command
  line): exit 144. Stop a background server by its PID instead.
- The bench harness (patching `download_daily_history`, `fetch_bcb_series`,
  `download_monthly_history` in place, then `app.app.run`) is a good way to see the screens with
  benchmarks in this container, where every provider is blocked.
- cProfile only sees the request thread; the waits on executors show up as `threading.wait`.
  Wrapping functions with timers was what found the disk-load race.

### Carried from the Operações/040 session (2026-10-19), still open
- Amortization does not reduce the title's principal in Posição (modelling decision); no
  "agendar cupom" shortcut from Posição; Proventos' list filter opens on the current year; an
  edited coupon keeps its stored IR. All in `next-steps.md`. 040 not run on the owner's data; not
  tried on the phone.
- Throwaway server: `DATABASE_PATH=… DATABASE_BACKUP_DIR=… ATTACHMENTS_DIR=… ALLOW_SIGNUP=1
  AUTO_BACKUP_ON_BOOT=0 python -c "import app; app.app.run(port=5055)"` from `backend/`, after
  `vite build`; signup through `POST /api/auth/signup`. Venv: `python3 -m venv <scratchpad>/venv`
  + `pip install -r requirements-dev.txt`; `npm ci` in `frontend/`.

### Carried from the Extrato-delete session (2026-10-19), still open
- The aporte row itself is still refused by `DELETE /api/transactions/<id>` (409); the Contas menu
  deletes the operação. Proventos are not deletable from the Extrato.

### Carried from the 039 session (2026-10-19), still open
- 039 not run on the owner's data (owner check in `next-steps.md`); the Extrato still shows a
  bank → Corretora transfer as a transfer; imports/Aprovar have no transfer-to-Corretora target.
- Rows 039 could not convert keep the archived category's name and count as despesa/receita.
- If the plan-bugs branch merges after 039, keep the `INVESTMENT_SOURCE_TYPES` skip in
  `services/monthly_plan.py` and `budget_month_lines()`.

### Carried from the Orçamento redesign session (2026-10-19), still open
- Orçamento reads only `GET /api/monthly-plan` (query key `['plano-do-mes', month]`); `needs_income`
  is not auto-opened; a legacy conversion over 100% is not blocked (backend flags
  `PLAN_OVER_INCOME`). Privacy hides only Saldo do plano and Disponível por dia there.
- "Sem categoria" shows % and R$ only (optional item in `next-steps.md`); 038 still not run on the
  owner's data; not tried on the phone.
- `PanelHeader`'s `description` is `hidden sm:block`. Playwright: "Mês anterior" also matches
  "Copiar mês anterior" — `exact: true`.
- Screenshots: throwaway `DATABASE_PATH` + `ALLOW_SIGNUP=1`, signup through
  `app.app.test_client()`, `scripts/seed_three_years_mock.py <email>`; it writes
  `backend/backups/finance-pre-mock-*.db` — delete it. No `sqlite3` CLI — use Python.

### Carried from the 038 backend session (2026-10-19), still open
- Categories inherit with the plan; a category write in an inherited month first copies the plan
  and categories into it (`materialize_month()`), so an old month's budget id is 404 there once the
  month has its own copy. `DELETE /api/monthly-plan` takes the month's categories with it.
- `totals.remaining` on `/api/budgets` is the *categories'* leftover (Início's budget strip), not
  Saldo do plano.

### Carried from the account-strip session (2026-10-19), still open
- The strip fix (`scroll-px-4`) was not tried on the phone. Any other `snap-x` strip with side
  padding needs `scroll-px-N` too (`grep -rn "snap-x" frontend/src` found only that one).

### Carried from the owner's review session (2026-10-18 night, later), still open
- **Item 19 has no real capture behind it** — the parser convention asks for one. The rule only
  fires on "Nx de R$ …"; replace the hand-made test texts with a capture when one shows up.
- Stored dates without the zero are not rewritten; a one-off SQL check is in `next-steps.md`.
- The list `POST /api/cc-expenses` still takes the invoice month as sent; archived cards still have
  no list/unarchive (both in `next-steps.md`).
- The recurrence form refuses to save while its account is archived ("Conta esta arquivada") —
  intended: it is the nudge to pick another account.
- `"10,005"` in a CSV is 10.005 (Brazilian decimal comma), so the thousands rule is dot-only.
- The test DB is one per session: a test that needs "no user yet" cannot get it.
- `parseMoneyInput` stays positive-only; Ajustes › Contas wraps it (`parseBalanceInput`) for a
  negative initial balance, and that field has no `inputMode="decimal"` (the keypad has no minus).
- Making the default a Corretora is refused: the default is where a lançamento with no account
  lands, and a Corretora's balance is hidden from Início.
- Throwaway server for screenshots: the backup dir variable is `DATABASE_BACKUP_DIR` (not
  `BACKUP_DIR`); without it the boot backup lands in `backend/backups/` — delete it after.

### Carried from the card-history session (2026-10-18 late night), still open
- Stuck data is not repaired: an item already open in an autopay-paid invoice stays until the owner
  pays it or undoes the autopay. Undo sends the invoice to `cc_invoice_manual` (autopay never
  re-debits it). Migration **038** is now the latest (this session).
- Cartões has no paid-invoice view, so "Desfazer pagamento" is only in the Extrato.

### Carried from the calculator session (2026-10-18 night), still open
- IR on the simulated gain, prefill from the portfolio, a reverse "quanto aportar por mês" mode:
  product decisions, in `next-steps.md`.
- A command ending in `&` inside a `&&` chain runs in a subshell here; start a server with the
  tool's background mode, and check `/proc/<pid>/environ` of the **python** process before
  trusting which DB it uses. Playwright: a button near the bottom nav on a 390 px viewport needs
  `scrollIntoView({ block: 'center' })` before the click, or the menu opens off-target.

### Carried from the Aprovar session (2026-10-18 night), still open
- "Prompt 1's bank field" does not exist; the ambiguity rule reads `accounts.institution`
  (`issuer_of_institution()`), a `bank` column first if one lands. Cards have no bank field.
  Institution is now editable (Ajustes › Contas › Editar conta), but empty on existing accounts
  until the owner fills it, so for them the rule is still dormant.
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
