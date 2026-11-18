# Prompt — everything automatic (banking and investments)

> Owner's decision, 2026-11-18: "quero que tudo seja automático, tanto investimentos como banking".
> Measured on the server's real data the same day (read-only; numbers in `docs/handoff.md`). Paste the block below
> into a fresh session. It is a multi-session job: do the phases in order, one PR per phase, and keep this file's
> checklist current (move a finished phase to `docs/done-tasks.md`).

## Progress (kept current by each session)

**Deploy only at the end** (owner, 2026-11-18: "irei fazer o deploy apenas quando tudo estiver pronto"). A merge
to `main` deploys, so nothing of this job is merged until all three phases are done. Each phase is a branch
stacked on the previous one; at the end the owner merges them in order (#99 → phase 1 → phase 2 → phase 3) and
deploys once.

| Branch | What | State |
|---|---|---|
| `fix/brokerage-guessed-side` | BTG Investimentos guess follows the real bank side, `scripts/review_breakdown.py`, this prompt | pushed, **PR #99 open**, not merged |
| `feat/auto-review-phase1` | Phase 1, commit `11b8eb8` (branched from #99) | local only, not pushed |
| phase 2 | branch from `feat/auto-review-phase1` (needs `auto_decisions`, 058) | not started |
| phase 3 | branch from phase 2 | not started |

**Phase 1 — done** (details in its status note below and in `docs/handoff.md`):
- 058 `auto_decisions` + `GET /api/review/auto`, `POST /api/review/auto/<id>/undo`; web Ajustes › "Decidido sozinho".
- 1.1 Pluggy's tree fills a notice-born row still on the default (`fill_default_category()`).
- 1.2 `review_auto_days` (default 3, 0 = off), web and APK setting (`services/review_auto.py`).
- 1.3 the Corretora's one-sided transfer waits `TRANSFER_MATCH_DAYS`, then a guessed aporte/resgate
  (`services/transfer_timeouts.py`); `fx_fallback` flagged.
- 1.4 `services/conflict_resolution.py`: `changed` after 7 days, `vanished` by the balance proof.
- Two real defects fixed: Pluggy recorded the Corretora's one side as a receita on the Corretora; a notice on one
  side of a transfer item blocked the other side's notice (fuzz seed 4).
- Tests: `npm test` 250 green, `vite build` OK, APK `compileDebugKotlin` OK (not run on a phone). Backend: new
  files, fuzz (200 seeds) and identity green; full run chunks 1–2 green, **chunks 3–4 still to rerun** (killed by
  low memory). The 4 failures that killed run printed in chunk 2 (the subprocess script tests:
  `test_the_identity_script_reads_without_migrating`, `test_it_prints_keys_never_values`,
  `test_the_script_alone_migrates_and_starts_no_thread`, `test_the_brake_is_off_by_default`) pass when run alone.
- Left from phase 1 (fold into phase 3): APK "Decidido sozinho" list; Conferência "Resolvido automaticamente";
  a `changed` conflict takes the bank's amount, not its date.
- **At the final deploy**: auto-confirm (3 days) starts at once — every Revisar row dated ≥ 3 days ago leaves on
  the first read.

**Phase 2 — corrections found while preparing it (read before the table below):**
- `AMORTIZATION` is already a provento type (`proceeds.ALLOWED_PROCEEDS_TYPES`): record the CRA amortization as
  `AMORTIZATION`, not `INTEREST` + metadata.
- `open_finance_investment_operations.state` has a CHECK (`RECORDED`, `LINKED`, `HELD`, `DISMISSED`, 044); a new
  `COVERED` state means rebuilding the table. Prefer `DISMISSED` + `held_reason = 'auto:custody'` (`apply()`
  never re-decides a `DISMISSED` line) and an `auto_decisions` row whose undo puts it back to `HELD`.
- Provisional buys are already dropped when the real operation arrives (`_drop_provisional()` in `decide()`):
  only check on the server that none is left.
- There is no fund asset class (`ALLOWED_ASSET_CLASSES` = STOCKS, FIXED_INCOME, REIT, OTHER).
- Renda+ is known to `tesouro_client` by name (`RENDA_MAIS`, `NAMED_BY_CONVERSION`); find why the real position
  still fails `unmapped:name` before mapping by ISIN.

---

Read CLAUDE.md, `docs/handoff.md` (2026-11-18), `docs/next-steps.md` and this file. If `fix/brokerage-guessed-side`
is not merged, merge it first (it carries `scripts/review_breakdown.py`).

**Goal:** the owner touches nothing for the app to be right. Notifications and Pluggy record; what the app used to
ask, it now decides by a written rule, and every automatic decision stays visible and undoable (never silent data
loss). Tests first for every rule (CLAUDE.md: "Add tests for every financial rule you touch"); identity tests
(`assert_identity()`) must stay green; run the backend suite in 4 chunks and `npm test`.

**What the data showed (2026-11-18):** recording is already automatic and clean (`check_identity.py` empty, 0
conflicts, queue 0). Last 30 days of live rows: 21 of 48 categories corrected by the owner — notice-born rows are
always "Outros" and the owner fixes them before Pluggy speaks; Pix to a person carries no category. 58 investment
operations are `HELD`. Learning rules from corrections, the merchant table at notice birth and auto-repasse by
person were **tested against the data and rejected** — don't build them.

## Phase 1 — Banking: review decides itself

> **Status 2026-11-18: built** on `feat/auto-review-phase1` (not merged; see `docs/handoff.md`). What differs
> from the text below: 1.2 auto-confirms an edited row too (the edit was the owner's decision; leaving it would
> keep it in Revisar forever); 1.3's Conta global case already recorded the reais side at once (nothing to
> build); 1.3's PTAX already fell back to the last stored rate, so only the flag (`fx_fallback`) was added;
> 1.4's `changed` takes the bank's amount but not its date (the conflict stores only the amount). The
> decisions live in `auto_decisions` (058), shown in web Ajustes › "Decidido sozinho" (not the Conferência,
> not the APK yet).

1. **Pluggy's category fills a row still on the default.** `open_finance_inbox.settle_review()` (and the untouched
   path of `reconcile_recorded()`): row untouched by the snapshot, category still the born one and that one was the
   default (`suggest_category()` without a rule) → set `category_decision()`'s category for any origin except
   `default`; `refresh_snapshots()` so it isn't the owner's touch. Never a transfer, refund, the Conta global, a row
   with a paid installment. Cases: Groceries → Alimentação on an untouched BTG black notice row; recategorised by
   the owner keeps theirs; an owner rule keeps the rule.
2. **Auto-confirm.** `review_auto_days` in `user_settings` (`GET/PATCH /api/inbox/settings`; **default 3**, 0 =
   off, max 30), run in `record_due()`: a `needs_review = 1` row older than N days (by its date) and untouched by the
   snapshot gets `needs_review = 0` with its current category. Before N days, a row on a Pluggy-mapped target waits
   for the bank (`awaiting_bank()` / `bank_refreshed_since()`, `BANK_WAIT_MAX_DAYS`) so phase 1.1 can fill it first.
   Revisar keeps listing what is still inside the window (the owner *may* act, never *must*). Toggle in Ajustes ›
   Avisos do celular (web) and Notificações do celular (APK).
3. **Nothing waits forever.** Today these still wait for the owner:
   - a one-sided transfer touching **the Corretora** (`hold_reason()` → `awaiting_transfer`): after
     `TRANSFER_MATCH_DAYS` with no other side, record it as the aporte/resgate the side implies (bank ↔ Corretora
     transfer with the guessed side marked in `guessed`, so a late side still moves it, `move_guessed_side()`);
   - a Pix to/from the Conta global without the dollar side: after the same hold, record the reais side as a
     despesa/receita in review (the dollar credit, when it comes, absorbs it as today, `_absorb_recorded_real_side()`);
   - a foreign-currency notice without a PTAX: use the latest PTAX ≤ the day (`services/fx`), flag it in
     `metadata.fx_fallback`.
   Each with tests in both arrival orders.
4. **Conflicts resolve themselves.** A Pluggy `conflict = 'changed'` (bank changed a row the owner edited): after 7
   days, the bank's amount/date win unless the row has a receipt, a share or a typed amount (≠ snapshot, the owner's
   explicit value); `conflict = 'vanished'`: removed through `apply_vanish()` after the orphan rule's balance check
   (`open_finance_orphans.py`), never without it. Log every automatic resolution (`applog`) and list them in the
   Conferência under "Resolvido automaticamente" with "Desfazer".

## Phase 2 — Investments: no `HELD` line waits for the owner

Real `HELD` lines (2026-11-18) and the rule for each:

| Held | Count | Real shape | Rule to build |
|---|---|---|---|
| `type` EQUITY TRANSFER | 14 | 2026-09-29, quantity 0, amount = market value (BBAS3, ITSA4, VALE3, AUPO11, …) | Custody record: the app already holds these (typed history since 2023). When the app's quantity on that date ≥ Pluggy's position quantity, mark `COVERED` (new state or `DISMISSED` with reason `custody`). Otherwise keep held. |
| `type` EQUITY INTEREST | 2 | ITSA4 R$ 8,92, KLBN4 R$ 17,05 | Link to the provento `proceeds_sync` computed (same asset, payment date ±3 days, same cents or ≤ R$ 0,05): `LINKED` + `proceed_id`; none → record as a provento (`INVESTMENT_PROCEED` path). |
| `missing:rateType` FIXED_INCOME BUY | 6 | `rateType` None, **`rate` 0**, `fixedAnnualRate` 11,7–16,9, `ratePeriodicity` DAILY, `dueDate` present (LCI, CDBs C6/Original, CRAs BTG) | `rateType` None + `rate` 0 + `fixedAnnualRate` > 0 → **pré** at that rate (`title_terms()`). It is a deduction from the data, not a guess: no indexer has a 0 % share. Verify one title against the owner's brokerage note before shipping; keep `CDI_PERCENT_RANGE`/`ANNUAL_PERCENT_RANGE`. |
| `unmapped:type` FIXED_INCOME TRANSFER | 4 | 2026-04-01, LCA Original / LCIs BRB, unit price and `net_amount` (original cost) | Custody transfer-in from another broker: a BUY at `net_amount` (cost) with `metadata.custody_transfer`, no cash (`cash_account_id: null`), dated the transfer. Unlocks the 5 `missing:buy` SELLs of the same Pluggy investment. |
| `missing:buy` FIXED_INCOME SELL/INTEREST | 7 | sells of those LCI/LCA; CRA coupons | Re-decided each pull: fill themselves once the two rows above record. Test the cascade in one pull. |
| `unmapped:type` AMORTIZATION | 1 | CRA BTG R$ 117,64 | An amortization is a partial redemption of principal: record it as an `INTEREST`-type provento with `metadata.amortization` (040 already types amortizations as proventos), taxed like the coupon. |
| `unmapped:name` FIXED_INCOME BUY | 1 | "Tesouro Renda+ Aposentadoria Extra (NTNB…)", ISIN BRSTNCNAP088, IPCA + 7,07, due 2084-12-15 | Map Renda+ titles in the Tesouro price file by ISIN/due date (`tesouro_client`), not by name. |
| `type` MUTUAL_FUND | 23 | BB RF LP High and BB RF LP Tesouro Selic: BUY/SELL by quotas, TAX | The bank account side is already `BANK_INVESTMENT` (aporte/resgate in the balance). Add a fund class (or reuse an existing category via `asset_categories`) that records quotas BUY/SELL/TAX with no cash link and is marked by Pluggy's position value (`open_finance_positions.raw`). If the funds hold zero quotas today, recording the history is enough. Check that the Patrimônio/allocation doesn't double what `BANK_INVESTMENT` moved. |

Also: the 3 provisional buys (BBAS3, ITSA4, LEVE3, 2026-10-31) must have been replaced by real operations; if any
is still `provisional`, make the replacement automatic in the pull.

After phase 2, `portfolio_check()` should report no held lines on the owner's data: run it read-only on the server
(SSH notes in the auto-memory `server-readonly-measurement`).

## Phase 3 — Watch and prove

- `scripts/review_breakdown.py`: add the automatic decisions (auto-confirmed, filled by Pluggy, resolved conflicts,
  custody, linked interest) and **filter by the row's own date** (the 2026-10-27 rebuild pollutes
  `auto_recorded_at` windows).
- A weekly line in the log (`applog`) with counts of each automatic decision; the Conferência shows them with
  "Desfazer".
- Update CLAUDE.md ("Only guesses are reviewed", "Fixed income from Pluggy only with exact data", the inbox engine)
  so the written rules match the code.

## Out of scope (rejected by the data, 2026-11-18)

Learning import rules from corrections (2 right / 3 wrong), the merchant table at notice birth (3 right / 2 wrong),
auto-marking repasses by person (the father's Pix flipped in October). A Pix to a person keeps the default category
after auto-confirm; that is the accepted cost of "everything automatic".

## Not code (owner)

- Server `.env`: `BRAPI_MAX_SYMBOLS_PER_REQUEST=1` (brapi plan takes 1 ticker per request; hourly errors in the log).
