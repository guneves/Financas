# Native phone app — project documentation

The phone app is being rewritten from React-in-a-WebView (Capacitor) to native Android
(Kotlin + Jetpack Compose), one screen at a time; the desktop stays React and gets its own
interface for a wide screen. Decided by the owner on 2026-10-22. The decision record and its
reasons are in `../native-app.md`; this folder is everything needed to do the work.

## Reading order

| File | What it holds | Read it when |
|---|---|---|
| `../native-app.md` | The decisions and why | Once, to understand the direction |
| `architecture.md` | Packages, layers, how native and WebView coexist, data, session, offline | Before writing any Kotlin |
| `conventions.md` | Rules for the Kotlin code: money, dates, strings, theme, components, tests | Before writing any Kotlin |
| `build-and-test.md` | CI, local builds, the debug APK, what a session container can and cannot do | Before pushing native code |
| `migration-order.md` | The steps, what each needs first, when to bump `native-level.txt`, done-when | To pick the next task |
| `rules-port.md` | Every client rule in `frontend/src/lib/`: port to Kotlin or move to an endpoint | Before a screen that uses one |
| `proposals/` | Backend endpoints proposed to replace client money rules, one file per proposal (status at its top) | Before implementing one, or before a screen it serves |
| `screens/` | One spec per screen (`_template.md` is the shape) | When building that screen |
| `findings.md` | Endpoints to add, inconsistencies and possible bugs found while specifying | Before a step, to see what touches it |
| `desktop.md` | The desktop redesign, screen by screen | When working on the desktop track |
| `agents.md` | How to run the migration with Claude Code agents, and the prompts | To start a working session |

## Status

| Step | What | Status |
|---|---|---|
| 0 | Kotlin + Compose in the project, native theme from the web's tokens, `android-check.yml` | Done 2026-10-22 |
| 1a | Step 1's foundation: `core/` (format.js, money input), `rules/` (cardFunctions.js, the sharing form), `data/` (ApiClient, ReadCache, repositories for accounts/categories/cards, AppGraph), the `NativeScreens` plugin (empty `routes()`, stub `open()`) | Done 2026-10-22 |
| 1 | "+ Novo" native (`NewEntryActivity`, the web opening it, `native-level.txt` 2 → 3) | Built 2026-10-22 on `claude/native-novo`, CI green, reviewer clean; waiting for the owner's phone check and the merge |
| 2–8 | Aprovar, Início, Extrato/Cartões, planning, Ajustes, Investimentos, remove the WebView | Not started |
| D | Desktop redesign | Not started |

Keep this table and each spec's `Status` row current; `docs/next-steps.md` holds the open items
and `docs/done-tasks.md` the finished ones, as for the rest of the project.

## The three things never to forget

1. **The server is the source of truth and keeps every money rule.** A native screen shows what the
   API returns and sends what the API accepts; it never computes a balance, an invoice month or a
   tax on its own unless the rule is ported with the same test cases (`rules-port.md`).
2. **A screen not migrated yet still works.** Every step ships a usable app: the WebView keeps
   serving whatever is not native.
3. **Bump `frontend/native-level.txt`** in the same commit as any change the web screens call in
   the APK (a new plugin method, an event). CLAUDE.md, "The APK's screens come from the server".
