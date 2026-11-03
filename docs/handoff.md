# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-02 · A receber deducts from income

Owner asked: money received for an A receber item must leave income (uncle paid R$ 300 for a R$ 230,28 headset; only
R$ 69,72 is income), editable afterwards, in the web and the APK.

**Why it didn't work in production:** the mark-day cut (`apply_settled_others()`) existed, but Pai's October repasses
carried over as "spare" and covered the uncle's November item, so November income stayed R$ 300 with nothing cut.

Done (tests: `test_receivable_income.py`, `sharing.test.js`, `ReceivablesTest.kt`; full backend suite green):
- Migration 053 `share_paid_by` on `transactions`/`cc_expenses`. `POST /api/receivables/settle` takes `income_id`;
  `link_income()` makes that income `SPLIT`/`OTHERS` with the linked share, in the Pix's month; undo or change gives it back.
  `GET /api/receivables/incomes?since=` lists candidates (reais incomes from 7 days before, with `room`).
- Fallback (no income chosen, old APKs): the mark-day cut, now covered only by a repasse of the **same person** (or unnamed).
- Web `PaidBySheet.jsx`: "Pago"/"Tudo pago" open it, suggestion preselected; a paid item's menu "Trocar a entrada".
- APK: same sheet in `AReceberScreen.kt`; tapping a paid item changes the income. Compiled + JVM tests, not run on a device.

**Fix after merge (2026-11-03, PR 61 follow-up):** the migration was first numbered 052, the same number as
`052_open_finance_pending_on.sql` merged just before. `init_db()` keys migrations by number, so it skipped the second one
silently and the deploy of PR 61 failed on main (150 tests: `no such column: share_paid_by`); PR 61's own CI was green
because its branch didn't have the other 052 yet. Renamed to `053_share_paid_by.sql` (production never applied it) and
added `test_migration_numbers.py` (no repeated number; every file on disk is in `schema_migrations`).
**Lesson:** pick the migration number after merging main, and rerun the suite on the merged tree.

**Not done:** before the deploy it was checked on a local scratch app only; production check after merge. The uncle's item is
already marked (mark-day fallback): after deploy November income should read R$ 69,72; choosing the Pix moves it there
explicitly.

Lessons: the person on a receivable ("Venda Tio Toninho") rarely matches the Pix text ("A. F. R. Corretora de Seguros"),
so auto-linking by name is unreliable; the owner picks, the app suggests by date and amount.
