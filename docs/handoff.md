# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-05 · Notifications + Pluggy, session 4 of 5: Phases 4 and 5

Branch: **`claude/friendly-pasteur-w9cbwq`**, from `main` at `b4679fc` (Phases 1–3 already merged; session 3's
branch `claude/notify-pluggy-phase3` is an ancestor of `main`, so nothing else to merge). No migration.
**The owner asked mid-session to open a PR and merge when done** (as in session 3), so Phases 4–5 go to
`main` through a PR; session 5 (final verification) starts from `main`.

**Done — Phase 4** (commit "Phase 4: review only what is a guess…")
- **The trap first**: `notification_untouched()` is snapshot equality only (no more `review.awaiting()`);
  `_absorb_recorded_real_side()` lost its `needs_review = 1` filter; `apply_change()` now also refreshes the
  item's snapshot (`refresh_snapshots()`), so a second bank change still applies to a notification row.
- `open_finance_inbox.settle_review()`: after Pluggy confirms (`reconcile_recorded()` untouched path, which
  the near match goes through; `open_finance_auto.record_item()` right after recording), a row whose
  `category_decision()` is rule/merchant/CNAE gets that category (while untouched), `needs_review = 0`, and
  the snapshots are refreshed in the same transaction (`review.clear()`).
- `inbox.settle_transfer_review()` / `transfer_confirmed()`: a recorded transfer with an OUT and an IN
  observation, at least one from Pluggy, leaves review (from `finish_absorb()`, `place()` step 3,
  `ingest_detection()` step 1, `reconcile_recorded()` for transfers).
- **Found and fixed**: `absorb_recorded_side()` required exactly one observation, so a despesa notified
  *and* confirmed by Pluggy (two observations, one side) never became the transfer when the other bank's
  side arrived. Now: at most one observation per channel, all movements, same direction.
- `services/twins.py`: `twin` on `GET /api/transactions` (both paths), `GET /api/review`,
  `GET /api/cc-expenses/statement`. Web: neutral `Badge` "2× igual" in the Extrato rows and `ReviewPanel`.
  APK: `twin` on `TransactionDto`/`ReviewItemDto`/`CardStatementDto`, badge in the Extrato row and
  `ReviewSection` (`twin_badge`).

**Done — Phase 5**
- `services/open_finance_orphans.py` (`sweep`, `choose`, `protected`, `ripe`, `balance_confirmed`), called
  in `_sync_item_locked()` **after** the `last_sync_at` stamp (so `bank_refreshed_since()` sees this pull as
  read), inside the same transaction, only when auto-record is on.
- `open_finance_check.balance_difference()` is the one formula; `list_view()` now calls it.
- `account_check(..., balance_confirmed=)` moves those rows out of `app_only`/`awaiting_bank` into
  `balance_confirmed` (+ count); their dates widen the window when Pluggy listed nothing.
- Web (Ajustes › Open Finance) and APK (`OpenFinanceCheckDto.balanceConfirmed`, Ajustes) list
  "Confirmado pelo saldo".

**Tests**
- New `test_quiet_review.py` (23): merchant category clears; the bank's merchant replaces the guess;
  Pluggy-tree and default stay; Pluggy-only padaria; owner's rule; card purchase clears, refund stays;
  Flash stays; two-sided transfer (notice + Pluggy) clears, two notices without Pluggy stay; Conta global
  stays; **after auto-clear**: amount change (twice, notification row) and Pluggy-only, vanish, the other side
  by Pluggy and by notification, pending → posted with another amount, near-amount notification after;
  "É meu" → date follows; changed category → date stays and only linked, category never overwritten;
  `notification_untouched()` direct.
- New `test_twins.py` (20): 4 min / 2 h / other merchant / other cents / other account / typed same day /
  income never / next page / another user; card twins, other description, other card, card twins in review;
  pure `close_in_time` / `twin_keys`.
- New `test_open_finance_orphans.py` (24): every row of the prompt's table, plus no subset, no tolerance,
  income with the wrong sign, connection never read, review doesn't protect, pure `choose` and
  `balance_difference`.
- JVM: `ReviewRulesTest.aCardTwinKeepsItsFlagInTheStatement`. Node: no new rule (rendering a flag).
- Results: backend full suite 2647 passed; `npm test` 236; `vite build` ok; android-check green.

**Tests changed (rule changed, design §3.4/§3.6)**
- `test_auto_record.py`: `needs_review` now 0 where the merchant is known (padaria, Smart Fit);
  `test_a_reviewed_row_is_never_redone` → `test_a_reviewed_row_follows_the_bank_date` +
  `test_a_recategorised_row_is_never_redone`; `test_a_reviewed_row_posted_days_later_is_only_linked` →
  `…recategorised…`; `test_pluggy_alone_is_recorded_for_review` uses "LOJA 123".
- `test_notify_pluggy_identity.py`: a reviewed-only row is now `SOURCE` (untouched); the "matched without
  successor" case recategorises to stay touched; B's `needs_review` 0.
- `test_notification_policy.py`: `test_a_row_the_owner_reviewed_stays` → reviewed-only is undone by a Flash
  decline, recategorised stays.
- `test_open_finance_auto.py` (two-sided transfer → 0), `test_open_finance_tick.py` (padaria → 0).

**Not done, and why**
- Cards: no removal by balance (prompt: list-only).
- No real data: production is off-limits.

**Next**: session 5, final verification (`06-verify-and-fix.md`) from `main`.

### For the final verification
- **Riskiest**: (1) "untouched" by snapshot means a row the owner only reviewed is now redone by the bank
  (date/card) and removed by a Flash decline or a vanish — intended (§3.4), but a behaviour change on
  production rows reviewed before this deploy. (2) The orphan sweep deletes rows: check `choose()` and
  `protected()`; it runs only after `bank_refreshed_since(date + 5 d)` of **every** active connection.
  (3) `absorb_recorded_side()` widened (one side, ≤ 1 observation per channel).
- Pull order is now: … `record_pending()` → `record_bank_payments()` → `mark_bank_investments()` →
  `last_sync_at` → `open_finance_orphans.sweep()`.
- **Not tested**: badges and the Conferência list were not clicked in a browser or on a device; the
  confirmed-by-balance list with pending Pluggy rows counted by the app (the difference never matches, so
  nothing is removed — the safe side).

Lessons:
- `connected()` pulls once on connect; a later pull of an account with no Pluggy row yet only looks back
  `OVERLAP_DAYS`. Tests that add older bank lines after connecting reset `synced_until` (as
  `test_global_account.pull()`).
- `bank_tx()`'s default description "COMPRA PADARIA" is in the merchant table: since Phase 4 it leaves
  review by itself. Use "LOJA 123" when a test needs a guessed category.
- `services/review.py` is imported by `inbox`; `services/twins.py` must not import `inbox` (cycle).
