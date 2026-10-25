# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-24 · native migration session D: Investimentos (all seven tabs)

Local session on the owner's PC, branch `claude/native-session-d` from `main` at `e2ee3e1`
(sessions A, B and C already merged, so no stacking), PR to `main`. No builder agents; one Sonnet
review at the end. Session B had added `client_id` (042), so Operações and Proventos creations are
queued offline, as the prompt asked.

### Done
1. **Routes**: `NativeRoutes.INVESTMENTS` (posicao, operacoes, proventos, rentabilidade, alocacao,
   ir, calculadora) in the NavHost, the plugin's `routes()`/`open()`, `NativeLinks`
   (`InvestimentosRoutes`), the web routes wrapped in `NativePage`; native-level 7 → 8. The seven
   tabs in the native top bar; a tab the APK lacks would open on the web.
2. **Outbox**: kinds `INVESTMENT` and `PROCEED` on both sides (`outboxRules.js`,
   `OutboxRules.java`, `OutboxPending.kt`, `PendingSheet.jsx`): they move no account, make no
   Extrato row, leave Início and the "Saldo estimado" banners alone, and in Pendentes only
   "Descartar". `EntrySaver.createJson()` keeps explicit nulls (`cash_account_id: null`).
3. **Screens** (`ui/investimentos/`): Posição, Operações (Registrar operação, edit, delete,
   corporate events, Aportes e resgates), Proventos (calendar first, collapsible filters), then
   Rentabilidade, and spec 16's native part: Alocação read-only + "Quanto vai aportar?", IR meter +
   DARF months, Calculadora. Targets, sectors and the full IR report open `?web=1`.
4. **Ports with JVM tests** of what the pages did inline: `PortfolioView`, `Operations`,
   `ProceedsForm`, `ReturnsRules`, `AllocationRules`, `CompoundInterest.chartPoints`; new
   `StackedAreaChart`; `LineSeries.width`.
- Checks: full JVM suite 500 green + `assembleDebug` locally; node 198; `npm run build`;
  `android-check.yml` green on `43f80e2` and `8c986e7` (the review-fix commit pushed after).
  No pytest run: no backend change.

### Not done, and why
- **No phone check** (the owner's): each spec's Acceptance list, airplane mode especially.
- Not built (listed in next-steps, step 7): pull-to-refresh, swipes, chart crosshair, landscape,
  the shell "+" opening Registrar operação, Proventos' 30-day total and payment-day notification,
  the DARF reminder.
- **Owner decision left**: web investment creations offline too (they still send no
  `client_id`). Privacy was decided (owner, after the PR): every R$ of Operações and Proventos is
  masked on both sides; the web followed in the stacked PR (`claude/web-privacy-investments`),
  checked in Chromium on a scratch server with privacy on. IR and the exemption notices stay
  unmasked on both.

### Review
One Sonnet reviewer over `origin/main..HEAD`: **no blockers, two majors, both fixed**: the
"Saldo estimado" counters (`HomeLogic.pendingInBalance`, `ExtratoViewModel.balanceEstimated`,
`Dashboard.jsx`, `useLancamentos.js`) counted a queued operação/provento — now only the kinds
that move an account (`ACCOUNT_KINDS`); a redemption's label showed its R$ in privacy mode. Minors
fixed: bonus cost, the redemption range message and the opportunities' average price masked; a
misplaced KDoc. Accepted: the queued body passes through `org.json` (numbers as `Double`; exact for
real amounts); suggested aporte amounts stay visible (they split what the owner types).

### Learned
- **`frontend/node_modules` in the main tree had lost `.bin` and packages** (likely a peer
  worktree's junction removal); `vite` was "not recognized". `npm ci` restored it.
- Android trims leading/trailing spaces of a `<string>`: put the " · " separator in code.
- `ScreenLoad` + `PlanejarScaffold` (session C) carry any screen; reuse them over new scaffolds.

### Next session
1. Fix what the owner's phone check of this PR finds, on this branch.
2. Otherwise step 8 (remove the WebView) planning, or `home-panels.md`.
