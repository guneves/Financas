# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

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
    gives up after 10 s and goes to the queue (`CREATE_TIMEOUT_MS` in `outbox.js`), reads after
    45 s, and edits and deletes have none. CLAUDE.md's outbox convention says why.
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
  - offline, an entry goes to "Pendentes" within 10 s. On reconnect the **WorkManager job** sent
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
