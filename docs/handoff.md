# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 · Health check; self-update proven on the phone

A quick health check of server, pipeline, phone updates and PC, then the owner's phone test of
both self-update paths. **Production is the home server**: `https://guilhermeserver.tail5084ff.ts.net`.

### What was done
- Health check: container healthy, `/api/health` 200, DB has the data (3 users, 563 operações),
  clean logs, running image = main, bundle manifest reachable, `android-release` has its 4 secrets.
- **Fixed the CI `apk` job** (`eda8d75`): it failed on every run with an empty certificate digest.
  The runner's build-tools 37 `apksigner` prints `V2 Signer: certificate SHA-256 digest: …`, not
  `Signer #1 …`; the check now greps either format and prints the full output. The key was fine.
- Installed the first CI APK (10009) over the phone's USB build (208) with `adb install -r`, after
  checking both carry certificate `5e0770ac…`. Data kept.
- Phone test, done by the owner, both passed: a screen-only push (`79d111c`, a text change in
  Ajustes › Versão; bundle `adaeed3`) arrived by "Verificar atualizações" → "Reiniciar agora";
  APK 10011 (dispatched with **apk** ticked) was offered as "Nova versão disponível" and installed
  from the app.
- `.claude/agents/app-bug-hunter.md` deleted at the owner's request (it was never committed).
- 1002 backend tests, 36 node tests.

### What was not done and why
- The rest of the self-update check (offline queue across a switch, a native-level bump, the 30 s
  fallback) — not asked for today; in next-steps.

### Next session
1. After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
2. Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
3. The remaining self-update cases, if the owner wants them.
4. The rclone backup, if the owner wants help with it.

### Carried from earlier sessions (still open)
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, now on the server.
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.

### Learned
- The APK published by a dispatch already contains the newest screens, so test a screen-only
  update *before* installing a new APK, or the APK hides it.
- A workflow-only push skips the `apk` job; use `gh workflow run deploy.yml -f apk=true`.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
- `pytest`'s own `tmp_path` is not accessible on this PC; make temp dirs next to the test database.
- `sudo` on the server covers only `/usr/bin/docker` passwordless.
- Capacitor 8 reads `serverBasePath` in `loadWebView()`, after every plugin's `load()`, and clears
  it itself when versionCode/versionName change.
