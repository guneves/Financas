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
