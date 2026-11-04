# Phase 1b: own transfers absorb across channels, nothing waits, near match

Read `00-common.md` first. Design: §1 (defect I), §3.2 steps 4, 5b and 7, §3.3 step 3b, §3.7,
§6 Phase 1. Server only; invisible while the gate is closed.

**Prerequisites** (stop if any is missing; Phase 1a must be merged, or the owner names its branch):

```bash
grep -n "def pluggy_claimed\|def notification_claimed" backend/services/inbox.py
```

```bash
grep -rn "superseded_by" database/migrations/
```

```bash
test -f backend/tests/identity_check.py && echo ok
```

## What to build

### 1. One absorb helper for both channels (defect I)

An own Pix whose two notifications reach the server in **separate uploads** becomes INCOME +
EXPENSE. To see it today, send each with its own `send()` call:
- `detection("PIX_OUT", 70000, ..., counterparty="Fulano Dono")` from Itaú;
- then `detection("PIX_IN", 70000, ..., app="br.com.bb.android", counterparty="Fulano Dono")`.

The existing test `test_an_own_transfer_waits_for_the_other_side_then_is_one_transfer` sends both
in one call, which is why it passes.

`_absorb_recorded_pix()` (`open_finance_inbox.py:680`) already turns a Pluggy-recorded despesa or
receita into the transfer when the other side arrives, but only for Pluggy rows. Make one helper
both paths call:
- **Where it lives**: watch circular imports. `inbox.py` is imported by `open_finance_inbox.py`,
  and the helper needs `target_snapshot()` and `untouched()`, which live in `open_finance_inbox.py`.
  Move those two (and `_dump`, `_snapshot_cents`) into a new low module, e.g.
  `services/recorded_snapshot.py`, importing neither. Re-export them from `open_finance_inbox` so
  existing callers and tests keep working. Then the absorb helper can live there or in
  `services/own_transfer.py`.
- **Candidates**: a recorded lançamento (`inbox_items.state = 'APPROVED'`, target `transactions`)
  with all of:
  - type `EXPENSE` for an incoming side, `INCOME` for an outgoing one;
  - same cents;
  - another active **reais** account;
  - date ±`TRANSFER_MATCH_DAYS`;
  - `share_mode IS NULL`;
  - its item has exactly one side source;
  - that source is a movement: a detection of `MOVEMENT_KINDS`, or a Pluggy row with movement
    `TRANSFER`/`SELF_TRANSFER`. Never a card purchase or a boleto;
  - counterparties not in conflict (`inbox.counterparties_conflict()`).
- **"Untouched" by snapshot, not by `needs_review = 1`.** Today's query has
  `t.needs_review = 1`. Phase 4 clears review by itself, and that condition would silently switch
  absorption off. Compare the snapshot: the item's `recorded_snapshot` for a notification item, the
  Pluggy row's for a Pluggy item.
- **Conversion**: as today's `_absorb_recorded_pix()` (UPDATE to `TRANSFER`, item fields). The
  incoming observation joins the item: a detection `SOURCE` with `item_id`/target, or the Pluggy
  row `SOURCE`. Refresh both snapshots.
- **Call it from:**
  - `_ingest_alone()` step 1 (`inbox.py:1602`), after `approved_transfer_awaiting()` and
    `transfer_partner()` find nothing, for `MOVEMENT_KINDS` with an account;
  - `place()` step 3, in place of `_absorb_recorded_pix()`.

### 2. A one-sided own transfer never waits

`auto_record.hold_reason()` (`auto_record.py:51`) returns `awaiting_transfer` for a one-sided
`TRANSFER` item, which then waits in "Não gravou sozinho". Change it to:
- **Convert and record**: before approving, the item becomes the despesa/receita of the side the
  notification saw, the way `open_finance_auto.one_side_now()` does for Pluggy. Same fields:
  category from `suggest_category()`, `reason = "external_transfer"`, the description from the
  detection. It is recorded at once, and step 1 makes it the transfer when the other side arrives.
- **Exceptions (keep waiting, or keep today's rule):**
  - **The Corretora.** A one-sided transfer touching the Corretora never becomes despesa/receita: an
    INCOME/EXPENSE on the broker account would distort Investimentos and Resumo. It stays a
    `TRANSFER`, with the guessed bank side when `guess_other_side()` finds one (Phase 1a fixes the
    guess later), or it waits for Pluggy, which brings both sides.
  - **The Conta global** (foreign currency): its own rules (`global_account.py`), unchanged.

### 3. Near match: same purchase, different amount (design §3.7)

**Eligibility, both sides:**
- **Notification side**: an item whose `SOURCE` detection kind is in `PURCHASE_KINDS`, with a
  merchant and 1 installment.
- **Pluggy side**: a row with `movement IS NULL`, direction `OUT` and 1 installment
  (`total_installments` NULL or 1).

  Never: Pix, transfers, refunds, invoice payments, installments > 1, the Corretora, the Conta
  global.

**Pluggy arrives second (the pull):**
- **When it runs**: a new pass in `_sync_item_locked()` **after** the batch `ingest()` and **before**
  `record_pending()`. Run it later and the Pluggy item is already recorded, and you would be
  deleting a row.
- **What it looks at**: Pluggy items created in this pull that are still `PENDING` with no exact
  partner. Their candidates are notification movements with a free `PLUGGY` slot, on a target
  that fits (`open_finance_fits_item()`), in the date window of `notification_item_for_open_finance()`.
- **Conditions**: merchant agrees, amount within the band, and exactly one candidate **each way**.
  Each way means: this Pluggy row has one notification candidate, and that notification has no
  other leftover Pluggy candidate in the pull.
- **Effect**:
  1. the Pluggy item becomes `REMOVED`, reason `near_match`;
  2. the row joins the notification item through the `_join_item()` / `reconcile_recorded()` path;
  3. the bank's amount wins: update `transactions.amount`, or the single `cc_expenses` row, and the
     item's `amount`;
  4. refresh the snapshots.
- **Exception**: when the current amount differs from the item's `recorded_snapshot` amount, the
  owner typed it. Then only link (`MATCHED`) and set the Pluggy row's
  `conflict = 'changed'` with `conflict_amount_cents`.
- **What doesn't block it**: category and review changes. Date and target are re-recorded only
  under today's full-untouched rule.

**Notification arrives second:** add step 5b in `_ingest_alone()`, right after
`open_finance_item_for_detection()` returns nothing.
- **Candidates**: Pluggy-sourced items (`PENDING` or recorded) with no notification `SOURCE`, which
  `_detection_fits_open_finance()` accepts. The notification's target is often a guess, and that
  function already handles it.
- **Conditions**: merchant agrees, amount in the band, and the pair unique each way.
- **Effect**: join (`_join_open_finance_item()`). The row keeps the bank's amount.

**Helpers** (`services/inbox.py`, pure, unit-tested without the DB):
- `merchant_agrees(merchant, *texts)`:
  - normalize with `inbox.normalized()`;
  - true when a token of ≥ 4 letters that is not a stop word appears in the other text, or when the
    space-stripped merchant (≥ 5 chars) is a substring of the space-stripped other ("SMART FIT" vs
    "SMARTFIT");
  - stop words: compra, cartao, debito, credito, pagamento, pagto, transferencia, ltda, eireli,
    comercio, servicos, brasil, internet, online, loja, store, sao, paulo, rio, janeiro;
  - compare against Pluggy's `merchant_name` and `description`.
- `near_amount(notified_cents, bank_cents, international)`:
  `abs(bank - notified) * 100 <= pct * notified`, integers only. `pct` is
  `NEAR_MATCH_FOREIGN_PERCENT` (10) or `NEAR_MATCH_DOMESTIC_PERCENT` (30), new in `config.py` via
  `read_int_env` (config is read once at import; conftest doesn't need to touch them).

**"International":**
- Pluggy side: new column `original_currency` on `open_finance_transactions` (migration). In
  `normalize_transaction()`, keep `raw["currencyCode"]` when it differs from the account currency,
  **before** the `amountInAccountCurrency` swap, and add it to `ROW_FIELDS`.
- Notification side: `parse_detection()` accepts an optional boolean `international` (refuse
  non-booleans). It is stored in a new `notify_detections.international` column (`INTEGER NOT
  NULL DEFAULT 0`) and saved by `_insert_detection()`. A detection whose `currency != 'BRL'` counts
  as international too. The phone sends the flag only from Phase 2; old APKs never send it.

**Near-amount succession**: in Phase 1a's `successor_for()`, when no exact successor exists, accept
a near amount only under the same conditions: purchases, merchant agrees between the old and new
description, unique each way, in the band.

### 4. A foreign-currency notification is recorded at PTAX

`auto_record.hold_reason()` returns `foreign_currency` for `needs` with `amount`, so it waits
forever. For a reais account or card, convert the way `open_finance_auto.in_reais_now()` does
(`fx.rate_on()`): amount × PTAX with `rounded_money()`, `edited` includes `amount`, the currency
becomes BRL. Then record it. The detection keeps the original currency, so near match treats it as
international.
- No PTAX yet (BCB down): it keeps waiting, as today.
- Tests patch where the name is read: `services.fx.fetch_bcb_window` plus `reset_fetch_throttle()`
  (CLAUDE.md), or `fx.rate_on` in the module that calls it.
- The Conta global keeps its own rules.

## Tests (extend `test_notify_pluggy_identity.py`; `assert_identity()` after each)

| Case | Expected |
|------|----------|
| I: own Pix, sides in **separate** `send()` calls | 1 `TRANSFER` Itaú → BB |
| I, then both Pluggy sides | still 1 transfer, both Pluggy rows linked |
| one side notified, Pluggy brings the other | 1 transfer (the notified row converted) |
| one side to a third party (counterparty conflicts) | stays despesa |
| own transfer, one side seen, nothing else | recorded as despesa/receita at once, `GET /api/inbox` waiting is empty |
| one-sided transfer into the Corretora with no guess | **not** recorded as income; waits |
| J: notified R$ 52,30 `international: true` → bank R$ 55,10 | 1 row of R$ 55,10, same id |
| K: notified R$ 100 → bank R$ 112, same merchant | 1 row, R$ 112 |
| L: bank R$ 55,10 first, then the notification of R$ 52,30 | 1 row |
| M: two notifications at one merchant (R$ 30 and R$ 40) + one bank line R$ 34 | no near pair (ambiguous): 3 rows until the orphan rule |
| N: Pix R$ 100 notified, bank Pix R$ 105 | 2 rows (never near) |
| different merchant, same amounts as K | 2 rows |
| outside the band (R$ 100 → R$ 140, domestic) | 2 rows |
| card purchase 3× notified, bank 3× with another total | no near match (installments) |
| O: the owner edited the amount to R$ 105 before the bank's R$ 112 | stays R$ 105; Pluggy row `conflict = 'changed'` |
| owner only reviewed and re-categorised, bank R$ 112 | amount becomes R$ 112, category kept |
| P: pending R$ 100 → posted R$ 112 under a new id, same merchant | same row, R$ 112 |
| Q: `currency: "USD"` notification on a reais card | recorded at once at PTAX; the bank's line replaces the amount |
| twins C–H and A, B, R from 1a | still green |

Plus pure tests for `merchant_agrees()` and `near_amount()`, including "SMART FIT"/"SMARTFIT",
"PADARIA BOM PAO"/"COMPRA CARTAO DEB PADARIA", a stop-word-only match ("COMPRA") giving false, and
the band edges exactly on 10% and 30%.

## Pitfalls

- `test_auto_record.py::TestWhatWaits::test_an_own_transfer_waits_for_the_other_side_then_is_one_transfer`
  asserts the old waiting behaviour. Rewrite it to the new rule in the same commit and name it in
  the handoff.
- The near pass must not touch items that Phase 1a's succession took over. Run it after
  succession, and only on items still `PENDING` from this pull.
- `rounded_money()` for every converted amount; cents as integers in comparisons.
- Keep `notification_wanted(detection)`'s signature (the fixture replaces it).

## Done when

All of the above green, the full suite green on a tree merged with `origin/main`, and CLAUDE.md
updated: auto-record (nothing waits), own transfers, the near match. Finish as in `00-common.md`.
Then run `06-verify-and-fix.md` for Phase 1 (1a + 1b) before opening the gate.
