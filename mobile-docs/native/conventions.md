# Native code conventions

CLAUDE.md holds for everything; a rule about a React screen applies to its native replacement.

## Code
- New code is Kotlin; `outbox/`, `notify/`, `update/` stay Java (`@JvmStatic` where
  Java calls Kotlin). One package per screen under `ui/`; `core/` and `rules/` are pure (no Android
  or Compose) and JVM-tested.
- Comments in Portuguese without accents; UI strings in `res/values/strings.xml`, with accents,
  prefixed by feature, the same words as the web. Server errors shown as they arrive.

## Money and dates
- Never `Double`/`Float` for money: `BigDecimal` from the JSON text, `HALF_UP` to 2 places, pt-BR
  format from `core/`. Typed amounts follow `lib/format.js`'s parser. Send the JSON the web sends.
- No money the server already returns is computed on the phone; a needed client rule is an
  endpoint or a port with the node test cases copied.
- `LocalDate`, ISO zero-padded; "today" is the device's local date.

## Writes, offline, identity
- Creations carry a `client_id` (UUID) stored in the outbox item before the first attempt, one per
  card purchase. Only creations are queued offline; edits and deletes are refused offline and never
  retried after a timeout (writes through `writeApi`). Categories go by `category_id`.
- `OutboxRules.java` ports `lib/outboxRules.js`: change one, change the other, with a test each.

## Look
- Colours only from `ui/theme/Tokens.kt` (the CSS names of `index.css`; `TokensTest` keeps them
  equal), never a hex literal. Web visual rules hold. Touch targets ≥ 48 dp. Amount fields open
  large and focused with the decimal keyboard. Privacy mode masks balances and the portfolio without
  resetting the screen. Light and dark both checked.
- `ui/components/` is the counterpart of `components/ui.jsx` (sheet, summary panel, "⋯" menu,
  snackbar toast, confirm dialog, alert card, list skeleton, segmented/tabs, percent slider,
  fit-value text); destructive actions always go through the dialog.

## Build and ship
- Sessions cannot build an APK (`dl.google.com` is blocked): push and let `android-check.yml`
  compile the debug APK and run the JVM tests (a push outside `frontend/android/` skips its path filter; dispatch it).
- A screen ships with its ViewModel and tests, its `NativeRoutes` page in the shell's NavHost
  (and `NativeLinks` for the web paths that point to it), the spec's `Status` row and the session
  docs, and green CI. A link to a page the phone does not have (desktop-only) gets no target: the
  shell says "Esta tela fica no computador". The owner checks the spec's Acceptance list on the
  phone with the debug APK.

## Never
- Send a bank notification's text off the phone, or accept `com.android.shell` in a release build.
- Recreate on the client a rule the server owns (invoice month, Saldo do plano, tax).
- Store the token anywhere but `Session` (Keystore-sealed).
