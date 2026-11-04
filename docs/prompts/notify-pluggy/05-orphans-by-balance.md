# Phase 5: a notified row Pluggy never lists: the bank's balance decides

Read `00-common.md` first. Design: §3.4 and §7 decision 1. Server, plus a label on the web and APK
Conferência.

**Prerequisites:** Phases 1, 2 and 4 merged. Phase 4's snapshot-based "untouched" is needed.

```bash
grep -n "def pluggy_claimed" backend/services/inbox.py
```

```bash
grep -n "bank_notifications" backend/services/inbox.py
```

## Scope: bank accounts only

Implement removal for mapped **BANK** accounts. **Cards are list-only** in this phase: a card's
balance mixes the used limit, pending holds and BB's rounding, so "the balance proves it" is not
yet safe there. Say so in CLAUDE.md and the handoff.

## What to build

`services/open_finance_orphans.py`, `sweep(conn, uid, of_item_id, today)`. It is called in
`_sync_item_locked()` after `record_bank_payments()` and `mark_bank_investments()`, so every row of
the pull is already placed. It runs for each mapped BANK account of that connection.

1. **An orphan** is a lançamento in `transactions` on that account where all of these hold:
   - it was recorded from a notification: its item has a `SOURCE` detection and
     `auto_recorded_at`;
   - it has **no live Pluggy claim** (`pluggy_claimed()`);
   - its type is `EXPENSE` or `INCOME`, never `TRANSFER`;
   - its date ≤ today − `OPEN_FINANCE_LATE_POST_DAYS`;
   - **the bank refreshed after date + 5 days and the app read it**: the connection's
     `pluggy_updated_at` passed that point and `last_sync_at` ≥ `pluggy_updated_at`
     (`open_finance_auto.bank_refreshed_since()`). A broken connection never qualifies.
2. **Protected, never removed**:
   - a receipt;
   - `share_mode` set (A receber);
   - a row in `open_finance_confirmed` ("Aconteceu");
   - an amount the owner typed (snapshot amount ≠ current).
3. **The balance decides.** Take the difference D = app − bank, in cents, from the Conferência's
   own computation (`open_finance_check.account_check()`, which gives `difference_cents` and
   `balance_explanation()`). **Don't write a second balance formula.** Each orphan's effect is −amount
   for EXPENSE and +amount for INCOME.
   - **Remove** when D equals the effect of one orphan (the oldest such), or of all orphans
     together. Nothing else: no subset search, no tolerance. When in doubt, keep.
   - **Kept with D = 0** (the bank's balance counts it; Pluggy left the line out): mark it so the
     Conferência shows "confirmado pelo saldo". Use a flag on the item or a computed status; it is
     not a new list in Revisar.
   - **Kept with D anything else**: unchanged, listed `app_only` as today.
4. **Removal** works like `auto_record.undo_declined()` (`auto_record.py:132`):
   - `_drop_target()`;
   - the item becomes `REMOVED` with reason `orphan`;
   - the detections lose their target.

   Count the removals in the pull log (`removed_orphans`).
5. **Conferência label**: web (`pages/ajustes/OpenFinanceSection.jsx` / the Conferência view) and
   APK (`rules/OpenFinanceRules.kt` + screen) show "confirmado pelo saldo" for those rows. Node and
   JVM tests if a rule is added.

## Tests (`test_open_finance_orphans.py`)

Build the bank balance with FakePluggy's account `balance`, and check that the app's balance and
D come from the same function the Conferência uses.

| Case | Expected |
|------|----------|
| notified R$ 50 expense, Pluggy never lists it, bank balance excludes it (D = −50), refreshed past +5 d | removed; pull log counts 1 |
| same, but the bank balance already counts it (D = 0) | kept, "confirmado pelo saldo" |
| same, D = −80 (something else differs too) | kept |
| two orphans R$ 20 + R$ 30, D = −50 | both removed |
| two orphans R$ 20 + R$ 30, D = −20 | the R$ 20 removed only if it is the oldest matching; the R$ 30 kept |
| orphan with a receipt / a share / "Aconteceu" / owner-typed amount | kept |
| connection not refreshed past +5 d (stale `pluggy_updated_at`) | kept |
| a converted own transfer | kept |
| a card purchase orphan | kept (list-only) |
| Pluggy lists it late (day +4), before the sweep | not an orphan; one row |
| income orphan (a notified Pix in that never posted), D = +X | removed |

## Pitfalls

- Pending rows: with `include_pending` on, the app counts pending Pluggy rows. If the bank's balance
  doesn't, D never equals a single orphan and nothing is removed. That is the safe side; don't
  "fix" it with a tolerance.
- Never delete a row the sweep cannot explain. A false keep costs the owner a look at the
  Conferência; a false removal makes the balance wrong and loses money tracking.

## Done when

All green on a tree merged with `origin/main`; CLAUDE.md describes the orphan rule (bank accounts
only, cards list-only). Then run `06-verify-and-fix.md` for Phase 5, and the final full pass.
