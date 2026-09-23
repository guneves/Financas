# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (night) · Phase 5 started: `app.py` split, everything but investments

Asked to "start phase 5". Took it as: start splitting `backend/app.py` and go as far as the steps
stay mechanical and verifiable. One commit per step, suite green before each (`826cc6c`..`6354c90`).

### What was done

- **Foundation modules** (bottom of the import graph): `config.py` (env + `.env`, read once),
  `db.py` (connection, migrations, backups, `row_to_dict`, metadata/row helpers, `new_id`,
  `utc_timestamp`), `validators.py`, `auth.py` (JWT + `token_required`), `money.py`
  (`rounded_money`), `dates.py` (ISO parsing, month arithmetic, `clamped_date`), `source_types.py`
  (every `transactions.source_type` value in one place, with its `source_id` shape).
- **Services:** `services/accounts.py` (default account, default categories, `resolve_*`,
  `account_balance_rows`), `services/invoices.py` (invoice month, closing, settlement, autopay,
  `local_today`), `services/attachments.py` (sniffing, paths, orphan sweep).
- **Blueprints** in `routes/`: system, auth, accounts (+ transfers, categories), transactions
  (+ CSV export), attachments, budgets, recurring, imports (+ rules), cards (+ cc-expenses,
  pay-invoice). Registered in one list in `app.py`.
- **Code moved verbatim.** An AST script cut whole top-level definitions (with their comment lines)
  and wrote the import lines; the only edits inside moved code are `@app.route` → `@bp.route`.
  pyflakes (installed in the scratchpad, not the venv) was clean after every step except the
  pre-existing `f-string is missing placeholders` in `app.py`.
- **`tests/test_route_map.py`** (new, 3 tests): the 60 routes with their methods, captured from
  `4182be2` before the split, must all exist and no others; and every route except health, signup
  and login answers 401 without a token. Suite: 605 passed.
- **Tests retargeted** to the module that reads the patched name: `test_backups.py` → `db_module`;
  `test_invoice_month.py` / `test_invoice_payment.py` → `invoices_module`, and the clock is frozen in
  both `services.invoices` and `routes.cards` (checked: patching only one makes an autopay test
  fail); `test_attachments.py` patches the limits on `routes.attachments` and calls the file helpers
  on `services.attachments`. New fixtures in `conftest.py`: `db_module`, `invoices_module`.
- **Seed script** `scripts/seed_three_years_mock.py` imports `config`, `create_token`,
  `rounded_money` and `seed_default_categories` from their modules (it only still uses `app.app`).
  Import-smoke-tested against a scratch DB.
- **Verified:** full suite green after every step; URL map identical to `4182be2` (diffed, 60 = 60);
  real `python app.py` booted on a scratch DB, signup + 7 GETs across the moved areas answered 200;
  `backend/finance.db` mtime unchanged all session. `CLAUDE.md` (tests, layout, conventions,
  sharp edges) and `docs/next-steps.md` updated.
- **`finance-guard`** (found by `subagent_type` directly), over `4182be2..HEAD`: no findings. It
  diffed all 166 moved functions against `4182be2:backend/app.py` — byte-identical; `user_id`
  filters, `@token_required`, archive-not-delete and the attachment double-id guard intact; each
  patched name is read in exactly the module the tests patch; no migration touched; 605 passed.

### What was not done and why

- **Investments — all of what is left in `app.py` (~3,600 lines).** It is the most coupled area and
  the one the tests patch most (`download_market_prices`, `download_close_prices`, `yf`,
  `market_price_provider`, `fetch_bcb_series`, `urllib`, `fixed_income_accrual_factor`,
  `fixed_income_rate_terms`, `unique_market_asset_targets`, `open_asset_ids`, …), with module-level
  caches and thread pools. It deserves its own session rather than the tail of this one.
- `create_app()` factory: not started; `app.py` still does its work at import time, which the test
  setup depends on. Do it after investments are out.
- The pre-existing pyflakes warning in `app.py` (f-string without placeholders) — left; it is in
  investments code that has not moved yet and "verbatim" was the rule.
- Carried: the owner has walked none of the UI remodel or earlier items (checklist at the top of
  `next-steps.md`); open decisions G (Ctrl K) and I (attention items) unanswered; `BRAPI_TOKEN`
  empty in `backend/.env`; `backend/backups/finance-pre-mock-20260922-205415.db` safe to delete;
  receipts not in the backup zip; amount/account conditions on import rules not built.

### Next session

- **Finish Phase 5 with investments**, bottom-up, a commit per module:
  1. `services/prices.py` — `_price_cache`, `_history_cache`, the lock, both executors,
     `ticker_key` … `refresh_market_prices`, `yahoo_symbol`, `quote_*`, and the `yf` import.
  2. `services/fixed_income.py` — `FIXED_INCOME_*`, `BCB_*`, rate terms, accrual factors,
     `fetch_bcb_*`, the fixed-income refresh.
  3. `services/investments.py` — asset/movement helpers, cash sync, tax rates, FIFO
     (`build_*_realized_result`), realized results, backing validation.
  4. `services/portfolio.py` — snapshot, materialized positions, evolution.
  5. Blueprints `routes/investments.py`, `routes/proceeds.py`, `routes/market.py`;
     `export_portfolio` goes with investments and takes `csv_response` from wherever it lands
     (today it is in `routes/transactions.py` and `app.py` imports it — move it to a shared spot
     rather than making a blueprint import a blueprint).
  For each step, list the test patches that touch the moved names first
  (`grep -n "monkeypatch.setattr(app_module" tests/`) and retarget them in the same commit — a patch
  on the wrong module passes silently.
- Owner: the walk-through at the top of `next-steps.md`; open decision 1 (card purchases vs. budget).

### Non-obvious things learned

- **Patch where the name is read.** Modules bind settings and helpers by name
  (`from config import X`), so `monkeypatch.setattr(config, "X", …)` does nothing to `db`. When two
  modules both call a patched function (`local_today` is called from `services.invoices` *and*
  `routes.cards`), patch both. Now in `CLAUDE.md` → Tests.
- **Don't reload the pure modules in conftest.** A first version popped every backend module from
  `sys.modules`; `brapi_client` got reloaded, and `test_market_price_provider.py` (which imports it
  at the top) raised a `BrapiHTTPError` from the *old* class that `app` no longer caught. The
  fixture now pops only `app` and `config`.
- **pyflakes exits 1 on the old f-string warning**, so `pyflakes … && next-step` silently skipped the
  next step once (a blueprint went unregistered; tests caught it as 404s). Use `;` after pyflakes.
  `test_route_map.py` now catches that directly.
- **Tooling** (scratchpad, not committed): `extract.py SRC DEST HEADER names…` moves top-level
  definitions verbatim and adds the import line to SRC; `prune_imports.py` drops what pyflakes calls
  unused; `section.py FILE A B` lists what a line range defines and needs. Recreate them from this
  description if the scratchpad is gone — they are ~100 lines each. The helper computing the module
  name must work from the backend root (a first version produced `from ...source_types` when SRC
  was inside `routes/`), and must skip the module docstring when finding the import block.
- Carried: scratch server = set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `ATTACHMENTS_DIR`,
  `AUTO_BACKUP_ON_BOOT=0`, `JWT_SECRET` before `import app` (or before `python app.py`); check
  `netstat -ano` for ports first. The venv's `python.exe` is a launcher — kill by port, then check no
  `app.py` process is left.
- Carried (frontend): Vite does not catch an undefined component or identifier — a throwaway
  ESLint 8 + `eslint-plugin-react` in the scratchpad with `no-undef` / `react/jsx-no-undef` does.
  For browser checks: seed with `seed_three_years_mock.main()` against the scratch DB, auth JSON
  into `localStorage['@financeMVP:auth']`, theme into `'@financeMVP:theme'`. Dark mode is a token
  swap — never `dark:` classes or a non-theme colour family.
