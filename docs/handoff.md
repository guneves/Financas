# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · Design: notifications + Pluggy, one movement one row (decided)

Owner asked for the best way to integrate notifications with Pluggy. There should be no overlap and
no duplicates, a real purchase made twice must be recognised as two, investments are Pluggy-only,
and notifications deliver only transfers to and from BTG Investimentos. Then the owner asked for
"the best scenario for each, no friction".

**Done:** `docs/notifications-pluggy-design.md`. It covers:
- the channel model and invariants I1–I5, with the twin-count argument;
- the matching windows, and the step-by-step for a notification and for a Pluggy row;
- the channel policy and investments Pluggy-only;
- five phases;
- §7, the decisions table. The rule: the owner types, answers and cleans nothing, and balances stay
  right.

The decisions:
1. **Orphans:** the bank's balance decides; no prompt.
2. **Samsung Wallet:** Flash card only.
3. **Investments:** typing refused on the Corretora; `HELD` lines fill themselves from Pluggy's
   position data where present.
4. **Twins:** both kept, with a quiet "2× igual" badge and no card.
5. **Bank notifications:** on by default, after Phase 1.
6. **Review:** only category guesses are reviewed.
7. **One-sided own transfers:** never wait.

**How it was grounded:** scratch probes against the real engine, not committed (the gate opened with
`any_bank_notifications`, `FakePluggy`, pending rows on). Two defects:
- **A:** a reviewed notification row, then Pluggy's `PENDING` id, then `POSTED` under a new id gives
  two rows. The old id stays a live `MATCHED` claim, because `vanish_missing()` skips `MATCHED` rows
  outside the broker. And `_explained_by_notification()` hides the row from the new id.
- **I:** an own Pix Itaú → BB whose two notifications reach the server in **separate uploads** gives
  INCOME + EXPENSE. In one upload it gives one transfer. The second side only looks for pending items
  or recorded transfers. Pluggy would then pair each side with its own row, so the split stays (by
  reading the code, not probed).

Correct: twins in every order, Pluggy first then the notification, two identical 3× card purchases,
and a Pix to BTG Investimentos on both sides. Untouched case B keeps one row but re-creates it.

**Not done, and why:** no code. The request was design and decisions. Phase 1 is next and must land
before the gate opens, or A and I happen on real data.

**Next:** Phase 1 (succession, channel-scoped claims, the shared absorb helper, tests A–I,
`scripts/check_identity.py`). Phase 3 starts with one real GET of BTG `/investments`. Whether
MeuPluggy fills `rate`/`rateType`/`fixedAnnualRate`/`dueDate`/`issuer` is unknown;
`_save_positions()` keeps none of them today.

Lessons:
- Probing beat reading twice. The old Pluggy id stays `MATCHED`, not `vanished`. And the own-transfer
  split only shows when the two sides are sent in separate requests; the existing test sends them
  together, which is why it passes.
- A card-mirror probe also left a dropped `PENDING` installment of a single purchase in place. It may
  be the fake's window, and it is not about duplicates; not investigated.
