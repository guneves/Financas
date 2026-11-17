# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-17 · The BTG Investimentos guess no longer doubles the BB side; Revisar measured, not removed

**Done (branch `fix/brokerage-guessed-side`, not pushed/merged yet):** the owner's earlier scenario run found that
the BTG Investimentos notice records a whole transfer with the bank side guessed as BTG conta corrente, so when the
money really came from or went to BB, the BB notice became a second row (BB → Corretora: a despesa plus a phantom
BTG → Corretora transfer; the R$ 50 redemption to BB: BB +100 and a fake R$ 50 receita). Pluggy fixed the transfer
but not the extra row.
- Fix: `guessed_transfer_awaiting()` + `move_guessed_side()` (`services/inbox_transfers.py`, re-exported by
  `inbox`). A real side (notification step 1 in `_ingest_alone()`, Pluggy step 3 in `place()`) on another account,
  same cents, ±1 day, takes over a guessed side that no channel observed, not edited, row untouched by the
  snapshot, counterparties compatible. `follow_bank_side()` now delegates to `move_guessed_side()`.
- "BCO DO BRASIL" / "BCO BRASIL" now name BB (`ISSUER_ALIASES`).
- Tests first, 4 failing before the fix: `TestGuessedSide` (BB notice after BTG Inv, both directions, with and
  without Pluggy afterwards; Pluggy-only both directions and orders; an edited guess and a notice naming someone
  else are not moved), `test_bco_do_brasil_names_bb`.
- One private-use ratchet line left `tests/architecture_private_uses.txt` (follow_bank_side no longer reaches
  `inbox._brl_active_account`).

**The "100% automatic, no review" question: not done, measured instead.** `scripts/review_breakdown.py`
(read-only, counts only, `test_review_breakdown.py`) prints today's Revisar queue by reason (only the notice /
Pix to a person / Flash / Conta global / refund / transfer with one side / Pluggy-confirmed with an unsure
category) and, for the last N days, how many auto-recorded rows the owner left as born, corrected (and which
field) or deleted. It was **not run on the real data**: the PC's `finance.db` stops on 2026-11-04 and is full of
throwaway test users, and running on the server is the owner's call:
`sudo docker compose exec -T -w /app/backend app python scripts/review_breakdown.py --email X --days 30`.

**Code-level finding:** `needs_review` changes no total (balance, Resumo, plan, budget never read it; only
`review.py`, the Extrato filter and the badges do). Recording is already fully automatic; review is a flag and a
queue. "Automate everything" therefore means clearing the flag by rule per bucket, not changing the engine. SSH to
the server from this session was refused by the permission layer, so the owner runs the script.

Full backend suite in 4 chunks: all passed.

**Next:** merge the branch (CI deploys); the owner runs the script; turn off review per bucket the owner never
corrects (the likeliest: own transfers observed on both sides already leave by themselves; compras confirmadas
with a Pluggy-tree category might, if the correction rate is ~0).

**Lesson:** two background suite runs writing the same log interleave; stop one before rerunning.
