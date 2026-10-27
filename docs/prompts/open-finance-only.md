# Prompt — Open Finance as the only source: BTG Investimentos, history, hourly, no Aprovar

> Paste everything below the line into a new session. It is written for a cold start. Owner's
> decisions still open are marked **(owner)**: ask before deciding them yourself.

---

Make Open Finance (Pluggy, through MeuPluggy) the app's **only source of movements** for my
connected banks, recorded **automatically**, and bring **BTG Investimentos** into Investimentos.
Read `CLAUDE.md`, `docs/handoff.md` and `docs/next-steps.md` first, as usual. The section "Open
Finance in Investimentos — BTG positions automatically" in `next-steps.md` holds the probe of what
BTG sends and the investments design; this prompt widens it.

## Where things stand (2026-10-27)

- Open Finance is on `main` and deployed (migrations up to 043; settings and Conferência in
  `955a292`). It is a **source of Aprovar** next to phone notifications: nothing is recorded without
  approval. The per-account **Conferência** (`services/open_finance_check.py`) compares the bank
  with the app: bank-only, app-only, awaiting.
- **Connected** (MeuPluggy, free plan, one CPF; every item's `connector_name` is "MeuPluggy"; the
  account names carry the bank; the item ids are in `open_finance_items` on the server):
  - Itaú: one checking account → app "Itaú".
  - BTG: "BTG Banking" checking → app "BTG conta corrente"; "Cartão BTG BLACK" → app "BTG black";
    **"BTG Investimentos"** checking (same number as BTG Banking) → **nothing yet**. It is the broker's cash, and the mapping refuses the Corretora
    on purpose, so it **does not show in the dropdown**. This is the main thing to build.
  - Banco do Brasil: checking → app "BB"; one "OUROCARD FACIL VISA" → app "BB ourocard"; a second
    Ourocard with no movements, **(owner)** what it is.
  - **Flash stays on phone notifications** (no Open Finance). Notifications cannot simply be turned
    off: they must keep working for Flash.
- The phone walk-through of the previous session stopped at step 4 (mapping). Check
  `docs/handoff.md` › "Phone test results" for what passed and what the owner mapped.

## Owner's decisions (2026-10-27) — they change rules in CLAUDE.md

1. **Only Pluggy from now on, recorded automatically.** For a connected, mapped account, a Pluggy
   movement becomes a lançamento (or card purchase) by itself. Aprovar stays for Flash and for what
   cannot be decided alone, and it should be empty in normal use. This reverses "nothing is
   recorded without approval" for Open Finance. Update `CLAUDE.md` › Aprovar and Open Finance to say
   so, and keep the reason: the owner checked the data and trusts it.
2. **Phone notifications of a connected bank are ignored** (answered 200 with status `ignored`, so
   the outbox doesn't retry), decided per bank or account, not globally: Flash's still go to
   Aprovar. The listener and the parsers stay as they are, so switching back is instant.
3. **BTG Investimentos goes to Investimentos**, never to Aprovar. Broker operations (BUY/SELL, and
   proventos paired with the computed ones) are **recorded automatically**, with a position check
   and a one-tap undo. Positions are never overwritten.
4. **The whole history is compared and brought in line**, not only new movements. Every past
   transaction Pluggy has (up to 12 months) is matched against what is already in the app.
5. **Automatic pull every 1 hour** (`sync_hours = 1`; the setting already exists, per user, in
   Ajustes › Open Finance).

## The work, in order

### 1. Safety switch and guards first
- One setting in `user_settings`, through `GET/PATCH /api/open-finance/settings` (validated,
  `@token_required`): automatic recording on or off. Off = today's behaviour (everything through
  Aprovar). Turning it on is refused (400, Portuguese message) unless every BANK/CREDIT Pluggy
  account of the item is mapped (or explicitly marked "não usar", like the second Ourocard or BTG Investimentos)
  and the item pulled in the last 48 h. Web and APK show it in Ajustes › Open Finance, behind
  `confirmAction()` on the web.
- Ignored notifications (decision 2): the server decides from the detection's target (card final /
  bank) whether it belongs to a connected, mapped account with automatic recording on. Pending items
  stay; nothing already stored is deleted.

### 2. Automatic recording for banks and cards
- In `services/open_finance_inbox.py`, with the switch on: a new Pluggy row of a mapped account is
  recorded directly, with the same rules approval applies today (`source_type = 'OPEN_FINANCE'`,
  `source_id = <pluggy id>`, a card purchase's `client_id = pluggy:<id>`, installments 2..n
  covered, refunds as `REFUND`, invoice payments as the payment the app already knows (never a
  second one), own transfers between connected accounts as one TRANSFER, bank ↔ Corretora as
  aporte/resgate (039)). Category: the import rules first, then Pluggy's category mapped to the
  owner's categories, else "Sem categoria". Write the mapping table and test it.
- A row that vanishes or changes amount after being recorded automatically: the lançamento is
  corrected or removed only if the owner never edited it. Otherwise flag it in the Conferência.
- Pending items already in Aprovar from Pluggy when the switch turns on: approve them as they are,
  in one pass (tested), so the history doesn't depend on clicking ~90 items.

### 3. History: compare and update every transaction that already happened (decision 4)
- Pull each mapped account back as far as Pluggy keeps (`first_sync_days` up to 365, or a dedicated
  backfill window) without request updates (`request_update=False`; reads don't spend the quota).
- Match each Pluggy row with the app's lançamentos by the Conferência's rule (same signed cents,
  ≤ 3 days, one to one; card purchases as a whole). A match is **linked** (stamp
  `source_type`/`source_id` on the existing row so it is never recorded twice). A Pluggy row with
  no match is **recorded** (decision 1). An app lançamento with no Pluggy match is **listed for the
  owner**, never deleted automatically **(owner)**: confirm before deleting anything. Show a preview
  first (counts per account: linked, to record, app-only) and apply only on confirmation, like
  `/api/import-rules/apply/preview` → `apply`.
- After it runs, every account's balance should read "Confere" against the bank. If it doesn't, the
  Conferência lists show why.

### 4. BTG Investimentos into Investimentos (decision 3)
Follow `next-steps.md` › "Open Finance in Investimentos". In short:
- The Pluggy account "BTG Investimentos" is linked to the **Corretora** (a separate kind of mapping:
  the Corretora is refused as an Aprovar target, so it needs its own field or rule). Its balance
  shows in Investimentos, compared with the Corretora's **by trade date**: ações/ETFs settle
  D+1/D+2, so trades of the last 2 business days are "a liquidar", not a difference.
- `GET /investments` and `/investments/{id}/transactions` (BTG has 36 positions and 71 operations
  with `tradeDate`, quantity, `netAmount`, `expenses`, `brokerageNumber`) become automatic
  movements, idempotent by Pluggy id, cash through the Corretora (`metadata.cash_account_id`). Past
  operations I typed are **matched and linked** (same asset, ±2 days, same quantity), never
  duplicated. Same preview → apply as step 3 for the first run.
- Proventos of ações/FIIs are computed from StatusInvest (026): pair Pluggy's with them, never
  duplicate. Corporate actions (017) stay authoritative. Fixed income and Tesouro: compare values,
  never mark to Pluggy's.
- Position check: Pluggy quantity per asset vs `build_portfolio_snapshot()`.

### 5. Hourly pull (decision 5)
- The setting exists; set it to 1 h for the owner. **Check the cost first**: each `PATCH /items`
  spends the CPF's monthly quota per institution. 3 items × 24/day ≈ 2.200 requests a month. Read
  Pluggy's current limits for MeuPluggy items (does `PATCH /items` even work on a MeuPluggy item,
  or does MeuPluggy refresh on its own schedule?). If the quota can't take hourly updates, keep
  **reads** hourly (free: the latest data Pluggy has) and request updates less often. Log
  Pluggy's refusals, so a quota running out shows in Ajustes and in `docker compose logs | grep -i pluggy`.

### 6. Small fixes found on the real connection
- The source line in Aprovar and the Extrato says "Open Finance MeuPluggy · …": use the account's
  bank (the account name or the item's institution) instead of the connector name.
- `suggest_target()` gave no suggestion for any account (it compares the connector name, which is
  "MeuPluggy"): compare the account name too.
- Desconectar asks for the connector name, which is "MeuPluggy" for all three: ask for the bank.

## Tests and checks
- pytest for every rule: the switch and its guard, ignored notifications per bank (Flash still
  recorded), automatic recording (bank, card, refund, installments, invoice payment, transfers,
  aporte/resgate), the history preview/apply (linked, recorded, app-only untouched), the
  investments sync (buy, sell, idempotency, typed operations linked, proventos paired, corporate
  action guard), the hourly interval, user isolation. Fakes in `tests/open_finance_world.py`
  (add `/investments`).
- node + Kotlin for any new screen rule (`lib/openFinance.js` ↔ `rules/OpenFinanceRules.kt`).
- `test_route_map.py` for any new route; `vite build`; `gradlew testDebugUnitTest assembleDebug`.
- Then with the owner, on the real data: the preview numbers per account, the balances reading
  "Confere" after apply, one real purchase arriving by itself within the hour, a BTG trade appearing
  in Investimentos with the right average cost.

End as usual: `next-steps.md`, `done-tasks.md`, `handoff.md`, commit with explicit paths (leave
the three untracked Capacitor folders out).
