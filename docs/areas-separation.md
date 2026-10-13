# Separating the investments area from the banking area

> **Status: plan approved by the owner on 2026-10-12 — nothing is built yet.** The phases are
> tracked as open work in `docs/next-steps.md`; this file is the design they point to. When the
> last phase lands, move the lasting rules into `CLAUDE.md`, record the work in
> `docs/done-tasks.md` and delete this file (as was done with `ux-reorganization.md`).

---

## 1. The request

The owner wants the investments area and the banking area (lançamentos, contas, orçamento) to be
separate: recording an investment operation must not, by itself, create anything in the Extrato.
When the owner wants the money to show up in an account, they ask for it on that operation.

## 2. What couples the two areas today

Every buy, sale and redemption mirrors a lançamento into `transactions`
(`source_type = 'INVESTMENT_TRANSACTION'`, `source_id` = the movement id, row id `cash:<id>`,
category "Investimento"). The only way out is `metadata.skip_cash` ("Operação anterior ao app"),
ticked per operation.

| Where | What it does today |
|---|---|
| `services/investments.py` — `sync_investment_cash_transaction()` | The writer. Upserts the linked row, always in the **default account** (`ensure_default_account()`); `investment_skips_cash()` is the opt-out. |
| `routes/investments.py` | Calls the sync after `POST /api/investments` and `PATCH /api/investments/<id>`; calls `delete_investment_cash_transaction()` on `DELETE` and on delete-by-asset. Nothing else calls either. |
| `routes/transactions.py` | `PATCH` / `DELETE` on a linked row answer 409 ("edit the movement"). |
| `routes/imports.py` — `RULE_APPLY_SKIPPED_SOURCE_TYPES` | Import rules never recategorize a linked row. |
| `routes/budgets.py` — the month's spend | A linked row counts under the category "Investimento" (resolved by name). |
| `export_csv.py` | Origin label "Carteira" in the statement export. |
| `services/goals.py` | A `NET_WORTH` goal = portfolio + account balances (a read-only sum). |
| `frontend/src/lib/transactions.js` — `isInvestmentOutflow()` | An EXPENSE that is linked, or typed in the category "Investimento", is an aporte and not an expense. Read by Início (cash flow, spending pace, categories), Extrato (badge, totals) and Recorrentes (label). |
| `pages/lancamentos/Extrato.jsx` — `isEditableHere()`, `originLabel()` | Linked rows are read-only and tagged "Pela carteira". |
| `pages/Dashboard.jsx` — `WealthHero` | Patrimônio = contas + carteira. |
| `components/NewEntrySheet.jsx`, `components/Layout.jsx` | "+ Novo" offers "Investimento", which opens `InvestmentLaunchModal`. |
| `components/InvestmentLaunchModal.jsx`, `pages/investimentos/Operacoes.jsx` | The "Operação anterior ao app" checkbox and the "anterior ao app" tag. |
| `pages/investimentos/Posicao.jsx` — `handlePartialSale()` | Fixed-income redemption: no checkbox, always linked. |

**What does not depend on the link:** FIFO, realized results, the IR report and exemption meter,
portfolio, evolution, TWR, contributions, allocation, sectors and proventos all read
`investment_transactions` (through `fetch_investments()`), never `transactions`. Separating the
areas touches no financial calculation.

**Why the automatic link is worth dropping** — it is already inconsistent:

1. The owner cannot choose the account (always the default one) and cannot edit the row.
2. Proventos never reach an account (`routes/proceeds.py` writes no lançamento), so a wallet that
   reinvests dividends drifts from the real balance anyway.
3. A linked sale or redemption is an INCOME row, and Início and Extrato count it as Receita
   (`isInvestmentOutflow()` only covers EXPENSE) — it inflates the month's result and the savings
   rate.
4. A statement import brings the bank's own debit line, and import only dedupes against its own
   rows: the same money leaves the account twice.
5. A first-time user entering old positions drives the balance deeply negative — the reason
   `skip_cash` was built on 2026-09-27.

**Local data when the plan was made** (read-only counts, 2026-10-12): two users. One has 36 buys,
all linked, all in the default account — 36 of its 49 Extrato rows. The other entered 12
operations and ticked the opt-out on all 12, with no lançamento at all. No sale, no provento, no
receipt on a linked row, no budget or recurrence on "Investimento".

## 3. The rule

**An investment operation touches the banking area only when the owner asks for it, per
operation.**

- The movement carries `metadata.cash_account_id`. Present: exactly one linked lançamento exists
  in that account, in the same shape as today (`source_type`, `source_id`, id `cash:<id>`, BRL,
  category "Investimento"). Absent: nothing is written to `transactions`.
- It replaces `metadata.skip_cash`. One key is both the switch and the account, so there is one
  rule function (`investment_cash_account_id(metadata)`), checked first in the sync — before any
  PTAX lookup, as `investment_skips_cash()` is today.
- Each movement decides for itself: a linked buy does not make its later sale linked.
- The banking area keeps one way of knowing about investments that does not need the link: a
  lançamento typed by hand in the category "Investimento" is still an aporte (or a resgate), not
  an expense (or an income).

The price, stated plainly: with the link off, an account balance is right only if the debit gets
there some other way — a statement import or a typed lançamento.

## 4. Decisions taken (owner, 2026-10-12)

1. **Rows already linked stay linked.** Migration 024 changes no balance; the owner unlinks in
   bulk from a preview, after seeing what moves.
2. **Início keeps Patrimônio = contas + carteira** as the one read-only bridge between the areas
   (the `NET_WORTH` goal sums both too).
3. **"+ Novo" becomes banking-only**; inside Investimentos it opens "Registrar operação".
4. **This session wrote documents only.** The code changes are the phases below.

## 5. Phases

Each phase is one commit that leaves the app working. Run `finance-guard` on phases 1 and 2.

### Phase 1 — backend: the link becomes opt-in

- `services/investments.py`: `investment_cash_account_id()` replaces `investment_skips_cash()`.
  The sync returns early (deleting any linked row) when the key is absent; when present it upserts
  into that account. The `UPDATE` must set `account_id` too — today it never does — so changing
  the account moves the same row instead of leaving it behind. `ensure_default_account()` is no
  longer used here.
- `routes/investments.py` (`POST`, `PATCH`): validate the key before writing, scoped by `user_id`
  (`require_account()`): unknown, another user's or archived account is refused; an account whose
  `currency` is not BRL is refused (the linked row is always BRL). On `PATCH`, an account that was
  already the movement's and has since been archived must not block the edit. The key is **not**
  added to the kept-keys list next to `fx_rate` — a metadata without it means "unlink", which is
  how the edit form toggles it.
- Migration `024_investment_cash_opt_in.sql`, data only, no table rebuild:

  ```sql
  -- A movement that has a linked lançamento today keeps it, in the account it is in.
  UPDATE investment_transactions
  SET metadata = json_set(
      CASE WHEN json_valid(metadata) THEN metadata ELSE '{}' END,
      '$.cash_account_id',
      (SELECT t.account_id FROM transactions t
       WHERE t.user_id = investment_transactions.user_id
         AND t.source_type = 'INVESTMENT_TRANSACTION'
         AND t.source_id = investment_transactions.id)
  )
  WHERE EXISTS (
      SELECT 1 FROM transactions t
      WHERE t.user_id = investment_transactions.user_id
        AND t.source_type = 'INVESTMENT_TRANSACTION'
        AND t.source_id = investment_transactions.id
        AND t.account_id IS NOT NULL
  );

  UPDATE investment_transactions
  SET metadata = json_remove(metadata, '$.skip_cash')
  WHERE json_valid(metadata) AND json_extract(metadata, '$.skip_cash') IS NOT NULL;
  ```

  A sketch, to be proven by the test below. Two things to settle while writing it: a linked row
  with `account_id IS NULL` (give it the user's default account first — none exists locally), and
  a movement whose metadata does not parse (the sketch replaces it with `{}`; confirm
  `parse_metadata_value()` already reads it as empty).
- Tests:
  - `test_investment_cash_link.py` rewritten around the opt-in: a plain buy writes nothing and
    leaves the balance alone; with the key, an EXPENSE in that account; a sale or redemption, an
    INCOME net of costs; changing the account on `PATCH` moves the row (still one row); removing
    the key deletes it; another user's account is refused and nothing is written; archived and
    non-BRL accounts; a foreign asset linked lands in BRL at the movement's rate, and unlinked
    fetches no PTAX. `TestPositionBeforeTheApp` goes away.
  - The six files that read linked rows pass the key explicitly: `test_attachments.py` (three
    places), `test_accounts_and_transfers.py`, `test_corporate_actions.py`,
    `test_transaction_edit.py`, `test_multicurrency.py`, `test_rule_apply.py`.
  - A migration test: build a scratch SQLite file from `001`–`023`, insert a linked movement, a
    `skip_cash` one and a bonus, apply `024`, and assert the `transactions` rows are identical, the
    key is set on the linked one, `skip_cash` is gone, and no linked row is left without a movement
    that names its account. It needs only `sqlite3` and the migration files (no app module).

### Phase 2 — forms and the bulk unlink

- One shared field (checkbox + account select, BRL accounts only, default account preselected,
  **off by default**) used in three places: `InvestmentLaunchModal.jsx` (buy and sale), the
  Operações edit form, and the Posição redemption sheet (`handlePartialSale()` gains the key).
  It replaces the "Operação anterior ao app" checkbox. Copy: "Lançar no extrato" — on a buy,
  "Cria uma saída deste valor na conta escolhida. Deixe desmarcado se o débito já está no extrato
  (importado ou lançado à mão)."; on a sale or redemption, "Cria uma entrada do valor líquido na
  conta escolhida."
- Operações: the row tag flips — "no extrato" on linked movements replaces "anterior ao app" on
  unlinked ones.
- Bulk unlink, in the shape of the import-rules apply (preview never writes; the write takes ids):
  - `GET /api/investments/cash-links` — every linked movement (asset, date, type, amount,
    account, receipt count) and the effect on each account's balance.
  - `POST /api/investments/cash-links/unlink` with `investment_ids` — unlinks only those ids,
    re-checking each (the user's, still linked); goes through the sync so there is one code path.
    A linked row with receipts is skipped and reported, not deleted. The id list is the
    confirmation guard: nothing can be unlinked without reading the preview first.
  - Both routes go into `test_route_map.py`; tests for the preview not writing, a stale or foreign
    id being ignored, and the receipt skip.
  - UI: Operações → `Menu` → "Desvincular do extrato…", a sheet with the list and the totals, then
    `confirmAction()`, then `toast()`.
- No frontend test runner: check in a browser on a scratch database.

### Phase 3 — the banking read side

- `lib/transactions.js`: a linked INCOME, or one typed in "Investimento", is a resgate and not a
  receita. Início's cash flow and month result and Extrato's totals stop counting it as income; the
  investment series becomes aportes − resgates. The Extrato badge covers both directions.
- Início's banking panels only know money that went through the Extrato: "Média investida" and the
  "Investimentos" series render only when the window has such rows. Patrimônio is untouched.
- "+ Novo": `NEW_ENTRY_TYPES` loses "Investimento"; in `Layout.jsx` the button opens
  `InvestmentLaunchModal` when the path is under `/investimentos`, and the banking sheet elsewhere.
- `CLAUDE.md`: rewrite the convention "A movement can opt out of the cash link" as the opt-in rule
  (with phase 1), and the "+ Novo" notes (with phase 3).

## 6. What is removed

- Phase 1: `metadata.skip_cash`, `investment_skips_cash()`, the silent default-account link,
  `TestPositionBeforeTheApp`.
- Phase 2: the "Operação anterior ao app" checkbox (launch form and Operações edit) and the
  "anterior ao app" tag.
- Phase 3: "Investimento" in the "+ Novo" sheet and its `onPickInvestment` hand-off.
- Documents, done on 2026-10-12: the "Operação anterior ao app — leftovers" section of
  `next-steps.md` (its redemption-form and bulk items are phase 2; its owner check was of a
  checkbox that is going away).

## 7. Not in the plan

Owner's call, each one independent of the phases:

- **Proventos in the Extrato.** The same opt-in for a provento (an INCOME in a chosen account).
  Today proventos never touch an account.
- **Metas under Investimentos.** Goals read the portfolio and sit in Planejamento, a banking
  section; moving them makes Investimentos seven tabs.
- **Remembering the last choice** of the checkbox and account on this device, if ticking it every
  time becomes a chore.

Rejected: modelling the broker as an account (buys debit it, a TRANSFER funds it). It is the
textbook answer and it couples the areas more, not less.

## 8. Risks and traps

- **Patrimônio can count the same money twice.** An unlinked buy whose debit never reaches the
  account leaves the money in the account *and* in the portfolio. The checkbox copy has to say
  when to leave it off. The opposite error — link on and the same debit imported — is today's
  behaviour for every operation.
- **The six test files break loudly — keep it that way.** Each one indexes into the linked row or
  compares it with a concrete value, so flipping the default fails them instead of emptying them
  (checked 2026-10-12). Fix each by sending the key, never by loosening the assertion. The silent
  case is a *new* test: "the linked rows did not change" compares an empty list with an empty list
  unless the test links first and asserts the row exists.
- **Unlinking deletes lançamentos.** They are derived and come back by linking again, but their
  receipts do not (`transaction_attachments` cascades, the files are swept at boot). Hence the
  skip in the bulk action. Unticking the box on a single edit deletes the row as `skip_cash` does
  today.
- **A budget on "Investimento"** sees only linked or typed aportes from now on. None exists
  locally.
- **Migration and code land together.** After 024 nothing may read `skip_cash`; before it, nothing
  writes `cash_account_id`.
