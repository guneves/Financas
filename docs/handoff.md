# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 · Início's "Resumo do mês"; dismissible plan flags

Cloud session; read the docs directly (no scout — the task named the files). Frontend only — no
backend file, no migration, no financial rule changed. One PR for both tasks.

### Done
- **Início** (`pages/Dashboard.jsx`): the hero lost its month pills (it keeps Saldo em conta, the
  balance, the accounts; the strip is `mt-auto` so it sits at the bottom when the hero stretches on
  desktop). New `MonthSummary` card "Resumo do mês" in `DailyTile`'s slot: Resultado do mês,
  Entrou, Saiu, Investido (only with an aporte or resgate), and the net of other people (label by
  sign, value unsigned, link "Ver em A receber"). `DailyTile`, `MonthProgress`,
  `getDaysRemainingInMonth` and Início's `plano-do-mes` query are gone; the skeleton mirrors the
  new top row. CLAUDE.md's "Disponível por dia" convention now points to Orçamento and describes
  the card.
- **Plan flags** (`components/MonthlyPlanPanel.jsx`): an X ("Dispensar") on each; per device in
  `lib/planFlags.js` (localStorage `@financeMVP:planFlagsDismissed`, try/catch, same shape as
  `lib/attention.js`, reusing `addDismissed()`); the key rule `planFlagKey()` / `visibleFlags()` in
  `lib/monthlyPlan.js`, 2 new node tests (117). `AlertMessage` got an optional `dismissLabel`.
- 1343 pytest, 117 node, `vite build`. Chromium on the seed: Início 390/1440 px, light/dark,
  without and with a split expense, privacy on; Orçamento 390 px with SPEND_PACE dismissed and
  INVEST_PENDING still shown (survives a reload). No console errors.

### Not done, and why
- Not tried on the phone (open item in `next-steps.md`).
- The bell does not list plan flags (it never did); dismissing one only affects Orçamento.

### Decisions worth knowing
- **Resultado do mês is `income − |expense|`, not `currentMonth.net`.** The task defines it as
  "entrou menos saiu, só a sua parte"; `net` also subtracts aportes and adds others' money, and it
  stays the cash-flow chart's "Resultado". So the card and the chart's last point can differ.
- **The others row shows when the *net* is non-zero** (task wording); the old hero pill showed when
  either side was non-zero. A month where paid and received cancel exactly shows no row.
- **Investido can be negative** (more resgates than aportes) and prints "−R$ X"; the hint shows
  both sides.
- **The Gastar bar keeps its colour** after a pace/over flag is dismissed: dismissing hides the
  message, not the fact.
- The X keeps `AlertMessage`'s own small button (24 px) rather than a 44 px `IconButton`, so every
  alert in the app closes the same way; widen it in `ui.jsx` if it is hard to hit on the phone.

### Learned
- Only the edit sets sharing on a lançamento: `POST /api/transactions` ignores `share_*`
  (`parse_share()` is read only in the PATCH, `routes/transactions.py`). For a seeded shared
  expense, create it and then `PATCH /api/transactions/<id>` with `share_mode`,
  `share_others_amount`, `share_person`.
- The seed's current month has two flags (SPEND_PACE, INVEST_PENDING) — handy for dismiss tests.
  The month after has none, so "comes back next month" is covered by the node test only.
- Login token is `access_token` in the signup/login response; the localStorage auth is that JSON.

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
