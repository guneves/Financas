# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-18 · "Fully automatic notifications + Pluggy?" measured on the real data

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

> Read CLAUDE.md, `docs/handoff.md` (2026-11-18) and `docs/next-steps.md`. First merge `fix/brokerage-guessed-side`
> if it isn't merged. Then, on a new branch, make Revisar ask only what no source can answer. Measured on real
> data (handoff): notice-born expenses are born "Outros" and the owner fixes them before Pluggy confirms; Pluggy's
> category would have been right in most of those cases. Tests first for each rule (`test_quiet_review.py` is the
> home; `any_bank_notifications` opens the gate), then the code:
>
> 1. **Pluggy's category fills a row still on the default.** In `open_finance_inbox.settle_review()` (and the
>    untouched path of `reconcile_recorded()` that calls it): when the row is untouched by the snapshot and its
>    category is still the one it was born with **and** that was the default (`suggest_category()` without a rule),
>    set `category_decision()`'s category whatever the origin except `default`; refresh the snapshots
>    (`refresh_snapshots()`) so it doesn't count as the owner's touch. Leave review only for
>    `CONFIDENT_CATEGORY_SOURCES` (unchanged); a `pluggy`-tree category stays in review, pre-filled. Never on a
>    transfer, refund, the Conta global, or a row with a paid installment. Cases: Groceries → Alimentação on an
>    untouched BTG black notice row; the same row recategorised by the owner keeps theirs; an owner rule on the
>    notice keeps the rule.
> 2. **Revisar waits for the bank.** A notice-born row on a Pluggy-mapped account/card (`bank_fed_account_ids()` /
>    the card mapping) with no Pluggy observation yet is left out of `review.queue()`/`count()` (and so the badge,
>    header pill, `GET /api/home` `review_count`) until Pluggy claims it or the connection refreshed past it
>    (`awaiting_bank()` / `bank_refreshed_since()`, `BANK_WAIT_MAX_DAYS`). Flash, the Conta global and unmapped
>    targets show at once (no bank will speak). `needs_review` itself stays 1; only the listing waits. Mark the
>    rows `awaiting_bank` in `GET /api/review` if the screen needs it; APK `ReviewSection` reads the same endpoint.
> 3. **Optional auto-confirm (owner's switch, default off).** `review_auto_days` in `user_settings`
>    (`GET/PATCH /api/inbox/settings`, int 0 = off, else 3–30): a row with `needs_review = 1` whose date is older
>    than N days and untouched by the snapshot gets `needs_review = 0` with its current category, run in
>    `record_due()`. A toggle in Ajustes › Avisos do celular (web) and Notificações do celular (APK). Confirm with
>    the owner before shipping the default.
>
> Don't: learn import rules from corrections, apply the merchant table at notice birth, or auto-mark repasses by
> person — the data rejected all three (handoff). Update CLAUDE.md's "Only guesses are reviewed" paragraph, add a
> line to `scripts/review_breakdown.py` if a new reason bucket appears, run the backend suite in 4 chunks and
> `npm test`, then the session-end process. After the deploy, re-run `review_breakdown.py --days 30` filtered by
> row date (see the lesson) to compare.
