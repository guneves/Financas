# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-05 · Notifications + Pluggy, session 5 of 5: final verification

Branch: **`claude/notifications-pluggy-verify-9tss34`**, from `main` at `da59556`. Phases 1–5 were already on
`main` (PRs #67 and #68, merged at the owner's request in sessions 3 and 4), so the "chain" to verify was
`main` itself; session 4's branch `claude/friendly-pasteur-w9cbwq` is an ancestor of `main`. The owner asked
mid-session to open the PR and merge it when done. No migration.

**Baseline**: full backend suite green on `main` before any change (5.5 min); `npm test` 236 green.

**Bugs found and fixed** (one commit each, failing test first)
1. *Duplicate (balance)*: a late notice of a transfer side Pluggy already completed opened a **second
   transfer** (Itaú notified the Pix to the Corretora, Pluggy brought both sides, the BTG Investimentos notice
   came later and guessed "BTG conta corrente → Corretora"). `approved_transfer_awaiting()` treated a side as
   taken by any channel; now the notification path asks only its own (I2). Test:
   `TestFuzzRegressions::test_a_late_brokerage_notice_joins_the_transfer_pluggy_completed`.
2. *Performance*: `near_notification_items()` scanned every inbox item of the 36-day window once per new
   Pluggy row (`substr(occurred_at)` defeats the index): a first pull of 3000 rows 5.1 s before Phase 1 →
   12.6 s → **6.0 s** now (driven by the window's notifications). Test:
   `test_notify_pluggy_plans.py::test_the_near_pass_costs_the_notifications_not_the_pluggy_items` (SQLite VM steps).
3. *Wrong totals*: an own transfer split into **despesa + receita** when Pluggy recorded the first side and its
   notice joined that item (the item has no snapshot of its own, so the notice said "touched" and blocked the
   absorb). ~25 of 200 generated worlds. Test:
   `TestFuzzRegressions::test_a_pluggy_side_confirmed_by_its_notice_still_becomes_the_transfer`.

**Added**: `test_notify_pluggy_fuzz.py` (200 seeds, the real gate, ~2.6 min), `test_notify_pluggy_plans.py`
(EXPLAIN QUERY PLAN of every statement of a generated world: no SCAN of a hot table), `TestInterleaving` (a
notice between `ingest()` and `record_pending()`; unique indexes), `TestEndToEnd` (A–S in one world). CLAUDE.md
and two docstrings fixed where they contradicted the code; design §8 records what was built and every
deviation.

**Checked and fine** (06 §3, line by line): live/claimed queries; `_explained_by_notification` gone; one claim
helper; succession one-to-one, same installment, no broker/COVERED/INVOICE_PAYMENT, empty-pull guard;
`hand_over()` updates `source_id` only where it was the old id, all installments' `client_id`, `client_key`;
guessed side never to the same/foreign/archived account; no import cycle; absorb by snapshot; near-match
eligibility; integer band edges; typed amount kept; PTAX via `rounded_money()` and waits without a rate; old APK
without `international`; gate signature, no trace when off, FUNDO DE QUINTAL, invoice text before `kindOf()`,
Samsung with a bank card ignored (fuzz); no guessed rate; guard on routes only; `op_key` of this user and HELD
(replay 400); both scripts `mode=ro`, no `app`; review clears in the same pass, `review_count` = Revisar
(fuzz); twin query with `user_id` and a date range, neutral badge; one balance formula, sign, international
kept, protected rows, stale connection, cards list-only. A two-connection race (pull committing between the
notice's read and its write) also gave one row.

**Not done, and why**
- Nothing on a phone, on real Pluggy data or on a device: production is off-limits, no Android SDK here.
  android-check: this branch doesn't touch `frontend/android/` (last run green on `main`).

**Next**: the owner's checks in `next-steps.md` (APK, Itaú purchase, Pix to BTG, `position_fields.py`, weekly
`check_identity.py`).

Lessons:
- A generated world must live **before the real clock**: `last_sync_at` is real time, and the app only "read"
  the bank once `last_sync_at ≥ pluggy_updated_at`; a world in the future never lets an orphan go.
- Give every account one old Pluggy line: a just-connected account with no rows looks back only
  `OVERLAP_DAYS`, and a single sandbox-sign card purchase is learned as a refund.
- `set_progress_handler` counts SQLite VM steps: a deterministic performance test, no stopwatch.
- `pkill -f pytest` also kills the shell running it; target the PID.
