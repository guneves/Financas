# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-26 (night) · Investidor10 ideas: benchmarks, sectors, IRPF text

One coordinating session. The owner picked three of the Investidor10 ideas; each went to a
`general-purpose` subagent in its own git worktree, merged into main one by one. `finance-guard`
audited `4bed1af..HEAD` on the merged result: **no findings**. No `session-scout` — the handoff and
plan were read directly.

### What was done
- **Benchmarks on Rentabilidade** (`58f5092`, migration **023** `benchmark_closes`): IPCA, Ibovespa,
  IFIX, IDIV next to CDI, as toggleable cards/lines. Live run on a scratch DB: Ibovespa +25.47% (12m,
  yfinance `^BVSP`), IPCA 11/12 months, IFIX/IDIV unavailable.
- **Allocation by sector** (`e74ec70`, migration **022**, sector columns on `assets`): brapi
  `/quote/list` fill, manual override (never overwritten), "Por setor" panel on Alocação, three new
  routes.
- **IRPF copy-paste text** (`e4c34b4`): `backend/irpf_text.py`, pure formatting over the IR report,
  returned inside `GET /api/tax-report`; "Copiar" per section on the IR tab.
- **Merge fix** (`f6690fc`): both branches had added a `_request_json` to `brapi_client.py` with
  different signatures — the later definition shadowed the first and broke three brapi tests. Sector
  helper renamed `_request_list_json`.
- Suite: **836 tests** pass (796 + 17 + 12 + 11). `npm run build` clean. Details in `done-tasks.md`.

### What was not done and why
- **Nothing opened in a browser** — the three features are owner-check items in `next-steps.md`.
- **brapi 1-ticker limit, not fixed**: the owner's plan rejects multi-ticker quote calls
  (`QUOTES_PER_REQUEST_EXCEEDED`) while `MAX_SYMBOLS_PER_REQUEST = 20`, so batch refreshes silently
  fall back to yfinance. It costs credits either way, so it is the owner's call (in the plan).
- **Two IRPF codes to confirm** in the 2026 program: FII payouts under isentos 99, and net vs gross
  for tributação exclusiva (JCP 10 / aplicações 06). CNPJs are always "(preencher)".
- Still open from before: **restart the backend** (the `:5000` process predates migrations 015–023);
  the owner walk-through; decisions 3 and 4.

### Learned
- **Parallel branches touching the same module can merge cleanly and still break**: git merges two
  new functions with the same name without a conflict. After merging worktree branches, always run
  the full suite on main, not just trust each branch's green run.
- IFIX and IDIV have no free monthly history (yfinance and brapi return only today's value); the app
  now stores every close it sees, so their history starts 2026-09.
- brapi's `/v2/stocks/quote` has no sector; `/quote/list` has sector (English) and subsector.
- Worktrees again started at a stale commit (36e0164 for one); all fast-forwarded as instructed.
