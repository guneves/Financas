# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-13 · The first stack merged and deployed; a second refactoring stack (#88–#93)

Continuation of the audit session (its report is `docs/audit.md`). The owner asked to merge and watch the first
stack, then to go on with R5, R7, R8, R10 and the rest of R6.

**Merged and deployed**: #76 first (deploy run 128 green: the pipeline blocked since 2026-11-11 is back), then
#77–#87 as one deploy (the stack merged upward into #80's branch, #80 into `main`; run 129 green: test, build,
deploy, apk). `main` = `3df0bf9`, the same tree that passed the full suite.

**Done, open as PRs** (each based on the previous branch; nothing merged):

| PR | Step | What |
|---|---|---|
| #88 | R6, rest | `inbox_store.py` (46 names) and `inbox_transfers.py` (16) out of `inbox.py`: 2749 → 1072 lines over the two slices |
| #89 | R7 | `open_finance_rows.py` (pure), `open_finance_settings.py`, `open_finance_mapping.py`; `open_finance_inbox.py` 1862 → 1654, `open_finance.py` 1230 → 850 |
| #90 | R5 | `services/entries.py`: one INSERT for a lançamento and one for a card row; nine hand-written statements call it |
| #91 | — | `conftest.py` removes the session's temp directory (each run left 3.7 GB) |
| #92 | R8, the move | ~940 Flask-free lines out of six blueprints into `*_payload.py` / `transaction_filters.py` |
| #93 | R10, first half | `buildSpending()` in `lib/homeSpending.js` and a parity test (real module run with node) against `/api/home/panels` |

Every move is verbatim and re-exported by the old module. Characterization written and green before each:
`test_entry_creation_rows.py` (the whole stored row per creation path), `test_home_panels_parity.py`.

**Numbers.** Full backend suite: 2921 on `main` → 2921 (#88, #89) → 2928 (#90, #92) → **2929 passed, 0 failed**
at the top (#93). `npm test` 245 pass, `vite build` ok. Ruff from `backend/`: 354 → 349, none new. APK: untouched.

**Not done, and why** (details in `next-steps.md`, top section)
- **The five long views** of R8: taking the rule out of a view that returns responses mid-way is a rewrite of
  money-moving code, not a move; one view per PR with a response-shape test first.
- **The engine knot** in `open_finance_inbox.py` (1654 lines) and what is left of `inbox.py` (1072): the sections
  call each other both ways; no mechanical cut exists.
- **R10's switch** (the web Início reading the server's panels): proved equal by the parity test, but a pending
  offline expense would stop counting in two panels until sent. The owner decides (#93).
- **Merging the two auto-record modules**: decided against, they are not copies.

**Next**: the owner merges #88 → #93 and answers #93's question and the three spending-rule decisions; then one
long view at a time.

**Lessons**
- Three times the full suite caught what the analysis missed, always the same shape: **something outside reaches
  a module through an attribute the refactor removed or re-homed**. A test patches `inbox.BANK_NOTIFICATIONS_DEFAULT`
  (an *imported* name, so a scan of the module's own definitions misses it); a test helper reads
  `open_finance.invoices`. Rule: when a module is split, the old module keeps every name others reach through it,
  and a function reading a test-patched name stays where the test patches. Never trust the related tests alone
  for a move: run the whole suite.
- After moving code, pruning unused imports from the **old** module is where those attributes disappear. Check
  each pruned name against the tests before dropping it.
- A full pytest run writes ~3.7 GB of temporary files. Before #91 nothing removed them: 35 runs filled a 250 GB
  disk mid-session. In a cloud session point `TMPDIR` at memory-backed storage (`/dev/shm`) for the run.
- The extraction scripts used (sections by dependency, Flask-free helpers by name) lived in the session's
  scratch directory and are gone; their rules are written in #86, #88 and #92.
