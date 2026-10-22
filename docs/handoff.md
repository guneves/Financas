# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (evening) · APK on every deploy, and the phone goes native

Cloud session. The owner asked how to make the APK "native", then: (1) "preciso apenas poder
baixar o app a cada deploy automaticamente"; (2) "uso praticamente apenas o celular, mas quero
manter o desktop, e gostaria que as interfaces fossem diferentes". Chosen (AskUserQuestion): the
phone native in Kotlin + Compose, screen by screen; the desktop redesigned for a wide screen. No
briefing subagent: the docs were read directly.

### Done
- **`apk` job on every deploy** (`deploy.yml`): the change-detection step, the `native` output,
  `fetch-depth: 0` and the `apk` input of `workflow_dispatch` are gone. DEPLOY.md, CLAUDE.md and
  `steps-to-production.md` updated.
- **Native plan**: `mobile-docs/native-app.md` (decisions, step 0, step 1 "+ Novo" in detail, the
  order, the desktop redesign, verification). It supersedes the "No native rewrite" row of
  `steps-to-production.md`. CLAUDE.md has the convention; `next-steps.md` the open steps.
- **Step 0**: Kotlin 2.3.20 + Compose compiler plugin in `android/build.gradle`, Compose BOM
  (`composeBomVersion` in `variables.gradle`), Material 3, `activity-compose`, `compose = true`,
  Kotlin JVM target 21 in `app/build.gradle`. `ui/theme/Tokens.kt`, `Theme.kt` (`FinancasTheme`,
  `Palette`, `LocalPalette`, `ShellPrefs`), `TokensTest.kt` (reads `index.css`). `ShellPlugin`
  stores the theme in `ShellPrefs`. Tokens cross-checked against the CSS with a Python script here.
- **`android-check.yml`**: debug APK + `testDebugUnitTest` on branch pushes that touch Android.
  First run green on 22338aa (run 39824479133: `testDebugUnitTest assembleDebug`, BUILD SUCCESSFUL in
  1m 55s, TokensTest included).

### Not done, and why
- **No native screen yet.** Step 1 ("+ Novo") is next, detailed in `native-app.md`. No
  `native-level.txt` bump: nothing the web screens call changed.
- **This container cannot build an APK**: `dl.google.com` (Android SDK and Google's Maven;
  `maven.google.com` redirects there) is blocked by the environment's network policy. Told the
  owner how to allow it. Until then, compile on the branch through `android-check.yml` and read
  the run with the GitHub MCP tools (`actions_list`, `get_job_logs`).
- Desktop redesign not started (plan in `native-app.md`, per-screen plan goes in next-steps first).
- Plus Jakarta Sans is not in the native theme (needs a `.ttf` in `res/font`).
- The phone check of "APK on every deploy" waits for the merge to main (next-steps).
- Carried, still open in `next-steps.md`: the card débito/Flash walk-through, no Flash capture,
  Flash package unconfirmed, brapi quota with hourly quotes, the older items.

### Learned
- Maven Central rate-limits this container quickly (429 after a few directory listings): don't
  probe versions by listing directories; `kotlin-gradle-plugin` 2.3.20 is dated 2026-03-16.
- Kotlin's JVM target must equal Java's (21, set by Capacitor's generated
  `capacitor.build.gradle`, which must not be edited) or the build fails.
- From earlier sessions, still true: the test DB is one per session (assert on your own user's
  rows); Java's `\s` does not match U+00A0; never name a backend module after a stdlib one.
