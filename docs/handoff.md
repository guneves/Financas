# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Addendum — 2026-10-27 (9) · Failed deploy fixed, `main` pushed

The deploy of `174924f` (conta-global) failed in CI on one test; fixed and pushed `main` (which also
carries session 8's `of-duplicate-guard` merge, so both are now deployed).
- `test_open_finance_auto.py::test_a_pix_to_someone_else_is_held_two_days_then_recorded` was a date
  bomb: the first sync used the real clock, so once today was ≥ 2026-10-28 (CI is UTC) the 2-day hold
  on a 2026-10-26 Pix had expired. It now pins `local_today` to the Pix day for the first sync.
  The pin alone didn't work: `services/auto_record.py` imported `local_today` by name, so
  `record_due()` (on GET /api/transactions) used the real clock; it now calls `invoices.local_today()`.
- Real bug found locally after 21:00: a Corretora without `metadata.portfolio_since` fell back to
  `created_at[:10]`, a **UTC** date, so a provento paid today was skipped in Brazil's evening
  (`test_fixed_income_interest.py` failed locally, never in UTC CI). `portfolio_since()` now converts
  `created_at` to the local date, like `local_today()`.
- Lesson: tests with hard-coded October 2026 dates near "today" break as the clock passes them; pin
  `invoices.local_today` for every sync, and run the suite in the evening too (UTC vs local).
- Not done here (the owner routed it to the other session): "remove all Para revisar flags" —
  clear `needs_review` so the app starts clean for daily use.

---

## Session — 2026-10-27 (8) · Pluggy duplicates of notification rows

Owner asked to check that notifications record at once and Pluggy (every 6 h) fills what is missing,
then to fix the duplicate found. Branch `claude/of-duplicate-guard` from `main`, merged locally into
`main`. **Not pushed, not deployed** (pushing `main` deploys; `main` also carries conta-global).

### Done
- Verified (code + tests): notifications record at once (`auto_record.record_notifications()` after
  every POST /api/inbox/detections; Samsung-only waits 10 min and records on the next read of
  Extrato/Início/Revisar); the Pluggy thread pulls each user every `sync_hours` (6) and records what
  no lançamento explains; a matched notification row keeps `needs_review = 1` (Pluggy never
  confirms for the owner — by design).
- **Bug fixed:** a notification-recorded row whose bank row came >1 day later was recorded twice
  (the notification's row is "taken" by its APPROVED item, so `free_candidates()` skipped it).
  `notification_item_for_open_finance()` now falls back to APPROVED/MATCHED notification items up to
  `OPEN_FINANCE_LATE_POST_DAYS` = 5 before the bank date (backwards only); `reconcile_recorded()`
  then redoes an untouched row at the bank's date or only links a reviewed one.
- **BB rounds up** (owner, mid-session: 18,19 shows as 19,00 in Pluggy): `ROUNDS_UP_ISSUERS = {"bb"}`,
  `rounded_up()`, `open_finance_rounds_up()` (connector/account name → issuer). Applies to the
  notification pairing both ways and to `invoice_payment_link()` (exact cents preferred).
- Tests: `test_auto_record.py` +9 (4 late-posting, 5 BB incl. an Itaú control). Full pytest: all
  pass except the known `test_fixed_income_interest.py::TestTheCouponReachesTheAccount` (after
  21:00 BRT).

### Not done, and why
- A different amount from another bank (IOF, international) still records twice: not safely
  separable from a second purchase; the Conferência shows the notification row as app-only.
- BB's rounding was taken from the owner's message, not seen in real data (the dev DB has only test
  rows): if BB also rounds Pluggy-only rows, those lançamentos carry 19,00 (nothing to compare with).
- When the notification arrives after a BB Pluggy row, they pair but the lançamento keeps 19,00.

### Next session
1. Owner: push `main` to deploy (conta-global + this fix), then watch the next 6 h pull for BB.
2. Then the conta-global data steps in next-steps.

### Lessons (non-obvious)
- Tests whose bank rows must arrive on a second pull need dates within `synced_until - 7 days`.

---

