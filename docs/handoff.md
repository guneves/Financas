# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (later) · Phase 6, first half: bank-notification listener and capture mode

A cloud session (no phone, no Android SDK). Built Phase 6 steps 1–3 and the debug half of step 7
of `mobile-docs/steps-to-production.md`. Session-scout was not used; the docs were read directly.
**Merged to `main`** by the owner as PR guneves/financas#1 (`e340d1c`). Deploy run 13 was green:
tests, image, deploy, and the `apk` job — the first Gradle build of this code — published APK
**10013** (native level 2) and `/apk/financas-debug.apk`, both signed with the phone's key
(`5e0770ac…`).

### What was done
- **Listener** (`frontend/android/app/src/main/java/br/financas/app/notify/`, Java):
  `BankNotificationListener` keeps only the allow-list — Samsung Wallet (`com.samsung.android.spay`,
  new; Play listing "Samsung Wallet (Samsung Pay)" found by a web search, since play.google.com is
  blocked from the cloud container), `com.itau`, `com.itaucard.activity`, `br.com.bb.android`,
  `br.com.bb.oewallet`, `com.btg.pactual.banking`. With capture on, each notification goes word for
  word into `financas_notify.db` (`NotifyStore`): package, title, text, bigText, every textual
  extra, posted time, `when`, key, channel, category, flags. Same posting = one row (`dedup_key`).
  On reconnect it reads what is still in the tray; on disconnect it asks for a rebind.
- **Pure rules** in `NotifyRules.java` with 12 JVM tests (`NotifyRulesTest`): allow-list, shell
  only when debug, dedup key (SHA-256, fits the server's `client_id` format), bigText preference,
  JSON/text export, and parity between `NotifyRules.APPS` and the manifest's `<queries>`.
- **Plugin `Notify`** + **Ajustes › Notificações dos bancos** (`NotificacoesSection.jsx`,
  `lib/notifyCapture.js`, `lib/notifyRules.js` with 9 node tests): access granted or not, when
  Android last connected the listener, "Abrir acesso às notificações", the "Permitir
  configurações restritas" steps (open by default when access is missing on Android 13+) with
  "Abrir informações do app" and who installed the APK, capture switch (off by default), count per
  app and "não instalado", the last 20 captured, "Exportar JSON" / "Exportar texto" (share sheet),
  "Apagar capturas" (confirmAction). Opened in Chromium at 360 px, light and dark, with the plugin
  mocked.
- **Test APK**: the debug build is package `br.financas.app.debug` ("Finanças debug"); only it
  accepts `com.android.shell`. The CI `apk` job now also runs `assembleDebug`, checks its
  certificate and publishes it as `/apk/financas-debug.apk` (not in `version.json`); the debug app
  never offers the published APK (`ApkUpdatePlugin`).
- `frontend/native-level.txt` 1 → 2 (new plugin the screens call).
- Plan (Samsung Wallet row, "One purchase, two notifications", steps 1–3 and 7 marked, Phase 7's
  `client_id` question), `next-steps.md`, `done-tasks.md`, `CLAUDE.md` (convention + counts).
- Tests: 42 JVM (12 new), 45 node (9 new), 1002 backend (untouched, run for safety).

### What was not done and why
- **Parsers (step 4), mapping screen (step 5), unrecognised → inbox (step 6)**: by the owner's
  instruction — there are no real texts yet, and parsers are written only against captures.
- **No deduplication between Samsung Wallet and the bank**, on purpose: capture must show the real
  pattern first. The plan and next-steps say Phase 6/7 has to pick one source per purchase.
- **No Gradle build in the session**: dl.google.com (Android SDK, Google's Maven artifacts) is
  blocked here. The Android classes were compiled with `javac` against Robolectric's `android-all`
  (API 36) and Capacitor 8.5.3's `classes.jar`, with stubs for three androidx methods
  (`NotificationManagerCompat.getEnabledListenerPackages`, `FileProvider.getUriForFile`,
  `PackageInfoCompat.getLongVersionCode`). The real build (manifest, debug resource override,
  `buildTypes.debug`, `testReleaseUnitTest`) first ran in CI after the merge, and passed.
- **Phone check**: needs the phone (below).
- **`DEPLOY.md`** does not mention `financas-debug.apk`: another session owns it.
- With capture off, the listener stores nothing (no parser would read it). Once parsers exist it
  must feed them regardless of the switch — written into step 4 of the plan.

### Next — the owner, before the next coding session
1. Done: merged, and CI published APK 10013 and the test APK. The server's screens now need
   native level 2, so the phone (APK 10011, level 1) keeps its current screens until 10013 is
   installed — this is also the self-update check of a native-level bump.
2. Real app: "Nova versão disponível" → install 10013. Ajustes › Notificações dos bancos → "Abrir acesso
   às notificações" → turn Finanças on. If Android says "Configuração restrita", follow the steps
   on that screen (this APK was installed by the app itself, which may count as sideloaded).
3. Test APK, from the PC on the tailnet:
   `curl -fLO https://guilhermeserver.tail5084ff.ts.net/apk/financas-debug.apk` then
   `adb install -r financas-debug.apk`. Open "Finanças debug", log in, grant it access, capture
   on, run the adb command shown on its screen. Done when the notification shows under "Teste
   (adb)" in the test app — and **not** in the real app. Export once to see the share sheet. If it
   never shows: `adb logcat -s FinancasNotify` prints the package it arrived from. Then
   `adb uninstall br.financas.app.debug` (it would otherwise capture bank texts too).
4. Real app, capture **on** for about a week of real purchases: Samsung Pay on each card (Itaú,
   BB, BTG), a debit purchase, Pix sent and received, an estorno, a declined purchase if one
   happens. Set the app's battery use to "Sem restrições" if the counts stall.
5. "Exportar JSON" and bring the file to the next session. **Decide first** whether parser test
   fixtures may go into the repo verbatim (merchant names, amounts, card final digits) or masked.

### Next — the coding session after that
- Phase 6 step 4 against the export: one parser per app, Samsung Wallet included; read which app
  notifies first in a Samsung Pay purchase and how far apart, and write the pairing rule (one
  source per purchase). Check whether any bank updates a notification (same key, new posted time).
- Then steps 5–6 and Phase 7.

### Carried from earlier sessions (still open)
- After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
- Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
- The remaining self-update cases (offline queue across a switch, a native-level bump — the
  merge of `e340d1c` is one: APK 10011 should keep its screens and be offered 10013 — and the
  30 s fallback).
- The rclone backup, if the owner wants help with it.
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, on the server.
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.

### Learned
- From the cloud container: dl.google.com and play.google.com are blocked, and maven.google.com
  redirects to dl.google.com, so no Android SDK and no androidx AARs. Maven Central works:
  `org.robolectric:android-all:16-robolectric-13921718` (the framework, ~190 MB) and
  `com.capacitorjs:core:8.5.3` are enough for a `javac` compile check.
- Android stamps a new posted time on every enqueue, so a notification the bank *updates* gets a
  new `dedup_key`. Capture keeps `Notification.when` too, in case Phase 7's id needs it instead.
- `cmd notification post` takes the package from the caller's uid: `com.android.shell` from
  `adb shell` on a stock build. The debug build logs refused package names in case One UI differs.
- The APK published by a dispatch already contains the newest screens, so test a screen-only
  update *before* installing a new APK, or the APK hides it.
- A workflow-only push skips the `apk` job; use `gh workflow run deploy.yml -f apk=true`.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
