# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-27 · Walk-through inconsistencies (three worktree subagents)

The owner asked to keep working on the plan with one subagent per task, at least three. The only
open items that need no owner input were the three small inconsistencies from the 2026-09-26 Chrome
walk-through; each went to an `isolation: "worktree"` agent, merged into main by this session. No
`session-scout` (read the docs directly). `finance-guard` ran on `e2f7e12..HEAD`: zero findings.

### What was done
- **Posição chart gross** — "Evolução do Patrimônio" bars now use `patrimonioBruto` /
  `ganhoCapitalBruto` (new, additive in `build_portfolio_evolution()`), same basis as the
  "Carteira" headline and the donut; net shows in the tooltip.
- **Rentabilidade = Posição today** — new `position_value_today()` in `services/portfolio.py`, used
  by both `build_portfolio_snapshot()` and the current month of `portfolio_month_positions()`.
  Root cause: the current month re-accrued unrefreshed fixed income from the series and took the
  yfinance month close for stocks/FIIs, while Posição used stored quotes. On a refreshed seed the gap
  was really in stocks/FIIs, not fixed income as logged.
- **Orçamento copy** — "Realizado" hint and two descriptions now match `budget_spend_by_category()`.
- Tests: **844 pass** (6 new). Frontend build passes. CLAUDE.md test count updated (was stale at 836).

### What was not done and why
- Two findings from the agents are **logged in `next-steps.md`, not fixed** — both need the owner:
  budgets on income categories add income into "Realizado"; a position whose running applied value
  goes ≤ 0 (big profitable partial sale) drops out of the monthly valuation but stays in Posição.
- Trade-off accepted: a fixed-income title never refreshed from the BCB now dips in the current TWR
  month until "Atualizar cotações" (consistency with Posição won). Noted under Known limits.
- None of the three changes opened in a browser.
- Still open from before: owner checks of benchmarks, sectors, IRPF text on real data; the **brapi
  1-ticker limit** (owner's call); two IRPF codes to confirm; **restart the backend** (`:5000`
  predates migrations 015–023); the owner walk-through; decisions 3 and 4.
- `docs/negociacao-2026-09-26-23-43-43.pdf` appeared untracked during the session — not ours, left
  out of the commit.

### Next session
Nothing left in `next-steps.md` that Claude can do without the owner: every open item is an owner
check or an owner decision. Ask the owner which of the two new findings / the Investidor10 ideas to
take, or do the walk-through with them.

### Learned
- Worktree agents again started on stale `36e0164`; the fast-forward instruction in the prompt worked.
- `finance-guard` reported "836 tests pass" — it read a stale count; the real run is 844. Pytest's
  `-q` here prints no summary line (addopts); use `-o addopts=""` to get "N passed".
- Scripted edits to `services/portfolio.py` (CRLF) silently turn it LF — check line endings.
- In PowerShell 5.1, `git commit -m @'...'@` with double quotes inside breaks; use `git commit -F`.
