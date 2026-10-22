# Architecture

## The picture

```
                ┌────────────────────────── Android APK (br.financas.app) ──────────────────────────┐
                │                                                                                    │
 Flask API  ◄───┤  data/  ApiClient (OkHttp + kotlinx.serialization, Bearer token from Session)      │
 (server,       │         ReadCache  (last good JSON per request, on disk, served offline)           │
 Tailscale)     │         repositories per area (accounts, categories, cards, inbox, ...)            │
                │              ▲                                                                     │
                │  ui/    ViewModels (StateFlow) ──► Compose screens (FinancasTheme, ui/components)  │
                │              │                                                                     │
                │              └─ creations ─► outbox/ (Java, existing): OutboxStore + OutboxWorker ─┼──► POST
                │                                                                                    │
                │  MainActivity (Capacitor WebView) — every screen not migrated yet                  │
                │  notify/ (Java, existing) — bank notifications → /api/inbox/detections             │
                │  update/ (Java, existing) — "Nova versão disponível"                                │
                └────────────────────────────────────────────────────────────────────────────────────┘
```

Native screens are a new client of the **same** endpoints the React app calls. No endpoint changes
for a screen to go native, except where `rules-port.md` decides a client rule moves to the server.

## Packages

All under `frontend/android/app/src/main/java/br/financas/app/`:

| Package | Language | Holds |
|---|---|---|
| `ui/theme/` | Kotlin | `Tokens`, `FinancasTheme`, `Palette`, `ShellPrefs` (done, step 0) |
| `ui/components/` | Kotlin | The native UI kit, the counterpart of `components/ui.jsx` (see `conventions.md`) |
| `ui/<feature>/` | Kotlin | One package per screen: `newentry/`, `inbox/`, `home/`, `statement/`, `cards/`, `receivables/`, `budget/`, `recurring/`, `goals/`, `settings/`, `investments/` — each with its `Screen`, `ViewModel` and state classes |
| `ui/nav/` | Kotlin | The native navigation and the bridge to the WebView (`NativeScreens`) |
| `data/` | Kotlin | `ApiClient`, DTOs, `ReadCache`, repositories |
| `core/` | Kotlin | Money parsing/formatting (pt-BR), dates, `client_id` generation — pure, JVM-tested |
| `rules/` | Kotlin | Client rules ported from `frontend/src/lib/` with their test cases |
| `outbox/`, `notify/`, `bundle/`, `update/` | Java | Existing; unchanged unless a screen needs it. `bundle/` goes away with the WebView |

Libraries (add each when the first screen needs it, versions pinned in `variables.gradle`, checked
to exist and be at least two weeks old): Navigation Compose, `lifecycle-viewmodel-compose`,
`kotlinx-coroutines-android`, `kotlinx-serialization-json` (plus its Gradle plugin), OkHttp. No
dependency-injection framework: one `AppGraph` object builds the client, the cache and the
repositories. No Room until a screen needs to query offline data; a JSON file per cached request is
enough for "show the last thing seen". Charts (step 7): a Compose chart library (Vico is the usual
choice) — decide in the Investimentos specs.

## Native and WebView side by side

Until the last step both live in the same APK.

1. **`MainActivity` stays the launcher** (Capacitor `BridgeActivity`), so the app opens exactly as
   today.
2. **A native screen is opened from the WebView** through a new Capacitor plugin, `NativeScreens`:
   `open({ screen, params })` starts the native Activity; `routes()` lists the screens this APK has
   natively. The React layout asks `routes()` once and, for a route listed there, calls `open()`
   instead of navigating in React. A web bundle on an older APK simply gets an empty list and keeps
   its React screens — this is why the plugin's arrival bumps `native-level.txt`.
3. **Step 1 is a sheet, not a page**: `NewEntryActivity` with a translucent theme draws a Compose
   bottom sheet over the WebView. Later steps use one `NativeActivity` with a Compose `NavHost` for
   every migrated page, so moving between native pages does not go through the WebView.
4. **Going back to the WebView** (a native screen links to one not migrated yet): the native
   Activity finishes with the route as a result; `NativeScreens` emits `navigate` and the React
   router opens it.
5. **Keeping data fresh across the boundary**:
   - native wrote something → `NativeScreens` emits `dataChanged` → the web calls
     `invalidateServerData()` (the same thing the outbox `changed` event already does);
   - the web wrote something → native reads again when its screen opens (cache first, then the
     network), so it is never more stale than the time the screen was closed.
6. **The last step** makes `NativeActivity` the launcher, deletes the WebView, Capacitor, `bundle/`,
   `services/app_bundle.py`, `native-level.txt` and `dist-android`.

## Session and login

- The WebView logs in today and hands the session to native (`lib/nativeApp.js` → `Outbox.setSession`
  → `outbox/Session.java`: base URL, user id, the token sealed with an Android Keystore key). Native
  screens read `Session.load(context)` — no second login.
- A 401 from a native request: the same handling as the outbox (`LoginNotifier`): stop, tell the
  owner to log in again, open the WebView's login.
- The native login screen is built with the shell (step 8, `screens/00-shell.md`); until then the
  WebView owns login and logout.

## Reads, offline and the cache

- Every read goes through a repository: return the cached copy at once (if any), fetch, replace,
  and expose "atualizado às HH:MM" when what is shown came from the cache. The React app does the
  same with its persisted TanStack cache (`lib/queryPersist.js`, 14 days).
- Offline: reads show the cache; **creations** go to the outbox (exactly the item shape
  `lib/outbox.js` writes, so the existing Java sender and its rules apply); **edits and deletes are
  refused offline** with a message, as on the web (CLAUDE.md, "The outbox holds creations only").
- A balance that counts pending outbox items is labelled an estimate, as on the web
  (`lib/outboxRules.js` / `OutboxRules.java`).

## Settings mirrored from the web

The web keeps these in `localStorage`, which Kotlin cannot read; each is mirrored the way the
theme already is (`ShellPlugin.setTheme` → `ShellPrefs`):

| Setting | Web | Native | When |
|---|---|---|---|
| Theme (Sistema/Claro/Escuro) | `lib/theme.js` | `ShellPrefs.dark` | Done, step 0 |
| Privacy mode (the eye) | `lib/privacy.js` | `ShellPrefs` + a plugin call | Step 3 (Início is the first native screen with balances) |
| Dismissed attention cards | `lib/attention.js` | to decide in `screens/03-inicio.md` | Step 3 |
| Extrato view (`?ver=`) | `localStorage` | native preference | Step 4 |

Once the WebView is gone, native owns them.

## Notifications and Aprovar

The listener (`notify/`) is already native and posts detections to the server. With Aprovar native
(step 2), a tap on the "pending items" notification opens the native screen directly, without
loading the WebView.

## Updates

A new APK on every deploy (`deploy.yml`, `apk` job) is how native code reaches the phone. The web
bundle self-update keeps updating the screens that are still React. See `build-and-test.md`.
