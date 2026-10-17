# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (late) · BTG Investimentos on the notification list

The owner asked how to check the notification gatherer (answered: Ajustes › Notificações dos
bancos; the phone now has the new APK and capture works), how to make captures change balances
(answered: Phase 6 steps 4–5 and Phase 7, after the week of capture), and then asked for the BTG
investments app to be read too, with every operation later recorded automatically and paid from
the brokerage account.

### Done
- `com.btg.pactual.digital.mobile` ("BTG Investimentos") added to `NotifyRules.APPS` and the
  manifest `<queries>`; `NotifyRulesTest` no longer asserts it is refused. JVM tests green
  (`gradlew :app:testDebugUnitTest --tests "br.financas.app.notify.*"`). CI will publish a new APK
  because `frontend/android/` changed; the owner installs it by "Nova versão disponível".
- The plan for brokerage operations written down: `mobile-docs/steps-to-production.md`
  ("Brokerage notifications" in Phase 6, step 7 in Phase 7) and two items in `docs/next-steps.md`.

### Not done, and why
- **No native-level bump**: no screen calls anything new; the screen's list of apps comes from
  `Notify.status()`, so an older APK just lists one app fewer.
- **No parser or operation suggestion**: nothing to write it against until the captures show
  whether, and how, the BTG investments app notifies an execution.
- **"Automatically"**: the standing decision is "Always confirm". Kept; flagged as the owner's call
  in next-steps.

### Learned
- Gradle on this PC needs `JAVA_HOME` = Android Studio's `jbr` and `ANDROID_HOME` =
  `%LOCALAPPDATA%\Android\Sdk`; neither is set in the shell.
- `POST /api/investments` does not take a `client_id`; a notification-confirmed operation needs one
  (024's shape) so a double tap cannot buy twice.

### Carried (Phase 6 on the phone, still open)
1. Done by the owner: the real app updated, access granted, capture working ("it is working").
   The next APK (BTG Investimentos on the list) must be installed the same way.
2. Test APK from the PC: `curl -fLO https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`,
   `adb install -r financas-debug.apk`, grant access, capture on, run the adb command on its
   screen; the notification must show under "Teste (adb)" there and not in the real app. Then
   `adb uninstall br.financas.app.debug`.
3. Capture on in the real app for about a week (Samsung Pay on each card, debit, Pix both ways,
   estorno, a declined purchase), then "Exportar JSON". Decide first whether fixtures may go into
   the repo verbatim. Next coding session: Phase 6 step 4 against that export, with the
   one-source-per-purchase rule (Samsung Wallet + bank).

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
