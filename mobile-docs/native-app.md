# Native phone app and a desktop for the big screen

Two interfaces for two platforms (owner, 2026-10-22): "I use practically only the phone, but I want
to keep the desktop, and I'd like the interfaces to be different, since they are two distinct
platforms". The phone becomes a native Android app (Kotlin + Jetpack Compose); the desktop stays
React and is redesigned for a wide screen. Earlier in the same conversation the owner accepted
installing a new APK after each deploy, and `deploy.yml`'s `apk` job now publishes one every time.

The project documentation — architecture, conventions, build, the order, one spec per screen, the
desktop plan and how to run the work with agents — is in `mobile-docs/native/` (start at its
`README.md`). This file keeps the decisions.

This replaces the "No native rewrite" decision of `steps-to-production.md` (its table, "Shape").
Everything else there — the native outbox, the notification listener, Aprovar, Tailscale, the
key — stays and is reused.

## Decisions

| Topic | Decision |
|---|---|
| Phone | Kotlin + Jetpack Compose, Material 3, in the existing Android project (`frontend/android`). Java and Kotlin live side by side; the Java packages (`outbox/`, `notify/`, `update/`) stay Java until a screen needs to change them. |
| Migration | One screen at a time, in the order of daily use. A screen not migrated yet keeps opening in the WebView, so the app is usable at every step. No big-bang rewrite. |
| Desktop | React, the same `frontend/src`, redesigned for a wide screen: tables, several columns, panels side by side, analysis first (investments, IR, import). The phone's needs stop shaping it. |
| Server | Unchanged. The Flask API is the only source of truth for both; the native app is one more client of the same endpoints, with the same `client_id` idempotency. |
| Money rules | Stay on the server. A rule the frontend computes today (`lib/*Rules.js`) is either moved behind an endpoint or ported to Kotlin with the **same test cases** as JVM tests — the pattern already used by `OutboxRules.java` ↔ `outboxRules.js`. Prefer the endpoint when the rule is about money. |
| Updates | A new APK from CI on every deploy, offered by "Nova versão disponível". The screen bundle (WebView self-update) keeps working for the screens not migrated yet and goes away with the last one. |
| Colours | The web's tokens (`frontend/src/index.css`) as `ui/theme/Tokens.kt`; `TokensTest` reads the CSS and fails when they differ. Light/dark follows Ajustes › Aparência (`ShellPrefs`, written by `ShellPlugin.setTheme`). |
| Build check | `.github/workflows/android-check.yml` compiles the debug APK and runs the JVM tests on every branch push that touches Android. The session container cannot build an APK: `dl.google.com` (Android SDK, Google's Maven) is blocked there. |

## Step 0 — Kotlin and Compose in the project (2026-10-22)

- `android/build.gradle`: Kotlin Gradle plugin and the Compose compiler plugin (`kotlin_version`).
- `android/variables.gradle`: `composeBomVersion`.
- `android/app/build.gradle`: `org.jetbrains.kotlin.android`, `org.jetbrains.kotlin.plugin.compose`,
  `buildFeatures.compose`, JVM target 21 (the same as Java in `capacitor.build.gradle`), Compose
  BOM, Material 3, `activity-compose`.
- `ui/theme/Tokens.kt`, `Theme.kt` (`FinancasTheme`, `Palette`, `LocalPalette`, `ShellPrefs`),
  `TokensTest.kt`.
- No screen yet, so no `native-level.txt` bump: the web screens call nothing new.

## Step 1 — "+ Novo" native

The most used screen, and the one where opening instantly matters most.

- A `NewEntryActivity` (Compose, a bottom sheet over the WebView) with the four forms of
  `components/NewEntrySheet.jsx`: despesa, receita, transferência, cartão (crédito/débito, by
  `lib/cardFunctions.js`), on a large focused amount field, in typing order.
- Writes into the native outbox (`OutboxStore.put()` + `OutboxWorker`) with a phone-generated
  `client_id`, exactly the item shape `lib/outbox.js` writes today — the sender, its rules and the
  server do not change. Offline works for free.
- Accounts, categories and cards: fetched from the API with `Session`'s token and kept on the phone
  (last good copy), so the form opens offline.
- The WebView's "+ Novo" button calls a new plugin method (`NativeScreens.open("new-entry")`);
  when the sheet closes, the WebView refreshes its data and the outbox count. **Bump
  `native-level.txt`** in that commit: screens calling the new method need this APK.
- Ported rules with tests: which forms a card offers (`cardFunctions.js`), the amount parser
  (comma decimal), the creation payloads.

## Step 2 onwards — the order

| # | Screen | Note |
|---|---|---|
| 2 | Aprovar | Comes from the notification; native can approve without loading the WebView. |
| 3 | Início | Balance, Resumo do mês, Precisa de atenção, the bell. `consolidatedBalance()`, `bankingTransactions()` and `attentionRules.js` are frontend rules today — candidates for an endpoint. |
| 4 | Extrato, Cartões | Long lists: where native gains most. |
| 5 | Orçamento, Recorrentes, Metas, A receber | Forms; `monthlyPlan.js`'s sliders. |
| 6 | Ajustes | Contas, Cartões, Categorias, Regras, Notificações, Versão do app. |
| 7 | Investimentos | The largest (Posição, Operações, Proventos, Rentabilidade, IR, charts). Last. |
| 8 | Remove the WebView | Capacitor, `bundle/`, `services/app_bundle.py`, `native-level.txt`, `dist-android`. |

Extras only native gives, once Início exists: a home-screen widget (balance, next invoice) with
Jetpack Glance, an app shortcut to "+ Novo".

## The desktop redesign

A separate track, in React, after the phone no longer depends on the same screens (it can start
any time: the APK carries its own build of the screens, so a desktop change reaches the phone
only through the bundle until each screen is native — check the phone after a desktop change while
both still share a screen).

- Layout for ≥ 1280 px: a fixed sidebar, content in columns, tables with sticky headers instead
  of stacked cards, filters always visible.
- Analysis first: Investimentos (Posição as a full table, charts beside it), IR, Importar, the
  Extrato with search and bulk actions.
- The phone-only parts leave the desktop: the 44 px touch targets below `lg`, the bottom
  navigation, "+ Novo" as a bottom sheet (a dialog or an inline row instead).
- A plan screen by screen goes into `docs/next-steps.md` before it starts; the owner checks each
  one at desk size.

## Verification

- Kotlin rules: JVM tests (`testDebugUnitTest`), run by `android-check.yml` on the branch and by
  `deploy.yml` (`testReleaseUnitTest`) on main.
- Each migrated screen: the owner on the phone, with the debug APK (`/apk/financas-debug.apk`,
  installs beside the real app) before it reaches the real one.
- Backend and web: as today (pytest, `npm test`, Chromium screenshots for the desktop).
