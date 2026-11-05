# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-05 · Manual entry everywhere, and the "+" out of the way

Branch: **`claude/funny-wright-o348r5`**, from `main` at `03c77cc`. The owner asked: "I should be able to add
transactions manually for everything in the app, and the button should not be where it is today, because it is
hiding content", then to open a PR and merge it when done. No migration.

**Done**
- **Typing everywhere**: `MANUAL_ONLY_OFF_PLUGGY` (config) now defaults to **off**. Every guard in
  `services/manual_entries.py` (typed row, card purchase/refund, transfer, statement import, investment operation on
  the Pluggy-fed Corretora) is skipped unless the env sets it to `1`; the code stays as a brake. The engine already
  links a typed look-alike to the bank's row (`free_candidates()`), so no second row.
- "+ Novo" lists every reais account and every card: web `NewEntrySheet.jsx`, APK `NewEntryViewModel.kt` (both
  dropped the `!pluggy` filter; the Conta global is still out).
- The Corretora cash note (`PLUGGY_FED_NOTE`, web + APK) now says the default is "não descontar" and the owner may
  pick the Corretora, instead of "only what it doesn't see".
- **The button**: on the APK the "+" was a floating 56 dp button over the page (bottom-right), covering the end of
  every list. It now lives inside `ShellBottomBar`, after Lançamentos (`ShellNav.NEW_ENTRY_AFTER`), 48 dp, on every
  page with the bar (Ajustes too). The snackbar's 80 dp lift (for the FAB) is 16 dp. The web already had it in the
  bottom bar / header and needed no change.
- Tests: `TestEverythingIsTyped` (default off via a subprocess, connected account/card/transfer accepted, a typed
  bank row and a typed card purchase linked to Pluggy's row); `ShellNavTest` updated.

**Not done, and why**
- The APK was not compiled here (no Android SDK); CI's `android-check` builds and unit-tests it on the PR.
- Nothing checked on a phone. The owner should look at the new bar once the APK updates.

**Next**: the owner's checks in `next-steps.md`, plus a look at the APK bar and one typed purchase on an Itaú card
that later arrives from Pluggy (should stay one row).

Lessons:
- A single sandbox-sign card purchase is learned as a refund (`learn_charge_sign()`); a test with one purchase
  uses `card_tx(..., docs_sign=True)`.
- `pytest -n` isn't available (no xdist); `| tail` hides a pytest usage error's exit code.
