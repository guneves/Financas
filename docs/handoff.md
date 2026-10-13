# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-13 · Mobile app: plan verified, idempotent creation, one origin, offline outbox

The previous session wrote `mobile-docs/steps-to-production.md` (an Android APK with offline entry
and bank notifications) and built nothing. This one checked the plan against the code and the web,
rewrote it, and built the phases that need neither the phone nor Tailscale. `session-scout` opened
the session and `finance-guard` audited the change, both found directly by `subagent_type`.

### What was done
- **The plan, verified and rewritten.** Its last section is a table of every claim and what
  checking found. The corrections that changed the design:
  - transfers use `POST /api/transfers`, so creation is three endpoints, not two;
  - a unique index on `(user_id, client id)` cannot be shared by N installments — the
    `cc_expenses` index includes `installment_info`;
  - the id is a `client_id` column, not `source_type = 'OFFLINE_ENTRY'` (an empty `source_type`
    means "typed" to the export and the Extrato);
  - **the outbox cannot live in the WebView on the phone.** The notification's Confirmar button
    and background sync must work with the app closed, so in the APK the queue and the sender are
    native (SQLite + `WorkManager`); the browser keeps IndexedDB. See "Where the outbox lives";
  - the category of a detected purchase is chosen by the server (`auto_category`, Phase 7), since
    the import rules live there and parsing runs with the app closed (so the parsers are Kotlin);
  - Itaú Cartões (`com.itaucard.activity`) and Ourocard (`br.com.bb.oewallet`) are separate apps
    and were added to the allow-list.
- **Owner decisions, recorded in the plan:** Flash and every VA/VR benefit are out of the app (no
  account type, no notifications); login lasts 180 days through the one `JWT_EXP_DAYS` setting.
- **Phase 3 — idempotent creation** (migration `024_client_entry_ids.sql`). `POST
  /api/transactions`, `/api/transfers` and `/api/cc-expenses/purchases` take an optional
  `client_id`; a repeat returns the first delivery's rows with 200. Convention in `CLAUDE.md`.
  Checked by hand on a scratch server: each of the four kinds posted twice answered 201 then 200
  and left 3 lançamentos, 3 installments summing R$ 100,00 and the balances moved once.
- **Phase 1, PC half.** `routes/frontend.py` serves `frontend/dist` at `/` with an `index.html`
  fallback (`FRONTEND_DIST_DIR`); a production build calls the API same-origin; `.\start.ps1
  -Built` builds and starts the backend alone. Checked with Flask's test client against the real
  build: `/`, a hashed asset, two client routes, `/api/health`, a JSON 404 for an unknown `/api`
  path, 401 without a token, and no `localhost:5000` left in the bundle.
- **Phase 4 — offline, in the browser.** `lib/outbox.js` (queue, `createEntry()`, `flush()`),
  `lib/outboxRules.js` (the rules, pure, 16 tests under `npm test`), `lib/offlineStore.js`
  (IndexedDB), `lib/queryPersist.js` (the read cache saved per user, restored before first paint,
  cleared when the session changes), a "Pendentes" sheet and header pill, pending rows in the
  Extrato, estimated balances on Início and Lançamentos. The four forms always send a `client_id`.
- **From the audit, fixed:** correcting a pending item whose first attempt had in fact reached the
  server would have dropped the correction in silence (the replay returns the old row). An edited
  item now compares what the server returned with what it asked (`deliveredDiffers()`) and stays in
  the list as "Recusado" with an explanation. Also: a `client_id` replayed on the other
  `transactions` endpoint is refused (409) instead of returning a row of another kind, and the
  concurrent-delivery branch of each route has a test.
- 948 backend tests (909 before), 16 frontend rule tests.

### What was not done and why
- **Phase 4 has not been opened in a browser.** It compiles and its rules are tested, but the
  queue, the sheet, the pending rows and the cache restore have never run. The scratch backend was
  stopped by Claude Code's low-memory guard during the session, and its notice said not to restart
  it unasked; a headless browser on top would have made that worse. This is the first open item in
  `docs/next-steps.md`, with the exact check. Treat the UI as unverified until then.
- **`backend/.env` was not edited** (the owner's secrets). `JWT_SECRET`, `JWT_EXP_DAYS=180` and
  `CORS_ORIGINS` are in `.env.example` and listed for the owner.
- **Phase 4, step 7 is partial:** the header says when the server is unreachable and an
  online-only action fails with a clear message; buttons are not disabled screen by screen.
- A second `finance-guard` run after the three fixes was skipped (small changes, each with a test,
  and memory was short).
- Phases 2 and 5–9 need the phone, Android Studio, Tailscale or real notification texts.
- Not mine and untouched: the reais-only work was committed by its own session during this one
  (`d8f2db8`).

### Waiting on the owner
- For Phase 1: Tailscale on PC and phone, MagicDNS and HTTPS certificates enabled in the tailnet
  (this publishes the PC's machine name in the public certificate log), and the `.env` values.
- For Phase 5: Android Studio with the SDK, the phone with USB debugging, a place outside the
  repository for the release keystore.
- For Phase 6: at least five real notification texts per bank app (Itaú, BTG, Banco do Brasil),
  copied exactly — credit, debit, Pix sent and received, an estorno, a declined purchase — and
  which apps are installed (Itaú Cartões? Ourocard?). They stay on this machine.
- For Phase 8: one real statement file per bank, for the dedup test.
- Carried from the previous session, all still open in `docs/next-steps.md`: the walk-through on
  the fresh database, the "no mês" pill, `NET_WORTH` goals, the unguarded movement delete, the
  multi-currency removal, three low test pins, the brapi 1-ticker limit.

### Next session
Run the Phase 4 browser check (first item of `docs/next-steps.md`) and fix what it shows. Then
Phase 2 can start on the PC at 360–412 px while the owner sets up Tailscale.

### Learned
- **`core.autocrlf` is `true` here**: the repository stores LF and the working copies are CRLF (a
  few LF). The mixed endings never reach a commit, so an LF file written by the Edit tool is
  harmless. What does bite: a Python patch script must open files with `encoding="utf-8"` — the
  Windows default (cp1252) wrote an em dash as byte `0x97` and the module stopped importing.
- A heredoc with `"""` in the Bash tool fails to parse; write the script with the Write tool.
- `tmp_path` fails on this machine (`PermissionError` on `%TEMP%\pytest-of-User`). Use
  `tempfile.mkdtemp(dir=os.path.dirname(db_module.DATABASE_PATH))`, as `test_backups.py` does.
- `node --test src/lib` treats the directory as a file and fails; pass the glob
  (`"src/**/*.test.js"`, which `npm test` does).
- The catch-all frontend route is GET-only, so a POST to an unknown path is now 405, not 404.
- A scratch backend for a by-hand check: set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`,
  `ATTACHMENTS_DIR`, `AUTO_BACKUP_ON_BOOT=0`, `LOG_TO_FILE=0` in `os.environ`, then `import app`
  and `app.app.run(port=...)`; assert `config.DATABASE_PATH` before serving. For a check that
  needs no browser, `app.app.test_client()` does the same without a server process.
- In a route, `return` inside `with get_db() as conn:` commits; to refuse after a write, call
  `conn.rollback()` first or raise.
- `pytest.ini` already passes `-q`; run plain `python -m pytest` or the summary line disappears.
- Playwright here: pass `executablePath` to `chromium.launch()` (the cached package wants
  `chromium_headless_shell-1234`, the installed build is `-1243`); screenshot a chart element, not
  the page; the "⋯" `Menu` closes on scroll, so scroll its button into view before clicking; on
  desktop the first DOM match in Operações is the hidden mobile card (`>> visible=true`); set
  `MSYS_NO_PATHCONV=1` in Git Bash for arguments that start with `/`.
- The owner reads every number as reais: when a multi-currency display looks wrong, convert, never
  surface the other currency. A dollar account for testing can only be created through the API.
- To look at `finance.db` without touching it: `sqlite3.connect("file:<path>?mode=ro", uri=True)`.
- The Grep tool returns nothing, silently, for a brace glob with a slash in it; use
  `**/{services,routes}/*.py`.
