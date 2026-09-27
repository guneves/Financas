# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-26 (late) · Chrome walk-through, yield on cost fix

The owner asked for a click-through with Claude in Chrome, then for the one real bug it found to be
fixed. No `session-scout` (short follow-up session). `finance-guard` ran on the fix — see below.

### What was done
- **Chrome walk-through on a scratch DB** (seeded with `seed_three_years_mock`, backend :5002,
  vite :5175; the real `finance.db` untouched): Início, Extrato (search), Cartões, Importar,
  Orçamento, Recorrentes, Metas (created a goal — forecast dez/2029 checked by hand), all six
  Investimentos tabs, "Atualizar cotações", "+ Novo" expense (flows to Extrato, category and
  budget), dark mode, privacy. No console errors; the headline totals reconcile across screens.
- **Yield on cost fixed** (`services/proceeds.py`): an asset's cost is now counted once (average
  of its events' cost at the record date) instead of once per payment; the summary sums per-asset
  costs. Seed 2026 YTD: 1,29% → 5,88%. Tests: 838 pass (2 new). Tooltip on the Proventos by-asset
  column now says "Custo médio nas datas com". Details in `done-tasks.md`.

### What was not done and why
- Three small inconsistencies from the walk-through are **logged, not fixed** (new section in
  `next-steps.md`): Posição chart net vs headline gross, a R$ 25,58 Rentabilidade/Posição gap in
  fixed income, and the Orçamento "Realizado" caption.
- Still open from the previous session: the owner checks of benchmarks, sectors and the IRPF text
  on real data; the **brapi 1-ticker limit** (owner's call, it costs credits either way); two IRPF
  codes to confirm (FII payouts under isentos 99; net vs gross for exclusiva 10/06); **restart the
  backend** (the `:5000` process predates migrations 015–023); the owner walk-through; decisions 3
  and 4.

### Next session
Pick from `next-steps.md` §1 — the three small inconsistencies are quick; the owner walk-through
still needs the owner.

### Learned
- A seeded scratch DB shows Posição and the evolution chart **disagreeing by ~R$ 22k** until
  "Atualizar cotações" is pressed: the seed's fixed-income quotes are left at cost (stale since the
  purchase date) while the chart accrues CDI. Not a bug — refresh before comparing screens.
- `VITE_API_BASE_URL` is the bare origin (no `/api`). Starting vite with
  `Start-Process powershell -ArgumentList '...$env:X="..."...'` drops the variable silently (the
  quotes are stripped) — use a `.cmd` with `set`.
- The Chrome extension worked for the whole session this time (screenshots, `find`, `form_input`
  on selects, typing into React inputs).
