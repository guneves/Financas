# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-01 · Every Pluggy movement enters the moment Pluggy has it, whatever it is

Owner reported (phone screenshot, BB, 31/10 22:20): "received R$ 400, Open Finance recognized it, the app did not".
Conferência: no banco R$ 225,00 · no app −R$ 175,00 · Diferença R$ 400,00 = R$ 200,00 "esperando no Revisar" +
R$ 200,00 "de antes da conferência". The money came from other people. Owner: "Pluggy should update it the moment it
got the information… every transaction… no matter what the transaction is".

What kept money out of the balance, and what changed (code and tests; **not deployed, not seen on production**):
- **The 2-day Pix hold** (`TRANSFER_HOLD_DAYS`): gone from the pull. A Pix to/from someone else is recorded in the
  pull that brings it.
- **One-sided own transfers waited forever**: now `one_side_now()` records the side the bank saw as a despesa/receita
  (`needs_review = 1`). When the other side arrives from another bank, `_absorb_recorded_pix()` turns that same row
  into the transfer (untouched, still to review, same cents, opposite direction, another reais account, ±1 day,
  counterparties that can be one person). Both sides in one pull still pair before recording.
- **Pix to the Conta global** waited for the dollar side: now a despesa in reais at once; the Wise credit turns it
  into the transfer with its dollars (`_absorb_recorded_real_side()`, mirror of `_absorb_recorded_dollar_income()`).
- **Another currency on a reais account** waited for the owner: `in_reais_now()` uses the day's PTAX; only without
  a PTAX yet does it wait for the next pull.
- **Pending bank rows were skipped**: migration 052 and `include_pending()` make "Trazer pendentes" on by default
  (and on for whoever had it off). A pending row that posts under a new id is `vanished`; the posted row now links to
  the same lançamento even if the owner edited it (`free_candidates()`, `_linked_elsewhere()`,
  `_explained_by_notification()` ignore vanished sources). Before this, an edited pending row + its posted version
  were two rows (test proves it).
- **The app read Pluggy only every 6 h**: `open_finance_refresh` ticks every 5 min; besides the due pull,
  `sync_fresh_items()` does one `GET /items/{id}` per connection and pulls at once a connection whose `lastUpdatedAt`
  moved. GET only (no PATCH, no CPF quota).
- Items already waiting on production are recorded by the first pull after the deploy (`record_pending()`).
- Texts (web and APK): the "Gravar sozinho" hint and the Revisar waiting notice.

**Not done and why:**
- No production access: I could not see the real rows behind the owner's R$ 200 + R$ 200. Pending rows and the
  removed hold should cover both; confirm on the BB Conferência after the deploy.
- **Itaú's ported salary is listed `PENDING`** beside BTG's TedSalary (next-steps). With pending on it may be recorded
  as a second income: check Revisar after the first pull and delete/mark it, or turn "Trazer pendentes" off.
- The Flash notification path (`auto_record.py`) still holds a one-sided transfer / another currency: Flash only,
  never those, so untouched.
- The APK was not built here (only Kotlin strings changed).

Lessons: a hold that hides an item from both the balance and Revisar reads as "the app ignored my money". Test dates
for vanish must sit inside the fake world's window (today 2026-10-27), or the pending row is never seen as gone and
the test passes for the wrong reason.

Next: deploy, watch the 5-minute fresh pulls in the log, read BB's Conferência and Revisar (Itaú salary).
