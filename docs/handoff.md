# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-26 (later) · Proventos per asset, time-weighted return, aportes and concentration

One coordinating session, three `general-purpose` subagents each in its own git worktree
(`isolation: "worktree"`), merged into main one by one. `session-scout` opened the session and
`finance-guard` audited the merged result twice (proventos + aportes, then TWR): **no findings**.

### What was done

- **Proventos per asset** (`3c6ac06`): proceeds reads moved to `services/proceeds.py`
  (`routes/proceeds.py` is write-only now); `by_asset` in `GET /api/investment-proceeds/summary`;
  per-asset `proceeds_net`, `proceeds_12m_net`, `dividend_yield_12m`, `total_return_percent` in the
  portfolio snapshot; goals' 12-month income reads the new service. Frontend: Proventos "Por ativo"
  + Mensal/Anual toggle + record date on phone; Posição "Proventos" and "Rentab. c/ proventos".
- **Time-weighted return** (`bfec9d5`): `services/returns.py`, `GET /api/investments/returns`,
  new tab Investimentos → Rentabilidade (`/investimentos/rentabilidade`, lazy page in `App.jsx`).
  `build_portfolio_evolution()` now sums `iter_portfolio_months()`; its output is unchanged.
- **Aportes x resgates + concentration** (`a70edcf`): `GET /api/investments/contributions`
  (in the *allocation* blueprint, to avoid colliding with the TWR work), chart on Operações;
  `concentration` in the allocation response, warning on Alocação.
- Decisions I made on the owner's behalf (the plan marked them as owner calls): TWR, not XIRR;
  **gross** values; a new tab rather than inside Posição; "Rentab. c/ proventos" added *next to*
  "Rentab."; total return's base = all money ever put in. Contributions and concentration came from
  the "needs the owner's call" survey list — the owner asked for at least three tasks this session.
  Method details in `done-tasks.md`.
- Suite: 787 tests pass (741 + 46). `npm run build` clean. CLAUDE.md updated (count, layering,
  services list, chart colours).

### What was not done and why

- **Nothing was opened in a browser.** Three UIs landed at once; the owner walk-through item in
  `next-steps.md` lists what to look at. Posição now has 9 columns — check the 1280px layout first.
- Follow-ups in `next-steps.md`: no class filter on Rentabilidade, no provento columns in the
  carteira export, `tax_report.proceeds_rows()` not folded onto `services/proceeds.py`.
- Returns per asset on Rentabilidade show TWR only; simple and total return live on Posição.
- Still open from before: **restart the backend** (the `:5000` process predates migrations 015–021
  and now these endpoints); decisions 3 and 4 belong to the owner.

### Learned

- **Worktree agents may start on a stale commit.** All three worktrees were created at `36e0164`
  (39 commits behind main); each agent noticed and fast-forwarded to main before working. Tell a
  worktree agent to check `git log -1` against main first.
- Worktrees have no `node_modules`: a directory junction to the main tree's works for
  `npm run build`; remove it with `cmd /c rmdir`, never a recursive delete.
- The two parallel backend changes to `services/portfolio.py` (snapshot vs evolution) merged
  cleanly; the only conflict was adjacent lines in `test_route_map.py`.
- `CHART` in `charts.jsx` has only grid/axis/tick/ink colours; series colours are `FLOW`/`SERIES`.
- "FII" is stored as the `REIT` class.
