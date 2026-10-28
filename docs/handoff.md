# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-28 (10) · Conta investimento (liquidação D+2), merged and pushed

Finished the pending `claude/settlement` work: fast-forwarded the APK commit from the worktree
branch `claude/settlement-apk` onto it, ran every suite, merged into `main` and pushed (deploys).

### Done
- Backend/web (`e5a4c0a`): the Corretora lançamento of an operation is dated on the liquidation day
  (`services/settlement.py`: D+2 business days on B3 with its holiday calendar, D+1 abroad, same day
  otherwise; `metadata.settlement_date`/`settlement_amount` override; Pluggy's `netAmount` fills the
  amount). `GET /api/investments/settlement` (`services/broker_cash.py`) feeds the Conta investimento
  card in Posição: saldo hoje, em trânsito (operations + announced proventos), saldo. The first read
  moves old rows still on the trade date (`resync_investment_cash_dates()`).
- APK (`2049d54`): the same card in Posição (`rules/BrokerSettlement.kt`, `BrokerSettlementTest`).
- Tests: pytest full suite, `npm test` 204, Android JVM 537 — all pass; `vite build` OK.

### Not done, and why
- Not checked on the owner's real data: the resync moves existing Corretora rows to D+2 on the first
  read of `/api/investments/settlement` — the Corretora balance "hoje" drops by trades of the last 2
  business days, which is the intent, but have the owner look at Posição after the deploy.
- The B3 holiday calendar is computed (fixed + Easter-based); a one-off holiday decreed by B3 is not
  known — use `metadata.settlement_date` on that operation.

### Next session
1. Owner: open Investimentos › Posição (web and APK) and compare Conta investimento with BTG.
2. Then the open items in `next-steps.md` (Open Finance walk-through, conta-global data steps).

### Lessons (non-obvious)
- A worktree subagent's work lives on its own branch (`claude/settlement-apk`); check
  `git worktree list` before calling a feature branch finished.

---
