# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (7) · Conta global (Wise in US$)

Local session, owner's prompt `docs/prompts/global-account-usd.md`. Branch `claude/conta-global`
from `main` (local `main` was 4 commits ahead of `origin/main`; the branch carries them).
**Not merged, not pushed, not deployed** (the prompt says ask first). The owner's data is untouched.

### Done (code)
- **047** `transactions.transfer_amount` / `inbox_items.transfer_amount`: a cross-currency transfer
  is one row, `amount` out in the origin's currency, `transfer_amount` in at the destination.
  `transfer_amount_for()` (POST /api/transfers and PATCH): required across currencies, refused
  otherwise. `account_balance_rows()` counts a cross-currency transfer without it as 0.
- Accounts: currency validated on create; a foreign account is never the default
  (`DEFAULT_ACCOUNT_ORDER`, PATCH 400) nor BROKERAGE. `PATCH /api/accounts/<id> {currency}` turns a
  reais account that only received BRL transfers (no initial balance, not mapped) into USD
  (`global_account.convert_to_foreign()`): the owner's "Wise" fits.
- Pluggy: USD↔USD mapping and suggestion, mismatch refused; `normalize_transaction(account_currency=)`
  keeps US$ rows in US$ (`edited: ["amount"]` so they need no conversion). `services/global_account.py`
  + `open_finance_inbox._place_cross_currency()` (new `place()` step 2): BRL Pix naming the global
  account waits as an own transfer; the dollar credit pairs by day ±1 and counterparty, ties by
  closest PTAX; an untouched auto-recorded US$ receita is turned into the transfer when the BRL side
  arrives late; a credit matching a transfer in the app fills `transfer_amount`. Hold: a US$ credit
  waits `TRANSFER_HOLD_DAYS`; a TRANSFER to a foreign account without `transfer_amount` is never
  "complete". Snapshot carries `transfer_amount` only when set (old snapshots stay equal).
  Conferência counts `COALESCE(transfer_amount, amount)` on the incoming side.
- Reais totals skip the foreign account's own rows: `banking_month_rows`, `month_banking_totals`,
  budgets, `GET /api/transactions` without `account_id`, review queue and count.
- Web: `pages/ContaGlobal.jsx` (`/inicio/conta-global`), `lib/globalAccount.js` (+ test),
  `formatForeignCurrency()`; "Conta global ›" under Início's accounts; Ajustes › Contas type
  "Conta global (US$)", the row links to the screen; "+ Novo" lists only reais accounts.
- APK: `ui/globalaccount/`, `rules/GlobalAccount.kt` (+ test), `core/Format.kt`, route + link,
  Início entry, Ajustes type/link/menu, NewEntry filter; spec `mobile-docs/native/screens/17-conta-global.md`.
- Docs: CLAUDE.md (reais-only exception, Conta global, two-amount transfers, Pluggy rules), memory
  `app-is-in-reais`.
- Tests: pytest 1971 passed + 1 known failure (below), `test_global_account.py` 18; node 204;
  JVM 531 (local `gradlew --offline`), debug APK assembled locally.

### Decision written down
Wise **counts in the consolidated balance converted to reais** (`balance_brl`, as before). Its own
US$ despesas/receitas count in **no** reais total (not converted into the month).

### Not done, and why
- **The owner's data** (convert Wise, map Pluggy Wise, pull, check balances): needs the deploy first
  and the owner's OK per write batch; steps in next-steps › "Conta global".
- No visual check of the web screen or the phone screen (build and tests only).
- Phone: no "Pix para cá" (web only); statement = first page. Web Aprovar has no `transfer_amount` field.

### Next session
1. Ask the owner to merge/deploy `claude/conta-global`, then run the data steps in next-steps.
2. Owner walks 17-conta-global.md's Acceptance on the phone.

### Lessons (non-obvious)
- A second pull re-reads only from `synced_until - OVERLAP_DAYS` (7): tests with old Pix dates must
  clear `synced_until` (`pull()` in `test_global_account.py`) or the rows never arrive.
- `test_fixed_income_interest.py::TestTheCouponReachesTheAccount` still fails locally after 21:00 BRT.
- Bash heredocs on this machine broke on a Kotlin file with `•` and `$`; write such files with Write.

---

