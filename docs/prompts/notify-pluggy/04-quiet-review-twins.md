# Phase 4: review only what is a guess; twins get a quiet badge

Read `00-common.md` first. Design: §3.5, §3.6 and §7 decisions 4 and 6. Server, web and APK.

**Prerequisites:** Phases 1–3 on your branch (merged in from session 3's branch). Phase 5
(`05-orphans-by-balance.md`) follows in this same session.

```bash
grep -n "def pluggy_claimed" backend/services/inbox.py
```

```bash
grep -rn "recorded_snapshot" backend/services/ | grep -v open_finance_inbox.py | head -3
```

## The trap to avoid first

`notification_untouched()` (`open_finance_inbox.py:874`) returns False when the row no longer
awaits review (`review.awaiting()`). If the server clears review by itself, every confirmed row
starts counting as "touched". From then on, the bank's later corrections (date, card, a vanished
row, the near match) silently stop. So, **before** clearing anything:

1. Redefine "untouched" as **snapshot equal**, for notification items and Pluggy rows alike. Keep
   the snapshot as the only test of what the owner changed. `category_id` is in the snapshot: an
   owner who changes the category has touched it, while an owner who only says "É meu" has not.
2. Whenever the **server** changes a recorded row (a category it decides, clearing review),
   refresh the item's `recorded_snapshot` and the Pluggy rows' (`mark_auto_recorded()`) in the same
   transaction.
3. Check every user of `notification_untouched()`, `untouched()` and `review.awaiting()`
   (`auto_record.undo_declined`, `reconcile_recorded`, the absorb helper from Phase 1b) and add a
   test for each. In each test the bank's change still applies **after** the review was cleared
   automatically.

## What to build

### 1. Review clears itself when the category is certain

- **Where**: after a Pluggy row confirms a lançamento. That is `reconcile_recorded()`'s untouched
  path, `open_finance_auto.record_item()` after recording, and the near match from Phase 1b.
- **How**: compute `category_decision()` for the Pluggy row (`open_finance_inbox.py:1067`). If its
  source is in `CONFIDENT_CATEGORY_SOURCES` (rule, merchant, cnae):
  - set that category when the row's category is still the automatic one (snapshot equal);
  - set `needs_review = 0`;
  - refresh the snapshots.
- **A transfer** with both sides present clears review too.
- **These keep review:**
  - Flash rows and any account without Pluggy;
  - rows whose category came from `pluggy` or `default`;
  - Conta global rows: reviewed on their own screen, unchanged.
- **Order**: the same pass that records must clear it, so the Revisar count (`review_count` of
  `GET /api/home`) never shows a row for a moment and then drops it.

### 2. Twins: the "2× igual" badge

- **Server** adds `twin: true` to rows of `GET /api/transactions` (and the paged
  `services/transaction_pages.py`), `GET /api/review` and `GET /api/cc-expenses/statement`. Two
  rows are twins when:
  - they are both expenses (`EXPENSE` or card purchases);
  - same account (or card), same cents and same `inbox.normalized(description)`;
  - their `occurred_at` are ≤ 60 min apart when both have a time, otherwise the same date.
- Query only the page's date range ±1 day, with `user_id` in the query.
- **Web**: a neutral `Badge` from `ui.jsx` with "2× igual". Use no green, red, amber or sky; a twin
  is neither a gain, a loss nor a warning. It goes on the Extrato row and in `ReviewPanel`.
- **APK**: the same text on the Extrato row and in `ReviewSection`.
- No attention card, nothing to dismiss, no action.

## Tests

| Case | Expected |
|------|----------|
| notification + Pluggy agree, merchant-table category | `needs_review = 0`, category from the table |
| same with a Pluggy-tree category | stays in review |
| Flash purchase | stays in review |
| both sides of an own transfer | review cleared |
| **auto-cleared row, then the bank changes the amount** (untouched otherwise) | amount follows (`apply_change`) |
| **auto-cleared row, then the bank drops it** | removed (`apply_vanish`) |
| **auto-cleared row; the other side of an own transfer arrives** | still absorbed |
| owner said "É meu" without changing the category; bank posts another date | date follows |
| owner changed the category; bank posts another date | stays; only linked |
| two R$ 8 coffees 4 min apart | both `twin: true` |
| same, 2 h apart | not twins |
| different merchant | not twins |
| two identical card purchases | both twins in the card statement |

Add node and JVM tests only for client rules you add (rendering a server flag needs none).

## Done when

All green on a tree merged with `origin/main`; android-check green. CLAUDE.md's Review section says
what clears review by itself and the new definition of "untouched". Commit, then continue with
`05-orphans-by-balance.md` in this same session.
