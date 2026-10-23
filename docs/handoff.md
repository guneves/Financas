# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-23 · native migration session 5: endpoint proposal + pending-balance port

Cloud session, branch `claude/native-migration-backend-proposals-7yx22w` (from `main` at `880f4fa`,
after PR #34). Briefing by `session-scout`, found by `subagent_type`, no fallback. Proposal and
port only: **no endpoint was implemented**, by the owner's brief.

### Done
- **`mobile-docs/native/proposals/home-attention-invoices.md`**: route, response JSON with an
  example, the server functions reused, the web switch and the pytest cases for `GET /api/home`,
  `GET /api/attention`, `GET /api/cc-invoices`, `DELETE /api/cc-expenses/purchases/<id>` and opt-in
  paging (`limit` + keyset cursor, with whole-filter `totals` and `day_totals`) on
  `GET /api/transactions`. Every case of `transactions.test.js` (10) and `attentionRules.test.js`
  (13) is mapped to a pytest case (or marked "stays client" with its server half), plus 18 new
  cases for `cashFlow.js`. Behaviour changes B1–B9 with a recommendation each. One new service
  `card_invoices.py` feeds all three reads, so Início, the bell and Cartões agree by construction.
- **Port** (agent `rule-porter`): `pendingAccountDeltas`, `applyPendingToAccounts`,
  `pendingAsTransactions`, `countByStatus` → `frontend/android/.../rules/OutboxPending.kt`, 11 JVM
  tests with the node cases in order (`OutboxPendingTest.kt`), commit `942e3f6`. `android-check.yml`
  run 39890464044 **green** (checked by `android-ci-watcher`). `npm test` 164 passed. No
  native-level bump (no screen calls it).
- Docs: `rules-port.md`, `findings.md`, `README.md` (new `proposals/` row), specs 03/04/05 point to
  the proposal; next-steps has "review the proposal" and `applyPendingToHome()`.

### Not done, and why
- **No endpoint built**: the brief was propose-only. The order of implementation is at the end of
  the proposal (cc-invoices first, one PR per endpoint, the web switched in the same PR).
- **`applyPendingToHome()`** (the overlay that keeps an offline despesa in "Saiu" once Início reads
  `/api/home`) is designed in the proposal, not written: it has no caller until `/api/home` exists.
- **`OutboxPending.kt` takes typed data classes**; there is no adapter yet from `OutboxStore`'s
  JSON items. The native Início will need one.
- **Out of the brief, flagged in the proposal**: Início's other panels (categories, pace,
  installments, invoice projection) and the Extrato's projections still need the full history; a
  second proposal (`home-panels.md`) would cover them.
- No pytest run: only docs and Kotlin changed (the scout counted 1536 collected).
- Carried, still open: the owner's phone check of native steps 1–2; native 401 handling; grouped
  Tesouro delete not atomic; the web `createEntry()` duplicate after a killed tab; the sharing form
  refusing "12,5"; pytest red 21:00–midnight local (`test_fixed_income_interest.py`); no screenshot
  check of last session's changed screens; `done-tasks.md` still has no row for the Aprovar
  session (PR #33).

### Questions for the owner
0. **The proposal** (PR "Proposal: home, attention and invoice endpoints"): edit it in the PR
   and merge to approve. Decide B2 in particular: the plan's "spent" (`month_banking_totals()`)
   counts a despesa typed in a Corretora account, Início's "Saiu" does not — should the plan follow
   Início? (It overlaps question 1.)

Carried from session 4 (the Inconsistencies in `findings.md`):
1. **Corretora in banking forms**: should "+ Novo", the pay-invoice sheet and autopay stop
   offering Corretora accounts? A despesa recorded there vanishes from Início today.
2. **Extrato vs Início for a transfer to the Corretora**: should the Extrato show it as
   aporte/resgate (`bankingTransactions()`), as Início does, and keep it out of its day totals?
3. **Débito purchase in Pendentes**: Corrigir reopens it as a Despesa. Acceptable, or should it
   reopen as Cartão › Débito?
4. **Installments**: the client stops at 48, the server at 72 — which limit? And should the
   description be required (client) or optional (server) for despesa/receita?
5. **"Despesas por categoria" on Início** groups by name, merging root "Outros" with "Lazer ›
   Outros". Group by id, showing "Lazer › Outros"?
6. **Privacy mode**: the cash-flow chart shows what Entrou/Saiu mask; Operações, Proventos'
   summary and history, Aprovar, Cartões' totals and A receber are unmasked. Mask which of these?
7. **Cards without a bank field**: Aprovar's ambiguous-target rule never runs for cards. Add a bank
   to cards?
8. Minor, no behaviour change, left for whoever touches Início: `/api/credit-cards` is cached under
   `['cartoes']` and `['inicio','cartoes']`.

### Next session
If the proposal PR is merged: implement it in its order, starting with `services/card_invoices.py`
+ `GET /api/cc-invoices` and Cartões switched (pytest cases listed in the proposal; freeze
`local_today` in every module that reads it). Otherwise the owner's answers above, then the pytest
21:00–midnight failure.

### Learned
- `month_banking_totals()` (plan "spent") and Início's flow differ on one case: a non-investment
  despesa/receita in a Corretora account (the plan counts it, `bankingTransactions()` drops it).
  `month_investment_flow()` matches Início exactly.
- `invoiceId()` in `attentionRules.js` does not zero-pad the month (`c1|2026-9`), so an attention
  endpoint must reproduce that, or every dismissal already stored on a device comes back once.
- `useAttentionItems()` applies pending outbox items to balances before the autopay shortfall
  check; a server endpoint cannot (proposal B3).
- `Math.round(1.005 * 100)` is 100 in JS but HALF_UP from the text gives 101 in Kotlin; harmless for
  form input (two decimals), noted in `rules-port.md`.
- The Docker image runs with `TZ=America/Sao_Paulo`, so the server's `local_today()` is the owner's
  date.
- The scout left pytest wheel files (`*.whl`) in the repo root while installing; deleted, never
  committed. Install into a scratch directory instead.
