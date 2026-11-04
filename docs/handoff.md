# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · Design: notifications + Pluggy, one movement one row

Owner asked: design the best way to integrate notifications with Pluggy. There should be no
overlap and no duplicates, a real purchase made twice must be recognised as two, investments are
Pluggy-only, and notifications deliver only transfers to and from BTG Investimentos.

**Done:** `docs/notifications-pluggy-design.md`. It covers the channel model (movement,
observation, channel), invariants I1–I5 with the twin-count argument, matching windows, the
step-by-step for a notification and for a Pluggy row, the channel policy table, investments
Pluggy-only, the twin card and the orphan rule. It ends with five phases and five owner
decisions. The plan is in `next-steps.md`, at the top.

**How it was grounded:** a scratch probe (not committed; the gate opened with
`any_bank_notifications`, Itaú in `FakePluggy`, pending rows on). Results:
- **A, the duplicate:** a reviewed notification row, then Pluggy's `PENDING` id, then the same
  movement `POSTED` under a new id, gives **two rows**. The old id stays a live `MATCHED` claim,
  because `vanish_missing()` skips `MATCHED` rows outside the broker. And
  `_explained_by_notification()` hides the row from the new Pluggy id because a notification claims
  it.
- **B, untouched:** one row, but the notification's row is deleted and re-created.
- **Correct:** twins (two R$ 8 coffees, notified or not, in either order), Pluggy-first then
  notification, two identical 3× card purchases, and a Pix Itaú → BTG Investimentos notified on
  both sides then pulled.
- **Parser:** a BTG Investimentos "ordem de compra" text would parse as a `PURCHASE`
  (`NotifyParsers.kindOf()`); the policy gate in the design stops it.

**Not done, and why:** no code. The owner asked for a design, and five decisions (design §7) change
what Phases 3–5 build. Phase 1 is server-only and needs no decision.

**Next:** get the owner's answers to §7, then Phase 1 (succession + channel-scoped claims, tests A–H
as permanent tests, `scripts/check_identity.py`). Opening the gate (Phase 2) needs Phase 1 first,
or A happens on real data.

Lessons:
- A probe against the real engine changed the root cause. Reading the code suggested the old id is
  marked `vanished`; the rows showed it stays `MATCHED`.
- In a card mirror probe, a dropped `PENDING` installment of a **single** purchase was not removed
  either (`FakePluggy` drop + sync). It may be an artefact of the fake's window, and it is not about
  duplicates; not investigated, not listed as a bug.
