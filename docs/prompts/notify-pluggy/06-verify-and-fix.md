# Verify and fix: run after each phase, and once at the end

Read `00-common.md` first. The owner tells you which phase to verify (1, 2, 3, 4, 5, or "final")
and where it is: `main`, or a session branch not yet merged. Your job is to **find bugs the phase
session missed, prove each with a failing test, fix it, and report**. You do not add features, and
you do not change a decision of design §7. If a fix needs a design change, stop and describe it to
the owner instead.

## 1. Set up the exact tree

- If the phase is on a branch, `git fetch` it and work on a new branch made from it. Then merge
  `origin/main` and run the full suite. A phase that is green alone but red merged is the first bug
  to report: the 052/053 migration clash happened exactly like that.
- Read the design (§1–§7), the phase's prompt, its handoff entry and `git log -p` of its commits.

## 2. Run everything, record the baseline

- Backend: the full suite, plus `test_migration_numbers.py`, `test_route_map.py` and the phase's
  own files.
- Frontend: `npm test` if `frontend/src` changed. Android: android-check on the branch, if
  `frontend/android/` changed (GitHub MCP actions tools).
- Note every failure, and whether it also fails on `origin/main` (that one is pre-existing: say so,
  don't fix it here).

## 3. Review the diff against the known traps

Go through the list for the phase. For each item, either point at the line that handles it or write
the test that shows it is missing.

**Phase 1a: claims and succession**
- [ ] Every query deciding "claimed/live" filters `role <> 'REMOVED'` **and** vanished. Grep every
  `FROM open_finance_transactions`.
- [ ] `_explained_by_notification` is gone, and no caller passes `for_notification` any more.
- [ ] `free_candidates()`, `_linked_elsewhere()` and the history preview (`_preview_status()`) use
  the same claim helper.
- [ ] Succession is one-to-one; it never crosses installment numbers; it never touches broker
  lines, `COVERED` or `INVOICE_PAYMENT`; the empty-pull guard is kept.
- [ ] `source_id` is updated only where it equalled the old id and the source is
  `OPEN_FINANCE`/`BANK_INVESTMENT`; `client_id` for **all** installments; `inbox_items.client_key`.
- [ ] `mirror_cards()` still mirrors a purchase after its succession.
- [ ] A `MATCHED` row without a successor gets `conflict = 'vanished'`, and the Conferência shows
  it sensibly.
- [ ] The rebuild (`services/open_finance_rebuild.py`, `scripts/rebuild_from_pluggy.py`) still
  works: `test_open_finance_rebuild.py` green. Read whether it calls `vanish_missing()` or the new
  functions.
- [ ] The guessed transfer side (R) never moves a side to the same account, the Corretora by
  mistake, a foreign account or an archived one.

**Phase 1b: absorb, nothing waits, near match**
- [ ] No circular import: `python -c "import app"` from `backend/` with the test env.
- [ ] Absorb uses the snapshot, **not** `needs_review = 1`.
- [ ] A one-sided transfer into the Corretora never becomes income; the Conta global is unchanged.
- [ ] The near pass runs **after** the batch ingest and **before** `record_pending()`.
- [ ] Never near-matched: transfers, Pix, refunds, invoice payments, installments > 1, the
  Corretora, the Conta global.
- [ ] Integer math in `near_amount()`; edges exactly at 10% and 30%.
- [ ] An amount the owner typed is never overwritten.
- [ ] PTAX conversion through `rounded_money()`; it waits when there is no rate.
- [ ] An old APK detection without `international` still works.

**Phase 2: the gate**
- [ ] `notification_wanted(detection)` still has that signature; `any_bank_notifications` tests are
  green and unchanged.
- [ ] With the setting off, a bank detection leaves **no** row in `notify_detections`.
- [ ] Investment words never reject a card purchase merchant (FUNDO DE QUINTAL, TESOURO DO MAR).
- [ ] Manifest `<queries>` equals `NotifyRules.APPS`.
- [ ] The invoice-payment text is filtered **before** `kindOf()`.
- [ ] Samsung Wallet with a bank card is rejected on the phone and on the server.
- [ ] CLAUDE.md has no sentence left saying bank notices are ignored (grep "ignored", "only the
  Flash", "Flash-only").

**Phase 3: investments**
- [ ] No rate is ever guessed: every unmappable field means HELD.
- [ ] The guard is in the routes only; `proceeds_sync`, `apply_paid_proceeds()` and
  `open_finance_investments` still write with the switch on.
- [ ] An `op_key` must belong to this user and be `HELD`; replaying it is refused (no second
  movement).
- [ ] `position_fields.py` and `check_identity.py` open the DB read-only and never import `app`.

**Phase 4: review and twins**
- [ ] "Untouched" is snapshot equality everywhere. After an automatic review clear, the bank's
  change, vanish, absorb and near match all still apply (one test each).
- [ ] Every server-side change to a recorded row refreshes the snapshots in the same transaction.
- [ ] No flicker in `review_count`: recording and clearing happen in one pass.
- [ ] The twin query has `user_id` and a bounded date range; the badge is neutral.

**Phase 5: orphans**
- [ ] One balance formula: the Conferência's. No tolerance, no subset search.
- [ ] Protected rows are never removed; a stale connection removes nothing; cards are list-only.

## 4. Hunt beyond the list: a seeded scenario generator

The matrix tests check the cases someone thought of. Add
`backend/tests/test_notify_pluggy_fuzz.py`. It uses plain `random.Random(seed)`, not Hypothesis
(not a dependency), and loops over seeds 0…199 marked `@pytest.mark.slow`, or parametrized if the
suite allows.

1. **Generate the truth.** 5–15 real movements over a week on 2–3 mapped accounts and one card:
   - purchases, some **identical twins**, some with a different posted amount (tip or
     international);
   - Pix to third parties;
   - own transfers between accounts and to the Corretora.
2. **Generate what each channel sees:**
   - each movement is notified or not, possibly twice (the BTG double post: same `when`, 24 ms
     apart);
   - each own transfer is notified on 0, 1 or 2 sides, in one upload or separate ones;
   - Pluggy shows each movement as posted, or pending then posted under the same or a new id,
     across 1–3 pulls, in random order relative to the notifications;
   - sometimes the owner reviews or re-categorises a row between steps.
3. **After the last pull, assert:**
   - `assert_identity()` holds;
   - **one row per real movement**: twins give two, a transfer gives one `TRANSFER`;
   - **each account's balance equals the truth's**, and so does each card's open total;
   - no own transfer counted as income or expense;
   - nothing waits in `GET /api/inbox` except what the design says may wait (the Conta global, a
     one-sided transfer into the Corretora).
4. **On a failure:** reduce it to the smallest scenario that still fails, copy that into
   `test_notify_pluggy_identity.py` as a named regression test, and **then** fix the code. Print the
   seed in the assertion message, so any failure can be reproduced.

This is property-based testing (Claessen & Hughes, "QuickCheck", ICFP 2000): check invariants over
generated inputs, not only hand-picked ones.

## 5. Interleaving and performance

- **Interleaving.** The 5-minute fresh pull thread and `POST /api/inbox/detections` can run at the
  same moment. Check that each path does its read-decide-write inside one `get_db()` transaction, and
  that the unique indexes (`idx_transactions_user_source`, the notification `dedup_key`, the Pluggy
  `dedup_key`) would refuse a double insert. Add a deterministic test that calls the service
  functions in alternating order: a notification ingested between the batch ingest and
  `record_pending()`.
- **Performance.** Run `EXPLAIN QUERY PLAN` on every new query over `open_finance_transactions`,
  `notify_detections` and `transactions`, especially the claim lookups by
  (`target_table`, `target_id`). If one scans the table, add an index in a migration. Time a pull of
  3000 rows before and after the phase; a pull that gets several times slower is a bug.

## 6. Fix

For each bug: write a failing test, make the smallest fix, run the full suite, and commit it with
the test (one bug per commit, the message names the test). Don't refactor beyond the fix.

## 7. Report (in Portuguese, to the owner)

- **Each bug**: severity (wrong balance or duplicate > wrong category or description > cosmetic),
  the test that reproduces it, the fix commit.
- **Each trap that was checked and found fine**, one line each.
- **What could not be verified here**:
  - anything on a real phone;
  - real Pluggy data;
  - the APK on a device.

  For each, the exact command or tap sequence the owner should run.
- Update `docs/handoff.md` and `docs/next-steps.md` as the session process asks. Push your branch;
  don't merge.

## Final pass (after Phase 5)

Do all of the above over the whole series, plus:
- one end-to-end test that runs cases A–R and J–Q in one user's world, then `assert_identity()`;
- CLAUDE.md read top to bottom for contradictions between the new rules and old sections (the
  inbox engine, auto-record, Open Finance);
- `docs/notifications-pluggy-design.md` updated with what was really built and every deviation,
  with the reason.
