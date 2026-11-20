# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-19 (3) · Everything automatic: real-data check, merge and deploy

**Merged and deployed** (owner's authorization of 2026-11-19, once the gates passed): #102 phase 3 → #101 phase 2
→ #100 phase 1 → #99 `fix/brokerage-guessed-side` → `main` (`00c6fdc`), one deploy, run 44628151379, green with the
APK job. The worktree `../Financas-phase2` was removed after the merge.

**Done:**
- **Phase 2 checked on the real data** (server read-only, `/tmp` cleaned): a copy of the server's database
  downloaded to the scratchpad and `open_finance_investments.apply()` replayed over it in a rolled-back
  transaction. Three wrong outcomes fixed (`e93bcbb`, tests in `test_investments_decide_themselves.py` ›
  `TestTitleIdentity`):
  - a typed fixed-income twin was linked by cents alone, so a TRANSFER linked another LCA/LCI of the same cost →
    `title_fit()` (type and maturity never contradict); two equal candidates wait `custody:ambiguous`;
  - the CRAs Madero/Caramuru were typed a day later at the note's value (R$ 4–6 more) → would be bought twice, with
    their coupon and amortization → a buy of the same type and maturity within `NEAR_LINK_PERCENT` (1%) links;
  - Renda+ was recorded as a new asset "… 2084" → `tesouro_client.commercial_name()` ("… EXTRA 2065", the owner's).
  Answers: pré is right for every `rate` 0 title (owner typed the same rates); TRANSFERs carry the original cost in
  `netAmount` and were typed at the old broker; Renda+ is "Tesouro Renda+ Aposentadoria Extra (NTNB1)"; both BB
  funds are `TOTAL_WITHDRAWAL` → **no fund class, no proposal needed**; no provisional buy left.
- **Anticipated installments on a purchase the owner changed** (owner asked mid-session; the Rota Transportes 6x of
  2026-11-18 was recategorised, so its `client_id` is not `pluggy:` and `_mirror_purchase()` skipped it entirely —
  the anticipation would never have moved): now only the anticipated lines move to the discount's invoice; amounts
  and lines stay the owner's (`eee3dd8`, `test_pluggy_owner_rules.py`).
- Gates: backend 4 chunks; card / Open Finance / identity / fuzz suites after the last fix; `npm test` 252;
  `vite build`; APK `compileDebugKotlin` + 603 JVM tests offline. All green.
- **Production after the deploy**: migrations 058, healthy. First pull (2026-11-20 00:47Z): portfolio HELD 58 → 4,
  43 decisions (23 `investment_closed_fund`, 14 `investment_custody`, 4 `investment_custody_in`, 2
  `investment_proceed_link`), exactly the replay. Revisar was already 0, so auto-confirm removed nothing. The weekly
  line "Decisoes automaticas da semana" was logged. No ERROR/Traceback except the old brapi one.

**Not done and why:**
- The 4 HELD lines are left for the owner (listed in `docs/next-steps.md`): resolving them needs their decision.
- The anticipation itself was not seen in production: the owner hasn't anticipated yet (the Rota is still 1/6 in
  December); proved only by the test.
- APK "Decidido sozinho" not run on a phone; the owner installs it.
- `changed` conflict date and `proceed:unmatched`: unchanged, still in next-steps.

**Next:** the week of watching in `docs/next-steps.md` (Everything automatic, items 1–4); then the rest of the plan.

**Lessons:**
- **Replay a new rule over a copy of the real database before merging** (memory `server-readonly-measurement`):
  unit tests built from the docs passed, and the copy showed three wrong operations in minutes.
- `_mirror_purchase()` returns early for a purchase whose `client_id` isn't `pluggy:`; any new mirror behaviour
  must decide explicitly whether an owner-changed purchase takes it.
