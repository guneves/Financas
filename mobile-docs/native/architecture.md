# Native architecture

All under `frontend/android/app/src/main/java/br/financas/app/`. The APK is all native since
session E (2026-10-25): no WebView, no Capacitor. Native screens are another client of the same
endpoints the React app (now browser only) calls.

| Package | Holds |
|---|---|
| `ui/theme/` | `Tokens`, `FinancasTheme`, `Palette`, `ShellPrefs` (theme choice, privacy) |
| `ui/components/` | The native UI kit (incl. `PendingPill` and `LocalShellChrome`) |
| `ui/charts/` | Compose `Canvas` charts (no library) |
| `ui/nav/` | `NativeActivity` (the launcher, via the `.MainActivity` alias) + `NavHost`, `ShellViewModel` (Pendentes, network, APK banner), `ShellChrome.kt` (bottom bar, "+", Pendentes sheet), `ShellNav`, `NativeLinks`, `ShellEvents` |
| `ui/login/` | Native login (`POST /api/auth/login`; signup stays closed on the phone) |
| `ui/<feature>/` | One package per screen: Screen, ViewModel, state |
| `data/` | `AppGraph` (no DI framework), `ApiClient` (OkHttp + kotlinx.serialization), `AuthRepository`, `ReadCache`, repositories |
| `core/`, `rules/` | Pure Kotlin: money, dates, ported client rules |
| `outbox/`, `notify/`, `update/` (Java) | Offline queue and sender (`Outbox`: sign in/out, flush), bank-notification listener (`NotifyAccess`), APK update (`ApkUpdater`) |

## The shell
- `NativeActivity` starts on `login` without a `Session`, else on `home`. Around every page: the
  bottom bar (Início, Lançamentos, Planejar, Investir, Ajustes; `ShellNav`), the "+" (the native
  "+ Novo", `NewEntryActivity`, Cartão inside Cartões), the APK banner and the Pendentes sheet.
  Back with nothing below goes to Início; on Início it moves the task to the back. Aprovar always
  goes back to Extrato (`ShellNav.backTarget()`).
- Switching a tab or a bottom-bar section saves the page that leaves (`popUpTo { saveState }`) and
  restores the one that comes back (`restoreState`): its ViewModel, data and scroll survive, so a
  tab shows at once where it was and re-reads behind. Pages fade in 120 ms (`PAGE_FADE_MS`), and
  the active top tab scrolls into view.
- Session: the login writes `outbox/Session.java` (`Outbox.signIn`: Keystore-sealed token, the
  workers rescheduled). A 401 on any request clears the session if it is still the token that was
  refused (`AppGraph.handleUnauthorized`) and the shell returns to the login; the queue stays.
  Sair does the same and clears the read cache.
- Links between screens are web paths (`/ajustes#contas`, `/lancamentos/cartoes`): `NativeLinks`
  maps them to a page; desktop-only pages (Importar, Regras de importação, Integrações, the full IR
  report, editing allocation targets and sectors) have no page and the screens show a note instead.
- Native writes call `ShellEvents.emitDataChanged()`: the shell rereads the queue and shows the
  notice; screens reread when they open. The background sender reports through `OutboxEvents`.
- Reads: cache first, then network, "atualizado às HH:MM" when from cache.
- Server address: `BuildConfig.API_BASE_URL` (`-PfinancasApiBase`) until a session stores its own.
