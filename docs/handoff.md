# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 (night) · Saving and editing operações without waiting

Cloud session, owner request (Portuguese): saving an operação in Investir takes too long after the
click, and so does editing one; optimize both and test other areas for bottlenecks. Scout not
used (handoff read directly; the task was narrow).

### Done
- **Measured first.** Throwaway DB, Flask test client, network faked (daily closes, CDI/IPCA):
  350 operações over 5 years (and 1500), plus `seed_three_years_mock.py` for the banking side.
  On the server a POST was 61 ms and a PATCH 67 ms, every GET under 25 ms on the 3-year mock,
  history ~90 ms and returns ~230 ms. So the wait was not the write itself but what the screen
  waited for after it:
  - Registrar operação (buy) awaited `POST /update-prices` (yfinance + BCB with its 30 s timeout
    and retry + Tesouro) and then `await onSaved()` = a full refetch of every open query;
  - every write invalidated everything, `update-prices` invalidated everything again, and the
    screen's `invalidateServerData()` a third time — TanStack's default `cancelRefetch` restarted
    the in-flight refetches each time, while the server finished the cancelled ones anyway (one
    gunicorn process, 8 threads, one GIL): the portfolio, history and Rentabilidade computed up to
    three times per save, competing with the next edit's PATCH;
  - every write and every portfolio GET rewrote `investment_positions` and
    `investment_realized_results` whole (write lock on each read the save triggered).
- **Frontend.** The sheet closes as soon as the POST answers; the buy's quote refresh runs behind
  (`refreshQuotes()` in `lib/dataApi.js`: `invalidate: false`, refreshes only when
  `updated_count` > 0), and Operações' edit and the "Atualizar cotações" button go through it too.
  `invalidateServerData()` now joins running refetches (`cancelRefetch: false`); the write
  listener keeps cancelling (a refetch started before the write may be stale). `changesPositions()`
  moved to `lib/proceedsRules.js` (tested) and excludes `update-prices` / `price-by-asset`, so a
  quote refresh no longer schedules a proventos sync.
- **Backend.** Writes and the portfolio/update-prices reads no longer rebuild
  `investment_positions` (its own GET still does; no screen calls it). `replace_realized_results()`
  compares with the stored rows and writes only on a difference (ids are deterministic,
  `realized:<movement>`). `gzip_responses.py`: gzip for API JSON ≥ 1 KB when `Accept-Encoding`
  allows (`/api/cc-expenses` was 664 KB and `/api/transactions` 490 KB on the 3-year mock).
- After: POST 22 ms, PATCH 24 ms on 350 operações (81 / 100 ms on 1500).
- Tests: `test_write_speed.py` (7), one node test; 1466 pytest, 138 node, `vite build`.

### Not done, and why
- Not measured on the home server or the phone, nor against real yfinance/BCB (blocked here).
  Owner check in `next-steps.md`.
- Static frontend files are still served uncompressed (`send_file` is skipped by design);
  Rentabilidade's daily loop still scales with open positions × days. Both in `next-steps.md`.

### Learned
- **Never name a backend module after a stdlib one.** The first version was `compression.py`;
  Python 3.14 (CI and the image) has a stdlib `compression` package that `gzip`/`zipfile` import,
  so the module shadowed it and the deploy of PR #24 failed in test collection (this container
  ran 3.13). Renamed `gzip_responses.py`; the suite now also passes under 3.14 here
  (`uv python install 3.14`).
- `queryClient.invalidateQueries()` defaults to `cancelRefetch: true`: calling it twice in a row
  aborts the first round in the browser but not on the server. Await with `cancelRefetch: false`.
- The werkzeug test client sends no `Accept-Encoding`, so the existing tests see plain JSON; a
  test that wants gzip sends the header.
- Profiling harness: env as in `conftest.py`, `services.prices.yf = None`, patch
  `services.prices.download_daily_history` and `services.fixed_income.fetch_bcb_series` with
  synthetic series — without the BCB patch the request time is the proxy's 403, not CPU.

### Carried from the BCB/Tesouro gov_http session (2026-10-19), still open
- The BCB failure's root cause was never observed (this container is refused api.bcb.gov.br and
  tesourotransparente.gov.br); if Ajustes › Integrações still shows an error after the deploy,
  its detail names the cause. Tesouro values not checked against the real price file (BTG
  reference: IPCA+ 2045 0,85 títulos líq. R$ 1.144,07 / bruto R$ 1.188,36; Renda+ 2065 42,79
  títulos líq. R$ 8.881,46 / bruto R$ 9.240,47).

### Carried from the Tesouro marked-to-market session (2026-10-19), still open
- Renda+/Educa+ early-sale custody modelled as the regular 0.20% (sources disagree); BTG's líquido
  is the check. A redemption of a merged title points to purchases (`related_id`); a position
  merged from >1 purchase has id `tesouro:<first id>`. `Menu` closes on scroll in Playwright.

### Carried from the asset-categories session (2026-10-19), still open
- No new DB class (Alocação by class, targets, goals, Rentabilidade's filter still 4 classes);
  old Tesouro titles typed as CDB stay in Renda fixa until edited — and so get no market price.
  The Proventos filter's "Ativo" is a select. Not tried on the phone.
- A button inside `Field` (a `<label>`) gives the click back to the input: a combobox option must
  `preventDefault()`. Signup returns `access_token`.

### Carried from the chart-speed session (2026-10-19), still open
- Chart speed and the fair comparison not measured against real yfinance/BCB or the owner's data;
  the first compared month counts the whole month for the index; no server cache of the computed
  response. All in `next-steps.md`. `pkill -f` from the Bash tool kills its own shell — stop a
  server by PID.

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
- TWR: the 12-month window definition (owner to decide), AMER3 not added.
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
