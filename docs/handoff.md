# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (evening) · UI remodel finished: every screen on direction C

Asked to "finish the work on next-steps.md". Read as: finish the in-progress item, the UI remodel
(Posição/Operações/Proventos, Orçamento/Recorrentes/Importar/Ajustes, `Menu` adoption, `Toast`).
Phase 5 (splitting `app.py`) and Phase 6 (corporate actions, multi-currency, tax report) are
separate multi-session projects and were not started — see "What was not done".

### What was done

- **Kit** (`components/ui.jsx`): `SummaryPanel({ lead, figures })` — one headline figure with up to
  three beside it, values already formatted by the caller (so the caller owns privacy), tones
  `neutral | gain | loss | muted`, `FitValue` so nothing truncates. `ProjectionHeader` (Extrato,
  Cartões) now uses it. `Toaster` mounted once in `Layout`, driven by `toast(message, { tone })` in
  the new `lib/toast.js` (module store + `useSyncExternalStore`, same shape as `lib/privacy.js`;
  max 3, 4 s, inverted zinc-900 surface so it reads in both themes).
- **Posição**: summary block from the backend's `total_invested` / `current_balance` /
  `current_net_balance` (now returned by `useInvestments()` as `totals`), masked by the eye except
  the %. Quote is read-only (dot + price); "Editar cotação" (not on renda fixa) / "Atualizar
  cotação" / "Excluir…" live in the row `Menu`; editing opens `QuoteSheet`. The partial redemption
  is `RedeemSheet` (was `window.prompt` ×2 + `alert`) — **payload unchanged**. Names wrap
  (`[overflow-wrap:anywhere]`) instead of truncating.
- **Operações, Proventos, Orçamento, Recorrentes**: `SummaryPanel` instead of four `MetricCard`s;
  row actions in `Menu`; success notices → `toast()`. Operações' `alert()` on a failed delete →
  the page's warning banner.
- **Extrato**: Editar/Excluir in `Menu`, paperclip still visible.
- **Importar**: three-step stepper; preview rows edge to edge in the panel.
  **Bug fixed:** `handleImport` set `result` and then called `runPreview`, which starts with
  `setResult(null)` — the "N lançamento(s) importado(s)" banner never showed. Now set after the
  reload.
- **Ajustes**: section chips in the pill style; Categorias and Regras row actions in `Menu`; Contas
  and Cartões keep their single icon button; notices → toast.
- **Verified** with Playwright on a scratch DB (seed scale 1, backend :5003, Vite :5176) at 1280 px
  light/dark and 390 px across all nine screens: no console errors, no horizontal overflow. Flows
  clicked: Posição menu (first item focused), Editar cotação → save → toast; Resgatar with a value
  above the balance is refused in the sheet, R$ 100 goes through with a toast and shows in
  Operações; Esc on a menu returns focus; Extrato menu opens upward near the bottom; a CSV import
  walks the stepper to step 3 with the banner. `vite build` clean; an ad-hoc ESLint `no-undef` /
  `react/jsx-no-undef` pass over every touched file was clean. Backend suite green (backend
  untouched). `backend/finance.db` mtime unchanged.
- **`finance-guard`** (found by `subagent_type` directly): no findings — the redemption payload is
  byte-identical to HEAD, every `window.confirm` survived the move into `Menu`, privacy masking
  intact, the removed fixed-income branch in `handleManualPrice` is unreachable (no "Editar
  cotação" on renda fixa), backend untouched.

### What was not done and why

- **Phase 5 / 6, frontend debt, operations** — each is its own project; nothing started.
- Proventos' form is still a collapsible at the top of the page, not a sheet; `DemoDataSection`
  keeps its success banner (it carries a link). Small, left for a later pass.
- On the phone a `SummaryPanel` with three figures leaves the third alone on its row — readable,
  left as is.
- Carried: the owner has walked none of the remodel; open decisions G (Ctrl K) and I (attention
  items) unanswered; `BRAPI_TOKEN` empty in `backend/.env`;
  `backend/backups/finance-pre-mock-20260922-205415.db` safe to delete; receipts not in the backup
  zip; amount/account conditions on import rules not built.

### Next session

- Owner: the walk-through at the top of `next-steps.md` — now one pass over every screen.
- Build: nothing UI-side is queued. The highest item left in the plan is Phase 5 (split `app.py`
  into blueprints, one at a time, suite green between steps); open decision 1 (card purchases vs.
  budget) is the most useful product question to put to the owner.

### Non-obvious things learned

- **Vite does not catch an undefined component or identifier** — it builds and the page throws at
  runtime. A throwaway ESLint 8 + `eslint-plugin-react` install in the scratchpad with `no-undef` and
  `react/jsx-no-undef` (`--no-eslintrc --resolve-plugins-relative-to .`) checks a set of files in
  seconds; the repo has no lint setup of its own.
- The heredoc trap from last session bit again (Python heredoc holding JSX template literals):
  write the script and the JSX chunks to scratchpad files and splice them in with Python.
- Carried: scratch server = set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `ATTACHMENTS_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`, sign up with
  `app.app.test_client()`, set `seed_three_years_mock.BACKEND_DIR` to the scratchpad and call
  `main()` with `sys.argv` patched; auth JSON into `localStorage['@financeMVP:auth']`
  (`access_token`), theme into `'@financeMVP:theme'`. Check `netstat -ano` for ports first. Dark
  mode is a token swap — never `dark:` classes or a non-theme colour family. A grid with no
  explicit columns sizes its track to content — use `grid-cols-[minmax(0,1fr)]`.
