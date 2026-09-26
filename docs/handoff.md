# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Sessions — 2026-09-26 · Recurring pause window, carteira export fixes, allocation / goals / exemption meter

Several Claude sessions worked in the same tree at once, coordinated by one that owned no files.
Each committed only its own files and hunks, in order: exports, recurring, then allocation/goals (020–021; 022 was reserved and not used).

### What was done

- **Open decision 2 — recurring pause/resume (migration 019).** Pausing stores `paused_at`.
  Resuming appends the window `(paused_at, resume day)` to `pause_gaps`, exclusive at both ends, and
  leaves the cursor alone. So an occurrence that was due before the pause (or on the pause day) stays
  pending, and only those strictly inside the pause are skipped. `/run`, the pending count and the
  forecast all walk dates through `recurring_occurrence_dates()` → `skip_pause_gaps()`. `/run` drops
  a window once the cursor passes it. The related bug is fixed too: a stored `last_occurrence_date`
  cursor (backfilled by 019, never moved back) now drives revival, so deleting the last generated
  lançamento and extending `end_date` no longer regenerates it. Recorrentes shows "pausada desde
  dd/mm" and the hint text explains the rule. Details in `done-tasks.md`.
- Carteira export fixes (2026-09-26, a735ee3): whole xlsx quantities use #,##0 (STYLE_QUANTITY_WHOLE); per-asset taxes = rounded gross − rounded net; totals via rounded_money(); per-asset total_invested feeds the export and the investment_positions cache. Owner should re-export carteira once to confirm.
- **Verified:** `test_recurring.py` gained 8 tests (73 → 81 functions), and 5 older ones now backdate their pause. The full backend suite passed with every
  session's in-progress work in the tree. The 019 backfill was checked on an in-memory DB built by
  migrations 001–018: another user's rows and a look-alike id prefix (`r10:` vs `r1:`) don't leak.
  `finance-guard` was run over the recurring files.

### What was not done and why

- **Recurring was not clicked through in a browser.** It is a backend rule with one label on the
  screen, and it is covered by tests. The owner item in `next-steps.md` covers it on real data.
- **Recurrences paused before 019 have no `paused_at`**, so they resume the old way (walk to today,
  dropping a pre-pause overdue occurrence). This is deliberate: the pause day can't be reconstructed.
- Still open from 2026-09-23: **restart the backend** (the `:5000` process predates migrations
  015+, and now 019–021 as well), and the owner walk-through at the top of `next-steps.md`.
  Decisions 3 and 4 remain open and belong to the owner.

### Next session

- The owner walk-through, now including re-exporting carteira, pausing/resuming a recurrence, and
  setting allocation targets and goals (item in `next-steps.md`).
- If the owner wants more from the Investidor10 survey, the list is in `next-steps.md` ("Ideas
  from the Investidor10 survey"); the cheap ones are the contributions chart and concentration alerts.
- Otherwise, only what the walk-through turns up.

### Non-obvious things learned

- **Tests fake a past pause by writing `paused_at` directly** (`pause_since()` in
  `test_recurring.py`), because the route's clock is `recurring_today()`. `pause_since(..., None)`
  simulates a pre-019 pause. Several older tests paused and resumed on the same day and relied on
  the old "skip to today" behaviour; they now backdate the pause.
- An explicit `next_run_date` in a PATCH clears the pause windows (the user took the cursor), and
  `last_occurrence_date` never moves back even after such a rewind.
- **Shared working tree:** with several sessions open, stage by path and by hunk, and check
  `git diff --cached --name-only` before committing. The index is shared.
- Carried from 2026-09-23: the Bash tool collapses `\\` in heredocs (write scripts with Write). The
  Chrome extension tab is "hidden" (no rAF), so use Playwright for motion and scroll checks. Scratch
  setup lives in the scratchpad `app/` folder (`mint_token.py`, not `token.py`).

### Third session — allocation, goals and the exemption meter (from an Investidor10 survey)

The owner asked Claude (Chrome extension, already logged in) to go through their Investidor10 PRO
wallet for features worth building here, then to build three of them. The survey covered every tab
(Resumo, Posições, Proventos, Patrimônio, Rentabilidade, Análise, Lançamentos, DARFs, IRPF, Metas);
nothing was changed there.

- **Built:** target allocation with a contribution split (Investimentos → Alocação, migration 020,
  `services/allocation.py`, `routes/allocation.py`); goals (Planejamento → Metas, 021,
  `services/goals.py`, `routes/goals.py`); the R$ 20 mil exemption meter (`exemption_meter()` in
  `services/tax_report.py`, `GET /api/tax-report/exemption`) on the IR tab and as a warning in
  "Registrar operação" → Venda. Rules and edges in `done-tasks.md`; conventions added to CLAUDE.md.
- **Verified:** 22 new tests (`test_allocation.py`, `test_goals.py`, `test_exemption_meter.py`)
  plus the route map, full suite 741 passed. Clicked through on a scratch DB (:5012/:5182): the
  Chrome extension for the targets sheet (its screenshots timed out partway), then Playwright at
  1400 px and 390 px for Alocação, Metas, the IR meter and the sale warning. That pass found and
  fixed a truncated forecast month, "ano(s)/mês(es)" plurals, a 12-month income total rebuilt from
  the rounded average (now sent by the server), and cramped phone rows on Alocação.
- **Not built:** everything else from the survey (benchmarks, fundamentals, B3 import…), listed in
  `next-steps.md` as ideas that need the owner's call. Not tried on real data.
- **Learned:** the frontend's Expand/Collapsible never opens in the Chrome-extension tab (no rAF),
  so an expanded row looks empty there; Playwright shows it fine. `docs/done-tasks.md` has mixed
  CRLF/LF line endings, so a scripted exact-match replace fails on it; use the Edit tool.
