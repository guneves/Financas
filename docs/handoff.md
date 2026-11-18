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

The owner then decided (2026-11-18): **everything automatic, banking and investments**. The prompt is
`docs/automation-prompt.md` (phases: banking review decides itself, no investment line held, watch and prove), built
on a second read-only pass over the held investment operations (custody transfers, `rate` 0 pré titles, BB funds,
Renda+). It replaces the smaller three-step prompt this entry first had (auto-confirm is now **on**, default 3 days).
Not implemented: the owner asked for the prompt only.
