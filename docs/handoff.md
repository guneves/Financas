# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

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

