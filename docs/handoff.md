# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · A R$ 110 Claude charge missing, Conferência said "Movimentos conferem"

Owner reported: paid Claude (R$ 110 from a bank account, 2026-11-02), it never reached the app; Ajustes › Open Finance showed
"Movimentos conferem" beside a balance difference of R$ 110 (R$ 1.847,75 vs R$ 1.737,75). Other movements of 11-03
had already come in.

**Finding:** not an ingestion bug. The owner confirmed Pluggy does not list the purchase yet: the bank already took it
from the balance (an international purchase "em processamento"), but Open Finance only lists what the bank posted. The
Conferência compares only listed movements, so they match, and the R$ 110 fell into `explanation.before`, which the
screens labelled "de antes da conferência (confira o saldo inicial da conta)" — misleading.

Done (tests: `test_open_finance_sync.py` 2 new + 1 adjusted, `openFinance.test.js`, `OpenFinanceRulesTest.kt` string):
- **Pull window** (`_date_from()`, the open item carried from 043): `LATE_POSTING_DAYS = 35` back from the last pull
  instead of 7. This very purchase would have been lost had the bank posted it dated 11-02 after ~11-09 (the window
  started 7 days before the last pull, and pulls run every 5 min/6 h). Floor: never before the account's first pulled
  Pluggy day (`MIN(COALESCE(posted_on, date))`, COVERED excluded), so a short "primeira busca" stays respected; an
  account with no rows keeps the old 7 days. `test_a_late_posting_older_than_a_week_is_still_pulled` fails on the old
  code.
- **Conferência text** (web `balanceExplanation()`, APK `OpenFinanceRules.balanceExplanation()`): the unexplained part
  now reads "no saldo do banco sem movimento listado: em processamento no banco (entra quando ele lançar) ou de antes
  da conferência (confira o saldo inicial)".

**Not done and why:**
- The APK change is a string literal and its JVM test; not compiled here (no Android SDK in the container). It ships with
  the next APK build.
- The green "Movimentos conferem" badge still shows beside "Diferença" (the badge is about listed movements). Changing it
  means a new summary state on web and APK (`checkSummary()` signature in Kotlin); left in `next-steps.md`.
- `synced_until` still advances while Pluggy's `lastUpdatedAt` is stale (an outage > 35 days loses rows). Not anchored:
  the fake's `lastUpdatedAt` is 2026-01-01 and many window tests would move; in `next-steps.md`.
- Not deployed or checked in production. After deploy, the first pulls read 35 days per account (one or two pages; GET
  only, no quota).

**Next:** watch the Claude charge post; then the Conferência for that account should read "Confere".

Lessons: when the Conferência says "Movimentos conferem" and the balance differs, the difference is something Pluggy
does not list (the bank's processing hold, or the initial balance) — the Histórico preview tells whether Pluggy has a
row the incremental pull skipped.
