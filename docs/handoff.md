# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-28 · Conta global out of "Saldo em contas"; Cartões opens collapsed

Owner asked: the Conta global balance must not show as "saldo em conta"; every card on Cartões
should appear closed when the screen opens.

Done:
- `services/home.py` `consolidated_balance()` skips non-BRL accounts (`is_foreign_currency()`), so
  Início's "Saldo em contas" and the Extrato/Cartões projections leave the Wise account out. The
  tile under the accounts still shows it converted. `test_global_account.py` updated. Client
  pending-overlay (`applyPendingToHome` / `OutboxPending.kt`) already skipped USD accounts.
- Conta global screen (web + APK): headline label "Saldo em conta" → "Saldo em dólar"; the
  description no longer says it enters the saldo em contas. CLAUDE.md rule rewritten.
- Cartões (web `Cartoes.jsx`, APK `CartoesViewModel.kt`): no invoice (not even the nearest) and no
  débito list starts expanded; only a tap opens. Doc `mobile-docs/native/screens/*cart*` updated.
- Tests: backend full suite green; node 214/214.

Not done: Kotlin unit tests not run here (no Android SDK in the container); the APK change is a
two-line default swap, nothing tests it.

Next: merge (deploys), install the APK, check Início's total and Cartões on the phone.

