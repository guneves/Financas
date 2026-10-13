# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-12 · Plan: investments area separate from the banking area

The owner asked to investigate making the investments area and the expenses (banking) area
separate, with the option of creating the lançamento in the banking area when they want it. This
was an investigation run: a plan was presented, the owner approved it, and the documents were
written. **No code changed.** No `session-scout` (the documents were read directly, since this
session rewrites them). No `finance-guard`: there is no backend diff to audit.

### What was done
- Investigation of the coupling. It is one function — `sync_investment_cash_transaction()` in
  `backend/services/investments.py`, called after `POST` and `PATCH /api/investments` — and no
  financial calculation reads the linked rows (FIFO, IR, portfolio, TWR and aportes read
  movements).
- `docs/areas-separation.md`: the design. The rule is that an operation touches the banking area
  only when the owner asks for it, through `metadata.cash_account_id` on the movement (replacing
  `skip_cash`); three phases with files, tests, a migration sketch, what gets removed and the traps.
- The owner's four decisions (all in the design doc): rows already linked stay linked and are
  unlinked in bulk from a preview; Início keeps Patrimônio = contas + carteira; "+ Novo" becomes
  banking-only; this run stops at documents.
- `docs/next-steps.md`: the three phases are the first open item. The "Operação anterior ao app —
  leftovers" section was removed — the plan supersedes all three of its items.
- `CLAUDE.md`: one line in the layout listing. Its conventions still describe the code as it is
  (`skip_cash`, the automatic link); they change with phase 1.

### What was not done and why
- Nothing is built: phases 1–3 are open, by the owner's decision 4.
- The migration 024 SQL in the design doc is a sketch — never run. Phase 1's migration test is what
  proves it.
- The frontend findings come from reading the code, not from running the app.
- Not decided, listed in `next-steps.md`: the same opt-in for proventos, moving Metas to
  Investimentos, remembering the checkbox's last choice.
- From the earlier session today (Ritmo de gastos, commit `550649e`), still open: the panel was not
  seen on the owner's real data; "Despesas por categoria" still compares with last month's whole
  total; no automated test (the frontend has no runner).
- Carried from before, still open: restart the backend and search LEVE3/FESA4; owner check of the
  fixed-income form (a CDB saved with a manual "Isento" tick loses it on the next edit —
  deliberate); two findings needing the owner (budgets on income categories; positions whose
  running applied value goes ≤ 0); owner checks of benchmarks/sectors/IRPF text; the brapi
  1-ticker limit; two IRPF codes; the owner walk-through, decisions 3 and 4.
- Dropped from the carry-over: the `skip_cash` box on the Posição redemption form (it is phase 2
  now) and the note about `docs/negociacao-…pdf` (the file is no longer in `docs/`).

### Next session
Phase 1 of `docs/areas-separation.md` — backend only: the opt-in link, migration 024, the tests.
Read the design doc's "Risks and traps" first. Run `finance-guard` before committing: the new
account id must be checked against `user_id`.

### Learned
- Six test files read linked rows (listed in the design doc). All of them index into the row or
  compare it with a concrete value, so they fail loudly when the default flips — fix them by
  sending the key, not by loosening the assertion. A *new* test asserting "linked rows did not
  change" is the one that can pass on two empty lists.
- The Edit tool rewrote `docs/done-tasks.md` and `CLAUDE.md` with LF endings (the docs are CRLF;
  `next-steps.md` kept its own). Count `\r\n` in bytes after editing and normalise in Python.
- A linked sale or redemption is an INCOME row and Início and Extrato count it as Receita. Nobody
  saw it because the local database holds no sale. Phase 3 fixes it.
- Local `backend/finance.db`, read-only counts: two users — one with 36 buys, all linked, all in
  the default account (36 of its 49 Extrato rows); the other with 12 operations, every one flagged
  `skip_cash`, and no lançamento. So migration 024 has real rows of both kinds to convert.
- To look at `finance.db` without touching it: `sqlite3.connect("file:<path>?mode=ro", uri=True)`
  from the venv's Python. Counts only; the app was never started against it.
- The Grep tool returns nothing, silently, for a brace glob with a slash in it
  (`{services,routes}/*.py`); use `**/{services,routes}/*.py`.
- From the earlier session today: Playwright's cached package wants
  `chromium_headless_shell-1234` but the installed build is `-1243` — pass `executablePath` to
  `chromium.launch()`. A Bash heredoc holding JSX with quotes and backticks breaks; write the edit
  script with Write. `sed -i` on a CRLF file turns it LF — patch in Python with bytes.
