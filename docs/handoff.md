# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (late night) · Card history: three money bugs

Owner's review, three "Alta" items, each reproduced before fixing: (1) deleting an installment
purchase deleted the paid installments; (2) a purchase dated into an invoice autopay had already
paid stayed open forever and later showed overdue (Aprovar too); (3) deleting a card cascaded its
purchases and stranded its payments, and a payment could not be undone. Cloud session; read the
docs directly (concrete ask).

### Done
- Migration **037** (`037_card_archive_and_payment_undo.sql`): `credit_cards.archived_at`,
  `cc_expenses.paid_by`, table `cc_invoice_manual`. Only new columns/table.
- (1) `DELETE /api/cc-expenses` refuses (409) any `PAID` id; Cartões fetches the candidates first,
  deletes only the `OPEN` ones and says how many paid ones stay.
- (2) `first_unpaid_invoice()` / `purchase_invoice_start()` in `services/invoices.py` (the refund's
  old loop, now shared): purchases (`/purchases`, Aprovar's `create_entry()`) and refunds start at
  the first invoice from their date that is not paid.
- (3) Card `DELETE`: 409 with open items, archive with history, real delete when empty. Archived
  cards are filtered from the GET, Aprovar's card list/hints/ambiguity, and refused by
  `require_active_card()`. Undo: `DELETE /api/cc-expenses/payments/<id>` +
  Extrato's "⋯" › Desfazer pagamento (desktop row and phone list).
- `test_card_history.py` (19 tests); `test_attachments.py`'s card-delete test now asserts the
  refusal; `test_route_map.py` has the new route. pytest **1253 passed**; `npm test` 106 passed;
  `vite build` clean. Clicked through in Chromium at 390 px on a throwaway DB: the late purchase
  went to 11/2026, the delete confirmation counted the paid installment, Desfazer reopened 10/2026
  and returned R$ 100 to the balance, Ajustes showed the 409 for a card with open items. No page
  errors.

### Not done, and why
- **Existing stuck data is not repaired**: an item already open in an autopay-paid invoice stays
  until the owner pays it or undoes the autopay (listed in `next-steps.md`). A migration cannot tell
  a late purchase from an item reopened by hand on purpose.
- No archived-cards list or unarchive; Cartões has no paid-invoice view, so the undo is only in the
  Extrato. Both are product calls, in `next-steps.md`.
- The old list `POST /api/cc-expenses` still takes the invoice month as sent.
- `native-level.txt` not bumped: no Java touched.

### Learned / decisions
- Undo sends the invoice to manual payment (`cc_invoice_manual`) instead of letting autopay re-debit
  it at the next read: otherwise "Desfazer" on an overdue autopay invoice would be undone by the
  very next GET. The confirmation says so.
- A payment from before 037 has no `paid_by` on its items; its undo falls back to "the `PAID` items
  of its invoice with no `paid_by`", and only when no item points at it — so undoing an old autopay
  never reopens what a newer manual payment paid.
- A card is refused deletion while it has open items rather than archived with them: an archived
  card leaves the pickers and Ajustes, so open invoices on it would be unreachable (autopay
  included).
- Migration **037** is claimed (036 is the Aprovar settings one).
- Backend error texts stay ASCII ("cartao", "Lancamentos > Cartoes"), like the rest of the API.

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
