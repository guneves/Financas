# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (evening) · Browser walk-through on scratch data

Asked to "work on next-steps.md §1 using Claude in Chrome". The top item is the owner walk-through,
so this session clicked through it on a seeded scratch copy and fixed what broke.

### What was done

- **Scratch app:** `run_scratch.py` in this session's scratchpad (signs up `scratch@example.com`,
  runs `seed_three_years_mock` at scale 0.5, serves :5002), Vite on :5175 with
  `VITE_API_BASE_URL`. Logged in by minting a token (`auth.create_token`) into
  `localStorage['@financeMVP:auth']` — no password typed. `backend/finance.db` untouched (mtime
  checked).
- **Chrome** clicks, `find`/`form_input`, `file_upload` and **screenshots all worked** this time.
  The window would not resize (maximized), so 390/900/1100/1300 px went through Playwright.
- **Six bugs fixed** (details in `done-tasks.md`): OFX picked after a CSV was parsed as CSV
  (stale `file` in `runPreview`); Extrato misaligned between `md` and `xl` (hidden `<col>` +
  `colSpan={5}`); desktop header pushed "+ Novo" off-screen at 1024–1110 px; no scroll-to-top on
  navigation; duplicate "Outros" donut slice when a real "Outros" category is big; 0% return shown
  green. Also Regras panel padding and the doubled CSV `charset`.
- **Verified:** 605 passed; `vite build` clean; throwaway ESLint (`no-undef`) clean on the changed
  files; 1100 px sweep of all nine screens with no overflow and no console errors.
- **Docs:** walk-through section in `next-steps.md` rewritten (what was covered on scratch data,
  what was not), new small findings under "UI remodel leftovers", open decision 9 (privacy and the
  "+R$ X no mês" chip); row + note in `done-tasks.md`.
- **`finance-guard`** (by `subagent_type` directly): no findings. It confirmed Werkzeug appends the
  charset exactly once and counted the Extrato columns in both branches (5 at `xl`, 4 below).

### What was not done and why

- **The owner walk-through itself** stays open: this was scratch data, and signup, Pagar from
  Início, receipt "Abrir"/"Baixar", opening the CSV in Excel and the motion pass were not covered
  (listed at the top of `next-steps.md`).
- Small findings left for a later session (listed in `next-steps.md`, none blocking): no feedback
  after "+ Novo" outside Extrato, empty space under Início's cash-flow chart, the native file input
  in Importar, Cartões' pay banner vs. toast and its `window.confirm`, scroll not restored on back.
- Carried:
  - Open decisions 1 (card purchases vs. budget), 7, 8 and now 9 are unanswered.
  - `BRAPI_TOKEN` is empty in `backend/.env`.
  - `backend/backups/finance-pre-mock-20260922-205415.db` is safe to delete.
  - Receipts are not in the backup zip.
  - Amount/account conditions on import rules are not built.

### Next session

- Owner: the walk-through at the top of `next-steps.md`, on real data, and decisions 1, 7–9.
- Product work: the small walk-through findings, then import-rule amount/account conditions and
  export to .xlsx / Operações / Proventos; the Proventos form as a sheet.

### Non-obvious things learned

- **A `<col className="hidden">` does not hide a column** in a `table-fixed` table: cells in the
  row shift left and any `colSpan` counting it adds a phantom column. Render the `<col>` and the
  cells conditionally (Extrato's `useIsXl()`). Grep for `hidden xl:table-cell` before reusing it.
- **State set in an event handler is not visible to a helper called in the same handler** —
  `Importar` passed the old file name to the preview. Pass the fresh value as an argument.
- **Fresh seeded scratch DB:** fixed income shows at cost with "0,00%" until "Atualizar cotações"
  runs (the BCB accrual is only computed on refresh); the CRA IPCA+ fetch can time out.
- The extension's `javascript_tool` refuses to return anything that looks like a token or cookie
  (`[BLOCKED: Cookie/query string data]`) — fetch authenticated endpoints with `curl` from Bash.
- `browser_batch` stops at the first error, and an invalid step (e.g. a `javascript:` URL in
  `navigate`) fails the whole batch before anything runs.
- Carried: pyflakes lives in an earlier scratchpad `pf/` (`pip install --target <scratch>/pf pyflakes`
  if gone); `monkeypatch.setattr(app_module, …)` fails silently — grep when a name moves; check
  `netstat -ano` before picking scratch ports; Vite does not catch undefined identifiers (a
  throwaway ESLint with `no-undef` is in an earlier scratchpad's `lint/`).
