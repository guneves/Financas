# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · Bank × Samsung Wallet pairing rule; Pluggy sync and reconciliation

The owner handed over `docs/prompts/notifications-pluggy-integration.md` (the message arrived cut,
starting in Part A step 3; the full file was on `claude/amazing-tesla-ip5fmc`, commit `0b3f223`,
which this branch fast-forwarded onto). Session-scout was not used: the documents were read
directly. Work is on `claude/stoic-brahmagupta-2yqkyd`, pushed; **nothing merged to `main`**, so
nothing deployed and no APK built.

### Done
- **Part A, the rule only** (`6ad278e`): `notify/NotifyPairing.java` + `NotifyPairingTest` (30
  JVM tests, all the prompt's cases: bank first, Samsung first, Samsung alone promoted, late bank
  after promote and after confirm, two same-amount purchases, declines, different cards, window
  edge). Pure; nothing calls it yet. JVM tests run here with `javac` + JUnit 4.13.2 + `org.json`
  from Maven Central (42 green with `NotifyRulesTest`), run from `frontend/android/app` (the
  manifest test reads a relative path).
- **Part B + C, server** (`94d8133`, 66 new pytest, 1116 total): `pluggy_client.py`, migration
  027, `services/pluggy_sync.py`, `routes/pluggy.py`, Pluggy on the integrations healthcheck,
  `services/import_rules.py` (moved out of `routes/imports.py` so the sync categorizes like the
  import), the claim in `POST /api/transactions` and `/api/cc-expenses/purchases`.
- **Screens** (`f13c8bb`, 9 node tests, 68 total): Ajustes › Banco (Pluggy), the Extrato's
  read-on-open + review notice + bank mark, the "+ Novo" toast for `matched_bank`. Walked in
  Chromium at 390 and 1280 px on a scratch database against a fake Pluggy (a local HTTP server
  speaking the SDK's shapes): add connection, link account and card, Sincronizar → "4 novos, 1
  conferido, 2 para revisar"; the balance (R$ 9.040,20) counted nothing twice; both reviews
  decided with "É este"; a "+ Novo" despesa of a row Pluggy had brought became that row with the
  owner's category. No console errors.
- Docs: CLAUDE.md (tests, layout, patch targets, the Pluggy convention, the notifications bullet),
  `mobile-docs/steps-to-production.md` (decisions table, "One purchase, one entry", Phase 7 step
  5), DEPLOY.md (the `.env` keys), a status block at the top of the prompt file.

### Not done, and why
- **Parsers, the detections table, WorkManager promotion, the inbox** (Part A 1, 3–5 wiring): the
  prompt's hard rule 1 — parsers only from the owner's export, and there is none yet (capture
  started 2026-10-17 and Samsung Wallet is not even in a published APK: `0b3f223` is not on `main`).
  The stopping point "show the owner the observed lag" needs that export too.
- **Nothing ran against the real Pluggy**: `docs.pluggy.ai` and `api.pluggy.ai` are refused by
  this container's proxy (403 on CONNECT; WebFetch cannot resolve them). The API shapes come from
  `pluggy-sdk` 1.0.0.post73 on PyPI (generated from Pluggy's OpenAPI). Not confirmed there: how
  long the `apiKey` lives (cached 1 h, renewed on a 401), and whether `from` is ≥ or > (asked one
  day early).
- **No native-level bump, no APK change**: no screen calls new Java; `NotifyPairing` is unused.
- The prompt asked for one commit per step; B and C share `decide_bank()`/`decide_card()`, so
  they went in one server commit, and the screens in another.

### Decisions taken without asking (say so if wrong)
- **200 `matched_bank` instead of the prompt's 409** for a phone confirmation that repeats a
  Pluggy row: a 409 parks the item as "needs attention" in the native queue with the app closed and
  needs an override for two real same-amount purchases; the claim keeps one row and stays
  eventually right (details in `docs/done-tasks.md`).
- Recurrence occurrences are attachable too (the prompt listed typed and imported rows).
- Only the **bank's** decline cancels a Samsung detection (the prompt said either source).
- PENDING at Pluggy waits for POSTED (the prompt's default) — so card purchases reach the app only
  when the bill closes; `PLUGGY_IMPORT_PENDING=1` changes it.
- The owner's values win on a confirmed row; differences are listed, never applied.
- The app takes a Pluggy **item id** typed in Ajustes; it does not embed Pluggy Connect.

### Next
1. Owner: Pluggy credentials in the server's `.env`, the product/plan question, one connection,
   links with "Desde", one real sync — the first real check of the field mapping.
2. Merge this branch (deploys the server and the screens; the APK self-update carries the
   screens), then the capture export → Phase 6 step 4 parsers, wiring `NotifyPairing`.
3. The known gaps in `docs/next-steps.md` ("Pluggy, known gaps"), the invoice-payment one first:
   a bank row "pagamento de fatura" synced before the in-app payment is debited twice.

### Learned
- `pkill -f "python app.py"` from the Bash tool kills the tool's own shell (its command line
  contains the pattern); anchor it (`pkill -f "^../.venv/bin/python app.py"`).
- Playwright: `getByRole('button', { name: 'Ligar' })` also matches "Desligar" — use `exact: true`.
- A Pluggy-like fake for screen walks: `http.server` answering `/auth`, `/items/<id>`,
  `/accounts`, `/transactions` with the SDK's JSON, and `PLUGGY_BASE_URL` pointed at it.

### Carried (Phase 6 on the phone, still open)
1. Done by the owner: the real app updated, access granted, capture working ("it is working").
   The next APK (BTG Investimentos on the list) must be installed the same way.
2. Test APK from the PC: `curl -fLO https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`,
   `adb install -r financas-debug.apk`, grant access, capture on, run the adb command on its
   screen; the notification must show under "Teste (adb)" there and not in the real app. Then
   `adb uninstall br.financas.app.debug`.
3. Capture on in the real app for about a week (Samsung Pay on each card, debit, Pix both ways,
   estorno, a declined purchase), then "Exportar JSON". Decide first whether fixtures may go into
   the repo verbatim. Next coding session: Phase 6 step 4 against that export. Samsung Wallet is
   back on the allow-list (`0b3f223`, reaches the phone only with the next APK from `main`), so
   the export must show both Samsung's and the bank's notification for the same purchases — that
   is what tunes `NotifyPairing`'s window.

### Carried from the investments check (2026-10-17 night) and earlier, still open
- After the deploy, open IR 2025 again on the server (next-steps, "Investments check"); the
  owner's decisions listed there (brapi 1 ticker/request, ETF code 07.09, units, isentos line 18).
- After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
- Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
- The remaining self-update cases (offline queue across a switch, the native-level bump of
  `e340d1c`, the 30 s fallback). The rclone backup, if the owner wants help.
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, on the server.
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.

### Learned earlier (investments check)
- The seed (`seed_three_years_mock.py`) and the API store a sale with the **sale price** in the
  price column; the screen stores the position's average there. Any cost read from that column
  was wrong for one of them — hence the server-side average cost.
- A full-page screenshot scaled down can turn "0,00" into "0.00": read the cell text before
  calling it a formatting bug.
- From the cloud container: gov.br, planalto, Receita's normas site, Play Store and dl.google.com
  are blocked (WebFetch fails to resolve them too); WebSearch works for citations.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
