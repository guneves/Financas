# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---


> Two sessions ran in parallel on 2026-09-23 and were merged into `main` together, so this file
> holds both entries. The next session replaces both with its own.

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
- **`finance-guard`:** no findings. It traced `consolidatedBalance()` against
  `account_balance_rows()` (transfers cancel across accounts, archived accounts included, no double
  count) and confirmed every touched balance goes through `usePrivateFormatter`. Its one note: the
  net-worth block itemizes only active accounts while the total includes archived ones — deliberate
  (archived, never deleted), left as is.

### Next session

- The owner's walk-through in both themes (branch `claude/sleepy-feynman-nkzw99` is pushed; the
  first push this session got a 403 until GitHub access was fixed).
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

---

## Session — 2026-09-23 (latest) · Receipts per lançamento

Asked to "work on next-steps.md". The top of the plan is still the owner's walk-through, which a
session cannot do, so this took the next daily-use item the previous handoff named:
attachments/receipts per transaction. Ran in a **Linux cloud container**, not the owner's Windows
machine: no `start.ps1`, a fresh `.venv` (`python3 -m venv .venv`, `pip install -r
backend/requirements-dev.txt`) and `npm ci` in `frontend/`.

### What was done

- **Migration 014** `transaction_attachments` (`id`, `user_id`, `transaction_id` → `transactions`
  `ON DELETE CASCADE`, `original_name`, `stored_name` UNIQUE, `content_type`, `size_bytes`,
  `sha256`, `created_at`) + index `(user_id, transaction_id)`. Mirrored in `database/schema.sql`.
  A table, not the plan's "path in `metadata`": several files per row, and
  `sync_investment_cash_transaction()` rewrites `metadata` wholesale.
- **Backend** (`backend/app.py`, after `delete_transaction`): `GET/POST
  /api/transactions/<id>/attachments` (multipart field `file`), `GET .../<aid>/file`
  (`?download=1` for `attachment` disposition; `nosniff`), `DELETE .../<aid>`. Type sniffed from
  the first bytes (PDF, JPG, PNG, GIF, WEBP, HEIC); a renamed HTML is a 415. Limits
  `ATTACHMENT_MAX_BYTES` (env, default 10 MB, checked from `Content-Length` before reading) and
  `ATTACHMENT_MAX_PER_TRANSACTION = 20`. Files in `ATTACHMENTS_DIR/<user_id>/<uuid hex><ext>`
  (env, default `backend/attachments/`, now gitignored; in `.env.example`). The file is written
  before the row (removed if the insert fails); `DELETE /api/transactions/<id>` collects the stored
  names and unlinks them after the commit, so a refused delete (investment cash, invoice payment)
  keeps the receipt. `prune_orphan_attachment_files()` runs at boot after the backup and removes
  unreferenced files older than 10 min (orphans from an investment movement deletion, which takes
  its cash row via CASCADE). `GET /api/transactions` gained `attachment_count` (scalar subquery).
- **Frontend:** `components/AttachmentsSheet.jsx` (list, "Anexar arquivo" with multi-select,
  Abrir in a new tab, Baixar with the original name, Excluir with `confirm`). Extrato: paperclip
  row action on every row (including rows from other screens, whose origin label now truncates to
  make room; action column `w-44 lg:w-36`), a clip + count beside the description when a row has
  receipts; on the phone a paperclip button in the edit form, and a tap on a non-editable row opens
  the sheet. `lib/api.js`: `apiFetch` leaves `FormData` bodies alone (no JSON Content-Type), new
  `apiBlob`/`saveBlob`; `apiDownload` now uses them, and the blob URL is revoked after 30 s instead
  of in the same tick.
- **Tests:** `backend/tests/test_attachments.py`, 27 tests. Suite **602 passed**.
- **Verified:** Playwright (scratch DB on :5002, Vite on :5175) at 1280 and 390 px: upload of a
  real PDF + a fake one (fake → inline error, real one listed), Abrir opens a blob tab, Baixar
  saves as `nota.pdf`, clip mark counts 2, delete on the phone. Screenshots caught the footer
  button and file details wrapping on the phone (fixed, re-shot). `vite build` clean.
- **`finance-guard`** (found by `subagent_type` directly): one finding, `schema.sql` not updated —
  fixed. It checked path traversal, `user_id` on every query, the sweep, and the nested-route guard
  and found nothing else.

### What was not done and why

- **Receipts are not in the backup zip.** Photos in every daily zip × 7 days of retention would
  balloon `backend/backups/`. The folder has to be copied alongside the DB by hand; documented in
  `.env.example`, `CLAUDE.md` and the plan. If the owner wants them backed up, a separate
  weekly/incremental copy of `attachments/` is the shape, not the DB zip.
- No thumbnails or inline preview in the sheet; "Abrir" opens a new tab. HEIC (iPhone camera)
  opens only in Safari — elsewhere "Abrir" downloads it. Converting HEIC server-side would need a
  dependency (pillow-heif); not worth it until the owner hits it.
- No receipts on card purchases (`cc_expenses`) — they are not `transactions` rows. A purchase
  receipt goes on the invoice payment for now; revisit with open decision 1.
- The CSV export does not mention receipts.
- Not walked on the owner's machine or data; added to the walk-through list.
- Carried forward: **`BRAPI_TOKEN` is still empty** in `backend/.env`;
  `backend/backups/finance-pre-mock-20260922-205415.db` (scratch demo data, gitignored) is safe to
  delete; dark mode (decision E) and the UI remodel prompt are still open;
  `docs/ui-remodel-prompt.md`'s "state at writing" note is stale; amount/account conditions on
  import rules are not built.

### Next session

- Owner: the walk-through at the top of `next-steps.md` (now includes comprovantes).
- Then the UI remodel prompt, dark mode, or Phase 5 (first blueprint). Smaller daily-use options:
  amount/account conditions on import rules; receipts on card purchases (tie to open decision 1).

### Non-obvious things learned

- **Playwright `setInputFiles` with a non-ASCII file *path* silently dropped that file** (only the
  other file was posted). Passing `{ name, mimeType, buffer }` works, and paths and buffers cannot
  be mixed in one call. It is a harness quirk: curl and a buffer upload with "farmácia" in the name
  both work.
- **Headless Chromium has no PDF viewer**: "Abrir" on a PDF turns into a download named
  `download` there. A real Chrome shows the PDF; don't chase it.
- `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` is the executable in the cloud container;
  `npm i playwright` in the scratchpad works with `executablePath`.
- A scratch server that seeds itself: set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `ATTACHMENTS_DIR`, `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET`, `CORS_ORIGINS` before `import app`,
  sign up with `app.app.test_client()`, write `{"access_token", "user"}` to a file, then
  `app.app.run(port=5002)`; Playwright puts that JSON in `localStorage['@financeMVP:auth']` via
  `addInitScript`.
- Carried: on Windows a second Flask bind to a busy port *succeeds* and requests reach the old
  process — check `netstat -ano` before picking scratch ports. `.app-table` rules sit under
  `:where()`; a panel with `overflow-hidden` breaks sticky headers (use `overflow-clip`); write
  edit scripts to a file rather than piping Python via stdin (mangles non-ASCII on Windows).
