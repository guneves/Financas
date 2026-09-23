# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-23 (late) · Phase 5 finished: investments out of `app.py`

Asked to "work on phase 5". Did the investments step the last handoff laid out: bottom-up, code
moved verbatim, suite green and one commit per step (`93fe66a`..`a06b3f1`).

### What was done

- **`app.py`: 3,603 → 60 lines.** It now only creates the Flask app, sets up CORS, registers the
  twelve blueprints and runs the boot (`init_db`, startup backup, orphan-receipt sweep).
- **New modules**:
  - `asset_classes.py`: `ALLOWED_ASSET_CLASSES`, `QUOTED_ASSET_CLASSES`, `ASSET_CLASS_LABELS`,
    `parse_asset_class_filter`. Both prices and the blueprints need these.
  - `responses.py`: `csv_response`, moved out of `routes/transactions.py` so the investments
    blueprint doesn't import another blueprint.
  - `services/prices.py`: caches, lock, `_price_fetch_executor`, brapi/yfinance download, quote
    staleness, `record_price_quote`, and the single `yf` import.
  - `services/fixed_income.py`: indexers, BCB, accrual, validating the metadata, the two-half
    refresh and `_index_fetch_executor`.
  - `services/investments.py`: movements, assets, the cash link, backing validation.
  - `services/realized_results.py`: tax rates, FIFO, realized results. **This departs from the
    plan**, which had it inside investments. Split out because investments would otherwise have
    been ~1,000 lines, and FIFO plus tax is a self-contained unit.
  - `services/portfolio.py`: the snapshot, materialized positions, the market-price refresh and
    the evolution series.
  - Blueprints `routes/investments.py`, `routes/proceeds.py` and `routes/market.py`. The proceeds
    helpers live in the blueprint because it is their only caller (same as `routes/budgets.py`).
- **Import order** among the services: prices ← fixed_income ← investments ←
  realized_results / portfolio. Nothing imports `app`, no blueprint imports another, and services
  don't import routes (checked by grep).
- **Tests retargeted** to the module that reads each name. New fixtures: `prices_module`,
  `fixed_income_module`, `realized_results_module`, `portfolio_module`. `yf` is patched in
  `services.prices` *and* `routes.investments`, because `get_historical_portfolio` reads it too.
  Tests that read `get_db`, `market_catalog` or `subtract_months` through `app_module` now
  `importlib.import_module` the module that owns them.
- **Verified:**
  - The suite (605) passed after every step. `test_route_map.py` still pins the 60 routes.
  - A script compared all 133 moved definitions against `363e518`: byte-identical apart from
    `@app.route` → `@bp.route`.
  - pyflakes is clean apart from 3 warnings that were already there.
  - Booted on a scratch DB: signup, a buy and a sell, then 14 GETs across investments, proceeds,
    market, export and the statement all returned 200. The FIFO result was right (buy 50, sell 60 →
    profit 10, 15% tax).
  - `backend/finance.db` mtime unchanged.
- **Docs:** `CLAUDE.md` (Layout, Tests, patch targets, layering rule), `next-steps.md` (Phase 5
  section rewritten as leftovers) and `done-tasks.md` (row + note).
- **`finance-guard`** (found by `subagent_type` directly), over `363e518..HEAD`: no findings. It
  ran its own AST check of the 114 moved functions plus their decorators (identical), confirmed
  every monkeypatch target including the two-module `yf` patch, and confirmed the asset-class
  delete guard and `@token_required` on all 20 moved routes. No imports break the layering, there
  is no cycle among the services, `database/` is untouched and 605 tests passed.

### What was not done and why

- **`create_app()` factory.** Not built, and I recommend against it for now. `config.py` still
  reads the environment at import, so a factory alone would not free the tests from setting
  `os.environ` before importing. It only pays off if config moves into the app object too, and
  nothing needs two apps in one process. Kept in `next-steps.md` as optional.
- **Pre-existing pyflakes warnings**, left alone under the verbatim rule: an f-string without
  placeholders in `services/investments.py` and `tests/test_budgets.py`, and an unused `time`
  import in `brapi_client.py`. Each is a one-line fix whenever convenient.
- Carried:
  - The owner has walked through none of the UI remodel or the earlier items (checklist at the top
    of `next-steps.md`).
  - Open decisions G (Ctrl K) and I (attention items) are unanswered.
  - `BRAPI_TOKEN` is empty in `backend/.env`.
  - `backend/backups/finance-pre-mock-20260922-205415.db` is safe to delete.
  - Receipts are not in the backup zip.
  - Amount/account conditions on import rules are not built.

### Next session

- Phase 5 is closed. Back to product work, from the priorities in `next-steps.md`: the smaller
  gaps and the known limits, plus open decision 1 (card purchases vs. budget) once the owner
  answers.
- Owner: the walk-through at the top of `next-steps.md`.

### Non-obvious things learned

- **The session tooling is in the scratchpad** (not committed). Recreate it from this description
  if it is gone:
  - `move.py SRC DEST DOCFILE names…`: moves whole top-level nodes, with their decorators and the
    comment lines right above them. It generates DEST's import block from SRC's own imports and
    adds `from DEST import …` back into SRC. It refuses if the moved code needs a SRC top-level
    name that is not being moved (a cycle).
  - `wrap.py`: parenthesizes `from` lines over 99 characters.
  - `verify.py OLD1 OLD2 NEW…`: byte-compares definitions.
  - `deps.py FILE`: prints, for each top-level name, which other top-level names it uses.
  - Plus the old `prune_imports.py` and pyflakes in `pf/`.
- **Edge cases the mover misses:**
  - A module used as `urllib.error` *and* `urllib.request` gets only one import. pyflakes does not
    catch this, because `urllib.request` pulls in `urllib.error`. Grep for `urllib\.\w+`.
  - A blueprint whose first import line is `from flask import …` does not get `Blueprint` added.
    pyflakes does catch this one.
- **`app_module.X` in a test breaks silently in one direction only.** A *read* of a name `app.py`
  no longer has fails loudly (AttributeError). A `monkeypatch.setattr(app_module, "X", …)` passes
  `raising=False`, like the old `yf` patch did, would just set a dead attribute. Grep for
  `setattr(app_module` whenever a name moves.
- Carried:
  - Scratch server: set `DATABASE_PATH`, `DATABASE_BACKUP_DIR`, `ATTACHMENTS_DIR`,
    `AUTO_BACKUP_ON_BOOT=0` and `JWT_SECRET` before `import app`. Copy the signup payload from
    `conftest._signup` (a one-letter username on an `x.io` email got a 400; I didn't check
    which field was the problem). The token comes back as `access_token`.
  - Check `netstat -ano` for ports first. The venv's `python.exe` is a launcher: kill by port.
  - Frontend: Vite does not catch undefined identifiers. Use a throwaway ESLint with `no-undef`.
    Dark mode is a token swap: never `dark:` classes or a non-theme colour family.
