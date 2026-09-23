# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---


## Session — 2026-09-23 (latest) · UI remodel: audit, direction C, dark mode, Início and Extrato

Asked to "work on a whole rework of the UI" with Claude Design. Stage 1 (audit + three directions on
a Claude Design canvas) went to the owner, who answered **"Go with C, include a dark mode"**; the
session then built the kit, shell, Início and Extrato. The rest of the screens got the new tokens
and kit for free but not their own rework.

### What was done

- **Audit + directions** — `docs/ui-remodel-audit.md`; canvas "Finanças — UI rework"
  (https://claude.ai/artifact/DPSbd7JxFULWe4r9z36tto, private) with A/B/C and a fourth row, C in dark.
- **Tokens + dark mode** — `tailwind.config.js` replaces the colour theme with seven families on CSS
  variables (`index.css`); `.dark` on `<html>` swaps them. `lib/theme.js` + a pre-paint script in
  `index.html`. Plus Jakarta Sans in `frontend/public/fonts` (OFL licence beside it), Google Fonts
  link removed. Chart colours moved to variables.
- **Shell + kit** — `Layout.jsx`: sticky top bar with pill sections, theme toggle, eye, user menu
  (Ajustes/Sair, Esc closes), bright "Novo"; sidebar removed. `ui.jsx`: pill buttons/tabs, flat
  rounded panels, primary button in `brand` green, page/panel descriptions hidden on phone.
  `FitValue` now clips its measuring copy (it widened the phone page to 483 px inside the hero).
- **Balance bug fixed (frontend)** — consolidated balance = sum of `/api/accounts?include_archived=1`
  balances (`consolidatedBalance()`); it had been a client sum of `transactions`, missing every
  account's `initial_balance` (R$ 247.500,00 on the seed). Início, Extrato, Cartões and the
  Evolução curve now agree with Saldo por conta.
- **Início** — net-worth block, Disponível por dia and next-invoice tiles, "Precisa de atenção"
  cards (adds closed-invoice Pagar and over-budget categories to the old three), panels reordered;
  Saldo por conta panel removed (accounts are in the block).
- **Extrato** — grouped by day with day totals (desktop table and phone list), no Data column, row
  actions on hover/focus, `ProjectionHeader` (also Cartões) is one summary panel.
- **Verified** on scratch data with Playwright: all ten screens at 1280 px in dark, Início and
  Extrato at 1280/390 in both themes, no horizontal overflow on phone; eye and theme toggles on
  Início/Extrato/Cartões/Posição: 0 API calls, no remount, balances masked. `vite build` clean;
  backend suite 575 passed (backend untouched).

### What was not done and why

- Cartões, Posição, Operações, Proventos, Orçamento, Recorrentes, Importar, Ajustes: only restyled
  through the kit; their own rework is listed in `next-steps.md`. Time went to the kit first, as the
  remodel prompt asks.
- No `Menu`/`Toast` in the kit yet; Extrato's row actions are hover-revealed icons, not a "⋯" menu.
- Decisions G (Ctrl K) and I (exact attention items) were never answered; I built I's proposed set.
- **Not pushed:** GitHub returned 403 for `guneves/Financas` (the Claude GitHub App has no access).
  The commits are local to this session's container.

### Next session

- Push first if the branch isn't on GitHub. Then the owner's walk-through in both themes.
- Next build item: Cartões (invoice as the unit, one Pagar where allowed).

### Non-obvious things learned

- **Dark mode is a token swap by construction.** A class like `bg-zinc-950 text-white` inverts
  correctly in dark (it becomes light-on-dark → dark-on-light); the only things that need a fixed
  colour are text on `brand` (`text-brand-ink`) and on `emerald-500` (`text-on-accent`). A new
  colour family or hex literal breaks dark mode silently.
- The table's sticky header offset is now `lg:top-[4.5rem]` (desktop top bar), in `index.css`.
- Scratch app on Linux (cloud sessions): `pip install -r backend/requirements.txt`, `npm ci`; the
  signup needs a `username`; backend via `python3 -c "import app; app.app.run(port=5001)"` with the
  env vars below, Vite with `VITE_API_BASE_URL=http://localhost:5001 npx vite --port 5174`.
  Playwright: `playwright-core`, `executablePath: '/opt/pw-browsers/chromium'`, auth in
  `localStorage['@financeMVP:auth']`, theme in `localStorage['@financeMVP:theme']`. In the sandbox
  yfinance has no network, so Evolução do Patrimônio stays a skeleton.
- Carried: seeding a scratch DB — set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`, sign up with
  `app.app.test_client()`, then `import seed_three_years_mock as s`, set `s.BACKEND_DIR` to the
  scratchpad and call `s.main()` with `sys.argv` patched. On Windows check `netstat -ano` for scratch
  ports left by other sessions. `BRAPI_TOKEN` still empty in `backend/.env`;
  `backend/backups/finance-pre-mock-20260922-205415.db` is safe to delete.
