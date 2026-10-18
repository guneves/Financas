# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 (night) · Deploy check, Pluggy Connect, Operação and Posição tweaks

Short owner-driven session on `main` (pulled PR #3, "Aprovar" 028, first). No session-scout: the
requests were concrete.

### Done
- **Phone up to date**: PR #3 and every commit below deployed green; no native change since the
  last APK, so the phone takes the screens by self-update on its next start.
- **Operação form**: the plain "Ativo" list (renda fixa, ETFs, cripto…) now lists only wallet
  assets of the chosen type; the catalog search (ações, FIIs) already filtered.
- **Pluggy Connect** (`0a3b5bf`): `POST /api/pluggy/connect-token` (`create_connect_token()`,
  body `{itemId}` for update mode), `lib/pluggyConnect.js`, "Conectar banco" and "Reconectar" in
  Ajustes › Banco. The SDK (`pluggy-connect-sdk` 2.14.2) is a lazy chunk; offline it just fails
  with a message. A 409 on registering means Pluggy returned an item already here — toast, no error.
  The token call was checked against the **real** Pluggy with the PC's `backend/.env`
  credentials, and the widget opened in Chromium (390 px) listing real banks. No bank login was
  tried.
- **Posição**: category groups collapse, all closed on opening (state per visit, not stored).
- Tests: 1169 pytest, 77 node.

### Not done, and why
- **The server's Pluggy credentials were not checked**: reading the container's environment over
  ssh was refused by the permission classifier. Ajustes › Banco says so on the server if missing.
- **The Pluggy app is a demo** (red "Aplicação demo. Proibido o uso comercial." bar in the
  widget). Whether a demo app can hold real bank connections for long is the owner's question
  with Pluggy.
- **Open Finance inside the APK is untested**: consent redirects to the bank; in Capacitor's
  WebView the popup may leave for the system browser and not come back. Connect from the computer
  first; connections live on the server, so the phone sees them.

### Next
1. Owner: one real connection via "Conectar banco" (computer), link accounts, Sincronizar — the
   first real check of the field mapping (next-steps, "Pluggy, on the owner's side").
2. If the APK flow is wanted, try it on the phone; if the consent never returns, pass
   `forceOauthInBrowser` and see if the item still lands (the widget polls the item).
3. The Pluggy known gaps in `docs/next-steps.md`, the invoice-payment one first.

### Learned
- Pluggy Connect's SDK runs `connect.pluggy.ai` in an iframe (zoid); in Playwright reach it with
  `page.frames().find(f => f.url().includes('connect.pluggy.ai'))`, button by role ("Continuar").

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
