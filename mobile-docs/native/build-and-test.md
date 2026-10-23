# Building and testing

## Where an APK can be built

| Place | Can build? | Notes |
|---|---|---|
| GitHub Actions — `android-check.yml` | Yes, debug, unsigned key | Every push to a branch other than `main` that touches `frontend/android/**`, `native-level.txt`, `capacitor.config.json`, `package*.json` or the workflow. Runs `testDebugUnitTest assembleDebug`. ~2 min with the Gradle cache. |
| GitHub Actions — `deploy.yml`, job `apk` | Yes, signed release + debug | Every push to `main`. Publishes `financas-<code>.apk`, `version.json` and `financas-debug.apk` to `/srv/apps/financas/apk/` on the server. |
| The owner's PC | Yes | Android Studio, or `.\mobile\build-apk.ps1` (builds, signs with the same key, installs over USB). |
| A Claude Code cloud session | **No** (today) | Java 21 and Gradle are there, but `dl.google.com` (Android SDK, Google's Maven; `maven.google.com` redirects to it) is blocked by the environment's network policy. The owner can allow it under the environment's Network access › Allowed domains; until then, compile through `android-check.yml`. |

## The loop for a native change from a session

1. Write the Kotlin and its JVM tests.
2. Check what can be checked locally: pure Kotlin logic can be cross-checked with a small script,
   the web side with `npm test`, the backend with `pytest`.
3. Commit and push the branch. `android-check.yml` starts.
4. Wait for it without polling by hand — a background shell loop on the public API works:

   ```bash
   until s=$(curl -sS "https://api.github.com/repos/guneves/Financas/actions/runs?branch=<branch>&per_page=1" \
       | python3 -c "import sys,json;r=json.load(sys.stdin)['workflow_runs'][0];print(r['status'],r['conclusion'],r['id'])") \
       && [ "${s%% *}" = completed ]; do sleep 30; done; echo "$s"
   ```

   (run with `run_in_background`; the session is woken when it exits).
5. On failure, read the job log (GitHub MCP `get_job_logs` with `failed_only`, or the `android-ci-watcher`
   agent), fix, push again. The workflow prints the failing JUnit XML on failure.
6. Green → the owner installs the debug APK to try it (below), then merges.

## The debug APK

- Package `br.financas.app.debug`, name "Finanças debug": installs **beside** the real app, never
  over it, with its own login and data on the phone (same server).
- From CI on `main`: `https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`.
- From a branch: `android-check.yml` builds it but does not publish it (no key, no server access).
  To try a branch on the phone before merging, build it on the PC (`.\mobile\build-apk.ps1`).
  Running `deploy.yml` on a branch does not help: its `android-release` environment is `main`-only.
  Open question for the owner: let `android-check.yml` upload the branch's debug APK as a workflow
  artifact. CLAUDE.md says APKs never go to GitHub, so this needs the owner's decision first.

## Tests that exist on the native side

| Test | Covers |
|---|---|
| `outbox/OutboxRulesTest` | The outbox's port of `outboxRules.js` |
| `notify/NotifyRulesTest`, `NotifyParsersTest`, `NotifyPairingTest` | Allow-list = manifest, the parsers from real captures, the bank × Samsung pairing |
| `bundle/BundleRulesTest`, `update/ApkUpdateRulesTest` | Screen bundle and APK update decisions |
| `ui/theme/TokensTest` | Native colours = `index.css` |

Every native step adds its own (`conventions.md`, "Tests").

## Before asking for a merge

- `android-check.yml` green on the last commit.
- `cd backend && python -m pytest` and `cd frontend && npm test` green if those sides changed.
- The spec's "Acceptance" list written so the owner can check it on the phone.
