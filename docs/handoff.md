# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (night) · All of section 1 of the plan

The owner asked to finish everything under "Open work" in `next-steps.md`, in priority order, and to
take the pending decisions. Done, except the owner's own walk-through on real data.

### What was done (one commit per item, `965df68`..HEAD)

- **UI leftovers:** toasts after "+ Novo", the investment modal, invoice payments (Cartões and
  Início), recurring run and demo data (a toast can carry a link); `lib/confirm.js` + `ConfirmHost`
  replace every `window.confirm`; Proventos form in a sheet; Início cash-flow chart fills its panel;
  Importar has its own file picker with drag and drop; back/forward restores scroll.
- **Decisions:** 1 (card purchases count in the budget in the purchase month; invoice payments no
  longer count), 5 (IR is a support tool), 7 (keep both Cartões buttons), 8 ("Receitas"), 9 (eye
  hides the month chip). Details in `done-tasks.md`.
- **Import rules:** amount range and account conditions (migration 015).
- **Exports:** real `.xlsx` (hand-written OOXML, no dependency), Operações and Proventos exports,
  column picker (`ExportSheet`), `?format=&columns=` on every export.
- **Receipts:** backup mirror, thumbnails and inline preview, receipts on card purchases (016).
- **Frontend debt:** TanStack Query everywhere; `apiFetch` invalidates the cache after any write;
  skeletons on the heavy screens; old localStorage caches of financial data removed.
- **Operations:** JSON logging (`applog.py`, `backend/logs/`), integrations healthcheck
  (`/api/health/integrations`, Ajustes → Integrações). It caught a real bug: brapi's payload moved
  under `data`, so every B3 quote had silently been falling back to yfinance — fixed.
- **Phase 6:** corporate actions (017, adjust on write), multi-currency (018, BCB PTAX), annual IR
  report (IR tab + multi-sheet `.xlsx`), fixed-income accrual in Evolução do Patrimônio.
- **Verified:** 698 backend tests (605 before). Clicked through on a seeded scratch DB (:5002/:5175,
  the real `finance.db` untouched): Chrome for Pagar from Início, "+ Novo" toast, Extrato filters,
  export sheet, confirmation sheet, card-purchase receipts (upload, thumbnail, PDF preview, Abrir,
  Baixar), Importar with rule conditions, Integrações, corporate-action undo; Playwright for scroll
  restore, the motion pass (incl. reduced motion), Proventos sheet, registering a split, the
  multi-currency flow, the IR tab. Downloads were intercepted in the page, nothing was saved.
- **`finance-guard`** (by `subagent_type`, twice): up to `8eb2955` nothing; over the rest one real
  gap — a PATCH whose `metadata` omitted `fx_rate` dropped the locked exchange rate and the cash
  link fell back to PTAX. Fixed (the PATCH keeps `fx_rate`/`fx_source`, like
  `corporate_adjustments`) with a test. One background run died on the usage limit and was rerun.

### What was not done and why

- **The owner walk-through on real data** — it is the owner's by definition; the list at the top of
  `next-steps.md` is rewritten for what changed. Signup in the browser was not done by Claude
  (creating accounts / typing passwords is off-limits for it); it was checked through the API.
- **Excel** is not installed here; `.xlsx` files were validated with openpyxl in a scratchpad.
- **Restart the backend.** The owner's `:5000` process predates migrations 015–018, the brapi fix
  and the new routes; `npm install` already ran (TanStack Query), the dev server picks it up.
- Open decisions 2–4 remain (not blocking anything).

### Next session

- Owner: the walk-through at the top of `next-steps.md`, especially re-planning budgets under
  decision 1 and comparing the IR tab with the broker's informe.
- Then only what the walk-through turns up; the plan has no open build items.

### Non-obvious things learned

- **The Bash tool collapses `\\` to `\`** inside heredocs: a Python edit script with `"\\n"` wrote a
  real newline into source files (twice). Write scripts with the Write tool, or edit with Edit.
- **Chrome extension tab is "hidden"** to the page: `requestAnimationFrame` never fires and scroll
  events are held, so anything rAF-based looks broken there. Use Playwright for motion/scroll checks;
  `lib/scroll.js` no longer depends on rAF for this reason.
- A `ref` click right after navigation can land on a shifted layout; clicking through
  `javascript_tool` (`[...buttons].find(...).click()`) was reliable.
- Registering a split with ex date = today leaves today's quote unscaled; the route now refetches
  the asset quote after any corporate action.
- A fresh seeded scratch DB still shows fixed income at cost in Posição until "Atualizar cotações";
  the evolution chart now uses the CDI series for such titles instead of dropping the last bar.
- Scratch setup lives in the scratchpad `app/` folder (`env.py`, `seed.py`, `serve.py`,
  `mint_token.py` — not `token.py`, which shadows the stdlib module).
