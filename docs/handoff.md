# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 · Orçamento redesigned around the income-based plan

Cloud session; read the docs directly (no scout). One PR, frontend only — no backend file, no
migration, no financial rule changed.

### Done
- `pages/Orcamento.jsx` rebuilt top to bottom: month picker → Saldo do plano (`SummaryPanel` lead,
  red when negative) with Disponível por dia, both masked in privacy mode → Renda do mês
  ("Recebido X de Y esperados"; Investir with "Falta investir" and "Como dividir" →
  `/investimentos/alocacao`; Gastar; Sem destino only when > 0; the flags) → Categorias do mês
  (% · R$, status, progress, live R$ beside the % in the add form and the inline edit, Sem
  categoria at the bottom, "Copiar mês anterior" kept).
- `components/MonthlyPlanPanel.jsx`: the Renda panel (default export, now takes `data`/`onEdit`)
  and `MonthlyPlanSheet` — Renda, Investir %, Gastar %, live "Investir R$ X · Gastar R$ Y · Sem
  destino Z%", save blocked over 100% or without income; the same sheet for the empty state
  ("Comece pelo plano do mês") and `needs_income` ("Informe a renda para converter o plano em
  porcentagens."), focused on Renda.
- `lib/monthlyPlan.js`: `percentOf()` (integer cents × millionths, ROUND_HALF_UP = backend's
  `percent_of()`), `formatPlanPercent()`, `unallocatedText()`, `incomeReceivedText()`,
  `livePlanTotals()`, `livePlanText()`, `categoryAmountPreview()`; 7 new node tests (115 total).
- `lib/dataApi.js` needed no change: `monthlyPlanApi` and `budgetsApi` already had every call.
- 1343 pytest, 115 node, `vite build`. Chromium at 390 px, light and dark, with a plan / no plan /
  `needs_income`, plus saving a conversion and the privacy toggle: right numbers, no console errors.
  Details in `done-tasks.md` ("Orçamento redesigned around the income-based plan").

### Not done, and why
- **Início still shows its own "Disponível por dia"** (computed on the client in `Dashboard.jsx`,
  with a no-plan fallback of balance − invoices). Out of scope here; **the next session removes it**
  (open item in `next-steps.md`, which also says to drop the matching rule from `CLAUDE.md`).
- Not tried on the phone; 038 still not run against the owner's real data.
- "Sem categoria" shows its % and R$ only, not spending outside the categories — the API has no such
  figure and computing it on the client would be a second rule (optional item in `next-steps.md`).

### Decisions worth knowing
- **The page reads only `GET /api/monthly-plan`** — its `categories.items` is the budget list, so
  one response feeds the whole screen. Same query key as Início (`['plano-do-mes', month]`).
- **`needs_income` is not auto-opened.** Like the empty state, it shows a card whose button opens
  the sheet with the text; popping a sheet on page load felt intrusive. Easy to flip if the owner
  wants it.
- **A legacy conversion over 100% is not blocked** in the sheet (only an explicit % sum is): the
  backend deliberately accepts it and flags `PLAN_OVER_INCOME` (see the 038 decisions in git
  history of this file). The live line turns red and says "Passa de 100% da renda em X%".
- Saldo, Disponível and the categories are hidden in a `needs_income` month (no R$ to show); the
  old R$ appear in the sheet's warning.
- Privacy mode hides only Saldo do plano and Disponível por dia, as asked; the plan's other R$
  stay visible (privacy is for balances and the portfolio, `lib/privacy.js`).

### Learned
- `PanelHeader`'s `description` is `hidden sm:block`: anything that must show on the phone goes in
  the panel body (the "Recebido … esperados" line does).
- Playwright: `getByRole('button', { name: 'Mês anterior' })` also matches "Copiar mês anterior";
  pass `exact: true`.
- Screenshots here: a throwaway `DATABASE_PATH` + `ALLOW_SIGNUP=1`, signup through
  `app.app.test_client()`, then `scripts/seed_three_years_mock.py <email>`; a `needs_income` month
  is a `monthly_plans` row with `income_amount`, `invest_percent`, `spend_percent` NULL (no
  `sqlite3` CLI in the container — use Python). The seed still writes
  `backend/backups/finance-pre-mock-*.db` — delete it.

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
