# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · Notifications + Pluggy, session 1 of 5: Phase 1 (1a + 1b), server only

Branch: **`claude/notify-pluggy-phase1`** (from `main` at `0257bc8`; not merged, no PR; pushed only
once the 1b suite is green).
Session 2 starts from it (`docs/prompts/notify-pluggy/02-open-the-gate.md`).

**Done (1a)**, commit "Phase 1a: …":
- **Claims per channel**: `inbox.pluggy_claimed()` / `notification_claimed()` / `claimed()`.
  `existing_rows(claimed_by=...)` replaces `for_notification`; `free_candidates()` uses the item's
  channel (`inbox_defaults.item_channel()`); `_linked_elsewhere()` and the history preview use
  `pluggy_claimed()`. `_explained_by_notification()` is deleted.
- `notification_item_for_open_finance()` ignores `vanished` sources **and looks only at the Pluggy
  slot of the same direction** (I2: a transfer has one per side). This goes a bit beyond the
  prompt: without it, defect R stays wrong when the Corretora's side is pulled before Itaú's
  (test `test_r_the_guessed_origin_follows_the_bank[btg-itau]`).
- **Succession**: `missing_rows()` → `ingest(..., missing=)` → `successor_for()` / `hand_over()` →
  `vanish_rows()`, in `_sync_item_locked()` (steps: per account normalize + missing; then the batch
  ingest; then vanish what is left; then the near pass, see 1b). Migration **054**
  `superseded_by`. The superseded row is `REMOVED`, `superseded_by`, and its `item_id`/target and
  `conflict` are cleared (so the ~49 queries on `open_finance_transactions` that don't filter role
  can't see it as a link); `ingest()` returns `known` if a superseded id ever comes back. The new
  row gets role, item, target, `auto_recorded_at`, snapshot; `transactions.source_id` and
  `client_id`, the card purchase's `client_id` (all installments) and `inbox_items.client_key`
  follow. An untouched own row also takes the posted date (transactions only). Status `succeeded`
  in the pull log.
- **R**: `follow_bank_side()` at the top of `reconcile_recorded()` for transfers.
- `identity_invariants.py` (pure), `tests/identity_check.py` (`assert_identity()`),
  `scripts/check_identity.py --email X` (opens SQLite `mode=ro`, never imports `app`; exit 0/1/2).
- Snapshot helpers moved to `services/recorded_snapshot.py` (re-exported by `open_finance_inbox`).

**Done (1b)**, commit "Phase 1b: …":
- **One absorb helper** `inbox.absorb_recorded_side()` + `finish_absorb()`, called by
  `_ingest_alone()` step 1 and `place()` step 3 (`_absorb_recorded_pix()` deleted). Untouched is
  the snapshot (item's for a notification source, the Pluggy row's for a Pluggy source).
- **Nothing waits**: `auto_record.one_side_now()` turns a one-sided own transfer into the side
  seen; the Corretora and the Conta global keep waiting.
- **Near match**: `merchant_agrees()`, `near_amount()`, `NEAR_MATCH_FOREIGN_PERCENT` (10) /
  `NEAR_MATCH_DOMESTIC_PERCENT` (30) in config; `near_match_pass()` after ingest and vanish,
  before investments/`record_pending()`, only on Pluggy items that became pending in this pull
  (`pending_pluggy_items()` before vs after); step 2b `near_item_for_detection()`; near succession
  (`_near_successor()`, unique each way against the pull's new ids); `follow_bank_amount()` (bank
  wins unless current amount ≠ snapshot amount). Migration **055**: `original_currency` on
  `open_finance_transactions` (from `normalize_transaction()`, before the
  `amountInAccountCurrency` swap, in `ROW_FIELDS`) and `notify_detections.international`
  (`parse_detection()` accepts a boolean; currency ≠ BRL counts too). `LATE_POSTING_DAYS` is read
  from `services/open_finance.py` lazily (`inbox.late_posting_days()`), never copied.
- **PTAX**: a foreign-currency notification on a reais card/account is recorded at once through
  `open_finance_auto.in_reais_now()`; no PTAX → it waits.

**Also**: `tests/conftest.py` now sets the test environment at import. Before, a file whose first
tests import `services.*` before `app_module` (`test_auto_invest_broker.py` run alone) bound `db`
to the real `backend/finance.db`. My first combined run hit exactly that: it applied migration 054
to the **dev copy** `backend/finance.db` and wrote test rows there (that file already held ~1700
test users from earlier sessions; production was never touched). Own commit.

**Tests**: `test_notify_pluggy_identity.py`, 63 cases, `assert_identity()` at the end of each
scenario. Full backend suite green after 1a, and after 1b (run in four sequential chunks of files,
because one full run was killed for low memory).

**Not done, and why**
- No frontend, no APK (server-only phase; the `international` flag from the parser is Phase 2).
- `hand_over()` and the near match move the date in place only for `transactions`. A card purchase
  whose posted date differs keeps its purchase date on succession, and on a near match it goes
  through `reconcile_recorded()`'s "bank disagrees" (deleted and re-recorded: one row, new id).
- `open_finance_auto.one_side_now()` (Pluggy's own one-sided transfer) has no Corretora exception;
  only the notification side got one (the prompt scoped it to `auto_record.hold_reason()`).
- Case A: a reviewed notification row keeps `source_type` NULL, so its `source_id` doesn't change;
  the assertion is that the live Pluggy row targeting it is the new id (old one superseded).

**Next**: session 2, `02-open-the-gate.md`, starting from this branch.

### For the final verification
- **Riskiest**: succession with the 35-day window. A pending row that Pluggy drops (a released
  pre-authorisation) and a different purchase of the same cents within 3 days on the same account
  are merged into one row (ledger and balance stay right; description/date may be the other
  purchase's). Near succession has the same risk inside the domestic 30% band, limited by "same
  merchant, unique each way".
- `vanish_missing()` used to run **before** ingest; now the missing rows stay live during the
  batch. A non-succeeded missing row (gap > 3 days) still occupies its item's Pluggy slot while the
  batch runs, so a same-cents row 4–5 days apart that would have joined that notification item
  now opens its own item. Not seen in tests; check it with the scenario generator.
- The per-side slot in `notification_item_for_open_finance()` (see above) and that
  `free_candidates()` now lets a notification item link a Pluggy-recorded row (and vice versa)
  when no same-channel claim exists: rows = max(n_N, n_P) is the intent; verify with twins in
  mixed orders.
- `near_join()` moves an untouched notification row's date to the bank's when the target agrees
  (test S keeps the id); reconcile then makes Pluggy the source.
- **Tests changed**:
  - `test_open_finance_settings.py::test_a_new_id_on_posting_removes_the_old_item` →
    `test_a_new_id_on_posting_succeeds_the_old_one_in_the_same_item`: the design replaces
    "new id → REMOVED + new item" with succession (same item).
  - `test_auto_record.py::test_an_own_transfer_waits_for_the_other_side_then_is_one_transfer` →
    `test_an_own_transfer_in_separate_uploads_is_one_transfer`: separate uploads now give one
    transfer (defect I), same upload still does.
  - `test_open_finance_auto.py::test_a_reviewed_side_is_not_rewritten` →
    `test_a_reviewed_side_still_becomes_the_transfer` + `test_an_edited_side_is_not_rewritten`:
    "untouched" is now the snapshot, never `needs_review` (1b prompt), so a reviewed side is
    absorbed and only an edited one stays.
  - `test_open_finance_sync.py::test_a_different_day_or_amount_is_not_the_same`: the R$ 45,91
    bank line now has another merchant ("POSTO SHELL"); with the same merchant it is the near
    match by design (§3.7).
  - `tests/conftest.py`: environment set at import (above).
- **Not tested**: real Pluggy data (pending/posted pairs, `currencyCode` on BTG/Itaú cards);
  `scripts/check_identity.py` on the server DB (tested on a copy of the test DB only).

Lessons:
- Running one test file alone could hit the dev DB; the full suite never did because an earlier
  file set the environment first. Now fixed in conftest, but don't trust a "passes alone" run made
  before this commit.
- A new migration file added while the full suite runs makes `test_migration_numbers` and the
  rebuild dry-run test fail in that run; add migrations between runs.
- Bash heredocs with nested quotes broke twice; write edit scripts with Write and run them.
