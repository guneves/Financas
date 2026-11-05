# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · Notifications + Pluggy, session 3 of 5: Phase 3 (investments Pluggy-only)

Branch: **`claude/notify-pluggy-phase3`**, from `claude/notify-pluggy-phase2` at `a5ff075` (Phases 1 + 2),
merged with `origin/main` (already up to date). Migration **056**. **The chain changed**: mid-session the
owner asked to open a PR and merge when done ("i'll continue the development through cloud sessions"),
so this branch went to `main` through a PR with Phases 1–3. Sessions 4 and 5 start from `main`.

**Done**
- **Raw position** (056 `open_finance_positions.raw`): `_save_positions()` stores the whole Pluggy object
  minus `transactions`, every pull. `backend/scripts/position_fields.py --email X`: read-only (`mode=ro`,
  imports `config`, never `app`), prints type / subtype and the keys that are filled, never values.
- **Fixed income from exact data** (`services/open_finance_fixed_income.py`, called from `decide()` for
  `pluggy_type == FIXED_INCOME`): `title_terms()` maps CDI+rate, IPCA+fixedAnnualRate, PRE+fixedAnnualRate
  and `subtype` (CDB, LCI, LCA, LC, CRI, CRA, DEBENTURE(S), TREASURY); Tesouro must be found in the price
  file with the same indexer and maturity. Everything else is `HELD missing:<field>` / `unmapped:<field>`.
  BUY: quantity 1, price = amount + expenses, `open_finance_units`, `treasury_units` on Tesouro, **no cash
  link**. SELL: PEPS over the buys of the same Pluggy investment id by units (`redemption_plan()`, pure).
  INTEREST: provento on the first buy's asset, `interest_tax_rate()` (moved from `routes/proceeds.py` to
  `services/proceeds.py`), then `broker_statement.adopt_proceed_line()` turns the statement line that
  already paid it into the proceed's row. Typed twins (same cents ±2 days) are linked. 056 also adds
  `open_finance_investment_operations.proceed_id` (deleting the proceed → DISMISSED).
- **The guard** (`manual_entries.require_manual_investment_cash()`, routes only): `POST /api/investments`
  and redemptions (both via `create_movements()`), `POST /api/investment-proceeds`
  (`proceeds_cash.proceed_cash_account_id()`), PATCH moving onto the fed Corretora. Exception by
  `metadata.open_finance_op_key` → `open_finance_investments.held_operation()` / `complete_held()`.
- **Held list**: `portfolio_check()['held']` now has `op_key`, `pluggy_type`, `prefill` (`held_prefill()`).
- **Web**: Ajustes › Open Finance › Carteira da corretora: "Lançar" per held line (operation →
  `InvestmentLaunchModal prefill=`; coupon and redemption: one confirm, then POST). `CashLinkField` uses
  `cashLinkWithAccounts()`: on a fed Corretora a new operation defaults to "Não descontar", with
  `PLUGGY_FED_NOTE`. New `lib/investmentPrefill.js`; reasons in `heldReasonLabel()`.
- **APK**: `rules/InvestmentPrefill.kt` (prefill → `LaunchForm`, `heldReasonLabel`), `LaunchForm.opKey`
  sent by `buyPayload`/`sellPayload`, `PortfolioAccount.cashLinkWithAccounts()` + `pluggy` on `Account`,
  the note in `CashLinkField`, `OpenFinanceDto.investments.held`, and "Operações da corretora para você
  lançar" with "Lançar" in Ajustes › Open Finance (opens `LaunchSheet` via `openPrefilled()`).

**Tests**
- New `test_open_finance_fixed_income.py` (60): raw kept/updated; `title_terms` mapping and every hold
  reason (incl. SELIC, CDI+fixed, unit ambiguity); Tesouro (in file, wrong year, wrong indexer, wrong
  maturity, no file); BUY recorded without cash, missing rateType, SELIC, fills itself later, repeat
  no-op, typed twin linked, undo for good, LCI tax-free, Tesouro category; redemption PEPS (oldest lot,
  across lots, continues, no buy, too many units, pure plan); INTEREST (20% from the first buy, no buy,
  undo, statement line adopted with `apply_paid_proceeds()` run after: one row); `position_fields.py` on
  a temp DB (keys, no values, file untouched, exit 2).
- New `test_pluggy_investments_only.py` (25): every row of the prompt's table plus naming the Corretora,
  another account, switch off, a Corretora without Pluggy, PATCH onto / keeping, unknown/not-held keys,
  redemption refused / null / completed by key, proventos refused / before `portfolio_since` / switch off
  / coupon completed by key / another user's key, `proceeds_sync` + `apply_paid_proceeds()` still write,
  Pluggy operations still record on the Corretora.
- Node: `investmentPrefill.test.js` (5), 2 cases in `portfolioAccount.test.js`, 2 in `openFinance.test.js`.
- JVM: `InvestmentPrefillTest` (6), 2 cases in `PortfolioAccountTest`.
- Results: backend full suite green in 4 chunks; `npm test` 236 green; `vite build` ok;
  `gradlew --offline testDebugUnitTest assembleDebug` green (569 JVM tests).

**Not done, and why**
- No real GET of BTG `/investments`: production data is off-limits. The owner runs `position_fields.py`.
- APK "Lançar" opens operations only; coupon and redemption are web (the APK has no proceeds/redemption
  form wired to a prefill yet).
- The web's one-tap redemption needs exactly one fixed-income position with the title's name; otherwise
  it says to redeem in Posição (that redemption carries no `op_key`, so the HELD line stays).

**Next**: session 4 (Phases 4 + 5, `04-…` then `05-…`) **from `main`**, then session 5's final verification.

### For the final verification
- **Riskiest**: (1) the meaning of Pluggy's `rate`/`fixedAnnualRate` units is assumed percent per the docs;
  `position_fields.py` shows only key presence, so the first real recorded CDB must be checked by eye
  (`cdi_percentage` 1.10 for 110%). (2) `adopt_proceed_line()` deletes a `BROKER_STATEMENT` row and points
  the Pluggy row at the proceed's entry — only when that entry exists (payment on/after `portfolio_since`).
  (3) The guard turns on in production (`MANUAL_ONLY_OFF_PLUGGY` is on there): typing on the BTG Corretora
  stops; the cash default in the forms is now "Não descontar".
- **Tests changed**: `test_open_finance_investments.py` — `test_other_types_wait_for_the_owner`
  (FIXED_INCOME now `unmapped:subtype`, equity TRANSFER/INTEREST still `type`) and
  `test_held_operations_are_listed` (`missing:rateType`): the rule changed (design §5, decision 3).
  `openFinance.test.js`: the `type` label is now "fundo, custódia ou outro tipo" (fixed income no longer
  says "type").
- **Not tested**: the web "Lançar" was built, not clicked in a browser; the APK screen compiled, not run on
  a device; real Pluggy data.

Lessons:
- `pytest.ini` already has `-q`; adding `-q` again hides the summary line, so a red run looks like dots.
- A module created in the session is untracked: `git checkout` does not restore it after a mutation test;
  copy it aside first.
- Fixed-income cash must not be linked: the statement line (step 2 of the pull) is already the money, and
  the investment step runs after it.
