# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-23 · native migration session 6: home, attention and invoice endpoints

Cloud session, branch `claude/mobile-docs-home-attention-invoices-pbo0kq` (from `main` at
`9a4e219`, PR #35 merged: the proposal is approved as merged). Briefing by `session-scout`, found
by `subagent_type`, no fallback.

### Done
- **Backend, proposal §1–4**: `services/card_invoices.py`, `services/home.py`,
  `services/attention.py`, `routes/home.py` (`GET /api/home`, `/api/attention`, `/api/cc-invoices`)
  and `DELETE /api/cc-expenses/purchases/<id>` in `routes/cards.py`. Each read first runs
  `ensure_default_account()`, `apply_due_autopay()` and `apply_paid_proceeds()`.
  `with_balance_in_brl()` moved from `routes/accounts.py` to `services/fx.py`, so a service can
  read it. `month_investment_flow()` now reads `investment_flow_sql()` from `services/home.py`:
  one "Investido" condition for the plan and Início.
- **Tests**: `test_home.py` (30), `test_attention.py` (15), `test_cc_invoices.py` (14),
  `test_cc_purchase_delete.py` (8), and 4 new rows in `test_route_map.py`. They carry every case
  the proposal lists, plus the two `buildMonthlyFlow` cases that lived in `sharing.test.js`. The
  shared setup and the frozen clock are in `tests/finance_world.py`. **pytest 1603 passed**
  (was 1536).
- **Web switched, no visible change**:
  - Início: hero, Resumo do mês, the next-invoice tile, Fluxo de caixa and Evolução do saldo
    read `useHome()`. Its "Precisa de atenção" cards read `useAttentionItems()`.
  - The bell reads `useAttentionItems()`, the same `['atencao']` query as Início.
  - Extrato: "Saldo em contas" is `consolidated_balance`.
  - Cartões: `['cartoes','faturas']`. Delete is one `removePurchase()`; the confirmation counts
    come from `installments_open`/`installments_paid`.
  - `applyPendingToHome()` is in `outboxRules.js` (6 node cases) and `rules/OutboxPending.kt`
    (6 JVM tests, same order).
- **Removed**:
  - `cashFlow.js` (its `isInvoicePayment` moved to `transactions.js`, with a test).
  - `consolidatedBalance` and `openingBalanceTotal`.
  - The rule half of `attentionRules.js`. Kept: dismissals, `overdueDetail`, and `isPastDue`/`invoiceMonthKey` for Início's projection panel.
  - **npm test 160** (was 164: 13 cases moved to pytest — 11 of `attentionRules.test.js`, 2 of `sharing.test.js` — and 9 added; `transactions.test.js` lost only the `consolidatedBalance`/`openingBalanceTotal` asserts).
- **Parity**: a throwaway database was seeded through the API (scratch script, not committed) and
  captured with Chromium at 1440 and 390 px, before and after:
  - The text of Início, the bell, Extrato and Cartões was **identical** on all eight captures.
  - Six PNGs were pixel-identical. Two differed in about 110 anti-aliased pixels, at most 2/255.
  - The Cartões delete was clicked through once: one `DELETE …/purchases/<id>`, row gone, totals refreshed.
- Docs: `rules-port.md` (the three modules are "endpoint, done"), the proposal's Status row,
  CLAUDE.md (the conventions that named removed functions, test counts, layout, layering),
  next-steps, done-tasks.

### Not done, and why
- **Paging (§5)** was not built. The proposal's *Order of implementation* puts it with the native
  Extrato, and says no endpoint should exist without a reader.
- **Início still downloads the whole history** for its other panels: "Despesas por categoria",
  "Ritmo de gastos", "Parcelamentos abertos" and the invoice projection. The Extrato's
  projections still read `GET /api/cc-expenses?status=OPEN`. All of this is the proposal's *Beyond
  the brief* (`home-panels.md`, not written). The list under "Próximas faturas" filters those rows
  by `/api/home`'s `next_invoices`, so its order is the old one.
- **The parity check ran on seeded data, not the owner's**: `backend/finance.db` was not touched,
  and the server's data is not reachable from here. It is a next-steps item for the owner.
- No native-level bump: no screen calls `applyPendingToHome()` yet.
- Carried, still open:
  - B2 (below).
  - The owner's phone check of native steps 1–2.
  - Native 401 handling.
  - Grouped Tesouro delete is not atomic.
  - The web `createEntry()` duplicate after a killed tab.
  - The sharing form refusing "12,5".
  - pytest red 21:00–midnight local (`test_fixed_income_interest.py`).
  - `done-tasks.md` still has no row for the Aprovar session (PR #33).

### Decisions made here (worth checking)
- **`applyPendingToHome()` covers every month of `flow`**, not only the current one. A pending
  item changes the month of its date, and the balance from that month on. That is exactly what
  `buildMonthlyFlow()` did over pending rows (B1, "keep today's behaviour"). For a pending item of
  the current month it is what §1 says. This is recorded in the proposal's Status row.
- **The invoice-payment prefix is compared case-sensitively** (`substr`), like the client's
  `startsWith`. `month_banking_totals()` uses `LIKE`, which ignores case. The two differ only for a
  typed "pagamento fatura…", which counts as a despesa on Início. That is unchanged from before.
- **The overdue invoices' order follows the rows' order** (invoice, then `created_at`) before the
  stable sort by due date, as the client's did. Two invoices due the same day keep the old order.

### Questions for the owner
0. **B2**: should the plan's "spent" leave out a despesa typed in a Corretora account, as Início's
   "Saiu" does (one rule)? It overlaps question 1.

Carried from session 4 (the Inconsistencies in `findings.md`):
1. Corretora accounts in "+ Novo", the pay-invoice sheet and autopay?
2. Should the Extrato show a transfer to the Corretora as aporte/resgate, as Início does?
3. A débito purchase in Pendentes: Corrigir reopens it as Despesa. Should it?
4. Installments 48 (client) vs 72 (server); description required or optional?
5. "Despesas por categoria" on Início groups by name: should it group by id? This also matters
   for `home-panels.md`.
6. Privacy mode across the other screens?
7. A bank field on cards?
8. `/api/credit-cards` cached under two keys. This is partly gone: Início no longer reads
   `['inicio','cartoes']`.

### Next session
1. Check this PR's `android-check.yml` run (see below).
2. If the owner answers B2, apply it (a one-line change in `month_banking_totals()` plus a test).
3. Otherwise write `home-panels.md` (categories, pace, installments, invoice projection, the
   Extrato's projections), so Início stops downloading the history. Or move to the native Início:
   `/api/home` + `/api/attention` + `applyPendingToHome()`, after an `OutboxStore` → typed-items
   adapter.

### Learned
- **`pkill -f <pattern>` inside a Bash call kills that call's own shell** when the pattern is part
  of the command line (exit 144). Keep server PIDs in a file and `kill $(cat pid)`.
- **Freezing `local_today()` needs six modules**: `services.invoices`, `routes.cards`,
  `services.card_invoices`, `services.home`, `services.attention` and `routes.home`.
  `tests/finance_world.py::freeze()` patches all six. `apply_paid_proceeds()` reads
  `invoices.local_today`.
- **A card's `autopay_start_date` is the creation day** (`local_today()` in `routes/cards.py`).
  Autopay only pays invoices due on or after it, so a test that wants autopay creates the card
  earlier on the clock.
- `apply_paid_proceeds()` deletes any `INVESTMENT_PROCEED` row without a paid provento behind it.
  A test needs a real provento: buy, POST the provento, then move the account out of Corretora.
- `GET /api/recurring` and `/run` use the real `datetime.now()`. Recurrence tests in
  `test_attention.py` therefore freeze the clock at `date.today()` (± days), not at a fixed date.
