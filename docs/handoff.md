# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-05 · Débito automático that actually debits, two Pluggy bugs, "+" centered

Branch: **`claude/amazing-newton-wgnmle`**, from `main` at `b60c444`. The owner: "Débito automático should take
the balance on the due day if I have enough; today I had to update mine by hand", plus a bug search on the
notifications + Pluggy logic, then (mid-session) "center the + and move Ajustes from the bottom to the top".
No migration.

**Done**
- **Why the debit didn't happen**: `apply_due_autopay()` skipped every Pluggy-mapped card on purpose (2026-10-30:
  "the payment comes from the bank"). So on the due day nothing moved until a pull brought the bank's payment
  (6–24 h later, or never if the bank posted it in a way `_pick_invoice()` couldn't match). Now a mapped card is
  debited like any other, on the due day, and **every** card (mapped or not) needs the account's balance at the
  end of the due day (`account_balance_until()`, new in `services/accounts.py`) to cover the invoice; without it
  the invoice stays open for Pagar.
  Guards for the mapped card: only up to `AUTOPAY_CONNECTED_DAYS` (5) after the due day (an old open invoice
  never becomes a debit the bank didn't make, which also keeps the rebuild test's promise), and never when a
  loose bank invoice payment (`source_id 'pluggy:…'`) sits on that account within ±5 days.
- **Bug 1 (autopay ↔ bank payment, would double)**: the bank often debits the next business day with an amount a
  few cents off the app's invoice. `_kept_payment()` only linked same-day or same-cents, so that payment became a
  second "loose" payment. It now also links an app `CC_AUTOPAY` row within `CARD_SIDE_DAYS` whose amount is within
  `AUTOPAY_NEAR_PERCENT` (5%) of the bank's (closest-amount check over the nearby bank payments); the owner rule
  "R$ 500 on 17/10 vs R$ 382,36 on 20/10 are two payments" (`test_pluggy_owner_rules.py`) still holds. Test fails
  without the fix.
- **Bug 2 (orphan sweep deleted real rows)**: `open_finance_orphans.account_difference()` and the Conferência
  compared Pluggy's balance (today) with the app's *whole* balance, future-dated rows included. A typed boleto of
  R$ 50 for next week made the difference +50, and the sweep removed a real, notified R$ 50 purchase Pluggy hadn't
  listed. Both now use the balance up to today (the Corretora already did, `settled_balance`).
  `test_a_future_typed_row_is_not_a_difference` fails without the fix.
- **APK bar**: Ajustes left the bottom bar (`ShellNav.BAR` = Início, Lançamentos, "+", Planejar, Investir), so the
  "+" is the exact center (test: as many tabs before it as after). Ajustes opens from a gear at the top
  (`SettingsButton`, in `NativeTopBar` and Início's header, hidden on Ajustes itself; `ShellNav.showsSettings()`).
  The web already had both (centered "+", gear in the header) and was not changed.
- Tests: 5 autopay tests in `test_open_finance_rebuild.py::TestInvoices` (replacing "never debits a connected
  card"), 1 in `test_open_finance_orphans.py`, `ShellNavTest` updated.

**Not done, and why**
- The APK was not compiled here (no Android SDK); CI's `android-check` builds and unit-tests it.
- Suspect, not changed: `auto_record.undo_declined()` removes an untouched row even when a live Pluggy row claims
  it. A declined purchase shouldn't post, so it is theoretical; a guard (`inbox.pluggy_claimed()`) would be cheap
  but needs a Samsung + bank + Pluggy test to prove.
- Nothing checked against the owner's real data: on the next due day, the autopay row should appear on the
  morning read and the bank's payment should link to it (one row, the bank's amount).

**Next**: watch the next autopay invoice of a connected card (Conferência shows no app-only payment once the bank
posts); the owner's checks in `next-steps.md`.

Lessons:
- An app account in `open_finance_world` starts at R$ 0 whatever Pluggy's balance says; an autopay test needs a
  typed income first.
- `balance_difference()` does float math: the as-of-day balance helper returns a rounded float, not a Decimal.

