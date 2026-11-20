# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-20 · Detection bug hunt (notifications + Pluggy), branch `fix/detection-bughunt`

**Not merged, not deployed, not pushed** — waiting for the owner's OK (the brief's rule).

**Done** (one commit per bug, each with a regression test that failed first; tests in
`test_notify_pluggy_identity.py` unless noted):
- **B1** a bank's notice never links to / joins / is taken by another bank's row: the notice's issuer
  contradicts an account/card of another bank (`account_bank()`/`card_bank()` in `inbox_store.py`, by
  institution, name, a card's debit account, the mapped Pluggy account; `OTHER_BANK_NAMES`), in
  `existing_rows(issuer=)`, `_detection_fits_open_finance()` and `notified_item_fits()`; a notice never links to
  an invoice payment, investment cash or the Inter line.
- **B2** a `PURCHASE` notice (no credit/debit) leaves the type open (`method_guessed()`); the bank's debit or
  card line pairs and `reconcile_recorded()` redoes it the bank's way.
- **B3** (owner: "meio-termo") `counterparties_conflict(a, b, a_is_owner, b_is_owner)` + `sides_conflict()`:
  CPFs, then whole names (`same_person_name()`), named vs unnamed only with a known owner side.
- **B4** (`test_global_account.py`) a notified Pix to Wise + the dollar credit → one transfer in any order
  (`_notified_pix_to()`, `absorb_dollar_income_for_notice()` called from `auto_record.record_item()`).
- **B5** an owner-changed card purchase takes the bank's invoice (`_move_line()` in `_mirror_purchase()`); the
  invoice is not in the snapshot, so it is no touch.
- **B6** a REFUND notice naming a card (`refund_card()`) is a card credit, category "Estorno".
- **B7/B11** reposts: a same-app pairing never hides the original from Samsung; a paired original is
  recognised; without `when_ms`, `REPOST_CLOSE_MS` (2 s).
- **B8** a card's pending 1/1 total continued by 1/n (`_split_into_installments()`); `_set_line()` copies the
  installment label.
- **B9** BB rounding also by the mapped app account/card.
- **B10** (owner: "update in place") `_follow_bank_in_place()`: date/account/card (and card invoices) change on
  the same row, review state kept; only account ↔ card redoes. Old `test_auto_record.py` tests that expected
  the redo now pass unchanged in substance (one renamed).
- **B12** (`test_open_finance_sync.py`) an account with no rows looks back the owner's window from the last pull.
- **B13** CLAUDE.md: Samsung-only purchases record at once; every changed rule documented.
- **Replay on a copy of the server's database** (scratchpad, server `/tmp` cleaned): B1 finds no notified row on
  another bank; B3 splits 0 of 89 real two-sided transfers (3 learned self keys); B9 unchanged (the Pluggy names
  are "BANCO DO BRASIL S/A" / "OUROCARD FACIL VISA"; all connections are MeuPluggy); `mirror_cards()` moves
  nothing today; 12 real BTG reposts, all same `when`.

**Not done and why:**
- B14 (APK ignores "compra cancelada") and B15 (`is_auto_invest()` ignores the counterparty): notes in
  next-steps, as the brief asked.
- Merge/deploy: needs the owner's OK. B10 changes owner-visible behaviour (rows keep their id).
- B2/B6/B10 were not seen live yet (no REFUND notice in the data); watch items in next-steps.

**Next:** owner's OK → push, PR, merge, deploy; then the watch list in next-steps ("Detection bug hunt").

**Lessons:**
- The tests' Pluggy first window is real today − 30 days (SQLite/Pluggy windows aren't frozen by `freeze()`):
  a scenario dated earlier silently pulls nothing. Keep test dates inside it.
- `created_at` is SQLite's unfrozen clock: never derive a window from it (B12 first try was a calendar bomb).
- `sides_conflict` / `side_is_owner` live in `inbox_transfers.py` and are **not** re-exported by `inbox`.
- `sed -i` in Git Bash rewrote a CRLF file as LF; harmless with `autocrlf`, but split scripts must read with
  universal newlines.
