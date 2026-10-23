# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (night) · native step 1's foundation: rules, data layer, NativeScreens

Local session on the owner's PC, branch `claude/native-foundation` (created here from `main`;
no branch was assigned). The owner's prompt: session 1 of the native migration, the foundation,
no screen. Briefing by `session-scout` (found by `subagent_type`, no fallback needed).

### Done
- **Three rule ports in parallel** (`rule-porter`, each in its own worktree and branch, merged into
  the session branch when green): `core/Format.kt` + `core/MoneyInput.kt` (all of `format.js`,
  `parseMoneyInput`/`moneyInputValue`), `rules/CardFunctions.kt` (all of `cardFunctions.js`),
  `rules/Sharing.kt` (`shareFormFrom`, `shareFormError`, `sharePayload`, `SHARE_OPTIONS`). Each
  `.js` and `.kt` starts with the "Port: change one, change the other" comment. The sharing port ran
  after the format one because `sharing.js` calls `formatCurrency`.
- **`data/` and the plugin** (`native-screen-builder`, branch `-data`, owner of the shared Android
  files this round): `ApiClient`, `ReadCache`, `Repositories` (accounts, categories, cards),
  `Dtos`, `JsonSerializers` (BigDecimal from the JSON text), `AppGraph`;
  `ui/nav/NativeScreensPlugin.kt` registered in `MainActivity` (`routes()` → `[]`, `open()` rejects
  UNIMPLEMENTED, `dataChanged`/`navigate` helpers). Libraries and versions in `done-tasks.md`.
- 64 new JVM tests (cards 7, format/money input 14, sharing 3, data 40). CI on each branch: 39878478611,
  39879129355, 39879583998, 39879956700, all green; the merged branch's run is in the PR.
- `npm test` unchanged at 144 (only comments were added to four `.js` files).

### Not done, and why
- **No screen.** `NewEntryActivity` and the web side of "+ Novo" are the rest of step 1
  (`next-steps.md`). **No `native-level.txt` bump**, on the owner's instruction: the web does not
  call `NativeScreens` yet. The commit that makes the React layout call `routes()`/`open()` must
  bump it.
- `settlePayload` and `shareSummary` (sharing.js) and the outbox's `buildItem`/`newClientId` are not
  ported; "+ Novo" needs the latter two.
- No `native-parity-reviewer` run: there is no screen to compare yet.
- **pytest is red between 21:00 and midnight local** (one test, the coupon landing in the portfolio
  account; UTC vs local date). Not from this branch — reproduced on the untouched backend. Open in
  `next-steps.md`.
- Carried, still open: everything in the previous entry's "Not done" (APK cannot be built in a cloud
  container; desktop redesign; `findings.md` triage; Plus Jakarta Sans; the "APK on every deploy"
  phone check; the card débito/Flash walk-through; brapi quota with hourly quotes) and the fuzzing
  leftovers (old rows not cleaned; frontend/Java parsers/CSV/uploads not fuzzed; no upper bound on
  proventos and corporate-action ratios).

### Next session
The rest of step 1: `native-screen-builder` with `mobile-docs/native/screens/01-novo.md`, reusing
`data/`, `core/`, `rules/`; port `buildItem`/`newClientId` first (rule-porter); then the web's
`routes()`/`open()` call and the native-level bump; then `native-parity-reviewer`.

### Learned
- **The sharing form refuses "12,5"**: `shareFormError()` reads the other person's part with
  `Number()`, unlike every other money field. The port mirrors it; fix both sides (next-steps).
- `parseMoneyInput()` in Kotlin returns `MoneyInput.Empty`/`Invalid`/`Amount`, not null/NaN.
  `moneyInputValue` has two overloads, so a bare `null` needs `null as BigDecimal?`.
- The Write tool can turn `\u00A0`-style escapes into the literal invisible character; write
  escapes in Kotlin sources and check them (the format port lost a CI round to it).
- The rule-porters didn't need a `node_modules` junction: `npm test` is `node --test` with no
  dependencies.
- Worktree agents told to branch from `origin/<session branch>` after a fetch started on the right
  commit — say it in every worktree prompt.
- Still true from earlier: Kotlin's JVM target must stay 21 (Capacitor's generated file); Maven
  Central rate-limits directory listings; Java's `\s` does not match U+00A0; `SERIES` in
  `charts.jsx` is hex literals, to move into `index.css` before step 7.
