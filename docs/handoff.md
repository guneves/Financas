# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (3) · Open Finance as the only source, BTG into Investimentos

Local session on the owner's PC, on `main`, from `docs/prompts/open-finance-only.md` (pasted). The
owner added mid-session: **only GET, and never update more often than every 6 hours**.

### Done
- **Migration 044**: `open_finance_accounts.ignored_at` ("não usar"),
  `open_finance_transactions.auto_recorded_at / recorded_snapshot / conflict /
  conflict_amount_cents`, tables `open_finance_investment_operations` and `open_finance_positions`.
- **GET only** (Step 5 + the owner's message): `PluggyClient.update_item` removed and `call()`
  refuses PATCH; `sync_item()` reads item, accounts, transactions and investments only;
  `sync_hours` is 0 or 6–24 (an old 1–5 reads as 6); config default stays 6 h. Refusals are kept in
  `last_sync_error` and logged (`Open Finance: a Pluggy recusou o pull`, with status/code).
- **Switch and guard** (Step 1): `auto_record` and `ignore_notifications` in
  `GET/PATCH /api/open-finance/settings`; turning `auto_record` on is refused (400, Portuguese,
  listing each blocker) unless every BANK/CREDIT account of every active item is mapped or ignored
  and each item has `last_sync_at` within 48 h. `auto_record_blockers` is in the GET.
- **Engine** (Step 2, `services/open_finance_auto.py`): after every pull, each pending item with a
  Pluggy source is approved through the normal `approve_item()` (remember off), so every rule of
  Aprovar applies (installments, refunds, transfers as one row, recurrence settlement). Held: a
  transfer still missing its other side (2-day hold, then a Pix to someone else is recorded as
  despesa/receita), an investment category on a bank account, `needs`. A typed look-alike is
  linked (first candidate no other Pluggy row explains). Backlog: turning the switch on runs the
  same pass. Corretora mapping is allowed only for the broker's investments account; its non-transfer
  rows are `COVERED`. Bank invoice payments link to the app's pay-invoice/autopay row. Category:
  rule → `open_finance_categories.py` → default ("Outros"/"Receita" — the app has no literal
  "Sem categoria" for a lançamento; that name is only the budget remainder). Mutation guard by
  snapshot (`apply_change()`, `apply_vanish()`; never on an empty pull, never a transfer, never a
  paid installment, never a typed row).
- **Notifications** (decision 2): `ingest_detection()` returns `ignored` for a connected bank (by
  Pluggy account name or the mapped target's name/bank; a Samsung card that is mapped). Flash stays.
- **History + Conferência** (Step 3): `POST /api/open-finance/history/preview` (counts per account,
  writes nothing) and `/apply` (`confirm: true`, needs the switch; re-pulls from N days and runs the
  engine). The Conferência now gives a `reason` per line, `conflicts`, and `explanation` of the
  balance difference (bank-only + awaiting − app-only + "before the window").
- **Investments** (Step 4, `services/open_finance_investments.py`): positions saved; equity BUY/SELL
  recorded on the trade date with cash through the Corretora; idempotent; typed twins linked;
  unknown ticker / sale without position / before a corporate action / fixed income / TRANSFER /
  INTEREST → `HELD`; deleting a recorded one → `DISMISSED`. `portfolio_check()` in `GET
  /api/open-finance` (`investments`): quantity per asset (D-1 position + later operations), broker
  cash with "a liquidar" for trades of the last 2 business days.
- **Small fixes** (Step 6): `bank_name` on items and Aprovar sources (web and APK show it);
  `suggest_target()` uses the account name (and suggests the Corretora for the investments
  account); Desconectar confirms with the bank's name (case/accents ignored).
- **Screens**: web Ajustes › Open Finance — "Não usar" option, Gravar sozinho and Ignorar avisos
  checkboxes, reasons/conflicts/explanation in the Conferência, "Carteira da corretora", Histórico
  (prévia → trazer). APK — the two switches, reasons, conflicts and explanation, bank name.
- Tests: `test_open_finance_auto.py` (61), `test_open_finance_investments.py` (25), older Open
  Finance tests updated (GET-only, 6 h floor, reasons); full pytest green; `npm test` 191;
  `vite build` ok; `gradlew testDebugUnitTest assembleDebug` 514 JVM tests, APK built.
- Docs: CLAUDE.md (the reversal, GET only, Gravar sozinho, history, investments), DEPLOY.md,
  `.env.example`, next-steps, done-tasks.

### Not done, and why
- **Nothing ran against the real Pluggy.** Mapping, switch, history and the investments sync are
  for the owner after the deploy (next-steps lists the order). The card purchase sign is still
  unverified on real data, and the engine will record whatever sign was learned — check it first.
- **Fixed income / Tesouro / custody TRANSFER / INTEREST** operations are only `HELD` and listed:
  recording them needs per-title metadata that the probe did not settle.
- **The web screen was not opened in a browser** (build + node tests only). The APK was built, not
  installed.
- History preview, portfolio check and "Não usar" are web-only (mapping already was).
- No "resolvido" action for a Conferência `conflict`.
- `docs/prompts/open-finance-only.md` stays as the record of the request.

### Next session
1. Owner's walk-through on real data (next-steps, first section), then fix what the real rows show:
   investment transaction ids/`expenses`/pagination, the category table, broker account categories.
2. If the owner wants: record fixed-income/Tesouro operations from Pluggy (per-title metadata).

### Lessons (non-obvious)
- `parse_iso_date()` returns a `datetime`, not a `date`: subtracting it from `local_today()` raises,
  and `.isoformat()` adds `T00:00:00` (breaks text BETWEEN on dates). Use `.date()`.
- In the fake, `connected()` already pulls once, so later rows must be dated inside the 7-day
  overlap (≥ 2026-10-20 with today 2026-10-27) or they are never pulled.
- Transactions are edited with `PATCH /api/transactions/<id>` (no PUT).
- `open_finance_transactions.role` is CHECK-bound: new states went into new columns (`conflict`)
  or reused `COVERED` rather than a table rebuild.
- `pytest-xdist` is not installed: `-n auto` exits without running.
