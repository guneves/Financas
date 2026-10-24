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
