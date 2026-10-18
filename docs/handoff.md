# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (night) · Aprovar: ambiguous target, "Trocar", "Sempre perguntar"

Owner, three numbered asks under Aprovar: (1) don't save a choice when the case is ambiguous — no
card final and more than one active account/card at that bank — and ask every time, resting on
"Prompt 1's bank field", falling back to today's behaviour for "Sem banco" accounts; (2) always
show the target with a quick "Trocar"; (3) optional Ajustes switch "Sempre perguntar a
conta/cartão", off by default. Cloud session; read the docs directly (the ask was complete).

### Done
1. **Ambiguous target** — `ambiguous_target()` / `bank_of_row()` in `services/inbox.py`, checked in
   `resolve_detection` (no hint, no guess), `remember_choice` (nothing saved, also a transfer's
   side keys), `apply_hint_to_pending`, and serialized as `item.ambiguous` (the screen hides
   "Lembrar a escolha" and says why under the picker). Details in `done-tasks.md`.
2. **Target line + "Trocar"** — `TargetLine` in `Aprovar.jsx` ("→ BB Corrente"), replacing the
   target badge; "Trocar" opens the same pickers as a guess, closes after a choice.
   `targetText()` / `targetFields()` moved into `lib/inboxRules.js` (tested).
3. **"Sempre perguntar a conta/cartão"** — Ajustes › Aprovar (`AprovarSection.jsx`),
   `GET/PATCH /api/inbox/settings`, migration **036** `user_settings`. With it on,
   `confirm_targets()` adds every target the owner didn't pick on the item, so nothing is "ready".
- Checks: pytest **1208 passed** (`-o addopts=""`); the 13 new tests all fail with the service
  and route changes stashed. node tests **94 passed**; `vite build` clean. Screenshotted the built
  app at 390 px against a throwaway DB (an ambiguous Itaú Pix, a remembered BB item, Trocar open,
  the Ajustes switch).

### Not done, and why
- **"Prompt 1's bank field" does not exist in this repo** (only `main` and this branch on the
  remote). I used what exists: `accounts.institution`, mapped to itau/bb/btg by
  `issuer_of_institution()`; a `bank` column, if Prompt 1 adds one, is read first. Cards have no
  bank field, so they keep today's behaviour. Institution is editable only at account creation, so
  for existing accounts the rule is dormant until the bank field lands.
- Name matching ("Itaú corrente") deliberately doesn't count as a bank: the owner said the rule
  rests on the bank field.
- Not tried on the phone.

### Learned / decided
- **Migration 036 is claimed here.** If Prompt 1's branch also adds a 036, whichever merges second
  renumbers before the server applies it.
- Ambiguity is computed from the hint key at each use, never stored, so adding or archiving an
  account changes waiting items on the next read.
- "Always ask" doesn't block approving: approving one item is the confirmation, the way a guess
  already worked. Picking the same value in a `<select>` fires no change, so a confirm button would
  have needed a new PATCH semantic for nothing.
- `/api/inbox/settings` takes GET and PATCH both, so a PATCH never falls to `/api/inbox/<item_id>`.
- Starting the app for screenshots: signup wants a username of 2+ characters, and the auth goes in
  localStorage `@financeMVP:auth` (the signup body, JSON). Global Playwright is at
  `/opt/node22/lib/node_modules/playwright`.

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
