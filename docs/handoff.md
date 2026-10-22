# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (later) · Bug hunt by fuzzing

Cloud session, owner request: "make a bug run hunt, fix the bugs as you find them", then "create a
PR when done". No briefing subagent: the handoff and the last commit were read directly.

### Done
- **Fuzzed the API** with two throwaway pytest files (not committed; method in `done-tasks.md`):
  junk values for every key each blueprint reads, then a valid payload per write route with one
  field broken at a time. Last run: 3,784 requests, zero 500s. Fixed, each with a test in
  `tests/test_input_edges.py` (41):
  - a JSON body that is a list/text/number → `parse_json_body()` returns `{}` (`allow_list=True`
    for the two routes that take a list: the old `POST /api/cc-expenses` and `POST /api/investments`);
  - **dates stored that broke later reads**: a refund in 9999 put its invoice in year 10000 and
    every Cartões read answered 500; now dates/months are 1900–2199 (`MIN_YEAR`/`MAX_YEAR`); the
    proceeds' `repeat` and Aprovar's date-only field check the range too;
  - **money**: `rounded_money()` turned ≥ 1e26 into 0.0 (Decimal precision); 0.004 passed "> 0"
    and was saved as R$ 0,00 (or hit the recurrences' `CHECK amount > 0`: 500). New
    `parse_money()` in `money.py` (≥ R$ 0,01 after rounding, ≤ R$ 1 trilhão) on every typed amount:
    lançamento, transfer, card purchase/refund/old list, recurrence, import commit, Aprovar edit,
    sharing, goals, the monthly plan's income and the initial balance (negative allowed);
  - **investments**: a quantity or price of 1e308 gave a NaN realized result and from then on
    *every* operação of the owner failed (NOT NULL); a `metadata` date like "0999-01-01" was stored
    as "999-01-01" and broke the IR report, and a non-date silently became today. Now
    `validate_movement_metadata()` (dates in range, numbers finite and ≤ 1e12) and the same cap on
    quantity/prices in POST/PATCH and the manual price;
  - `credit_enabled` / `fixed_income_type` / `indexer` as a list or object (unhashable → 500), the
    invoice year of `pay-invoice` unbounded (overflow), and a purchase with fewer cents than
    installments (a R$ 0,00 installment) → 400.
- Checks: pytest 1534 green; `npm test` 144 green (no frontend change).

### Not done, and why
- Rows already stored with such values are not cleaned (none expected in production; the fixes
  only refuse new ones). `next-steps.md`, "Bug hunt by fuzzing".
- Not fuzzed: the frontend (no test runner), the Java parsers/listener, CSV/OFX contents, uploads.
- Proceeds' amounts and corporate-action ratios still have no upper bound (nothing broke).
- Carried from the previous session, all still open in `next-steps.md`: the owner walk-through of
  card débito / Flash; no Flash capture (no benefit-credit detection, package `br.com.flashapp`
  unconfirmed); a débito purchase does not record its card; brapi quota with hourly quotes; the
  server/phone timing of saves, static files uncompressed, Rentabilidade's daily loop, the Planejar
  owner check.

### Learned
- With `TESTING = True` Flask re-raises; to see 500s as responses in a scratch test set
  `PROPAGATE_EXCEPTIONS = False` and `TESTING = False` (monkeypatch `app.config`) and hook
  `flask.got_request_exception` for the traceback.
- `/api/health/integrations`, returns and evolution take ~1.5 s each with no network (gov_http's
  retry): a fuzz over them is slow, not hung.
- `pkill -f <pattern>` matches the shell running it when the pattern is in its own command line.
- Linux `strftime("%Y")` does not zero-pad years < 1000, and Decimal's default context (28 digits)
  cannot quantize ≥ 1e26 to cents — both are now guarded, but remember them for new code.
- The test DB is one per session: assert on your own user's rows (carried).
- Never name a backend module after a stdlib one (carried).
