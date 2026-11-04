# Phase 1a: claims per channel, Pluggy succession, guessed transfer side

Read `00-common.md` first. Design: §1 (defects A, B, R), §2 (invariants), §3.3 step 0 and §6
Phase 1. This phase is **server only** and **invisible while the bank notification gate is
closed**. Today only the Flash notifies, and the Flash has no Pluggy. It still changes how every
Pluggy pull places rows, so the whole Pluggy suite must stay green.

**Prerequisites:** none. This is the first phase.

## What to build

### 1. One definition of "claimed", per channel (half of defect A)

Today a lançamento claimed by *any* source blocks *every* source. Build helpers in
`services/inbox.py` (no new imports there: `inbox.py` is imported by `open_finance_inbox.py`, and
the reverse import would be circular):

- `pluggy_claimed(conn, uid, table, target_id, exclude_item_id=None)`: a live Pluggy row points at
  it. Live means `role <> 'REMOVED' AND COALESCE(conflict, '') <> 'vanished'`.
- `notification_claimed(conn, uid, table, target_id, exclude_item_id=None)`: a `notify_detections`
  row with role `SOURCE`, `PAIRED` or `MATCHED` points at it.
- Rows typed by the owner have no claim, so they are free for both channels.

Then switch every caller:

| Where | Today | After |
|-------|-------|-------|
| `existing_rows()` (`inbox.py:1224`) | `for_notification=True` drops what `_explained_by_notification()` (`:1283`) says, for any source | `claimed_by="notify"` or `"pluggy"`: drops only rows claimed by **that** channel. Callers: `inbox.py:1657` (notification → `"notify"`), `open_finance_inbox.py:989` (Pluggy → `"pluggy"`) |
| `free_candidates()` (`inbox_defaults.py:104`) | blocks a candidate targeted by another item unless that item's only sources are vanished Pluggy rows **and it has no detections**, so a notification item always blocks | the item's channel: Pluggy if it has a Pluggy `SOURCE`, else notify. A candidate is blocked only by a claim of the **same** channel from another item |
| `_linked_elsewhere()` (`open_finance_auto.py:156`; also the history preview, `open_finance.py:998`) | Pluggy claims, ignoring vanished | `pluggy_claimed()` |
| `notification_item_for_open_finance()` (`inbox.py:1822`) | `NOT EXISTS` any Pluggy row with `role <> 'REMOVED'` | also ignore `conflict = 'vanished'`. A free `PLUGGY` slot is what counts |

Delete `_explained_by_notification()` once nothing calls it.

### 2. Pluggy succession: pending → posted under a new id (defects A and B)

Pull order today (`_sync_item_locked()`, `open_finance.py` around 760–815): for each account,
normalize, then `vanish_missing()` **before** the batch `ingest()`. Change it to:

1. Per account, compute *missing* without writing anything. New function `missing_rows(...)`, the
   same selection as `vanish_missing()` (`open_finance_inbox.py:1225`) plus `MATCHED` and `PAIRED`
   rows. Exclude:
   - broker lines (`target_id LIKE broker_statement.ID_PREFIX || '%'`): keep their behaviour;
   - `COVERED` rows;
   - `INVOICE_PAYMENT` rows: `_kept_payment()` already links a re-id'd payment.
2. `ingest()` the batch. For a **new** `dedup_key` (the `existing is None` branch, line ~360), call
   `successor_for(conn, uid, account, tx, missing)` before `place()`.
3. After the batch, vanish only the missing rows nobody took over:
   - `SOURCE`/`UNMAPPED`: as `vanish_missing()` does today;
   - a `MATCHED`/`PAIRED` row without a successor gets `conflict = 'vanished'` (new; today it stays
     a silent live claim);
   - **keep the empty-pull guard**: when Pluggy returned no ids for that account (`seen` empty),
     nothing recorded is vanished, as today.

**`successor_for()`**: one-to-one; once a missing row is taken, remove it from the set. All of:
- same `of_account_id` and `direction`;
- same `amount_cents`, or `inbox.rounded_up()` when `open_finance_rounds_up(account)`;
- same `installment_number` and `total_installments` (a 2/3 never succeeds a 1/3);
- date gap ≤ 3 days.

Tie-break: same normalized description, then the nearest date, then the oldest id. Near-amount
succession is Phase 1b, not here.

**`hand_over(conn, uid, old, tx)`**, in one transaction:
1. Insert the new row like `ingest()` does, copying from the old one: `role`, `item_id`,
   `target_table`, `target_id`, `auto_recorded_at` and `recorded_snapshot`; `conflict` NULL.
2. Old row: `role = 'REMOVED'`, `superseded_by = <new row id>`. Use the new migration (number
   picked after merging `origin/main`; column `superseded_by TEXT` on `open_finance_transactions`).
3. `transactions`:
   `SET source_id = <new pluggy id> WHERE id = target AND user_id = ? AND source_type IN
   ('OPEN_FINANCE', 'BANK_INVESTMENT') AND source_id = <old pluggy id>`.
   A row the owner typed, or one a notification created, has another source and stays as it is.
   The unique index `idx_transactions_user_source (user_id, source_type, source_id)` cannot
   collide, because the new id is new; a test proves it.
4. `cc_expenses`: `SET client_id = <new dedup_key> WHERE user_id = ? AND client_id = <old
   dedup_key>`, for **all installments**. Receipts hang off expense ids and sharing off `client_id`,
   so both follow.
5. `inbox_items.client_key`: from the old dedup key to the new one.
6. Snapshots: `target_snapshot()` holds neither `source_id` nor `client_id` (checked:
   `TRANSACTION_SNAPSHOT_COLUMNS`, `CARD_SNAPSHOT_COLUMNS`), so the copied snapshot stays valid. If
   you also move the date (next point), recompute it with `mark_auto_recorded()` and the item's
   `recorded_snapshot`.
7. The posted row's details (`description`, `posted_on`, `bill_month`, date) go on the new row.
   If its date differs and the lançamento is untouched (`untouched()`) and its own target
   (`own_target()`), move the lançamento's date, the same rule as `reconcile_recorded()`'s "bank
   disagrees".

Return a new status `succeeded`, counted in the pull log.

**Card mirror check**: `mirror_cards()` (`open_finance_invoices.py:288`) only mirrors purchases
whose `client_id` starts with `pluggy:`, and finds the anchor by `target_table`/`target_id`. After
a card succession, test that the installments and invoices are unchanged and that a later mirror
still moves them.

### 3. A guessed side of a recorded transfer follows the bank (defect R)

Today the BTG Investimentos app alone notifies R$ 500 in, and `guess_other_side()` picks "BTG
conta corrente". When Pluggy shows the money left Itaú, `open_finance_fits_item()` accepts the Itaú
row (the origin was only a guess), and `reconcile_recorded()` only **links** any `TRANSFER`. The
origin stays wrong, so two balances are off by R$ 500.

In `reconcile_recorded()` (`open_finance_inbox.py:918`), before the "transfer → only link" return:
- **When**: the item is a `TRANSFER`; the side this row is on (`account_id` for OUT,
  `transfer_account_id` for IN) holds another account; that side is in `item.guessed` and not in
  `item.edited`; and the transaction is unchanged against the item's `recorded_snapshot` (compare
  the snapshot; don't use `notification_untouched()`, which also requires review).
- **Then**: set that side to the Pluggy account in `transactions` and in the item, drop the guess,
  recompute the description with `_transfer_description()`, refresh the snapshots, and link the
  row.
- **Never**: both sides on the same account, or a foreign (Conta global) account. A non-active
  account is refused.

### 4. Invariant helper and server script

- `backend/tests/identity_check.py`, a helper module that imports `db` only inside the function:
  `assert_identity(user_id)` fails when any of these holds:
  1. one lançamento is targeted by two live Pluggy rows **of the same direction**. A transfer
     legitimately has one per side; broker lines are their own;
  2. one lançamento is targeted by two live bank-app detections, or two Samsung detections, of the
     same direction;
  3. one item has two live Pluggy `SOURCE` rows of the same direction.

  Call it at the end of **every** test in the new file.
- `backend/scripts/check_identity.py --email <email>`: the same checks, read-only, printing the
  violations. Open SQLite read-only (`sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, path from
  `config.DATABASE_PATH`). **Never import `app`**: `app.py` runs `init_db()` at import, which
  migrates. The owner runs it on the server as
  `sudo docker compose exec -T -w /app/backend app python scripts/check_identity.py --email <email>`
  (DEPLOY.md's pattern). In normal use it prints nothing.

## Tests: `backend/tests/test_notify_pluggy_identity.py`

Use `pytestmark = pytest.mark.usefixtures("any_bank_notifications")` and the fixtures below. This
is the probe that found A and B; reuse it.

```python
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import confirm, notifications_on, rows_of
from test_inbox import ITAU, detection, ms, send

@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    client.patch("/api/open-finance/settings", json={"auto_record": True}, headers=auth)
    return World(client, auth, fake_pluggy)

def _setup(world):
    item_id, _p, made = connected(world, connector_name="Itaú")
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    return item_id, made

# A: notification -> owner reviews -> Pluggy PENDING -> POSTED under a new id
send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
[row] = world.transactions(mine)
confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
pending_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
world.sync(item_id)
world.fake.drop_tx(made["bank"][0], pending_id)
world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
world.sync(item_id)
# today: 2 rows. Expected: 1 row, the SAME id as `row`.
```

R uses `meupluggy(world)` and `auto_on(world)` from `test_open_finance_auto.py`:
- `send(..., detection("TRANSFER_IN", 50000, at=..., app="com.btg.pactual.digital.mobile", merchant=None))`;
- then `bank_tx(-500, ..., category_id="04000000")` on `made["itau:0001/1-1"][0]`;
- then `bank_tx(500, ..., "RECEBIMENTO TRANSFERÊNCIA", category_id="04000000")` on
  `made["btg:0002/2-2X"][0]`;
- sync both items.

Each case asserts the rows **and** `assert_identity()`:

| Case | Expected |
|------|----------|
| A, reviewed, new id | 1 row, same id, `source_id` = new Pluggy id; old row `REMOVED` with `superseded_by` |
| B, untouched, new id | 1 row, **same id** (today it is re-created) |
| B on a card purchase (`connected(..., bank=False, card=True)`, `card_tx(..., status="PENDING")`) | 1 purchase, installments intact, `client_id` = new `pluggy:` key, receipt still attached |
| BB rounding (`connected(world, connector_name="Banco do Brasil")`), pending 19,00 → posted 19,00 new id after a notification of 18,19 | 1 row |
| two pending R$ 8 → two posted R$ 8, new ids | 2 rows, each kept its id |
| pending 1/3 vanishes, posted 2/3 appears | no succession across installment numbers |
| pull returns nothing for the account | nothing vanishes, nothing succeeds |
| a `MATCHED` row whose id leaves with no successor | `conflict = 'vanished'`; the Conferência lists it |
| C–H of design §1 (twins, either order, 3× twins, Pix to the Corretora) | still correct (regressions) |
| R, guessed origin | 1 transfer **Itaú → BTG Corretora**; balances of Itaú and BTG conta corrente right |
| R, but the owner had edited the origin | stays as edited; the Pluggy row only linked |

## Pitfalls

- `test_auto_record.py`'s `TestPluggyReconciles` and `test_open_finance_auto.py` must stay green
  **unchanged**. If one fails, your claim scoping is wrong, not the test.
- Don't make Phase 1b's changes here (absorb, one-sided transfers, near match). Small phases are the
  point.
- `superseded_by` is new; nothing else may read it as "live". Every live-claim query already
  filters `role <> 'REMOVED'`; grep `open_finance_transactions` for queries that don't, and decide
  for each.

## Done when

The new test file is green with `assert_identity()` everywhere, the full suite is green on a tree
merged with `origin/main`, and CLAUDE.md's Open Finance bullets say how succession and per-channel
claims work. Finish as in `00-common.md`; the next prompt is `01b-absorb-near-match.md`.
