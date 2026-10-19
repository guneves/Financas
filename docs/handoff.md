# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 · The monthly plan starts from income (backend + 038)

Cloud session; read the docs directly. One PR. **The screen redesign is the next session** — this
one is the backend, the migration and only the frontend changes needed to keep saving and reading.

### Done
- Migration **038**: `monthly_plans.invest_percent` / `spend_percent`, `budgets.planned_percent`
  (TEXT, six decimals), with the conversion of plans that had income and of the categories of
  their months. Details and the API shape in `done-tasks.md` ("The monthly plan starts from
  income (038)").
- `services/budgets.py` (new): the budget rules moved out of `routes/budgets.py`, plus the plan
  row of a month, `plan_figures()`, category inheritance (`category_source_month()`,
  `materialize_month()`) and the legacy conversion. `services/monthly_plan.py` builds the full
  response on top of it; `routes/budgets.py` only validates and serves.
- Interim frontend: `MonthlyPlanPanel` (Renda R$ + Investir % + Gastar %; "Informar renda" for a
  `needs_income` plan, blank % = convert), Orçamento ("% do Gastar", `?month=` on edit/delete/
  lines, "Saldo do plano" = `totals.plan_balance`), Início (`plan_balance`, null-safe), the
  `NEEDS_INCOME` status label, the `CATEGORIES_OVER_SPEND` flag text.
- Seed (`seed_three_years_mock.py`): one plan a year back (income, 20% / 65%) and seven category
  percentages that the later months inherit; it now also wipes `monthly_plans`.
- 1343 pytest (21 new in `test_monthly_plan_income.py`, `test_budgets.py` rewritten for
  inheritance), 108 node, `vite build`. Seed run on a throwaway DB and Orçamento driven in
  Chromium (save the plan, edit a category %, open Início): right R$, no console errors.

### Not done, and why
- **No redesign** of Orçamento / the plan (asked for the next session). The interim screen is
  functional, not designed: it still lists the plan panel, the summary and the categories
  separately. The open items are in `next-steps.md` ("Plano do mês a partir da renda — the screen").
- Not tried on the phone, and 038 not run against the owner's real data (the cloud has none).
- Início's "Disponível por dia" still divides on the client; the server returns
  `daily_available` with the same rule.

### Decisions worth knowing
- **Categories inherit with the plan.** The brief asked for "category percentages included" in
  inheritance. Before 038 a month with no budget rows showed none; now it shows the categories of
  the latest month ≤ it with a plan row or budget rows. To keep that sane, any category write in
  an inherited month first copies the inherited plan and categories into it, a PUT that creates a
  month's plan copies the categories in, and `DELETE /api/monthly-plan` takes the month's
  categories with it. So a budget id from an earlier month is valid in a later one only while that
  month still inherits; once it has its own copy, `?month=` with the old id is 404 (the screen
  always uses the ids of the month it shows).
- **"Saldo do plano" is one number** (`plan_balance` = Gastar R$ − the month's spent, all
  categories). `totals.remaining` on `/api/budgets` was kept as the *categories'* leftover because
  Início's budget strip compares categories against their own plan; it is no longer labelled
  "Saldo do plano" anywhere.
- **The PUT converts more than "that month".** Old categories without % are converted in every
  month the saved plan governs (its month up to the next plan row), since those months now take
  their Gastar from it. A category whose month has Gastar 0 stays `needs_income` (no base).
- **Over 100% after conversion** (an old plan whose spend + invest passed the income, or old
  categories summing past the spend) is kept and flagged, not clipped; a PATCH may lower a
  category while the month is still over 100% but not raise it.
- Old R$ columns are NOT NULL, so new rows write 0 there; nothing reads them once a % exists.

### Learned
- The Playwright trap from the calculator session hit again: the "⋯" menu near the bottom nav at
  390 px needs `scrollIntoView({ block: 'center' })` before the click.
- The seed writes `backend/backups/finance-pre-mock-*.db` even with `DATABASE_BACKUP_DIR` set —
  delete it after.

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
