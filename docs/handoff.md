# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---


## Session — 2026-09-23 (latest) · UI remodel, Stage 1 (audit + three directions)

Asked to "work on a whole rework of the UI of the app" with Claude Design. Ran Stage 1 of
`docs/ui-remodel-prompt.md`, which by its own rules stops for the owner to pick a direction before
anything is built. **No frontend or backend code changed this session.**

### What was done

- **Before screenshots** of all ten screens at 1280 and 390 px, Playwright on a scratch DB seeded
  by `seed_three_years_mock.py` (Linux cloud container, not the owner's machine). Kept out of git.
- **Audit + three directions** in `docs/ui-remodel-audit.md`: per-screen audit, directions
  A Sereno / B Painel / C Cartões, a recommendation (A's look + B's keyboard layer, dark as a token
  swap) and decisions E–J for the owner.
- **Claude Design canvas** "Finanças — UI rework" (https://claude.ai/artifact/DPSbd7JxFULWe4r9z36tto,
  private): nine artboards — Início, Extrato and phone Início for each direction — filled with the
  seed's real figures. The generator script lived in the session scratchpad; the canvas files are
  the source of truth now (edit them there, not from a script).
- `docs/next-steps.md`: new "UI remodel" section with Stage 1 ticked and the owner's pick pending.

### What was not done and why

- Stages 2 and 3 (plan, build): the prompt requires the owner's pick first.
- **Balance mismatch found, not fixed:** consolidated "Saldo em conta" (R$ 1.061.007,88 on the
  seed) ≠ sum of "Saldo por conta" (R$ 1.308.507,88); the gap is exactly the accounts'
  `initial_balance`. Backend is out of the remodel's scope and it needs its own test — it is in
  `next-steps.md`. The mocks use the per-account sum.
- `finance-guard` not run: no backend or financial-rule change.
- Carried forward: the owner's walk-through at the top of `next-steps.md`; `BRAPI_TOKEN` still
  empty in `backend/.env`; `backend/backups/finance-pre-mock-20260922-205415.db` safe to delete.

### Next session

- If the owner has answered: Stage 2 — write the numbered plan into `next-steps.md` (replacing the
  "UI remodel" section), kit and tokens first. Otherwise the balance mismatch is a good small task.

### Non-obvious things learned

- **Scratch app on Linux** (cloud sessions have no `.venv`/`start.ps1`): `pip install -r
  backend/requirements.txt`, `npm ci` in `frontend/`; the seed needs a `username` on signup
  (`/api/auth/signup` rejects without one); run the backend with `python3 -c "import app;
  app.app.run(port=5001)"` and the env vars from the recipe below, and Vite with
  `VITE_API_BASE_URL=http://localhost:5001 npx vite --port 5174`. Playwright: `playwright-core`
  with `executablePath: '/opt/pw-browsers/chromium'`; auth goes in
  `localStorage['@financeMVP:auth']`.
- In the sandbox Google Fonts fail TLS, so screenshots render in the fallback font, and yfinance has
  no network, so Evolução do Patrimônio stays a skeleton — neither is an app bug.
- Carried: seeding a scratch DB — set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`, sign up with
  `app.app.test_client()`, then `import seed_three_years_mock as s`, set `s.BACKEND_DIR` to the
  scratchpad and call `s.main()` with `sys.argv` patched. On Windows, check `netstat -ano` for
  scratch ports left by other sessions (a second Flask bind succeeds and hits the old process).
  `.app-table` rules sit under `:where()`; a panel with `overflow-hidden` breaks sticky headers
  (use `overflow-clip`).
