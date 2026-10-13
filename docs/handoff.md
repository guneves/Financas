# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-12 · Investments separate from banking: planned, then built

Two parts on the same day. First an investigation run that ended in a plan
(`docs/areas-separation.md`, commit `57ee057`). Then the owner said to build it, with two changes to
the plan: **Início shows only the banking balance** ("so the user does not get the false sense they
have more money to spend" — this reverses the plan's decision 2), and **the database may be wiped**
instead of migrated. No `session-scout` (the documents were fresh in context). `finance-guard` ran
three times: twice on the cash-link diff (the first pass found one real gap, below; the second
audited the fix) and once on the reais-only edits (one finding, fixed).

### What was done
- **Backend — the link is opt-in.** A movement writes a lançamento only when
  `metadata.cash_account_id` names one of the user's active BRL accounts
  (`investment_cash_account_id()`, `resolve_investment_cash_account()` in
  `services/investments.py`; validation in `POST`/`PATCH /api/investments`). `skip_cash` and the
  silent default-account link are gone. Detail in `docs/done-tasks.md`.
- **The audit's finding, fixed.** An edit that zeroed an operation's cash amount (price 0, or costs
  above the sale) made the sync delete the linked lançamento and its receipt without passing the
  unlink guard. Now `sync_investment_cash_transaction()` returns whether a row is in place, and
  `POST`/`PATCH` refuse (400, everything rolled back) a movement that asks for the Extrato with
  nothing to write.
- **Forms.** `components/CashLinkField.jsx` ("Lançar no extrato", off by default) in "Registrar
  operação", the Operações edit sheet and the Posição redemption sheet; Operações tags linked
  movements "no extrato".
- **Banking read side.** Início's hero is "Saldo em conta" (no portfolio, no Patrimônio); a resgate
  is not a receita on Início, Extrato and Recorrentes; "+ Novo" is banking-only and opens
  "Registrar operação" inside Investimentos.
- **Reais-only on screen.** After two corrections from the owner ("The app is in brazilian reais",
  "Everything on the app should be reais"): no form offers a currency, every account balance on
  screen is the converted one (`accountBalanceBrl()`), and the foreign-currency notes and export
  column are gone. The IR tab's exterior panel and export row now appear only when the year has a
  foreign result: my first version removed them outright and `finance-guard` pointed out that a
  foreign sale's 15% estimate would then be shown nowhere. Detail in `docs/done-tasks.md`.
- **Database reset.** `backend/finance.db` was moved (not deleted) to
  `backend/backups/finance-pre-areas-separation-20261012-224633.db` and verified there. The next boot
  builds an empty database from the migrations and the owner signs up again — a boot with no
  database file was rehearsed on a scratch path (23 migrations, boot backup, signup, a plain and a
  linked buy).
- **Documents.** `docs/areas-separation.md` deleted (built); its lasting rules are two conventions
  in `CLAUDE.md`; what is left is the first item of `docs/next-steps.md`.
- Built by three subagents in parallel on disjoint files (backend, forms, banking screens), at the
  owner's request; integration, verification and commits were done in the main session.
- Commits: `785df81` (backend and tests), `35fd789` (forms), `88411f3` (banking screens and
  documents), `6589e78` (Início in reais), and the one that carries this handoff (reais-only).
- An untracked `mobile-docs/` folder appeared in the tree during the session. It is not this
  session's work and was left untouched and unstaged.

### What was not done and why
- **Migration 024 and the bulk "Desvincular do extrato" tool** — both existed only to carry the old
  linked rows across. The owner chose a reset instead. Consequence: the old backup cannot simply be
  restored into this code (see `next-steps.md`).
- **`NET_WORTH` goals still add accounts and portfolio.** The owner's instruction was about Início;
  Metas was left alone and is listed as the owner's call.
- **The "no mês" pill changed meaning** (accounts' net movement instead of receitas − despesas).
  A judgement call that follows from the banking-only hero; listed for the owner to confirm.
- Deleting a movement (or its asset) still deletes its linked lançamento and that row's receipts,
  unguarded, as before.
- The owner has not seen any of it: everything was checked on a scratch database.
- **The backend's multi-currency machinery (018) was left in place**, tested and reachable only
  through the API. Taking it out is a refactor of the stream FIFO and IR read, with no visible
  change; it is the owner's call in `next-steps.md`.
- Low, from the second audit — correct in its scratch tests but not pinned by the suite: a refused
  edit also undoes the price quote and the quantity; the redemption branch of the "nothing to
  write" refusal; a refused second item of a batch `POST` undoing the first.
- From the earlier session today (Ritmo de gastos, commit `550649e`), still open: "Despesas por
  categoria" still compares with last month's whole total; no automated test (the frontend has no
  runner).
- Carried from before, still open: restart the backend and search LEVE3/FESA4; owner check of the
  fixed-income form (a CDB saved with a manual "Isento" tick loses it on the next edit —
  deliberate); two findings needing the owner (budgets on income categories; positions whose
  running applied value goes ≤ 0); owner checks of benchmarks/sectors/IRPF text; the brapi
  1-ticker limit; two IRPF codes; the owner walk-through, decisions 3 and 4.

### Next session
The owner walk-through on the fresh database (first item of `docs/next-steps.md`), then the three
owner's-call items there. Nothing is half-built.

### Learned
- **In a route, `return` inside `with get_db() as conn:` commits.** To refuse after a write, call
  `conn.rollback()` first (the PATCH does) or raise so the `with` exits by exception (the POST
  does).
- **Removing a display is not neutral when it is the only place a number is shown.** Check where
  else a figure surfaces before deleting its panel; prefer "show only when non-zero".
- **`pytest.ini` already passes `-q`.** Adding another `-q` hides the summary line; the exit code
  and the dots are then the only signal. Run plain `python -m pytest`.
- **A Playwright full-page screenshot shows Início's charts empty** (only the dots of the
  "Resultado" line). The bars and lines are there — measured in the DOM, and an element screenshot
  of the chart shows them. Screenshot the chart element, not the page.
- **The "⋯" `Menu` closes on scroll**, and Playwright's click scrolls the button into view first.
  Scroll the button into view, wait, then click; click the menu item through `evaluate`.
- On desktop the first DOM match for a ticker in Operações is the hidden mobile card: use
  `text=… >> visible=true`.
- Posição keeps fixed income behind the "Renda fixa" switch of the table.
- Git Bash rewrites an argument that starts with `/` (`/investimentos/…` became a Windows path):
  set `MSYS_NO_PATHCONV=1`.
- `scripts/seed_three_years_mock.py` writes its "pre-mock" copy to `backend/backups` whatever
  `DATABASE_PATH` says; to try it on a scratch database, import it and point `BACKEND_DIR`
  elsewhere before calling `main()`.
- Six test files read linked rows; they now send `cash_account_id` explicitly. A new test asserting
  "nothing changed" must link first and assert the row exists, or it passes on two empty lists.
- Files in this tree have mixed line endings (most CRLF, some LF). The Edit and Write tools write
  LF: patch through a Python script that keeps the file's own ending, and count `\r\n` afterwards.
- **The owner reads every number as reais.** A dollar account's tile on Início showed its US$
  amount labelled R$; I "fixed" it by printing US$ and was corrected twice. The right fix was the
  converted balance — and then no foreign currency anywhere. When a multi-currency display looks
  wrong, convert to reais; do not surface the other currency.
- The scratch seed's dollar account is still the way to test that: create it through the API
  (`"currency": "USD"`), since no screen can.
- To look at `finance.db` without touching it: `sqlite3.connect("file:<path>?mode=ro", uri=True)`.
- The Grep tool returns nothing, silently, for a brace glob with a slash in it
  (`{services,routes}/*.py`); use `**/{services,routes}/*.py`.
- Playwright's cached package wants `chromium_headless_shell-1234` but the installed build is
  `-1243` — pass `executablePath` to `chromium.launch()`.
