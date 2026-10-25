# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-25 · native migration session E: the native shell, then no WebView

Cloud session, branch `claude/affectionate-thompson-3vd16f` from `main` at `36ea64f` (sessions
A–D merged), PR to `main`. One Sonnet review at the end (shell + removal only).

### Done
0. **Route check first**: every phone route was native or desktop-only except Início's four
   history panels (`/inicio?web=1`) and the Pendentes sheet (web only). Stopped and asked; the
   owner said build both natively. The five desktop-only pages stay desktop-only.
1. **Início panels**: `GET /api/home/panels` (`services/home_panels.py`, `test_home_panels.py`)
   and `ui/home/HomeHistoryPanels.kt` (+ `rules/HomePanelsRules.kt`, test). The row that opened
   the web Início is gone.
2. **Shell**: `NativeActivity` is the launcher (activity-alias `.MainActivity`, splash), native
   login (`ui/login/`, Entrar only), bottom bar with the four sections and Ajustes plus a floating
   "+", the pending pill in every header and a native Pendentes sheet, the APK banner above the
   bar, a 401 → session cleared → login (the queue stays). Desktop-only links show a note.
3. **Removal**: Capacitor (gradle, package.json, `capacitor.config.json`), `MainActivity`,
   `ShellPlugin`, `OutboxPlugin` → `outbox/Outbox.java`, `NotifyPlugin` → `notify/NotifyAccess`,
   `ApkUpdatePlugin` → `update/ApkUpdater`, `bundle/`, `NativeScreensPlugin` → `ShellEvents`,
   `PendingRoute`, `services/app_bundle.py` + routes + tests, the web bridge (`nativeApp.js`,
   `nativeScreens*`, `appBundle*`, `notify*`, `NativePage`, `ApkUpdateBanner`, the two APK-only
   Ajustes sections), `bundle-manifest.mjs`, `native-level.txt`, `dist-android` (Dockerfile,
   `deploy.yml`, `android-check.yml`, `build-apk.ps1`). outbox/, notify/, update/ and the
   notification allow-list test (`NotifyRulesTest`) are untouched in behaviour.
- Checks: pytest 1648 green, node 169 green, `vite build` ok, `android-check.yml` green on
  `40161837854` (JVM tests + `assembleDebug`) after three red runs (Capacitor colours in the base
  theme, two removed enum values, a Capacitor leftover in `ApkUpdater`).

### Not done, and why
- **No phone check** (the owner's; the PR has the checklist). Nothing of the shell has run on a
  device: the session cannot build or run an APK.
- The "+" inside Investimentos opens "+ Novo", not Registrar operação; the launcher shortcut.
- The web Início still computes the four panels itself (only native reads the new endpoint).
- `CORS_ORIGINS=https://localhost` stays on the server until the phone has the native APK (the
  WebView APK still needs it); drop it after.

### Learned
- **Installing over the WebView app**: same package, same key and higher versionCode keep
  `financas_outbox.db`, `Session` and the read cache; the alias keeps the launcher shortcut.
  The old APK refuses a `version.json` without `native_level`, so CI keeps writing 9.
- Capacitor brought resources the app theme used (`colorPrimary`…): the build fails at
  `processDebugResources`, before Kotlin, so each CI round shows one layer of errors.
- `palette["x"]` throws at runtime for an unknown token (`amber-700` does not exist; use
  `amber-800`): check new names against `Tokens.kt`.

### Next session
1. Fix what the owner's phone check of this PR finds, on this branch.
2. Otherwise: the web Início onto `/api/home/panels`, or the desktop redesign plan.

---
