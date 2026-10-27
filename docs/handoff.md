# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (4) · Auto-record → reconcile → review (045)

Local session on the owner's PC, on `main`, from a pasted request: every notification is recorded at
once, the Aprovar queue goes away, Pluggy reconciles (and feeds Investimentos), card purchases join
the Extrato, and the owner's only job is confirming + categorizing.

### Done
- **Migration 045**: `transactions.needs_review`, `cc_expenses.needs_review` (default 0, partial
  indexes), `inbox_items.auto_recorded_at / recorded_snapshot`.
- **Notifications record at once** (`services/auto_record.py`): after `POST /api/inbox/detections`
  and in `record_due()` on reads of `/api/transactions`, `/api/home`, `/api/review`. Missing targets
  are guessed (`services/inbox_defaults.py`), nothing remembered; typed look-alikes linked
  (`free_candidates()`, also checks other inbox items). Waits only: Samsung-only (10 min), own
  transfer with one side, other currency.
- **Pluggy engine** (`open_finance_auto.py`) uses the same defaults and marks rows for review; an
  investment category on a bank account is now recorded (was held); the history preview no longer
  counts it as `waiting`.
- **Reconciliation** (`open_finance_inbox.reconcile_recorded()`): a Pluggy row matching a
  notification-recorded item links silently (source OPEN_FINANCE / card `client_id = pluggy:<id>`,
  OF snapshot) when untouched; other date or card/account → delete + re-record the bank's way; reviewed
  or edited → MATCHED only.
- **Switches default on** via `AUTO_RECORD_DEFAULT` (config): `auto_record` in
  `/api/inbox/settings` (new) and in `/api/open-finance/settings` (was off by default). Tests run
  with it off (conftest) except `test_auto_record.py`.
- **Review**: `services/review.py`, `routes/review.py` (`GET /api/review` → items/count/waiting;
  `POST /api/review` batch, all or nothing); `?review=1` on `/api/transactions`; `review_count` in
  `/api/home`.
- **Card purchases in the Extrato**: `GET /api/cc-expenses/statement` (`services/card_statement.py`,
  one row per purchase, Extrato filters); merged in the web by `lib/review.js` `mergeStatement()`.
- **Web**: `ReviewPanel` on the Extrato (category select + "É meu", "Confirmar todos"), "A revisar"
  badge, "Revisão" filter, card rows with a "Cartão · Nx" tag and "Ver em Cartões"; header pill and
  Extrato tab count reviews; Aprovar out of the tabs (route kept; the Extrato links to it when
  something waits); Ajustes "Avisos do celular" with the Gravar sozinho switch. `lib/inboxCount.js`
  removed.
- Tests: `test_auto_record.py` (33); OF/inbox tests adjusted (investment now recorded, settings shape);
  full pytest **1942 passed**; `npm test` 200; `vite build` ok. Clicked through on a scratch app with
  Playwright at 1400 px and 390 px (review panel, one-tap confirm, card rows, filter) — no console
  errors.
- Docs: CLAUDE.md (new section "Auto-record → reconcile → review", inbox engine renamed, Gravar
  sozinho updated, conftest note), next-steps (new 045 section), done-tasks.

### Not done, and why
- **APK not touched**: it still shows its Aprovar screen and an Extrato without card rows/review.
  Recording works for it (server-side); the review UI is web-only. Next step if the owner wants it.
- **Own one-sided transfers still wait in Aprovar** — deliberate deviation from "nothing waits":
  recording them as despesa and later receiving the other side as receita would split one transfer
  into two movements (and history imports pull banks one at a time). The Extrato points to them.
- No "não é meu" button (delete covers errors; fraud is real money). Amount differences (IOF) are
  not reconciled as corrections. PATCH does not clear `needs_review`.
- Nothing ran on real data. The defaults flip **on** at deploy: the first phone upload and Pluggy
  pull will record backlogs — the card-sign check in next-steps still applies.

### Next session
1. Owner's check on real data (next-steps › 045, then the 044 list).
2. APK: review panel and card rows in the native Extrato.

### Lessons (non-obvious)
- `local_today()` lives in `services/invoices.py`, not `dates.py`.
- Holding by transaction date breaks history backfills (each connection's pull runs the engine
  before the other bank's rows exist): that's why own transfers wait for their pair, not a deadline.
- Category creation takes `kind`, not `type`.
- In headless Playwright the first `text=Revisar` match is the hidden header pill on phone; wait for
  `text=Extrato da conta >> visible=true`.

---

