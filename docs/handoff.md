# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

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
