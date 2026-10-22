# Migration order

One step per APK. Each step leaves a usable app: what is not native yet keeps opening in the
WebView. The order follows daily use (the owner uses the phone for entering and approving every
day, for investments a few times a month).

| Step | Screens | Spec | Needs first | Bumps `native-level.txt`? | Done when |
|---|---|---|---|---|---|
| 0 | — (foundation) | — | — | No | Kotlin + Compose build in CI; theme from the web's tokens. **Done 2026-10-22.** |
| 1 | "+ Novo" (despesa, receita, transferência, cartão crédito/débito) | `screens/01-novo.md` | `core/` money + date parsing ported with tests; `data/` client + cache for accounts, categories, cards; `NativeScreens` plugin; `NewEntryActivity` | **Yes** (the web calls `NativeScreens`) | The owner records each kind on the phone, online and in airplane mode, and each appears once in the Extrato after reconnecting |
| 2 | Aprovar | `screens/02-aprovar.md` | `NativeActivity` + `NavHost`; the inbox repository; opening from the notification | Yes if the web gains a call | Every Aprovar action works natively, including "Aprovar prontos", "É este", "Não é esta", "Trocar" |
| 3 | Início, the bell | `screens/03-inicio.md`, `screens/00-shell.md` (bell, privacy) | Privacy mirrored to native; decision on the client rules (`rules-port.md`: balance, cash flow, attention) | Yes (privacy mirror) | Início natively shows the same numbers as the web on the same data |
| 4 | Extrato (both views), Cartões | `screens/04-extrato.md`, `screens/05-cartoes.md` | Edit/delete flows; receipts (camera/file picker); export via share sheet | Maybe | The same lançamentos, edits, invoice payment, "Desfazer pagamento" and refunds as the web |
| 5 | Orçamento, Recorrentes, Metas, A receber | `screens/08-…`, `09-…`, `10-…`, `06-…` | `PercentSlider`; `monthlyPlan.js` rules ported | Maybe | Each screen matches the web's numbers and actions |
| 6 | Ajustes | `screens/11-ajustes.md` | — | Maybe | Each section native, or deliberately left to the WebView/desktop as the spec says |
| 7 | Investimentos | `screens/12-…` to `16-…` | A chart library; the investments rules (`rules-port.md`) | Maybe | Posição, Operações, Proventos, Rentabilidade (and what the specs keep native of Alocação, IR, Calculadora) match the web |
| 8 | Shell: native login, navigation, remove the WebView | `screens/00-shell.md` | Every page above native (or moved to desktop-only) | — (the level file is deleted) | The APK has no WebView; Capacitor, `bundle/`, `services/app_bundle.py`, `dist-android` and `native-level.txt` are gone |
| 9 | Importar | `screens/07-importar.md` | — | — | Desktop-first: decided in its spec |
| D | Desktop redesign | `desktop.md` | Can run in parallel from step 1 | — | Per screen, in `desktop.md` |

## What can run in parallel

- **Specs, rule ports and the desktop** can run in parallel with any step.
- **Two screens can be built in parallel** only after the foundation they share exists
  (`ui/components/`, `data/ApiClient`, `ReadCache`, `NativeActivity`, `NativeScreens`). Build those
  in the step that first needs them (1 and 2), alone; from step 3 on, screens of the same step can
  go to parallel agents on separate branches (`agents.md`).
- Files every screen touches — `variables.gradle`, `app/build.gradle`, `AndroidManifest.xml`,
  `strings.xml`, the `NavHost`, `NativeScreens`' route list — are edited by one branch at a time;
  merge in order.

## When a step changes the web too

Steps 1–7 change the React layout to open the native screen. That change reaches older APKs as a
web bundle, so:

- the web asks `NativeScreens.routes()` and falls back to the React screen for anything not listed
  (an old APK lists nothing);
- `native-level.txt` is bumped in the step that adds the plugin (step 1) and in any later step that
  adds a plugin method or event the web calls.
