# Notifications + Pluggy: rules for every phase session

Read this file before your phase prompt (`01-…` to `05-…`). The design is
`docs/notifications-pluggy-design.md`. Read all of it before writing code: §7 lists the owner's
decisions, and they are not open for discussion.

## Getting the design into your checkout

The design and these prompts are on `main` (merged 2026-11-04). If your checkout lacks
`docs/notifications-pluggy-design.md`, run `git fetch origin main` and then
`git merge origin/main`.

**Line numbers** in the prompts are as of 2026-11-04. Earlier phases move them, so always find code
by the function name (`grep -n "def <name>"`).

## Before you start

1. Read `CLAUDE.md`, the whole design, `docs/handoff.md` and your phase prompt.
2. **Check your phase's prerequisites** (each prompt lists greps). If one fails, stop and tell the
   owner which phase must be merged first. Don't build on a missing phase.
3. Set up the backend tests. The container has no `.venv`. First set `SCRATCH` to your session's
   scratchpad directory (the system prompt names it), then:
   ```bash
   python3 -m venv "$SCRATCH/venv"
   ```
   ```bash
   "$SCRATCH/venv/bin/pip" install -q -r backend/requirements-dev.txt
   ```
   ```bash
   cd backend && "$SCRATCH/venv/bin/python" -m pytest -q
   ```
   Run the full suite once **before** changing anything, so you know what was already red. It has
   about 1600 tests and takes minutes; run it in the background or with a long timeout.
4. Frontend, only if your phase touches it: `cd frontend && npm ci && npm test`.
5. Android: the container has **no Android SDK**. A push to a branch that touches
   `frontend/android/**` runs `.github/workflows/android-check.yml` (JVM tests + debug APK). Read
   the result with the GitHub MCP actions tools (`gh` is not available). A red android-check means
   the phase is not done.

## Hard rules (each one has broken this project before)

- **Never push to `main` and never merge.** A push to `main` deploys to the owner's server
  (`deploy.yml`). Work on your session branch and push there. At the end, open a pull request to
  `main` (the owner asks for it in every session prompt), and leave the merge to the owner.
- **Never read or write production data.** Not over SSH, not through the API. Phase 3's real-data
  check is a command the owner runs (see that prompt).
- **Migrations**: append-only, a new numbered file. Pick the number **after**
  `git fetch origin main && git merge origin/main`, then rerun the **full** suite on the merged
  tree. On 2026-11-03 two branches both used 052, `init_db()` silently skipped one and production
  broke. `test_migration_numbers.py` guards it; run it.
- `user_id` on every table and every query; money only through `rounded_money()` / `parse_money()`;
  dates zero-padded.
- **Tests**:
  - a test never imports `db`, `routes.*` or `services.*` at the top; use the fixtures or
    `importlib.import_module` inside the test;
  - patch a name where it is read, not where it is defined (see the CLAUDE.md list);
  - `conftest.py` sets `AUTO_RECORD_DEFAULT=0` and `MANUAL_ONLY_OFF_PLUGGY=0`; turn them on per test
    with `monkeypatch`, as `test_auto_record.py` and `test_pluggy_owner_rules.py` do;
  - the bank notification gate is opened per test with the fixture `any_bank_notifications`, which
    replaces `services.inbox.notification_wanted` with `lambda detection: True`. **Keep that
    function's signature `(detection)`**, or every engine test breaks.
- **FakePluggy** (`tests/open_finance_world.py`):
  - `World` and `connected()` build a mapped connection;
  - `fake.add_tx()` / `fake.drop_tx()` change what the next `world.sync()` returns;
  - `bank_tx(..., status="PENDING")` makes a pending row;
  - `pluggy_updated_at` in the future never counts as read;
  - copy the date patterns of `test_auto_record.py` (2026-10-xx works there).
- **Pull window**: since 2026-11-04 each pull reads `LATE_POSTING_DAYS` (35) days back from the
  last pull (`_date_from()` in `services/open_finance.py`), because an international purchase
  "em processamento" posts days later with its purchase date. Anything that scans "rows of this
  pull's window" (`vanish_missing()`, the succession's *missing* set) covers those 35 days.
- **Pull order** (`services/open_finance.py`, `_sync_item_locked()`):
  1. per account: normalize, then `vanish_missing()`;
  2. `ingest()` of the whole batch, sorted by (date, outgoing first);
  3. investments;
  4. `record_pending()`;
  5. `record_bank_payments()`;
  6. `mark_bank_investments()`.

  Anything you add must say where in this order it runs, and why.
- **Don't weaken a test to make it pass.** If an existing test fails because the design changes the
  rule, change it in the same commit and name it in the handoff with the reason. If it fails for
  any other reason, the code is wrong.
- **Every financial rule you touch gets a test.** A frontend rule tested with node imports nothing
  from the browser, React or `lib/api.js`.
- Comments and identifiers mix Portuguese and English; match the file. User-facing text is
  Portuguese; `docs/` is English.

## Finishing a phase

1. Full backend suite green on a tree merged with `origin/main`. Also `npm test` if you touched the
   frontend, and android-check green if you touched the APK.
2. Update `CLAUDE.md` for what is now true. Change the rule text, don't append a diary.
3. Session process (CLAUDE.md):
   - move your phase's items from `docs/next-steps.md` to `docs/done-tasks.md`; what is left stays
     open and is rewritten;
   - replace `docs/handoff.md`: what you did, what you didn't do and why, what comes next, and the
     non-obvious lessons.
4. Commit with a clear message and push your session branch. Open a pull request to `main` titled
   "Notifications + Pluggy — <phase>". Use the repository's PR template if there is one; the body
   lists the changes, the tests and what the owner must check. **Don't merge it.**
5. Tell the owner, in Portuguese:
   - the PR link;
   - what changed for them;
   - the tests added, by name;
   - what they must check after merging;
   - which session comes next.

   The verification session (`06-verify-and-fix.md`) runs on your branch **before** anything is
   merged.
