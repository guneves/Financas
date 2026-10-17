# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 · The APK's screens update themselves from the server

The owner was given three ways for the phone to update itself and went ahead with the first: the
app downloads its own screen bundle from the server, and keeps the APK's copy as the fallback.
**Production is the home server**: `https://guilhermeserver.tail5084ff.ts.net`.

### What was done
- **Server**: the image builds the frontend a second time for the APK (`frontend/dist-android`,
  `ARG APP_API_BASE`) and stamps `bundle.json` with `frontend/scripts/bundle-manifest.mjs` (version
  = content hash, `native_level` from `frontend/native-level.txt`, `api_base`).
  `GET /api/app-bundle` (manifest + zip sha256/size/url) and `GET /api/app-bundle/<version>.zip`,
  both public like `/` (`services/app_bundle.py`, `routes/app_bundle.py`, 13 tests).
- **Phone**: native plugin `AppBundle` (`android/.../bundle/`: `BundleRules` pure + 15 JVM tests,
  `BundleStore`, `BundlePlugin`). Downloads, checks size + SHA-256, unzips safely, stages; the next
  cold start opens it on trial through Capacitor's own `serverBasePath`. No `ready()` in 30 s, or
  two kills before it → back to the APK's screens, version never downloaded again. A new APK
  wipes downloaded bundles. `BuildConfig.NATIVE_LEVEL` from `native-level.txt`.
- **Screen**: `lib/appBundle.js` (ready after the first render via `AppStarted` in `main.jsx`;
  checks at start and on resume at most every 30 min; switches on resume after 30 min away when
  no sheet is open), rules in `lib/appBundleRules.js` (4 node tests). Ajustes › **Versão do app**,
  APK only: APK version, native level, screen version, "Procurar atualização", "Usar a versão nova
  agora", "Voltar à versão do APK". That also closes Phase 9 step 4 (version in Ajustes).
- `build-apk.ps1` stamps the APK's own `bundle.json`. Docs: plan section "The screens update
  themselves", CLAUDE.md convention (when to bump the native level), DEPLOY.md, next-steps,
  done-tasks.
- Checked: 1002 backend tests, 33 node tests, JVM tests, `vite build`; a local Docker image
  served the manifest and a zip whose SHA-256 matched; a Windows build and the Linux image give the
  same version (`51714bc…`).

### What was not done and why
- **Nothing has run on the phone yet.** The installed APK predates this, so it needs one last
  USB install (`.\mobile\build-apk.ps1` from a clean tree). Until main is pushed and deployed the
  server answers 404 to `/api/app-bundle` and the app says "O servidor não oferece atualização".
- The 30 s fallback has not been exercised with a really broken bundle (would need a deliberately
  broken deploy).
- **No pre-commit audit.** `finance-guard` was started on this change and stopped before it
  reported, at the owner's request, and the owner then had the agent removed from the project
  (`.claude/agents/finance-guard.md` deleted, its routine taken out of CLAUDE.md). The change
  touches no financial table or rule; the two new endpoints are public on purpose.
- Option 2 (CI-built APK offered in the app) not built; in next-steps as "only if native changes
  become frequent".
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.
- `.claude/agents/app-bug-hunter.md` is still untracked and not this session's; left alone. It still
  mentions `finance-guard` in one line.

### Next session
1. The phone check of the self-update (steps in next-steps, Mobile section).
2. After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
3. Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
4. The rclone backup, if the owner wants help with it.

### Carried from earlier sessions (still open)
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, now on the server.

### Learned
- Capacitor 8's `Bridge` reads `CapWebViewSettings`/`serverBasePath` in `loadWebView()`, *after*
  `registerAllPlugins()` has run every plugin's `load()` — so a plugin can choose the folder for
  the same start. It clears that path itself when versionCode/versionName change (`isNewBinary`).
- `pytest`'s own `tmp_path` is not accessible on this PC (`pytest-of-User` access denied); make
  temp dirs next to the test database, as `test_frontend_serving.py` does.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
- `sudo` on the server covers only `/usr/bin/docker` passwordless, so a reboot (or anything else)
  needs the owner's password in an interactive `ssh -t`.
