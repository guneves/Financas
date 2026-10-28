# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-28 · Conta global: the last code gaps; check of `main`

Owner asked to finish the pending work of `docs/prompts/global-account-usd.md`, make sure the Conta
global works, and check the last merge. Branch `claude/epic-volta-ujrt5i` from `main` (PR opened).

### Done
- **Last merges checked** (`ccf2ba0` Ourocard "PGTO DEBITO CONTA"/"PGTO. CASH", `97ba9fa` BTG
  "CardBankslip" → invoice payment, never a refund/transfer half): code read, full pytest on `main`
  green (all ~1600), node 204/204.
- **Real gap fixed:** a reais Pix to Wise waiting for its dollar side could not be resolved anywhere:
  approving it is refused without `transfer_amount`, and neither the web Aprovar nor the APK asked
  for it. Web Aprovar's edit sheet shows "Entrou (US$)" for a cross-currency transfer
  (`crossCurrencyOf()`, `changesFromDraft(item, draft, crossCurrency)`: `undefined` = currencies
  unknown, leave it; `null` = same currency, clear it); the APK's "Não gravou sozinho" asks
  "Quanto entrou (USD)" (`ReviewRules.waitingTransferCurrency()`, `InboxItemDto.transferAmount`).
- APK Conta global: **"Pix para cá"** (sheet; `GlobalAccount.pixSources/pixMissing/pixBody`, the web's
  messages; POST /api/transfers with a `client_id`, online only, never queued) and **"Carregar mais"**.
- Tests: `inboxRules.test.js`, `globalAccount.test.js` (+2), `ReviewRulesTest.kt`,
  `GlobalAccountTest.kt` (+2). node 206/206; vite build OK.

### Not done, and why
- **The APK was not compiled.** The container has no Android SDK (dl.google.com is blocked). The pure
  `rules/`, `core/`, `data/` code and their tests ran on a plain-JVM Gradle project (380 tests green);
  the Compose/ViewModel changes (`GlobalAccountScreen/ViewModel.kt`, `ReviewSection.kt`,
  `ExtratoViewModel.kt`) were checked by reading only. CI's apk job is the first real build.
- **Owner's data steps** (Wise → USD, map the Pluggy Wise account, check the three October Pix):
  need production, reachable only through the owner's tailnet/Chrome; nothing ran here. Steps are in
  `next-steps.md`.
- A waiting dollar credit can't be paired by hand with a reais account (server refuses another
  currency as origin); left as is, written down in next-steps.

### Next session
1. Merge the PR (deploys), install the APK, walk `17-conta-global.md`'s Acceptance.
2. The owner's data steps in next-steps › Conta global.

### Lessons (non-obvious)
- To run the APK's JVM tests without the SDK: a Kotlin-JVM Gradle project whose source sets point at
  `app/src/{main,test}/java/br/financas/app/{rules,core,data}` (exclude `AppGraph.kt`), with
  kotlinx-serialization, coroutines, okhttp 4.12, org.json, junit. Maven Central answers 429 at
  first: retry; once cached it builds in ~20 s.
## Session — 2026-10-28 (10) · Conta investimento (liquidação D+2), merged and pushed

Finished the pending `claude/settlement` work: fast-forwarded the APK commit from the worktree
branch `claude/settlement-apk` onto it, ran every suite, merged into `main` and pushed (deploys).

### Done
- Backend/web (`e5a4c0a`): the Corretora lançamento of an operation is dated on the liquidation day
  (`services/settlement.py`: D+2 business days on B3 with its holiday calendar, D+1 abroad, same day
  otherwise; `metadata.settlement_date`/`settlement_amount` override; Pluggy's `netAmount` fills the
  amount). `GET /api/investments/settlement` (`services/broker_cash.py`) feeds the Conta investimento
  card in Posição: saldo hoje, em trânsito (operations + announced proventos), saldo. The first read
  moves old rows still on the trade date (`resync_investment_cash_dates()`).
- APK (`2049d54`): the same card in Posição (`rules/BrokerSettlement.kt`, `BrokerSettlementTest`).
- Tests: pytest full suite, `npm test` 204, Android JVM 537 — all pass; `vite build` OK.

### Not done, and why
- Not checked on the owner's real data: the resync moves existing Corretora rows to D+2 on the first
  read of `/api/investments/settlement` — the Corretora balance "hoje" drops by trades of the last 2
  business days, which is the intent, but have the owner look at Posição after the deploy.
- The B3 holiday calendar is computed (fixed + Easter-based); a one-off holiday decreed by B3 is not
  known — use `metadata.settlement_date` on that operation.

### Next session
1. Owner: open Investimentos › Posição (web and APK) and compare Conta investimento with BTG.
2. Then the open items in `next-steps.md` (Open Finance walk-through, conta-global data steps).

### Lessons (non-obvious)
- A worktree subagent's work lives on its own branch (`claude/settlement-apk`); check
  `git worktree list` before calling a feature branch finished.

---
