# Phase 3: investments come only from Pluggy

Read `00-common.md` first. Design: §5 and §7 decision 3. Independent of Phases 1–2 in code, but it
adds migrations. Run it **after** Phase 2 is merged. If the owner runs it in parallel, renumber
your migration after merging `origin/main` and rerun the full suite: two migrations with one number
break production silently.

**Prerequisites:**

```bash
grep -n "def _save_positions\|def decide" backend/services/open_finance_investments.py
```

## What to build

### A. Keep everything Pluggy says about a position

`_save_positions()` (`open_finance_investments.py` ~318) keeps only code, name, type, subtype,
quantity, value, balance, status and date. Pluggy's documented Investment object also has `rate`,
`rateType`, `fixedAnnualRate`, `dueDate`, `issuer`, `issueDate` and `isin`. Nobody knows yet which
of these MeuPluggy fills for BTG.
- Migration: `raw TEXT` (JSON) on `open_finance_positions`. Store the whole object **minus
  `transactions`**, updated on every pull.
- `backend/scripts/position_fields.py --email <email>`: read-only (SQLite `mode=ro`, never import
  `app`). For each position it prints the type, subtype and **which keys are non-null**. No values,
  except type and subtype. The owner runs it after the deploy:
  `sudo docker compose exec -T -w /app/backend app python scripts/position_fields.py --email <email>`.
  Put that command in your final message.

### B. Record held fixed income only from exact data

In `decide()` (~290), today everything that is not `EQUITY` BUY/SELL is `HELD "type"`. Add one
path:
- **Which positions**: fixed income and Tesouro, whose position (same Pluggy investment id) has a
  `raw` that maps **exactly** to the app's metadata.
- **How to map**: read `validate_fixed_income_metadata()` and `fixed_income_rate_terms()`
  (`services/fixed_income.py` ~170–200).
  - The app accepts `rate_type` POS/PRE and the indexers in `FIXED_INCOME_INDEXERS` (CDI, CDI+,
    IPCA+).
  - Map Pluggy's `rateType` and `rate`/`fixedAnnualRate` only when the meaning is unambiguous:
    - CDI with a rate is a "% do CDI";
    - IPCA with a fixed annual rate is "IPCA+ x%";
    - pre-fixed with a fixed annual rate is "PRE x%".
- **Hold, never guess**:
  - SELIC, anything unmappable, or any missing field stays `HELD` with reason
    `missing:<field>`;
  - the module says why: a wrong rate marks the portfolio wrong without warning.
- **Title type** (CDB, LCI, LCA, LC, CRI, CRA, DEBENTURE, TREASURY) decides IR and category. LCI
  and LCA are exempt; follow `services/asset_categories.py`.
- **Tesouro** goes through `services/treasury.py`. The title name must match the Tesouro price
  file's names (`tesouro_client.py`); if not exact, hold it.
- **Redemption** (`related_id`): the BUY of the same Pluggy investment id. With several buys, PEPS
  (oldest first), the rule of `lib/treasury.js`. With no buy in the app, hold it.
- **INTEREST** (coupon) becomes a provento `INTEREST` (040), taxed from the title's first BUY
  (`interest_tax_rate()`).
- **Idempotency**: by `op_key`, as today; `DISMISSED` stays dismissed.

### C. Typing is refused on the Pluggy-fed Corretora

- **Which routes**: `POST /api/investments` (`routes/investments.py` ~451; with no cash key it uses
  `portfolio_cash_account_id()`, the Corretora), `POST /api/investments/redemptions` (~548) and
  `POST /api/investment-proceeds` (`routes/proceeds.py:376`).
- **The rule**: refuse with 400 "A Pluggy traz as operações da corretora." when the resolved cash
  account is in `manual_entries.bank_fed_account_ids()`, and only while
  `manual_entries.MANUAL_ONLY_OFF_PLUGGY` is on. A PATCH that moves an operation **onto** that
  account is refused too.
- **Exception**: the payload's `metadata.open_finance_op_key` names a `HELD` operation of **this
  user**. The guard lets it through, and the HELD row becomes `RECORDED` with the new id, in one
  transaction. Another user's key, an unknown key, or a key that is not `HELD` gives 400.
- **Guard only the routes.** Never touch the server's own writers: `proceeds_sync`,
  `apply_paid_proceeds()` and `open_finance_investments`.
- **Tests**: conftest has `MANUAL_ONLY_OFF_PLUGGY=0`, so the hundreds of existing investment tests
  keep typing. Turn it on per test with
  `monkeypatch.setattr(importlib.import_module("services.manual_entries"), "MANUAL_ONLY_OFF_PLUGGY", True)`,
  as `test_pluggy_owner_rules.py:380` does.

### D. Screens

- **"Lançar"** (web and APK): the HELD list (Ajustes › Open Finance, "operações para você lançar")
  gets a "Lançar" that opens the operation form pre-filled and carries the `op_key`.
- **The operation form**: when the Corretora is Pluggy-fed (`pluggy: true` on `GET
  /api/accounts`), the cash default is "Não descontar" or another account, never the Corretora. A
  short note says why.
- **Crypto and other assets Pluggy can't see** stay typed.

## Tests

| Case | Expected |
|------|----------|
| position with a complete CDB CDI 110% raw, a BUY operation | recorded with indexer CDI 110% |
| same, `rateType` missing | `HELD missing:rateType` |
| SELIC position | HELD |
| redemption with two buys | lot of the oldest (PEPS) |
| INTEREST | provento INTEREST, taxed from the first buy |
| typed BUY on the fed Corretora, switch on | 400 |
| typed BUY with `cash_account_id: null`, switch on | 201 |
| typed BUY with a valid HELD `op_key` | 201, the HELD row becomes RECORDED |
| another user's `op_key` | 400 |
| `proceeds_sync` with the switch on | still writes |
| `position_fields.py` on a temp DB | prints keys, no values |

Extend `FakePluggy.add_position()` to accept the extra fields (`rate`, `rateType`,
`fixedAnnualRate`, `dueDate`, `issuer`), defaulting to absent.

## Done when

All green on a tree merged with `origin/main`; CLAUDE.md's Investments section says typing is
refused on the fed Corretora and how HELD lines are recorded. In your final message, tell the owner
to run `position_fields.py` after the deploy and paste the output into the next session. Until
then, whether held lines fill themselves on real data is unknown. Then run `06-verify-and-fix.md`
for Phase 3.
