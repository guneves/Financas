# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 · Open Finance (Pluggy) as a source for Aprovar

Local session on the owner's PC, branch `claude/pluggy-open-finance` from `main` at `56379fa`,
following `docs/prompts/pluggy-open-finance.md` (all six phases in one branch).

### Done
- **Backend**: migration 043 (`open_finance_items`, `_accounts`, `_transactions`; why a table of
  its own and not `notify_detections` is in its header), `pluggy_client.py` (pure: API key reused
  ~100 min, one retry on network errors, `/v2/transactions` by cursor, no secrets/descriptions in
  logs, `integrations` for the healthcheck), `services/open_finance.py` (connect token, register,
  map with suggestions, pull, disconnect with the bank-name guard, balance check),
  `services/open_finance_inbox.py` (normalize + place into Aprovar), `routes/open_finance.py`
  (7 routes, all `@token_required`), `services/open_finance_refresh.py` (thread, 6 h, `0` off),
  Pluggy in the healthcheck. Hooks in `services/inbox.py` / `inbox_decisions.py`: both source
  tables read where sources matter, pairing in both orders, card refunds approved as `REFUND`,
  `source_type = 'OPEN_FINANCE'` on approval, split of an Open Finance source.
- **Web**: Ajustes › Open Finance (connect via `pluggy-connect-sdk@2.14.2`, lazily loaded; map;
  Atualizar; Reconectar; Desconectar; first-sync days; balance check masked in privacy mode);
  Aprovar's source line shows "Open Finance <banco> · <conta> · …" with a bank icon.
- **APK**: the source in Aprovar (`InboxRules.kt` port), Ajustes › Open Finance (status, balances,
  Atualizar; `rules/OpenFinanceRules.kt` = `lib/openFinance.js`). Built locally: 507 JVM tests,
  `assembleDebug` ok.
- **Tests**: pytest green (≈ 115 new: `test_pluggy_client.py`, `test_open_finance_normalize.py`,
  `_connect.py`, `_sync.py`); `npm test` 180 green; `vite build` ok.
- **Sandbox end to end in Chromium** (Playwright, scratch DB, the owner's credentials from
  `backend/.env`): widget → Sandbox → `user-ok`/`password-ok` → item registered → mapped → 8 items in
  Aprovar → one card purchase approved (client_id `pluggy:<id>`, invoice 11/2026) → Desconectar.
  The sandbox item was deleted from Pluggy afterwards. Screenshots were in the session scratchpad.
- Docs: `next-steps.md` (design + what is left), `done-tasks.md`, `DEPLOY.md` › "Open Finance
  (Pluggy)", both `.env.example`, `CLAUDE.md` (Aprovar and tests), native specs 02 and 11.

### Not done, and why
- **No real bank yet** — by design, the first real connection is the owner's (after the deploy).
  The list of what to check is in `next-steps.md` › "Open Finance (Pluggy) … — what is left";
  the most important: **card purchases must come as −R$ purchases** (the sign is learned, see below).
- Not built (listed in next-steps): offering "Pagar fatura" from a detected invoice payment,
  Pluggy's category as a rule suggestion, learning "it's me" from a Pluggy transfer, `PENDING`
  transactions (skipped, owner's call), webhooks (impossible: tailnet-only).
- Not pushed or merged: the owner reviews the branch; `android-check.yml` will confirm the APK.

### Next session
1. If the owner ran the first real connection: act on what they report (card sign, pairing,
   installments). Otherwise the items carried over from the previous handoff still stand: the phone
   checks of 2026-10-25, the web Início on `/api/home/panels`, the desktop redesign plan.

### Lessons (non-obvious)
- **Pluggy's sandbox and docs disagree on card signs**: docs "positive = debit", sandbox
  purchases are `type: CREDIT`, negative. Never trust one convention; `learn_charge_sign()` learns
  it per card account and stores how.
- **Pluggy refuses an update within 1 h** of the last one ("Client updates on this item are allowed
  at most every 1 hours"), and connecting counts. A refused update must fall back to a plain pull.
- `pluggy-connect-sdk` has only the named export `PluggyConnect`; its README's default import
  fails at runtime ("is not a constructor") while `vite build` passes.
- The page-based `GET /transactions` is deprecated (gone for new apps); `/v2/transactions` needs
  no `pageSize`, and `dateFrom` cannot be combined with `createdAtFrom`.
- `conftest.py` must blank `PLUGGY_CLIENT_ID/SECRET`: `load_dotenv()` would otherwise feed the real
  credentials from `backend/.env` into the test process.
- The local Android build needs network now (`--offline` misses new androidx artifacts).

