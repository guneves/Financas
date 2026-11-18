# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-18 (2) · Everything automatic, phase 1 (banking review decides itself)

**State of the branches:** `fix/brokerage-guessed-side` was pushed and opened as **PR #99** (the previous
session's fix + `review_breakdown.py` + the automation prompt); **merging it was refused by the permission
classifier** (a merge to `main` deploys), so the owner merges #99. Phase 1 is on `feat/auto-review-phase1`,
branched from it, **committed, not pushed**.

**Done (phase 1 of `docs/automation-prompt.md`):**
- **058 `auto_decisions`**: every automatic decision (kind, target, `detail` with the before, `undone_at`), one
  `applog` line each; `GET /api/review/auto`, `POST /api/review/auto/<id>/undo` (`services/auto_decisions.py`,
  `auto_undo.py`). An undone decision is never taken again on that row. Web: Ajustes › "Decidido sozinho".
- **1.1** Pluggy's tree fills a notice-born row still on the default (`fill_default_category()` in
  `settle_review()`): row stays in review, snapshots refreshed, never with an owner rule / owner category / paid
  installment.
- **1.2** `review_auto_days` (default `REVIEW_AUTO_DAYS_DEFAULT` = 3, 0–30; conftest 0) in
  `GET/PATCH /api/inbox/settings`, run in `record_due()` (`services/review_auto.py`). A Pluggy-fed row waits for a
  Pluggy claim or N + `BANK_WAIT_MAX_DAYS`. Setting on web (Avisos do celular) and APK (Notificações do celular;
  compiled locally, not run on a phone).
- **1.3** The Corretora's one-sided transfer: **defect found** — Pluggy's `one_side_now()` recorded it as a
  receita *on the Corretora* at once (only the notice path refused BROKERAGE). Now it waits
  `TRANSFER_MATCH_DAYS`, then becomes the guessed aporte/resgate (`services/transfer_timeouts.py`), the item keeps
  its snapshot so a late real side moves the guess. The Conta global Pix already recorded at once (nothing to
  build). FX: the last stored PTAX was already used; now flagged (`fx_fallback`).
- **1.4** `services/conflict_resolution.py`, last in the pull: `changed` → bank amount after 7 days (`conflict_at`,
  `conflict_direction` in 058) unless receipt/share/"Aconteceu"/typed amount; `vanished` → only by the orphans'
  balance proof.
- A second defect the fuzz found (seed 4): a notice on one side of a transfer item blocked the other side's
  notice from joining it (`open_finance_item_for_detection()` refused any item with a notice); now per side.
- Tests: `test_automatic_review.py`, `test_nothing_waits.py`, `test_conflicts_resolve.py`, `autoDecisions.test.js`;
  `test_notify_pluggy_identity.py`'s brokerage-wait test now pins the clock (it waits only the window).
  `npm test` green (250), `vite build` OK, APK `compileDebugKotlin` OK. Backend: the first full 4-chunk run had
  only the fuzz seed 4 failing (fixed); after the fixes, the fuzz (200 seeds), identity and the new files are
  green, and chunks 1–2 of a second full run passed, but **chunks 3–4 of that run were killed by the PC running
  low on memory** — rerun them before merging.

**Not done and why:**
- Phases 2 (investments: no `HELD` line) and 3 (watch and prove) — not started; multi-session job by design.
- The APK has no "Decidido sozinho" list; the Conferência has no "Resolvido automaticamente" block (the web list
  in Ajustes shows every decision, conflicts included).
- `changed` conflicts take the bank's amount, never its date (only the amount is stored on the conflict).
- Not deployed, not checked on the real data. **On deploy, 3-day auto-confirm starts at once**: every row in
  Revisar dated ≥ 3 days ago leaves on the first read (the owner keeps the queue at 0, so little).

**Next:** owner merges #99, then push/PR `feat/auto-review-phase1`; after deploy, read
`GET /api/review/auto` on the server for a week. Then phase 2 (start with the custody `EQUITY TRANSFER` and the
`rate` 0 pré titles — verify one against a brokerage note first).

**Lessons:**
- Tests that move time must freeze both `dates.now_source` **and** the module copies `open_finance_world`
  froze (`finance_world.freeze()`); the Pluggy pull reads `invoices.local_today` (pinned to 2026-10-27).
- The fuzz (`test_notify_pluggy_fuzz.py`, 200 seeds) catches arrival-order bugs the hand-written tests miss: run
  it whenever a "wait"/"record" rule changes. A failing seed reproduces with `Run(world, Scenario(seed)...)`.
- A Pluggy-recorded item has no `recorded_snapshot`; `follow_bank_side()` needs one to move a guessed side.

## Previous session — 2026-11-18 · "Fully automatic notifications + Pluggy?" measured on the real data

**State of the branch:** still `fix/brokerage-guessed-side` (previous session's fix: the BTG Investimentos guessed
side follows the real bank side, plus `scripts/review_breakdown.py`), **not pushed/merged**. This session added only
docs. Merge it first: the server image doesn't have `review_breakdown.py` yet (it was run from `/tmp` in the
container and removed after).

**Done (read-only, on the server over SSH, owner's account):**
- Recording is already fully automatic and healthy: `check_identity.py` printed nothing; 0 Pluggy `conflict`s;
  1 undecided inbox item (`DENIED`); Revisar's queue is **0** (the owner keeps it empty); 39 pulls in 48 h (17
  Pluggy timeouts, retried by themselves).
- `review_breakdown.py --days 30` says 742 auto-recorded, 116 corrected, **but that is inflated by the 2026-10-27
  rebuild** (it re-recorded a year of history: the 52 "repasses" and the 26 BB → Inter transfers are 2025–2026-09
  rows). Restricted to rows **dated** in the last 30 days (live flow): 67 rows, 48 not transfers; category right at
  birth 27/48; **21 categories corrected**, 8 shares (repasse/split), 3 transfers.
- Where the 21 wrong categories come from:
  - **Notice-born rows are always "Outros"** (`inbox.suggest_category()`: owner rule → default; the owner has 0
    rules). The owner fixed them before Pluggy confirmed, so `settle_review()` never got the chance. With Pluggy's
    say: merchant table/CNAE would set 3 (2 right, Drogaria → Saúde where the owner chose Alimentação); the Pluggy
    tree (`Groceries`/`Eating out` → Alimentação) would set 5 more, 4 right (Distribuidora → Lazer was the owner's).
    Today a tree category is **never** applied to a notice-born row: `settle_review()` only acts on
    `CONFIDENT_CATEGORY_SOURCES`.
  - **Pix to a person** (6): Pluggy says only "Transfer - PIX"; owner chose Serviços, Doação, Alimentação, Compras.
    No source knows these.
  - **Flash** (Samsung notices, no Pluggy): mixed, 3 Outros → Alimentação, 5 left as Outros (a restaurant
    included): no reliable default.
- Rejected by the data:
  - **Learning a rule from the owner's correction** (key = merchant/description, applied from the next occurrence):
    5 applicable, 2 right, **3 wrong**. Few merchants repeat within a month.
  - **The merchant table at notice birth**: 3 right, 2 wrong over 22 notice-born expenses.
  - **Auto-repasse by person**: the father's Pix was OTHERS ~85% historically, but October was 4 own vs 2 OTHERS.
  - **Inter transfers**: historical only (stopped 2026-09, the `inter:` month rows); nothing live.
- Investments (`open_finance_investment_operations`): 58 `HELD` — MUTUAL_FUND BUY/SELL/TAX 23 (funds not supported),
  EQUITY TRANSFER 14 (custody moves), EQUITY INTEREST 2, `missing:rateType` 6, `missing:buy` 7, `unmapped:*` 6.
  `position_fields.py` (finally run): MeuPluggy fills `rateType`/`rate`/`fixedAnnualRate`/`dueDate` on 26 fixed-income
  positions; **4 CDB positions lack `rateType`** (rate and fixedAnnualRate present). Never-guess stays.
- Side finding, not touched: brapi's plan allows 1 ticker per request; every hour the log asks for
  `BRAPI_MAX_SYMBOLS_PER_REQUEST=1` in the server's `.env` (quotes fall back to yfinance meanwhile). Owner's call.

**Verdict:** "100% automatic" for recording: already true. For review: removing it outright would bake ~40% wrong
categories on notice-born rows into budget and plan. What is applicable is small and safe: let the bank speak
before asking, let Pluggy's category fill a row still on the default, and an opt-in auto-confirm. Prompt below.

**Not done:** no code changed. The owner hasn't decided on auto-confirm (opt-in, default off in the prompt).

**Lessons:**
- Any "last N days" measure over `auto_recorded_at` is polluted by the rebuild; filter by the row's own date.
- SSH works from this PC: `ssh guilherme@guilhermeserver`, `sudo -n docker compose ...` in `/srv/apps/financas`.
  A script not in the image can be piped to `/tmp` in the container (`sh -c 'cat > /tmp/x.py'`) and run with
  `PYTHONPATH=/app/backend`; open SQLite with `mode=ro`, never import `app`/`db`/`services` (import migrates).

### Prompt for the next session

The owner then decided (2026-11-18): **everything automatic, banking and investments**. The prompt is
`docs/automation-prompt.md` (phases: banking review decides itself, no investment line held, watch and prove), built
on a second read-only pass over the held investment operations (custody transfers, `rate` 0 pré titles, BB funds,
Renda+). It replaces the smaller three-step prompt this entry first had (auto-confirm is now **on**, default 3 days).
Not implemented: the owner asked for the prompt only.
