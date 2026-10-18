# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (evening) · Five bugs from the owner's review

Owner: "Fix every one of these and create a pr when done" — a numbered list of five bugs, each
already confirmed: the transfer 500 against Aprovar, Início/bell looking at next month's invoice,
categories matched by name, the rename that only touched lançamentos, identical card purchases
merged. Cloud session (no phone, no browser); read the docs directly instead of session-scout,
since the task list came complete.

### Done
1. **Transfer vs Aprovar** — `absorb_created()` called `_absorb()` with an extra `"transfer"`
   argument (`services/inbox_decisions.py`), so `POST /api/transfers` matching a pending TRANSFER
   item raised `TypeError`, rolled back and answered 500. Removed; test in `test_inbox.py`.
2. **Next invoice per card** — `nextInvoices()` / `nearestOpenInvoice()` / `isPastDue()` in
   `lib/attentionRules.js`, used by Início (tile, "Próximas faturas" panel and chart, "Pagar
   fatura"), the bell (`lib/attention.js`) and Cartões (the invoice it opens and pays; "Em atraso"
   only after the due day — it said so on the due day itself). "Disponível por dia" without a plan
   = balance − each card's next invoice − any overdue one ("Saldo menos as faturas a pagar").
3. **Categories by id** — every category select sends `category_id` ("+ Novo", Extrato edit —
   only when changed —, Importar, Aprovar, Ajustes › Regras). Migration **035** adds
   `cc_expenses.category_id` (backfilled by name, root first) and the budget counts card purchases
   by it. Server: `category_id_for_name()` / `category_ids_by_name()` (root, then the oldest
   subcategory), `resolve_category(current=...)` keeps a row's id when the edit sends its own name
   back, `allow_archived` for the import commit, rule apply compares ids, the import default
   ("Outros") is the root one.
4. **Rename everywhere** — `rename_category_rows()` (`services/accounts.py`) rewrites the name in
   `transactions`, `cc_expenses`, `recurring_transactions`, `import_rules`, `inbox_items`; a row
   with only the old text adopts the id when the old name was this category's.
5. **Each card purchase is its `client_id`** — `same_purchase_sql()` / `cc_purchase_expense_ids()`
   (`services/attachments.py`) for receipts, sharing, A receber, the attachment count;
   `GET /api/cc-expenses/candidates?id=` (Cartões delete and the share sheet); `cardPurchaseKey()`
   (`lib/transactions.js`) for Cartões' rows and Início's grouping. Every new purchase gets an id
   (generated when the client sends none, also refunds and Aprovar); 035 gives the old ones
   `legacy:<id>`, splitting identical ones by write order.
- Checks: pytest **1195 passed** (`-o addopts=""`); node tests **91 passed**; `vite build` clean.
  Each new backend test was run against the old code (fixes stashed) and fails there: 9 of 11 in
  each new file; the other four are guards for the new paths.

### Not done, and why
- Not clicked through in a browser or on the phone (cloud container). The owner check is in
  `next-steps.md` ("Bug fixes of 2026-10-18").
- The outbox's 5xx = retry rule is unchanged on purpose: a transfer stuck in a phone's queue is
  delivered (same `client_id`) once this is deployed. A cap for a plain 500 would need
  `outboxRules.js` and `OutboxRules.java` together plus a native-level bump.
- Card purchases already orphaned by a rename before this fix stay orphaned (the text matches no
  category; a card purchase's category can't be edited). Identical purchases shared together
  before the fix keep the pair's share on both halves. Both need the owner's data.
- Início's "Despesas por categoria" still groups by name (CLAUDE.md: the Dashboard groups on the
  text column) — owner's call.
- The unused list `POST /api/cc-expenses` still writes rows with no `client_id` (old-key fallback).

### Learned / decided
- **The invoice month is the due month** (`invoice_closing_date()`): "next month's invoice" is
  right only for cards that close after their due day (25/5). The seed's cards (3/10, 13/20) close
  before it, which is why the bug showed on every seeded database.
- `client_id` doubles as the purchase id, as the owner suggested — no new column. A refund can
  never share a purchase's `client_id` (the refund route returns the existing rows for a known id).
- 035's category backfill follows the budget's own name order, so no realizado moves at migration
  time; only new rows and edits change where things count.
- A refund sent with the purchase's name and `refund_of` takes the purchase's id
  (`current=original`), so `CardRefundSheet` needed no change — and sending the id would have
  refused a purchase in an archived category.
- Migration number 035 was free: the remote had only `main` when this branch was cut.
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
