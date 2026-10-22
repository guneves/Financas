# Conventions for the native code

These add to `CLAUDE.md`, which still holds for everything (money, `user_id`, transfers, categories
by id, card purchases by `client_id`, the outbox, invoices...). Where a CLAUDE.md rule is about a
React screen, it applies to its native replacement with the same meaning.

## Language and files

- New code is **Kotlin**. The Java packages (`outbox/`, `notify/`, `bundle/`, `update/`) stay Java;
  don't rewrite working Java for style. Kotlin calls Java directly; when Java must call Kotlin, use
  `@JvmStatic` (as `ShellPrefs` does).
- One package per screen under `ui/` (see `architecture.md`); pure code (`core/`, `rules/`) imports
  nothing from Android or Compose, so it runs in JVM tests.
- Comments in Portuguese without accents, like the existing Java; identifiers in English, or the
  Portuguese domain word when there is no good English one (`fatura`, `provento` are fine).
- UI strings are Portuguese, **with** accents, in `res/values/strings.xml`, prefixed by feature
  (`newentry_title`, `inbox_approve_all`). The same words as the web screen — the owner should not
  have to relearn a label. Server error messages are shown as they arrive (they are already
  Portuguese).

## Money

- **Never `Double` or `Float` for money.** Parse JSON amounts into `BigDecimal` from their textual
  form; format with the pt-BR formatter in `core/` (`R$ 1.234,56`); round only with
  `RoundingMode.HALF_UP` to 2 places (the server's `rounded_money()`).
- Typed amounts follow the web's parser (`lib/format.js`, tested): comma is the decimal separator,
  a dot in groups of three is thousands. Port it with its test cases before the first form.
- Send amounts in the same JSON shape the React app sends today (look at the request in the spec);
  the server validates and rounds.
- A screen computes no money that the server already returns. When it must (a preview, a sum of
  what is on screen), the rule is ported with tests (`rules-port.md`).

## Dates

- `java.time.LocalDate`, ISO `AAAA-MM-DD`, zero-padded (the server compares as text). "Today" is the
  device's local date, as on the web.
- Shown as `dd/MM/aaaa` or the web's short forms (`lib/format.js`); month names in Portuguese.

## Identity and idempotency

- Every creation carries a `client_id` generated on the phone (UUID), stored in the outbox item
  before the first attempt — never regenerated on a retry. A card purchase has one `client_id` for
  all its installments.
- Categories are sent by `category_id`, never by name.

## Look and feel

- Colours only from `LocalPalette` / `MaterialTheme.colorScheme`, which come from
  `ui/theme/Tokens.kt` (the web's tokens; `TokensTest` keeps them equal). A new colour enters
  `Tokens.kt` under its CSS name, never as a hex literal in a screen.
- The web's visual rules hold: green/red/amber/sky only for gain/loss/warning/info; a signed amount
  through the signed formatter; numbers right-aligned in lists; big values shrink to fit rather than
  being cut.
- Touch targets at least 48 dp (Material's minimum; the web used 44 px).
- Money forms open on a large, focused amount field, in typing order, with the numeric keyboard
  (`KeyboardType.Decimal`).
- Privacy mode masks balances and the portfolio (never transaction amounts in forms), and toggling it
  does not reset the screen.
- Light and dark both work on every screen; check both before calling a screen done.

## The native UI kit (`ui/components/`)

Build each piece once, the first time a screen needs it, as the counterpart of the web's kit:

| Web (`components/ui.jsx`, `lib/`) | Native |
|---|---|
| `Sheet` | `ModalBottomSheet` wrapper with the app's padding and handle |
| `SummaryPanel` | The headline-numbers card of a screen |
| `Menu` ("⋯") | `DropdownMenu` behind an icon button, for two or more row actions |
| `toast()` | Snackbar host per screen |
| `confirmAction()` | `AlertDialog` with the same title/body/confirm texts |
| `AlertMessage` | Inline error/warning/info card |
| `ListSkeleton` | Placeholder rows while loading (never the empty state) |
| `SegmentedControl`, `Tabs` | Material 3 segmented buttons / tabs |
| `PercentSlider` | Slider with − and + for the fine step and the R$ beside it |
| `FitValue` | Auto-shrinking text for big money values |

No `window.confirm`-style shortcuts: destructive actions always go through the dialog.

## Tests

- Every rule in `core/` and `rules/` has JVM tests (`src/test/java/...`), with **the same cases** as
  the web's `*.test.js` when it is a port. When the web rule changes, the port changes in the same
  commit, with a test on each side (the pattern of `OutboxRules.java`).
- Parity tests that read the web's source (`TokensTest` reads `index.css`, `NotifyRulesTest` reads
  the manifest) are welcome wherever a value must stay equal on both sides.
- Compose UI tests need an emulator, which CI does not run today; screens are checked by the owner
  on the phone with the debug APK (each spec's "Acceptance").

## Shipping a screen

In one commit (or one PR):

1. The screen, its ViewModel, its tests.
2. The `NativeScreens` route registered, and the React layout opening it natively.
3. `frontend/native-level.txt` bumped if the web now calls something new in the APK.
4. The spec's `Status` row, `README.md`'s status table, `docs/next-steps.md` and
   `docs/done-tasks.md` updated.
5. `android-check.yml` green on the branch before asking for the merge.

## Never

- Send a bank notification's text off the phone (CLAUDE.md, "Bank notifications are read on the
  phone and stay there").
- Accept `com.android.shell` notifications in a release build.
- Recreate on the client a rule the server owns (the invoice month, the plan's Saldo, the tax).
- Store the token anywhere but `Session` (Keystore-sealed).
- Remove a Java plugin method that a lower native level's web screens still call.
