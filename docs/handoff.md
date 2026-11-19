# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-19 · Everything automatic, phase 2 (investments decide themselves)

**State of the branches** (deploy only at the end, owner 2026-11-18; nothing merged):
`fix/brokerage-guessed-side` (PR #99, open) → `feat/auto-review-phase1` (local) → **`feat/auto-investments-phase2`**
(local, built in the worktree `../Financas-phase2`, whose `frontend/node_modules` is a junction to the main
tree's). Progress table at the top of `docs/automation-prompt.md`.

**Done:**
- Phase 1's backend run finished: chunks 3–4 (the ones killed by low memory) passed, so all four chunks are green
  on `feat/auto-review-phase1`.
- Phase 2, every real `HELD` group has a rule (details and caveats in `docs/automation-prompt.md` › Phase 2):
  equity custody TRANSFER → `DISMISSED auto:custody` when the app holds the quantity on that day; equity
  INTEREST → linked to the computed provento; `rate` 0 + `fixedAnnualRate` → pré (`pre_by_deduction()`);
  fixed-income TRANSFER → BUY at `netAmount`, no cash, unlocking its redemptions in the same pull; AMORTIZATION →
  AMORTIZATION provento; Renda+ without a year → found by `dueDate`; a closed BB fund's lines →
  `DISMISSED auto:closed_fund`.
- Five new `auto_decisions` kinds (`investment_custody`, `investment_proceed_link`, `investment_closed_fund`
  undo → line `HELD undone`, never retaken; `investment_custody_in`, `investment_rate_deduced` are
  `undoable: false`, 409, undone by deleting the operation). Web "Decidido sozinho" shows them.
- A side fix: a redemption now goes to its lot's own asset (a linked typed buy named by the owner used to make
  the redemption land on a second asset and be refused as unbacked).
- Tests: `test_investments_decide_themselves.py` (new); `test_open_finance_investments.py`'s two "TRANSFER/
  INTEREST wait as `type`" cases now expect the new reasons. `npm test` 251 green, `vite build` OK. Backend: all 4 chunks green.


**Not done and why:**
- **Not checked on the real data**: the server was unreachable all session (Tailscale here shows
  `guilhermeserver` offline, ping/SSH time out). Before merging: run `held_dump`-style read-only queries (which
  held line each rule takes, the `rate` 0 titles against a brokerage note or the owner's typed titles, the real
  Renda+ name, whether the BB funds hold quotas, any provisional buy left).
- A fund still holding quotas waits `fund:open`: no fund class (needs the real data to choose class and marking).
- An unmatched equity INTEREST waits `proceed:unmatched`: recording it would double what StatusInvest brings later.
- Phase 3, the APK "Decidido sozinho" list, the Conferência block.

**Next:** the real-data check above (it may change the fund and INTEREST rules), then phase 3 from
`feat/auto-investments-phase2`.

**Lessons:**
- `apply()` re-decides every `HELD` line each pull, so a new rule takes the old held lines on the first pull after
  deploy, and a line whose decision the owner undid must be skipped explicitly (`was_undone()` check in `apply()`).
- A custody rule that compares quantities must run after the pull's buys/sells (they are written in the same
  loop): equity TRANSFERs are decided last.
- A worktree avoids editing files under a running pytest; reuse the main `.venv` by path and junction
  `node_modules`.
