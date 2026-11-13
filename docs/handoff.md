# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-11/12 · Architecture audit, four fixes and the first refactoring stack

Owner's brief: audit the repository (read-only), plan, then refactor in small proven steps; financial rules and owner
decisions untouchable. He approved C1–C4, then R1–R11 ("take the decisions that make sense for a spending tracker").

**Done** — `docs/audit.md` (the report: baseline, layer map, findings with evidence, top-10 debt files, duplications)
and eleven PRs, none merged when this was written:

| PR | Step | What |
|---|---|---|
| #76 | C1 | Tests only. Three tests failed from 2026-11-11 (hard-coded November dates against the real clock) and **blocked the deploy** (run 127); two more would fail every February. `fake_pluggy` freezes every clock module |
| #77 | C2 | `PATCH /api/categories` with a `currency` key answered 500 (a block pasted from the account route) |
| #78 | C3 | Two simultaneous requests paid one invoice twice. `db.begin_write()` (BEGIN IMMEDIATE) before `settle_invoice()` reads; the slower request gets the existing 409 |
| #79 | C4 | The PTAX was fetched from the BCB with the SQLite write lock held (a slow BCB = 500 on the owner's writes). `prefetch_rates()` before the transaction, `rate_on(fetch=False)` inside |
| #80 | R1 | `test_architecture.py`: layers, no import cycle (function-level included), ratchet on `_private` uses of other modules; the inbox ↔ open_finance cycle undone |
| #81 | R2 | `money.to_cents()` / `from_cents()` / `cents_or_zero()` replace eight copies; proved equal on every two-decimal value |
| #82 | R3 | One clock, `dates.local_now()` (51 direct reads replaced); `dates.now_source` freezes the whole app in a test |
| #83 | R4 | `services/spending_rules.py`; an 18-case matrix pins what Início, the plan and the budget each count |
| #84 | R9 | Proventos listing: one read per asset instead of one per provento |
| #85 | R11 | Hygiene: WebView/Capacitor leftovers out of the APK tree, 7 dead backend functions, 13 dead frontend exports |
| #86 | R6 (slice 1) | `services/inbox_rules.py`: the 94 pure names of `inbox.py` (2749 → 2071 lines), re-exported |

Each fix has a test that failed before it (first commit of its PR). Each refactor has its characterization test
written and green **before** the move.

**Numbers.** Baseline on `main`: pytest 2868 passed / 3 failed, `npm test` 245, ruff 406. Full suite on the stack:
after R1 (C1–C4 merged in) **2882 passed, 0 failed**; after R4 **2919 passed, 0 failed**; the runs at R11 and R6 are
in the PR descriptions/comments. `npm test` 245 pass and `vite build` OK after R11. Ruff: no new finding in any step
(402 after C2; 3 fewer after R11). APK: not built (no Android SDK in the cloud container).

**Not done, and why**
- **R5, R7, R8, R10 and the rest of R6** (see `next-steps.md`, top section). Each needs its own characterization
  tests first (golden rows, response shapes, JS/server parity) and each moves code the eleven open PRs also touch.
  Stacking five more risky moves on an unreviewed stack was the wrong trade; they start once the stack is merged.
- **The three disagreements between Início, the plan and the budget** were pinned, not resolved: resolving them
  changes numbers on screen. The recommendation is in #83 and in `next-steps.md`.
- **Import sorting / `ruff.toml`**, the four client-less routes, the 12 test-only frontend exports: kept (reasons
  in #85).
- **APK**: #85 deletes files under `frontend/android/`; only `android-check` compiles it.

**Next**: merge #76 first (the deploy is blocked), then the order in `next-steps.md`. Then R5.

**Lessons**
- Python's `sqlite3` opens a transaction only at the first write: a `SELECT` used as a guard is unprotected. Use
  `db.begin_write(conn)` before the check when two requests racing would cost money.
- Never call the network on a connection that already wrote; fetch first, then open the transaction.
- A test world must freeze **every** module that reads the clock (`finance_world.freeze`), not only
  `services.invoices`; from R3 on, `dates.now_source` does it in one place. SQLite's `now` never moves.
- The cloud container was replaced twice mid-session and local work was lost once: push each commit as it is made,
  run one full suite at a time, keep scratch scripts re-creatable.
- `ruff check backend` from the repository root and `ruff check .` from `backend/` give different totals (406 vs
  354 on `main`); compare like with like.
- To extract code from a giant module without breaking test patches: move only functions whose dependencies are
  all in the moved set and that read no name a test replaces on the old module; re-export by name.
