# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (night, later) · Owner's review: items 4–21 ("Média" and "Baixa")

Cloud session; read the docs directly (concrete list from the owner). Every item fixed, with a
test that fails without the fix; one PR.

### Done
- **Cards (4, 11, 13):** `PATCH /api/credit-cards/<id>` takes `name`, `due_day`, `closing_day`
  (each optional) besides the autopay; Ajustes › Cartões › "⋯" › Editar cartão. Closing day 29–31
  is clamped to the purchase month in `compute_invoice_start()`. `PATCH /api/cc-expenses/status`
  and `/invoice-status` **removed** (and from `dataApi.js`); the list `POST /api/cc-expenses`
  rounds, refuses `PAID` and gives each purchase a `client_id` (installments of one request share
  it; a repeated installment opens a new purchase).
- **Accounts (5, 6):** Ajustes › Contas › "⋯": Editar conta (name, institution, initial balance —
  negative allowed), Tornar padrão, Vincular/Desvincular da carteira, Arquivar; "Arquivadas (n)"
  with Reativar. The server always has one default (`ensure_default_account()` writes the mark),
  never a Corretora; the 409 no longer clears it first.
- **Lançamentos (7, 16, 17):** `keep_or_require_account()`; Extrato sends `account_id` only when
  changed and lists the archived own account as "(arquivada)"; `accountName` reads all accounts.
- **Import (8, 9, 12):** `INVESTMENT_PROCEED` out of the rules' reach; `type_says_debit()`;
  `THOUSANDS_ONLY` (dot only); `ofx_decimal_separator()`; a repeated FITID gets `:1`, `:2`.
- **Recurrence (10):** `recurring_archived_account()`; `/run` returns `blocked`, Recorrentes and
  Início show `blockedRecurringMessage()`.
- **Dates (14), categories (15), security (18), Aprovar (19), money field (20), conventions (21)**:
  see `CLAUDE.md` (new bullets) and `docs/done-tasks.md`.
- pytest **1305 passed**; `npm test` **108**; JVM `NotifyParsersTest` + `NotifyPairingTest` **52**
  (javac + junit 4.13.2 from `/opt/gradle-8.14.3/lib`, org.json/hamcrest jars from Maven Central);
  `vite build` clean. Clicked through in Chromium on a throwaway DB (390 px Ajustes, desktop
  Extrato): edit account, negative initial balance, Arquivadas › Reativar, edit card, edit a
  lançamento of an archived account. No page errors.

### Not done, and why
- **Item 19 has no real capture behind it** — the parser convention asks for one. The rule only
  fires on "Nx de R$ …"; replace the hand-made test texts with a capture when one shows up.
- Stored dates without the zero are not rewritten (a migration would touch every money table for
  a case the screens never produced); a one-off SQL check is in `next-steps.md`.
- The list `POST /api/cc-expenses` still takes the invoice month as sent; archived cards still have
  no list/unarchive (both in `next-steps.md`).
- The recurrence form refuses to save while its account is archived ("Conta esta arquivada") —
  intended: it is the nudge to pick another account.
- `native-level.txt` not bumped: the Java change is inside the parser, no JS↔Java API changed. The
  APK job will build a new APK because `frontend/android/` changed.

### Learned / decisions
- `"10,005"` in a CSV is 10.005 (Brazilian decimal comma), so the thousands rule is dot-only; the
  first try made it symmetric and `test_commit_rounds_money_half_up` caught it.
- The test DB is one per session: a test that needs "no user yet" cannot get it; the signup test
  signs the owner up first and then closes signup.
- `parseMoneyInput` stays positive-only; Ajustes › Contas wraps it (`parseBalanceInput`) for a
  negative initial balance, and that field has no `inputMode="decimal"` (the keypad has no minus).
- Making the default a Corretora is refused rather than allowed: the default is where a lançamento
  with no account lands, and a Corretora's balance is hidden from Início.

### Carried from the card-history session (2026-10-18 late night), still open
- Stuck data is not repaired: an item already open in an autopay-paid invoice stays until the owner
  pays it or undoes the autopay. Undo sends the invoice to `cc_invoice_manual` (autopay never
  re-debits it). Migration **037** is the latest; no migration in this session.
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
