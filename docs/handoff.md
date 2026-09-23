# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-22 (latest) · Visual design pass + privacy-mode rework

Three steps, all in one session: an audit with screenshots, a 7-item plan with decisions A–E, and —
after the owner said "go-ahead with the decisions" — the build. In between, the owner asked for the
privacy mode to stop remounting the screen and to hide only account values and the portfolio; that
shipped first (`a85b5de`).

### What was done

- **Privacy mode** (`a85b5de`, `frontend/src/lib/privacy.js`): state outside React, subscribed with
  `useSyncExternalStore`; no remount, no refetch. Plain formatters never mask; sensitive spots use
  `usePrivateFormatter()`, `usePrivateAxisFormatter()` or `MetricCard sensitive`. Hidden: account
  balances, net worth, "Disponível por dia", the balance chart, Ajustes → Contas, the balance in
  `PayInvoiceSheet`, all of Posição (incl. fixed-income principal and price field) and position
  values in the sale picker. Name and e-mail are no longer masked ("only hide" read literally).
- **Visual pass** — one commit per theme, `a9d2422`..`d3a20be` (see `next-steps.md` → "Visual design
  pass" for the full list): tokens and money type (tabular figures, U+2212 minus,
  `formatSignedCurrency`, pt-BR `formatPercent`, flat background); chrome (no eyebrow, no page-level
  "+ Novo", 256 px sidebar); `MetricCard` + `FitValue`; tables (Extrato, Posição, Operações,
  Proventos, Cartões purchases) with right-aligned values, ~44 px rows, sticky headers, Extrato 100
  rows + "Mostrar mais"; colour only with meaning; charts (one-line axes via `compactAxis`, AA
  ticks, `shortMonthLabel`); phone density (metric cards two across, Extrato tap-to-edit, Operações
  actions inline); states and kit leftovers (grey disabled buttons, lighter badges,
  `SegmentedControl` sliding pill via shared `useSlidingPill`, `AlertMessage` for the Início invoice
  note, Ajustes section links in the tabs look).
- **Verified:** `npm run build` clean after every commit; backend suite 561 passed (frontend-only
  change); Playwright before/after screenshots of every screen at 1280 and 390 px on a scratch
  database, plus the privacy script (0 API calls on toggle, no remount, no console errors, same
  masked counts) re-run after the last visual commit. `finance-guard` ran on both changes.
- `CLAUDE.md`: test count 561, a privacy-mode line and a visual-rules line in the frontend
  conventions. `next-steps.md`: the pass section rewritten as done, decisions 6–7 updated, a
  walk-through item added.

### What was not done and why

- **Dark mode (decision E)** — optional and separately scoped by the owner's own brief.
- **Not walked by the owner.** Playwright drove a real Chromium, but nobody clicked through the
  inline edit in the new Extrato table, the phone tap-to-edit, or a real invoice payment with the new
  disabled style. Those are on the walk-through list.
- Rows of Extrato's inline-edit mode were not restyled beyond fitting the new columns (the type
  select now sits under the category select).
- `docs/ui-remodel-prompt.md` (written by a parallel session while items 1–3 were in flight) was left
  as its author wrote it; `next-steps.md` notes that its "state at writing" is stale.
- Carried forward: **`BRAPI_TOKEN` is still empty** in `backend/.env`; and
  `backend/backups/finance-pre-mock-20260922-205415.db` (scratch demo data only, gitignored) is still
  on disk — the seed script writes its backup there regardless of `DATABASE_BACKUP_DIR`, and deleting
  it was refused by the permission classifier. Safe to delete.

### Next session

- Owner: the walk-through at the top of `next-steps.md` (visual pass and eye toggle are on it).
- Then either the UI remodel prompt (starting from this pass, not before it), dark mode, or Phase 5.

### Non-obvious things learned

- **Playwright works without installing:** 1.62.1 is in the npx cache
  (`~/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright`) with its Chromium in
  `~/AppData/Local/ms-playwright`; `require()` the absolute path from a `.cjs` script. Git Bash
  rewrites a leading `/route` argument into a Windows path — pass routes without the slash.
- **Scratch app:** runner sets `DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `AUTO_BACKUP_ON_BOOT=0`,
  `JWT_SECRET` and **`CORS_ORIGINS=http://localhost:5174`** before `import app`, then
  `app.app.run(port=5001)`; users via `POST /api/auth/signup`, data via
  `scripts/seed_three_years_mock.py <email>`. Frontend: PowerShell
  `$env:VITE_API_BASE_URL='http://localhost:5001'; npm run dev -- --port 5174 --strictPort`.
- Full-page Playwright screenshots resize the viewport and Recharts draws past its panels; judge
  charts from viewport shots.
- `.app-table td { … }` beats a `py-1.5` utility on specificity (class + element vs class), so the
  table rules now sit under `:where(.app-table)`. Same trap for any future component-layer rule.
- `overflow-hidden` on a panel makes it the sticky container, and a sticky `thead` inside stops
  sticking to the page; `overflow-clip` keeps the rounded corners without that.
- Recharts wraps tick text at the axis width ("R$ 900 / mil"); the shared `axisProps.tick.width`
  gives it room.
- `document.fonts.ready` can resolve before the Inter weight in use has loaded; `FitValue` also
  observes its hidden measuring copy so it re-measures when the font arrives.
- The Python-via-stdin route mangled non-ASCII (`Operação`) on this machine — write edit scripts to
  a UTF-8 file in the scratchpad and run that.
