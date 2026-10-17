# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (night) · Samsung Wallet back as a fallback; prompt for pairing + Pluggy

The owner asked for Samsung Pay notifications to be read again, with the rule "samsung
notification should be used when bank notifications doesnt reach about card use", said Pluggy will
be used too, and asked for a prompt an AI can follow to integrate both.

### Done
- `com.samsung.android.spay` ("Samsung Wallet") back in `NotifyRules.APPS` and the manifest
  `<queries>`; `NotifyRulesTest` asserts it is heard; Ajustes text mentions it again. Itaú Cartões
  and Ourocard stay off. JVM tests green here (plain `javac` + JUnit 4.13.2 + `org.json`, 12 tests);
  `notifyRules.test.js` green. CI will build a new APK because `frontend/android/` changed.
- `docs/prompts/notifications-pluggy-integration.md`: the full prompt — parsers from captures,
  pairing rule (same amount, same card, 10-min window to tune), hold-then-promote for Samsung via
  WorkManager, one `client_id` per purchase group, Pluggy client/mapping/sync
  (`source_type = 'PLUGGY'`, polling because the server is tailnet-only), and server-side
  reconciliation (attach to an existing row via a new `external_id`, inbox when ambiguous).
- CLAUDE.md, `mobile-docs/steps-to-production.md`, `docs/next-steps.md` updated to the new rule.

### Not done, and why
- **No pairing code**: it needs parsers, and parsers are written only against the owner's
  exported captures (CLAUDE.md). With capture on, Samsung Wallet and bank notifications are both
  stored verbatim, which is exactly the fixture set the pairing needs.
- **No Pluggy code**: needs the owner's credentials and plan (developer/MeuPluggy/paid), and the
  Pluggy API fields must be checked against docs.pluggy.ai.
- No native-level bump: no screen calls new Java.
- Nothing pushed to `main`; committed and pushed to `claude/amazing-tesla-ip5fmc` only.

### Carried (Phase 6 on the phone, still open)
1. Done by the owner: the real app updated, access granted, capture working ("it is working").
   The next APK (BTG Investimentos on the list) must be installed the same way.
2. Test APK from the PC: `curl -fLO https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`,
   `adb install -r financas-debug.apk`, grant access, capture on, run the adb command on its
   screen; the notification must show under "Teste (adb)" there and not in the real app. Then
   `adb uninstall br.financas.app.debug`.
3. Capture on in the real app for about a week (Samsung Pay on each card, debit, Pix both ways,
   estorno, a declined purchase), then "Exportar JSON". Decide first whether fixtures may go into
   the repo verbatim. Next coding session: Phase 6 step 4 against that export, . Samsung Wallet is
   back on the allow-list (this session), so the export must show both Samsung's and the bank's
   notification for the same purchases.

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
