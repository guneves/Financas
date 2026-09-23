# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---


## Session — 2026-09-22 (latest) · Budget strip on Início

A short session. Asked to "work on next-steps.md": everything at the top of the plan is the
owner's walk-through, so this took the next buildable daily-use item from "Smaller gaps" — the
budget on Início — over the bigger options (UI remodel, dark mode, Phase 5), which are still open.

### What was done

- **Início → "Orçamento do mês"** (`BudgetStrip` in `frontend/src/pages/Dashboard.jsx`), full width
  below "Despesas por categoria". Reads the existing `GET /api/budgets?month=` for the current
  month; no backend change. Shows the month's spent of available (carry-over included), a bar,
  "Restam"/"Passou", a status badge, and up to four categories that are WARNING/OVER (OVER first,
  then by percent) with "+N" linking to Orçamento; otherwise a one-line "todas no plano". Hidden when
  the month has no budget; a failed fetch just hides it. Not privacy-masked (orçamentos stay visible
  by the owner's choice).
- **`frontend/src/components/BudgetProgress.jsx`**: the status tones/labels and progress bar moved
  out of `Orcamento.jsx` so both screens share them, plus `budgetStatus()` — the same rule as
  `serialize_budget()` in `backend/app.py`, applied to the month total.
- **Verified:** `npm run build` clean; Playwright on a scratch DB (mock seed) at 1280 and 390 px —
  strip renders, no console errors; Orçamento still renders its 7 badges and bars. Backend suite not
  re-run (frontend-only change; still 561). `finance-guard` ran on the change and found one real divergence: the total badge compared the raw percent with 80, while `serialize_budget()` rounds it half-up to cents first (799,99 of 1.000,00 → 80,00% → WARNING). Fixed in `budgetStatus()`. It also re-ran the backend suite: green.

### What was not done and why

- No "Orçamento estourado" entry in "Precisa de você": a budget is a plan, not a task, and that
  banner is for things with an action. Easy to add if the owner wants it.
- What the strip counts as spent inherits open decision 1: card purchases reach a budget only when
  the invoice is paid.
- Not walked by the owner — added to the walk-through list in `next-steps.md`.
- Carried forward: **`BRAPI_TOKEN` is still empty** in `backend/.env`;
  `backend/backups/finance-pre-mock-20260922-205415.db` (scratch demo data, gitignored) is still on
  disk and safe to delete; dark mode (decision E) and the UI remodel prompt are still open;
  `docs/ui-remodel-prompt.md`'s "state at writing" note is stale.

### Next session

- Owner: the walk-through at the top of `next-steps.md`.
- Then the UI remodel prompt, dark mode, or Phase 5 (first blueprint). Smaller daily-use options
  still open: editing an import rule's pattern / applying rules to recorded lançamentos (Phase 4
  leftovers), attachments per transaction.

### Non-obvious things learned

- **Seeding a scratch DB without touching `backend/backups/`:** from a wrapper script, set the env
  (`DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`), `import app`,
  sign up with `app.app.test_client()`, then `import seed_three_years_mock as s`, set
  `s.BACKEND_DIR` to the scratchpad and call `s.main()` with `sys.argv` patched. The rest of the
  Playwright/scratch-app recipe from the previous handoff still holds (`CORS_ORIGINS` for :5174,
  token in `localStorage['@financeMVP:auth']` via `addInitScript`).
- Carried from last session: `.app-table` rules sit under `:where()` so utilities win; a panel with
  `overflow-hidden` breaks sticky table headers (use `overflow-clip`); write edit scripts to a UTF-8
  file rather than piping Python via stdin (it mangles non-ASCII here).
