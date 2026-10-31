# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-30 · The app waits for Pluggy; expense to transfer; instant saves

Owner asked: expenses wait until Pluggy refreshes and are flagged only if a run updated and still did not
identify them; deletes and edits feel slow; an expense must be editable into a transfer; Pluggy does 99% of
the work, notifications only for the Flash; a TED salary failed with "escolha a conta" on "não é entre minhas
contas"; update only on the 6 h period; remove "Movimentos com diferença"; check the owner's account.

Done (rules in CLAUDE.md › "Open Finance is the only banking source"):
- TED salary: a one-sided incoming transfer is stored OUT with no origin, so the button asked for an account and
  would have sent a despesa. `settle_one_side()` fixes it on the server (works on the installed APK);
  `ReviewRules.singleType` too. New salaries are income (`is_income_row()`).
- Waiting: `awaiting_bank()` keeps a pending item out of `waiting` until every connection refreshed after it; the
  Conferência's `awaiting_bank` does it for app rows. "Não gravou sozinho" reads what Pluggy did not identify.
- 6 h: reads no longer run `record_pending()`; only the pull writes bank movements. The button still pulls.
- Expense/income → transfer: PATCH, web and APK, absorbing the other side Pluggy already recorded.
- Speed: PATCH and DELETE take ~15 ms on 3000 rows; the wait was the screens holding the row until every list
  reloaded. The Extrato (web, APK) now changes the row at once. `PRAGMA synchronous = NORMAL` was set on
  one connection only, so every other commit paid a full fsync; `get_db()` sets it.
- "Movimentos com diferença" badge removed (web, APK); "Movimentos conferem" stays, details stay in "Ver a
  conferência"; the balance "Diferença R$" stays.
- Notifications: confirmed Flash-only on the server (`notification_wanted()`); no change.

**Not done:** the owner's account was **not** compared with Pluggy: SSH was refused and the Chrome extension
was offline. Nothing in production was read or changed. See next-steps.

Lessons: a `perf` run right after `import app` measures the Tesouro boot download thread (150 ms of TLS reads
in the profile are not the request). `FakePluggy` connects with a first pull, so `synced_until` is today: rows
older than 7 days never arrive in a test; and `pluggy_updated_at` in the future never counts as read.

Next: merge (deploys), update the APK, walk the salary button, one expense → transfer, a delete.
