# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-19 (late night) · Planejar's Investir = Início's Investido

Cloud session, owner request: the invested figure in Planejar (Metas/plan) must be the same as
Início's, and Início's rule wins because it counts the money sent conta → Corretora. Scout not
used (narrow task).

### Done
- `month_investment_flow()` in `services/monthly_plan.py` is now SQL over `transactions`, the twin
  of `bankingTransactions()` + `buildMonthlyFlow()` in the frontend: aporte = transfer from a
  non-Corretora account to a Corretora, or an EXPENSE with an investment source type in a
  non-Corretora account; resgate = the reverse (transfer Corretora → bank, INCOME with an
  investment source type outside the Corretora). Before, it summed the portfolio's movements, so a
  buy paid with cash already sitting in the Corretora counted as new money and a transfer that was
  not yet spent did not count. `actual.aportes/resgates/invested`, `progress.invest_*` and the
  INVEST_* flags all read it.
- Tests in `test_monthly_plan.py`: the old buy-based ones now use transfers; new ones for a buy
  from the Corretora (not counted) vs one paid from a bank (counted), and transfers bank↔bank /
  Corretora↔Corretora (not counted). Full pytest suite green (1468).

### Not done, and why
- Not checked against the owner's real data (no access here): owner check in `next-steps.md`.
- The Metas goals themselves (`services/goals.py`) were not touched: they read the portfolio and
  account values, not a monthly flow, so they had nothing to align.
- Last session's open items (server/phone timing of saves, static files uncompressed,
  Rentabilidade's daily loop) are still in `next-steps.md`.

### Learned
- Início's "Investido" includes a provento row paid into a non-Corretora account as a resgate
  (it is `INVESTMENT_PROCEED` and INCOME); the backend twin keeps that on purpose so both screens
  give the same number.
- Never name a backend module after a stdlib one (Python 3.14's `compression` package broke CI
  once; carried from the previous handoff).
