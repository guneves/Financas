# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 (third, parallel) · Bug pass on the Android and desktop apps

The owner asked to check both apps for bugs. Another session (`financas-d5`, the monthly plan,
migration 025) was working in the same tree at the same time, and each session committed only its
own paths. The entry below this one is the previous session's, kept because it is still the
reference for Phase 5.

### What was done
- Backend suite, and frontend `npm test` (16), both green.
- **Desktop.** A Playwright walk of all 14 screens at 1400 px and 390 px, on a seeded scratch
  database (port 5003, vite 5178). It found no console errors, no 4xx/5xx and no horizontal
  overflow. The offline "+ Novo" → "Pendentes" → "Sincronizar agora" flow arrives on the server
  once.
- **Bug fixed, both platforms** (`lib/layers.js`):
  - Every Sheet and Menu listened for Escape on `document` by itself, and so did the Android back
    button, which sends Escape.
  - With the discard confirmation open over "Pendentes", one Escape closed the *underneath* sheet
    and left the question orphaned. React re-rendered between listeners, and the confirm's
    listener was re-registered mid-dispatch.
  - Escape on a "⋯" menu inside a sheet closed the sheet as well.
  - Each sheet saved and restored `body.style.overflow`, so two closing out of order left the
    page unable to scroll.

  Now there is one stack: only the top layer handles Escape, the scroll lock is counted, and
  `nativeApp.js` back calls `closeTopLayer()`. This also fixes back being swallowed during a
  sheet's 200 ms exit animation, when the old code still found `[role=dialog]` in the DOM.
  Verified in Playwright: each Escape closes one layer, and scroll unlocks after the last.
- **Phone, read-only.** The installed APK is `44542b8-dirty`. The owner was using the phone
  (a Samsung Pass prompt was open, and they entered data), so nothing was tapped there.
- Static review of the native outbox: two findings, both added to `docs/next-steps.md`. Backoff
  can reach hours with the app closed after a long outage. `KEEP` has a small scheduling window.

### What was not done and why
- No APK rebuild: the owner was on the phone. The back-button fix reaches the phone only with
  the next `mobile/build-apk.ps1`.
- `lib/layers.js` has no automated test: it imports React, and the node test runner has no DOM.
  It is covered by the Playwright flow only (scratchpad, not committed).
- The backoff and `KEEP` findings were left unfixed: they need a test on the phone.
- `frontend/dist` was rebuilt at about 16:15 from a tree that included the other session's
  uncommitted work. Rebuild after both sessions commit.
- `backend/brapi_client.py` briefly had a SyntaxError in the tree (another session's edit). It was
  back to `HEAD` when this session committed.

### Learned
- A browser-dispatched keydown runs microtasks between listeners, so a React 18 update from one
  `document` listener can re-render and re-register the next listener before it fires. Never
  rely on several independent Escape listeners agreeing; use `useLayer()`.

---

## Session — 2026-10-16 (second) · Mobile Phase 5: the APK, built and on the phone

The owner asked for Phase 5:
- Capacitor, pointed at the Tailscale address;
- the offline queue in native Android code;
- their own signing key, plus a build-and-install script.

The PC had no JDK or SDK. The owner chose to install Android Studio themselves, then enabled USB
debugging and tested on their phone, a Galaxy S25 (adb serial `RQCY10655FW`). The docs were read
directly (no `session-scout`). `finance-guard` audited the code commit (`4da45c4`); see below.

Commits:

| Commit | What |
|---|---|
| `4da45c4` | The code: Capacitor, native outbox, scripts |
| `ae777c7` | Gradle 9.1; scripts no longer treat stderr as failure |
| `f3efbdc` | Bars' colour at launch |
| `b2a9741` | `apiFetch` timeouts and `FitValue` slack |
| (this one) | Docs |

### What was done
- **Capacitor 8.5.3** in `frontend/`:
  - `capacitor.config.json`: id `br.financas.app`, name "Finanças", `webDir: dist-android`,
    `SystemBars.insetsHandling: native`;
  - `frontend/android/` is committed.
- **The APK's own web build:** `dist-android/` (gitignored), built with
  `VITE_API_BASE_URL=https://financas.tail5084ff.ts.net`. `frontend/dist`, which Flask serves,
  still calls its own origin.
- **The address is `financas.tail5084ff.ts.net`, not `desktop-behm4lb…`.** `desktop-behm4lb` is
  the Windows hostname the owner gave, and it does not resolve in the tailnet. `tailscale serve`
  (saved, survives restarts) proxies the address to `127.0.0.1:5000`.
- **Native outbox** (`frontend/android/app/src/main/java/br/financas/app/outbox/`), in Java:
  - `OutboxStore`: SQLite;
  - `OutboxRules`: a port of `outboxRules.js`, with 9 JVM tests;
  - `OutboxSender`: no redirects followed; a 2xx counts only when its body is the created row;
    results are written back only to the version that was sent;
  - `OutboxWorker`: WorkManager, `CONNECTED` constraint, backoff from 30 s;
  - `Session`: the token is encrypted with a Keystore AES-GCM key;
  - `LoginNotifier`;
  - `OutboxPlugin`.

  `lib/nativeApp.js` swaps it in. It also wires the back button and the bars' theme (`ShellPlugin`).
- **Signing and build:**
  - `mobile/new-keystore.ps1` was run: the key is in `%USERPROFILE%\.financas-android`;
  - `mobile/build-apk.ps1` builds, signs, verifies and runs `adb install -r`. It never
    uninstalls.
- **First build.** Android Studio's JDK is **Java 25**: Gradle 8.14 failed with "Unsupported
  class file major version 69", so the wrapper is now **Gradle 9.1.0**. AGP stays at 8.13.0 and
  compileSdk/targetSdk at 36. It compiled first time after that, and the JVM tests pass.
- **Fixed on the phone:**
  - **The bars were light under the dark theme at launch.** `index.html` sets the `dark` class
    but leaves the meta theme-color light. `applyTheme()` now reads the class.
  - **"Salvar" spun forever in airplane mode.** With the Tailscale VPN "connected" and no network
    under it, fetch hangs instead of failing. `apiFetch` gained `timeoutMs`: a "+ Novo" creation
    gives up after 6 s and goes to the queue (`CREATE_TIMEOUT_MS` in `outbox.js`), reads after
    45 s, and edits and deletes have none. CLAUDE.md's outbox convention says why. Ten seconds
    was still too slow for the owner, so with no real network (`Outbox.hasNetwork()`: any
    non-VPN network with internet; `navigator.onLine` in the browser) `createEntry()` now queues
    at once without trying.
  - **"R$ 1.000,…" on Início.** The phone's 90% text zoom left the fitted text 288.4 px wide in
    a 288 px box: integer `clientWidth`/`scrollWidth` hid the overflow. `FitValue` now measures
    with `getBoundingClientRect` and leaves 2% slack (`FIT_SLACK`). Checked on the phone: 281.7
    in 288.
- **On the phone, verified:**
  - it installs and opens;
  - login works through Tailscale;
  - the owner's real data loads;
  - the bars follow the theme;
  - the balance fits;
  - offline, an entry went to "Pendentes" (then within 10 s; now at once in airplane mode, not yet
    re-checked by the owner). On reconnect the **WorkManager job** sent
    it: logcat shows `OutboxWorker` RETRY at 15:51:44, then SUCCESS at 15:52:15. It arrived on
    the PC once (read-only query on `finance.db`).
- `backend/.env`: `https://localhost` was added to `CORS_ORIGINS`, and `JWT_EXP_DAYS=180` was set.
  `JWT_SECRET` was not touched.
- **finance-guard** (code commit): no cross-user leak and no duplicate path. It found two ways to
  *lose* a queued item, a redirect read as success and a write-back from a stale snapshot. Both
  were fixed before commit (see `4da45c4`). The later fixes are frontend-only, with no financial
  rule; they did not get a second audit.

### What was not done and why
- **The "done when" with the app closed is unproven.** In the owner's test the app was still on
  screen when the job sent. The job is the same code either way, but Samsung's battery management
  could hold it once the app is swiped away. `docs/next-steps.md` has the check and the fallback:
  battery use "Sem restrições".
- Not walked on the phone:
  - the back button;
  - the theme toggle at runtime;
  - the keyboard over "+ Novo", and whether the decimal keypad's comma is accepted;
  - the notification permission prompt.
- **The version in Ajustes** (Phase 9, step 4). Builds already stamp `versionName`.
- The browser `flush()` snapshot issue is still open (`docs/next-steps.md`).
- The pre-26 PNG launcher icons are Capacitor's defaults. Only Android 7 and older would show
  them.

### Waiting on the owner
- **Back up `%USERPROFILE%\.financas-android` off this PC.** Without that key, no future build
  can update the installed app, and reinstalling means emptying "Pendentes" first.
- Repeat the offline test with the app swiped away.
- For daily use the PC needs three things:
  - the backend (`.\start.ps1 -Built -NoBrowser`);
  - Tailscale connected on both devices;
  - the PC awake.
- Carried:
  - Phase 6 needs real notification texts;
  - Phase 8 needs one statement file per bank;
  - an eye on Phase 4's screens.

### Next session
If the owner reports the closed-app test passed, close Phase 5 in the docs. Then either the version
in Ajustes (small) or the browser `flush()` fix. Phase 6 waits on notification texts.

### Learned
- **Build toolchain:**
  - Android Studio's JBR is Java 25, which needs Gradle 9.1+;
  - `mobile/android-tools.ps1` finds the JBR and `%LOCALAPPDATA%\Android\Sdk`.
- **Windows PowerShell 5.1** throws on a native command's stderr under
  `$ErrorActionPreference = 'Stop'` when output is redirected. Keytool, Gradle and adb all hit
  it. The scripts switch to `Continue` around native calls and check `$LASTEXITCODE`.
- **Debugging the WebView on the phone:**
  1. temporarily add `"webContentsDebuggingEnabled": true` under `android` in
     `capacitor.config.json` and rebuild;
  2. find the socket with `adb shell cat /proc/net/unix | grep webview_devtools_remote`;
  3. run `adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>`;
  4. send `Runtime.evaluate` over the CDP websocket from `http://127.0.0.1:9333/json` (a
     20-line node script);
  5. remove the flag and rebuild.
- **Screenshots** with `adb exec-out screencap -p > file` from Bash. PowerShell's `>` corrupts
  binary output.
- **Background sends** show in `adb logcat` under `WM-WorkerWrapper ... OutboxWorker`.
- **Tailscale:**
  - the tailnet name is in `tailscale status --json` (`Self.DNSName`);
  - `tailscale.exe` is in `C:\Program Files\Tailscale\`;
  - `tailscale serve status` shows the proxy.
- **Capacitor 8 specifics:**
  - `SystemBars` is built in, with no status-bar plugin;
  - its `native` insets handling also pads for the IME;
  - plugins of our own are registered in `MainActivity` before `super.onCreate`.
- **Bash tool:** it collapses `\\` in heredocs. Write edit scripts with Write, then grep for
  `[\x00-\x08\x0b\x0c]`.
- Carried:
  - `core.autocrlf` is true;
  - `tmp_path` fails here, so use `tempfile.mkdtemp(dir=...)`;
  - run `python -m pytest` plain;
  - `node --test` wants the glob;
  - open `finance.db` read-only with `file:<path>?mode=ro`.
