# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-24 · native migration session C: Orçamento, Recorrentes, Metas, A receber, Ajustes

Cloud session, branch `claude/practical-hamilton-e6nxfi` from `main` at `505a258` (session A's PR
#43 already merged, so no stacking), PR to `main`. No builder agents; one Sonnet review at the end.
Decision field (installments 48/72, description required) left blank: both stay as today.

### Done
1. **Ports** (JVM tests with the node cases): `rules/MonthlyPlan.kt` (percentRoom, clampPercent,
   stepPercent, PERCENT_STEP, percentOf, categoryAmountPreview, livePlanTotals/livePlanText, flag
   texts and order, spendStatus, planFlagKey, visibleFlags; `BudgetStatus`); `lib/planFlags.js` →
   `PlanFlagDismissals` (SharedPreferences). `frequencyLabel` → `lib/recurring.js` and the goal
   texts → new `lib/goals.js`, node tests first, then `Recurring.kt` / `Goals.kt`.
   `groupReceivables`, `localDateOfTimestamp`, `notifyRules.js` (`NotifyTexts.kt`), the APK half
   of `appBundleRules.js` (`ApkUpdateTexts.kt`); inline web rules got `Receivables.kt` and
   `Settings.kt` with tests.
2. `ui/components/PercentSlider.kt` (−/+, the R$ beside it, capped at room, haptic tick),
   `NativeTopBar`, the routes (`NativeRoutes`, `NativeLinks`, `NativeScreens.routes()`), the web
   opening them (`NativePage`), native-level 7.
3. Orçamento, Recorrentes, Metas, A receber native, online-only like the web (writes on
   `writeApi`, never queued; offline message "Esta ação só funciona conectado.").
4. Ajustes native: Contas, Cartões, Categorias, Aprovar, Aparência, Perfil, Notificações dos
   bancos, Versão do app (APK only). Regras and Integrações stay in the WebView (spec Status).
   Theme and Sair reach the WebView through `ShellPrefs` + `Shell.takeThemePreference/takeSignOut`.
- Checks: node 196 green, vite build green, the pure JVM suite (core + rules, 220-odd tests) green
  in a local harness; `android-check.yml` — see the PR (the first run failed only on the
  ModalBottomSheet `@OptIn`, fixed in `d05a10f`).

### Not done, and why
- **No phone check** (the owner's; the APK cannot be built here). Each spec's Acceptance list is
  in the PR as a checklist.
- Not built (listed in next-steps): month swipe / pull to refresh, swipe and long-press menus,
  widgets, "Sempre perguntar" inside native Aprovar, biometric gate, the listener-lost
  notification, the bundle half of Versão.
- The full JVM suite (ui/, data/ tests with Android classes) only runs in CI.

### Learned
- **This container can run the pure JVM tests**: a scratch Kotlin/JVM Gradle project with
  `sourceSets` pointing at `app/src/{main,test}/java/.../{core,rules}` plus the DTO files, the jars
  fetched with `curl` from `repo1.maven.org` (repo.maven.apache.org answers 404/429 through the
  proxy, and Gradle caches the miss) and `kotlin-stdlib` served from a `file://` repo.
  `kotlin.stdlib.default.dependency=false`. ~30 s per run. It caught three DTO name clashes
  (`BudgetItemDto`, `BudgetTotalsDto`, `InboxSettingsDto` already existed) before CI.
- Android strings: a bare `"` inside `<string>` is dropped by aapt — escape as `\"`; a literal `%`
  in a string without arguments needs `formatted="false"`, and `%%` where there are arguments.
- `ModalBottomSheet`/`SheetValue` are experimental in this Material3: every sheet composable
  needs `@OptIn(ExperimentalMaterial3Api::class)` (CI fails, the IDE would only warn).

### Next session
1. Fix what the owner's phone check of this PR finds, on this branch.
2. Otherwise step 7 (Investimentos screens) on session B's ports, or `home-panels.md`.
