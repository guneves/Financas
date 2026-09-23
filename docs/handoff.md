# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---


## Session — 2026-09-22 (latest) · Import rules on recorded lançamentos

Asked to "work on next-steps.md, claude in chrome is available, commit everything in the work
tree". The top of the plan is still the owner's walk-through, so this took the Phase 4 leftovers
(the next buildable daily-use item) and used Chrome to click them through on scratch data.

### What was done

- **Committed the work tree as found** (`f12ec18`) — changes not made by this session: Extrato,
  Posição, Operações and Proventos switch from table to cards below `xl` (was `md`), wider date
  columns, Extrato's Conta column from `xl`; Proventos' empty calendar now explains that it only
  lists recorded proventos with a future payment date and offers "Registrar provento". `vite build`
  clean before committing; not otherwise reviewed or walked.
- **Apply import rules to recorded lançamentos** (`backend/app.py`, after `import_rule_detail`):
  `POST /api/import-rules/apply/preview` (never writes) and `POST /api/import-rules/apply`
  (`transaction_ids` required; each id re-checked against the rule before writing; rewrites
  `category` + `category_id`; adds to `hits`). `rule_id` optional: one rule (even inactive — the
  owner picked it) vs. all active rules in import priority. Skips TRANSFER, `INVESTMENT_TRANSACTION`,
  `CC_INVOICE_PAYMENT`, `CC_AUTOPAY` and rows with no description. A row already in the rule's
  category is not a candidate. Preview capped at 2,000 rows (`truncated`).
- **Ajustes → Regras** (`frontend/src/pages/ajustes/RegrasSection.jsx`): pencil edits a rule (pattern
  included — the PATCH already accepted it) in the same Collapsible as "Nova regra"; "Aplicar" per
  rule and "Aplicar ao extrato" in the header open a Sheet listing the changes, all ticked, with
  "Todos" and "Recategorizar N". Rule row buttons are grouped so they wrap together on the phone.
- **Tests:** `backend/tests/test_rule_apply.py`, 14 tests. Suite **575 passed**.
- **Verified:** Chrome on scratch data (:5175/:5002): the preview listed 22 "Estacionamento"; unticking
  2 and applying changed 20 and bumped hits to 20; the per-rule preview then listed just those 2;
  editing the pattern saved and reset the form; no console errors. Playwright screenshots at 1280 and
  390 px caught a squashed rule row on the phone (fixed, re-shot).
- **`finance-guard`:** no findings. Its one note was that invoice payments were excluded but never
  tested; I added `test_invoice_payments_are_never_recategorized`.

### What was not done and why

- Amount/account conditions on a rule: not needed for the owner's flow yet; left in the plan.
- No "undo" for an apply: the preview plus per-row ticks is the guard, and a mistaken row can be
  fixed in Extrato. If the owner wants one, store the previous category in `metadata`.
- The committed layout change (cards below `xl`) is a real behaviour change at 1024–1279 px;
  added to the walk-through list rather than second-guessed.
- Carried forward: **`BRAPI_TOKEN` is still empty** in `backend/.env`;
  `backend/backups/finance-pre-mock-20260922-205415.db` (scratch demo data, gitignored) is still on
  disk and safe to delete; dark mode (decision E) and the UI remodel prompt are still open;
  `docs/ui-remodel-prompt.md`'s "state at writing" note is stale.

### Next session

- Owner: the walk-through at the top of `next-steps.md` (now includes rules apply/edit and the
  `xl` card breakpoint).
- Then the UI remodel prompt, dark mode, or Phase 5 (first blueprint). Smaller daily-use option still
  open: attachments per transaction.

### Non-obvious things learned

- **Scratch ports collide with other sessions.** Another session's scratch backend and Vite were
  still on :5001/:5174. On Windows a second Flask bind to :5001 *succeeds*, and requests reach the
  old process (symptoms: "Token invalido", 404 on a new route). Check `netstat -ano` first; this
  session used :5002/:5175 and left the other processes alone.
- The stored session is `localStorage['@financeMVP:auth'] = {"access_token": ..., "user": ...}` —
  `access_token`, not `token`. Minting one: `app.create_token(user_id)` under the scratch
  `JWT_SECRET`.
- Chrome extension: clicks via `find` refs and `javascript_tool` work; `screenshot` came back blank
  and then timed out (background window). Playwright from the npx cache handles screenshots.
- Windows Python output captured with `$(...)` in Git Bash keeps a `\r`; strip it before using it
  in a header.
- Carried: seeding a scratch DB — set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`, sign up with
  `app.app.test_client()`, then `import seed_three_years_mock as s`, set `s.BACKEND_DIR` to the
  scratchpad and call `s.main()` with `sys.argv` patched. `.app-table` rules sit under `:where()`;
  a panel with `overflow-hidden` breaks sticky headers (use `overflow-clip`); write edit scripts to a
  file rather than piping Python via stdin (mangles non-ASCII).
