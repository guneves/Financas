# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-13 · One spending rule (#95) and the web Início on the server's panels (#96), both merged

The owner's three decisions of 2026-11-13 (audit findings B2 and B3).

**Done and deployed: #95** (merged, deploy run 43423449705 green). The month's spending is one rule on every
screen (`services/spending_rules.py`): a despesa/receita typed in a Corretora account counts in neither the plan
nor the budget; the legacy invoice payment (category starting with "Pagamento Fatura") matches in any case and is
out of expenses **and** income everywhere. Tests rewritten first and failing (9 backend, 2 node), then the fix.
Client mirrors that repeat the name test were updated too: `lib/transactions.js` `isInvoicePayment()`,
`lib/outboxRules.js` and the APK's `rules/OutboxPending.kt` (pending-item estimates). Suite 2929 → 2936.

**Done and merged: #96** (its deploy was watched at the end of the session; this file was written just before,
so if the latest `deploy.yml` run on `main` is red, start there). `Dashboard.jsx` reads `GET /api/home/panels`
through `useHomePanels()` (`lib/attention.js`): categories, spending total, pace, the purchases under each invoice,
installments. Nothing on the page needs the whole history, so `useInicioMovements`, `lib/homeSpending.js`,
`homeSpending.parity.mjs` and `test_home_panels_parity.py` were removed. The balance, "Saiu" and the "estimado"
note still count pending items (`applyPendingToHome`).
- Checked in Chromium (Playwright) on a throwaway 3-year seed, 390 px and 1400 px, light and dark: the page text
  and every chart path are identical to the old build (the one diff, an x-axis tick of "Evolução do saldo" at
  phone width, also differs between two runs of the old build). Screenshots: branch `pr-assets/web-home-panels`.
- Início's API bytes: 1 268 606 → 21 897 (10 requests → 8).
- Full backend suite 2935 passed (2936 minus the removed parity test), `npm test` 246, `vite build` ok, ruff 405
  from the repo root before and after.

**Also this day: Metas, "Atual" is what is invested (migration 057)**. The owner asked that a goal's "Atual"
be what they have invested today and that "Previsão" follow it. The forecast already started from `current`;
the wrong number came from the form's default kind, "Patrimônio" (`NET_WORTH`), which added every account's
balance to the portfolio. That kind is gone: `services/goals.py` reads only the portfolio (net) or one class,
057 turns stored `NET_WORTH` goals into `PORTFOLIO`, an old APK that still sends `NET_WORTH` is stored as
`PORTFOLIO`, and the web and APK forms offer "Carteira | Classe | Renda" (default Carteira). Tests:
`test_goals.py` (4 new), `npm test` 246, `GoalsTest` 6 (local Gradle). Related backend files only, not the full
suite; ruff is not installed in the venv here.
- **Not seen on the real data**: the Chrome extension was disconnected and the PC's `finance.db` has no goals,
  so this is the reading of the request from the code (it also closes the old "owner's call" on `NET_WORTH`).
  If the owner meant something else (gross value as in Posição's "Carteira", or the Corretora's cash counted),
  it is one line in `current_values()`; both are in `next-steps.md`.
- A second session (pluggy/open_finance files, `test_zz_*`) was working in the same tree, uncommitted; none of
  it is in this PR.

**Also this day: audit of the notification / Open Finance engine** (owner: "verify the logic, no bugs").
Read every module of the engine (inbox*, open_finance*, auto_record, recorded_snapshot, review, twins, the two
routes, `pluggy_client`), probed suspicions with scratch tests and ran the generated worlds on 700 seeds beyond
the 200 of the suite. Five defects, each with a test in `test_notify_pluggy_audit.py` (or its own file):
- **A paid card purchase was deleted and redone** when the bank listed it under another date or card
  (`reconcile_recorded()` dropped it and re-recorded it OPEN). Now only linked (`has_paid_installment()`).
- **Two near purchases at one merchant ended as three rows** (fuzz seed 247: two foreign top-ups notified
  before the bank listed either). `late_near_pass()` joins the leftover pair once it is unique.
- **The same Pluggy id with another amount** (the tip on a pending row, fuzz seed 251) left a recategorised
  notification row at the old amount; it now follows the bank (`apply_change()` → `follow_bank_amount()`). A
  row Pluggy itself recorded keeps the 044 guard (edited → `conflict`), as its test demands.
- **A repeated transactions cursor returned a short list** (`pluggy_client.list_transactions`): the pull would
  have vanished what was left out. It is a `PluggyError` now (the old test asserted the short list; rewritten).
- **A malformed 10-character date raised `ValueError`** and failed the whole pull; it is a `Skip`.
- Checked and found right (no change): twin own transfers in any pull order, the per-channel slots, the gate.
- **Not changed, owner's call**: a Pluggy purchase of the same cents on the same day as a notified own
  transfer from that account can take the transfer's Pluggy slot (`open_finance_fits_item()` does not ask
  for a movement); tightening it would double a transfer whose row has no Pix/TED mark.

**Not done, and why**
- The branch `pr-assets/web-home-panels` (screenshots only) is still on the remote: #96's description links to
  it. Delete it when the pictures are no longer wanted.
- The owner has not clicked through the web Início on the real data.

**Next**: the owner's walk-through of the web Início; then one long view at a time (`next-steps.md`).

**Lessons**
- `gh pr merge --auto` on this repo merges immediately (auto-merge is off, `main` is unprotected): #95 merged
  before its Android check finished (it passed). Wait for the checks first.
- Never `git stash` while a background test run reads the tree; the run had to be restarted.
- `subprocess.run(text=True)` decodes node's UTF-8 output as cp1252 on Windows: pass `encoding="utf-8"`.
- A PR's screenshots can live on an orphan branch (the repo is public; `android-check` ignores it by path).
