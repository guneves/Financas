# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-22 (latest) · Visual audit + privacy-mode rework

The owner asked for a visual design pass in three steps: audit (report first), plan (wait for
approval), build. Steps 1 and 2 were delivered; the owner has **not approved the plan yet**. In
between, they asked for one concrete change — privacy mode should not remount the screen and should
hide only the main account values and the investment portfolio — which was built, verified and
committed.

### What was done

- **Audit, with real screenshots.** 48+ before-shots of every screen at 1280 px and 390 px, plus
  privacy mode, the "+ Novo" sheet and an empty account, taken with Playwright against a scratch app
  (see "Non-obvious" below for how). The findings and the 7-item plan with decisions A–E are in
  `docs/next-steps.md` → "Visual design pass". The screenshots lived in the session scratchpad and
  are not in the repo.
- **Privacy mode rework** (`frontend/src/lib/privacy.js`, new):
  - The state lives outside React; `useValuesHidden()` subscribes with `useSyncExternalStore`, so a
    toggle re-renders only the components that show a sensitive value. `Layout.jsx` no longer keys
    an inner `<Fragment>` on the mode — nothing remounts, nothing refetches.
  - `formatCurrency`, `formatUnitCurrency` and `compactCurrency` no longer mask anything. Sensitive
    spots opt in: `usePrivateFormatter(format)`, `usePrivateAxisFormatter(format)` (blank ticks rather
    than a column of "R$ ••••••") and `MetricCard sensitive` (the count-up stays mounted underneath,
    so revealing does not recount).
  - Hidden: Início's four top cards, "Evolução do saldo" (badge, axis, tooltip), "Saldo por conta",
    the autopay-shortfall warning (balance and "faltam", which reveals it); `ProjectionHeader` on
    Extrato/Cartões and Cartões' two "Saldo…" cards; Ajustes → Contas; the balance in
    `PayInvoiceSheet`'s account picker and its shortfall message; all of Posição — allocation donut,
    Evolução do Patrimônio, group totals, quantities, values, and for fixed income the principal
    (PM) and the price field (quantity 1, so the "price" is the value); the position values in
    `InvestmentLaunchModal`'s sale picker.
  - Visible on purpose: lançamentos, faturas, orçamentos, recorrências, operações, proventos,
    percentages. **Username and e-mail are no longer masked** (sidebar, Perfil) — "only hide" read
    literally; the Perfil name field is editable in privacy mode again.
- **Verified by script** at 1280 and 390 px on Início, Extrato, Cartões, Posição, Operações, Ajustes:
  0 API calls on toggle, a DOM marker on the page title survives (no remount), no console errors, and
  the masked counts match the list above (Operações: 0, as intended). Screenshots checked by eye.
- `CLAUDE.md`: test count 533 → 561; a frontend-convention line on privacy mode.
- `frontend/package-lock.json` is committed as found: a browserslist/caniuse-lite bump that appeared
  during the session from a process outside this one (not from any command run here). The owner said
  "commit everything".

### What was not done and why

- **The design pass itself (plan items 1–7).** Waiting for the owner's approval and decisions A–E.
  The plan in `next-steps.md` is the brief; its item 5 already lost "privacy axes" (done here).
- **Not clicked through by a human.** Playwright drove a real Chromium, but the owner has not walked
  the new privacy behaviour; it is on the walk-through list.
- `backend/backups/finance-pre-mock-20260922-205415.db` was left on disk: the seed script writes its
  pre-seed backup there regardless of `DATABASE_BACKUP_DIR`, and deleting it was refused by the
  permission classifier. It holds only the scratch demo user; `backups/` is gitignored. Safe to delete.
- Carried forward: **`BRAPI_TOKEN` is still empty** in `backend/.env` (quotes come from yfinance).

### Next session

- Get the owner's go on the visual plan (items + decisions A–E), then build it kit-first, one commit
  per theme, with before/after screenshots at both widths using the scratch setup below.
- Owner: the browser walk-through at the top of `next-steps.md` (now includes the eye toggle).

### Non-obvious things learned

- **Playwright works without installing anything:** 1.62.1 is in the npx cache
  (`~/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright`) with its Chromium
  (rev 1234) in `~/AppData/Local/ms-playwright`. `require()` the absolute path from a `.cjs` script.
- **Scratch app:** a runner in the scratchpad sets `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET` and **`CORS_ORIGINS=http://localhost:5174`** (the `.env`
  only allows :5173 — without it every login fails with a CORS error) before `import app`, then
  `app.app.run(port=5001)`. Users via `POST /api/auth/signup` (`email`, `password`, `username`), data
  via `scripts/seed_three_years_mock.py <email>` run with the same env (~R$ 2M net worth, 804
  lançamentos). Frontend: PowerShell `$env:VITE_API_BASE_URL='http://localhost:5001'; npm run dev --
  --port 5174 --strictPort` (`npx vite` was refused by the classifier).
- Full-page Playwright screenshots resize the viewport, and Recharts' `ResponsiveContainer` then
  draws charts wider than their panels. That is a capture artifact — use viewport shots to judge
  charts.
- The old privacy remount re-ran every fetch, and the pages render their *empty* state (not a
  skeleton) while data is missing — that was the "Sem movimentações" flash. Other remounts (route
  changes) still have that shape; plan item 7 covers loading vs. empty.
