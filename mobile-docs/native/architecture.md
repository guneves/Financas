# Native architecture

All under `frontend/android/app/src/main/java/br/financas/app/`. Native screens are another client
of the same endpoints the React app calls.

| Package | Holds |
|---|---|
| `ui/theme/` | `Tokens`, `FinancasTheme`, `Palette`, `ShellPrefs` |
| `ui/components/` | The native UI kit |
| `ui/charts/` | Compose `Canvas` charts (no library) |
| `ui/nav/` | `NativeActivity` + `NavHost`, the `NativeScreens` bridge to the WebView |
| `ui/<feature>/` | One package per screen: Screen, ViewModel, state |
| `data/` | `AppGraph` (no DI framework), `ApiClient` (OkHttp + kotlinx.serialization), `ReadCache`, repositories |
| `core/`, `rules/` | Pure Kotlin: money, dates, ported client rules |
| `outbox/`, `notify/`, `update/` (Java) | Offline queue and sender, bank-notification listener, APK update |
| `bundle/` (Java) | Screen self-update; leaves with the WebView |

## Native beside the WebView
- `MainActivity` (Capacitor WebView) is the launcher until the shell step. The web asks
  `NativeScreens.routes()` and calls `open()` for a listed route; an older APK lists nothing and
  keeps the React screen.
- A native screen that links to one not migrated finishes with the route; `NativeScreens` emits
  `navigate`. Native writes emit `dataChanged` (the web invalidates its cache); native re-reads when
  a screen opens. A route survives process death for 2 minutes.
- Session: the WebView logs in and hands it to `outbox/Session.java`; a 401 opens the web login
  until the native shell exists.
- Reads: cache first, then network, "atualizado às HH:MM" when from cache.
- Mirrored settings: theme and privacy via `ShellPrefs`; dismissed attention cards are per store.
- The last step makes `NativeActivity` the launcher and deletes Capacitor, `bundle/`,
  `services/app_bundle.py`, `native-level.txt` and `dist-android`.
