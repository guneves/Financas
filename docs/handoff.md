# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-01 · Every Pluggy movement enters the moment it arrives

Owner reported (phone screenshot, BB, 31/10 22:20): "received R$ 400, Open Finance recognized it, the app did not".
The Conferência read: no banco R$ 225,00 · no app −R$ 175,00 · Diferença R$ 400,00 = R$ 200,00 "esperando no Revisar"
+ R$ 200,00 "de antes da conferência". Owner: the money came from other people; "Pluggy should update it the moment it
got the information… every transaction".

Why it didn't move: an incoming Pix was held `TRANSFER_HOLD_DAYS` = 2 (in case another bank's pull brought its other
side), and an own transfer with one side waited until the other side came, forever if it never did. Meanwhile
`awaiting_bank()` kept the item out of Revisar, so the screen said "espera no Revisar" and Revisar showed nothing.

Done (code and tests; **not deployed, not seen on production**):
- `open_finance_auto.hold_reason()`: only a one-sided transfer to/from the Conta global still waits (the dollar side).
  A Pix to/from someone else is recorded in the pull that brings it.
- `one_side_now()`: a one-sided own transfer becomes the despesa/receita of the side the bank saw, `needs_review = 1`.
- `open_finance_inbox._absorb_recorded_pix()` (step 3 of `place()`): when the other side arrives from another bank,
  the recorded, untouched row (still `needs_review = 1`, same cents, opposite direction, another reais account,
  ±1 day, counterparties that can be one person) becomes the transfer; the new row joins its item. Reviewed or edited
  rows are left alone. Both sides in one pull still pair before recording.
- Items already waiting on production are recorded by the first pull after the deploy (`record_pending()` runs over
  every pending Pluggy item), so the owner's R$ 200 should land then.
- Texts: "Gravar sozinho" hint and the Revisar waiting notice (web and APK) no longer mention one-sided transfers.
- Tests: `test_open_finance_auto.py` (new: recorded now, other side converts, two different people never pair,
  reviewed side kept), `test_pluggy_waits.py`, `test_open_finance_resolve.py`, `test_open_finance_rebuild.py` rewritten
  where they relied on the hold (the waiting case is now a Pix to the Conta global, or the brake).

**Not done and why:**
- The other R$ 200 ("de antes da conferência") is not explained from here: no production access. Most likely a
  Pluggy `PENDING` row (31/10 was a Saturday): bank accounts skip pending rows unless Ajustes › Open Finance ›
  "Trazer pendentes" is on. Not flipped by default because Itaú keeps the ported salary `PENDING` beside BTG's
  TedSalary (a double income). Check after the deploy: if the difference stays at R$ 200, read the BB rows.
- The APK was not built here (only Kotlin strings changed).

Lessons: a hold that hides an item from both the balance and Revisar reads as "the app ignored my money"; the
Conferência's `awaiting` count must agree with what Revisar shows.

Next: deploy, pull, read the BB Conferência; decide "Trazer pendentes" with the owner.
