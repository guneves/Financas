# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-24 · native migration session A: Extrato and Cartões

Local session on the owner's PC, branch `claude/native-session-a` from `main` at `457d0da`, PR to
`main`. No session-scout, no builder agents; one Sonnet review at the end. Decisions left blank by
the owner, so both stay as today: Corretora accounts stay in the banking forms / pay sheet /
autopay; the Extrato shows a transfer to the Corretora as a transfer.

### Done
1. **Paging** on `GET /api/transactions` (`limit`/`cursor`, keyset, whole-filter `totals`, `count`,
   `day_totals` over each whole day) + the web's filtered Extrato on "Carregar mais" (one commit).
2. **`lib/investmentStatement.js` ported** (`InvestmentStatement.kt`, the 8 node cases, same-day
   order as today) plus its `detailText`.
3. **Shared pieces**: `/api/home` gained `projections` (pytest), `LancamentosRepository`, multipart
   upload / download in `ApiClient`, camera + file picker (`ReceiptPicker.kt`, FileProvider, no
   camera permission), Android share sheet for export and receipts, strings, the rules ports.
4. **Extrato native** (both views), 5. **Cartões native** — details in `done-tasks.md` and each
   spec's Status row. Routes `extrato`/`cartoes` in the plugin and NavHost; native links to
   Lançamentos stay native (`NativeLinks`); native-level 6.
6. **Aprovar's writes** on `writeApi`.
- Checks: pytest 1615 green, node 180, both vite builds, JVM 348 locally + assembleDebug;
  `android-check.yml` green on `04a570b` and `e338e45`. Review: no blockers/majors; its note (no
  double-tap guard on the edit save) fixed.

### Not done, and why
- No phone check (the owner's; there is an emulator but logging in needs a cleartext server).
- Not built natively: swipe/long-press, the new-row flash, attach from another app, card carousel,
  widget, offline refunds (listed in next-steps).
- The web Extrato still loads the whole history for the unfiltered list and projections.

### Learned
- **A peer session switched this shared working tree to `main`** at 10:47; my next four commits
  landed on local `main` and the first push sent an empty branch. Repaired with `git branch -f`
  (nothing reached `origin/main`). Check `git branch --show-current` before committing.
- This PC builds the APK: `gradlew.bat --offline` with `JAVA_HOME` = Android Studio's `jbr`.
- The spec/docs files are CRLF; the Bash tool collapses `\\` in heredocs — write edit scripts with
  the Write tool.
- A pending outbox row dated before the server's newest day opens that day twice: LazyColumn keys
  must not be the date alone.

### Next session
1. Fix what the owner's phone check of this PR finds, on this branch.
2. Otherwise steps 5+ or `home-panels.md`; merge order with `claude/native-b-investments` (both
   touch `native-level.txt` and the `NativeScreens` routes).
## Session — 2026-10-24 · native migration session B: what Investimentos needs (no screen)

Local session on the owner's PC, branch `claude/native-b-investments` (from `main` at `457d0da`),
in its own worktree `..\Financas-native-b` because another session was editing the main tree
(`transactions.py`, a paging test). PR to `main`. Decisions: `client_id` **yes** (owner, mid-session:
"keep the offline queue"); endpoints: **all five** (the field was blank; the step listed five).

### Done
- **Backend** (pytest 1603 → 1636, full run green locally): migration 042 (`client_id` on
  investment, provento and corporate-action creations); `POST /api/investments/redemptions` (PEPS
  and the single-title cost on the server, the old `treasury.test.js` cases in pytest);
  `DELETE /api/investments/by-assets` (atomic grouped Tesouro delete); `realized_result` read by
  Operações, `by_year` by Proventos, `net` by IR. Details in `done-tasks.md` (session B note).
- **Screens unchanged**, checked with before/after Chromium shots (Operações and Proventos
  byte-identical; IR and Posição identical to the eye, Posição differing only by chart animation).
  The redemption was walked through Posição's sheet.
- **Colours**: SERIES and FLOW are CSS variables (`--series-0..7`, `--flow-*`), same values in
  both themes, mirrored in `Tokens.kt` (TokensTest) and fixed by `chartColors.test.js`.
- **`ui/charts/`**: `ChartGeometry.kt` (tested) + `DonutChart`, `SignedBarChart`, `GapLineChart`.
- **Ports** (43 JVM tests, same cases and order as node): `PortfolioAccount`, `AssetSearch` (node
  tests written first), `FixedIncome` (new form-error cases on both sides), `TreasuryLabels`,
  `ProceedsRules`, `CompoundInterest`. node 176 → 185; full JVM suite 361, 0 failures.
- **CI**: `android-check.yml` run 40101206958 on `660a8ae` **green** (JVM + debug APK). There is no
  branch pytest workflow (pytest runs in `deploy.yml` on `main`), so pytest was run here.
- Docs: specs 12/13/15/16 carry a dated note on what now exists; next-steps, done-tasks.

### Not done, and why
- **No queue yet for investment creations**: the server is idempotent, but neither outbox knows the
  kinds — that belongs with the native screens (step 7). The web sends no `client_id` on them.
- **The grouped delete was not clicked** (the walk had used up the second lot); pytest covers it.
- Carried, still open: B2; the owner's phone checks of steps 1–3; native 401 handling; the web
  `createEntry()` duplicate after a killed tab; the sharing form refusing "12,5"; pytest red
  21:00–midnight local.

### Review
One `native-parity-reviewer` (sonnet) over `origin/main..HEAD`: **no blockers, no majors**; every
claim checked. Noted, accepted: the server rounds the redemption with `rounded_money()` (can differ
from JS `Math.round(x*100)/100` by a cent only on float-noise inputs like 1.005); a single title with
`current_value <= 0` is now refused (the client used to send NaN); `by_year` may differ from the old
sum of rounded months by a cent. Fixed: the calculator port took an infinite period as "até 100
anos" where JS says "não fecha em meses inteiros".

### Next session
1. Session C of the prompts (the Investimentos screens), on top of this branch once merged.
2. Or `home-panels.md` / step 4, as the previous handoff said.

### Learned
- **The `native-parity-reviewer` agent file was removed in `f921be2`**; it was recovered from git
  (`git show f921be2^:.claude/agents/native-parity-reviewer.md`) and run as general-purpose.
- **A worktree needs Capacitor's ignored folders for Gradle**: copy
  `frontend/android/capacitor-cordova-android-plugins/`, `app/src/main/assets/` and
  `app/src/main/res/xml/config.xml` from the main tree, and junction `frontend/node_modules`.
- **pytest has no xdist here**; `-n auto` fails before running anything (and `| tail` hides the
  exit code).
- **The proventos sync hits StatusInvest live from a scratch server** (no patch outside pytest):
  both runs of a before/after walk must use the same network state.
