# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 · Pluggy removed

Owner's request: "remove pluggy from all the app … since in the free plan i dont have access to
anything". No session-scout: one concrete task.

### Done
- **Backend**: deleted `pluggy_client.py`, `routes/pluggy.py`, `services/pluggy_sync.py` and their
  tests; the "+ Novo" bank claim (`matched_bank`) is gone from `routes/transactions.py` and
  `routes/cards.py`; the healthcheck, `source_types`, `export_csv`, `config` and `.env.example`
  no longer know Pluggy. `PLUGGY_MATCH_DAYS` became `INBOX_MATCH_DAYS` (same default, 3): Aprovar
  still uses that window for notifications.
- **Aprovar (028) kept, notifications only**: `services/inbox.py`, `inbox_decisions.py`,
  `routes/inbox.py` lost the bank source (ledger rows, the lock on bank-given fields, split of a
  bank source). `test_inbox.py` lost its Pluggy cases; the one-sided-transfer memory test was
  rewritten with TRANSFER_OUT notifications.
- **Migration 029** (`029_drop_pluggy.sql`): a pending Aprovar item that only the bank brought
  becomes REMOVED; a Pluggy-born lançamento becomes manual; drops `pluggy_items`,
  `pluggy_account_links`, `pluggy_transactions`, `transactions.external_id`,
  `cc_expenses.external_id/source_type/source_id` and their indexes. Checked on a copy of the
  dev DB with 026–028 applied and fake Pluggy rows (integrity and FK checks clean).
  `schema.sql` updated. 027/028 still mention Pluggy: migrations are append-only.
- **Frontend**: deleted `PluggySection`, `pluggySync.js`, `pluggyRules.js(+test)`,
  `pluggyConnect.js` and the `pluggy-connect-sdk` dependency; Ajustes has no "Banco (Pluggy)";
  the Extrato has no bank mark; Aprovar has no "Ler o banco" button. `candidateKindLabel` moved
  to `lib/inboxRules.js`, tested there.
- Docs: CLAUDE.md, DEPLOY.md, mobile-docs, next-steps (the three Pluggy items), done-tasks;
  `docs/prompts/notifications-pluggy-integration.md` deleted (the pairing plan lives in
  `mobile-docs/steps-to-production.md`, "One purchase, one entry").
- Tests: 1082 pytest, 66 node; `npm run build` clean.

### Not done, and why
- **The server's `.env`** may still hold `PLUGGY_*` lines: harmless (nothing reads them), but
  the owner can delete them. Revoking the Pluggy credentials on Pluggy's dashboard is the
  owner's call too.
- `schema.sql` still lacks the 028 tables (`inbox_items`, `notify_detections`, `inbox_hints`) —
  drift that predates this session.

### Next
- **A new APK will be built by CI**: `NotifyPairing.java` changed (comment only), and any change
  under `frontend/android/` triggers the `apk` job. Installing it is optional; nothing
  native changed, so no native-level bump.
- After the deploy, open Lançamentos › Aprovar and Ajustes on the server once to confirm 029 ran.

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
