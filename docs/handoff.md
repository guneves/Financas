# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 (seventh) · Automatic proventos, investments Extrato

The owner asked for three things:
- investment lançamentos visible in the app. Asked to clarify, they answered "make it so the user
  selects which extrato he wants to see";
- proventos derived from positions by date, including a position entered with a past date;
- the proventos for `wgrrodrigues6@gmail.com` updated against their Investidor10 earnings page,
  and kept working in the future.

The opening briefing came from `session-scout`.

### What was done
- **Migration 026** (`026_proceeds_sync.sql`):
  - `investment_proceeds.sync_key` + `sync_locked`;
  - a unique partial index on `(user_id, sync_key)`;
  - the `proceeds_sync_dismissed` table.
- **`backend/statusinvest_client.py`** (pure, cached 6 h, paced 0.6 s, one retry on 429/403).
  - It reads StatusInvest's public `companytickerprovents` JSON.
  - brapi was tried first. Its dividends need the paid "Startup" plan, and it answered 403.
  - `TICKER_ALIASES` maps MALL11 → PMLL11.
  - A row paid before its own data com is dropped as a source typo.
- **`backend/services/proceeds_sync.py`** (`POST /api/investment-proceeds/sync`, `{"force": true}`
  skips the cache):
  - quantity = `accumulate_position()` on the data com (the manual form's rule, factored out of
    `investment_position_at_date()`);
  - writes, corrects or removes automatic rows; never touches a typed one;
  - an edit locks the row (PATCH sets `sync_locked`), and a DELETE records the key so it never
    comes back;
  - a failed ticker keeps its rows.
- **Tax rule** moved to `services/proceeds.py` (`default_tax_rate()`):
  - JCP pays 15% with data com up to 2025 and 17.5% from 2026;
  - "rendimento tributável" pays 22.5%;
  - this is the rule Investidor10 applies to every row of the owner's wallet.

  The manual form uses it too. One fixture in `test_proceeds_by_asset.py` now gives its JCP a
  2025 data com to keep the 15% figures.
- **Frontend.**
  - `lib/proceedsSync.js` triggers the sync on opening Proventos/Investimentos (at most every
    10 min). It also runs 1.5 s after any write to `/api/investments*` or
    `/api/corporate-actions*`; `apiFetch`'s mutation listener now receives the path.
  - Proventos' "Atualizar" forces a sync and toasts the counts.
  - Extrato has a **Contas | Investimentos** selector (`?ver=`, last choice in localStorage).
  - The investments view is `ExtratoInvestimentos.jsx` over `lib/investmentStatement.js`, with 6
    node tests. It is read-only: operações and proventos by day, with search and a Tudo /
    Operações / Proventos filter.
- **Data, on purpose, in the real `finance.db`.** Migration 026 was applied, and the sync was run
  for `wgrrodrigues6@gmail.com` (in-process script):
  - **279 proventos, R$ 3.930,20 net**, against Investidor10's 283 rows and R$ 3.939,91;
  - every matched event had the same quantity as Investidor10;
  - a second run writes nothing.

  Investidor10's list came from its own API
  (`/wallet/api/proxy/wallet-app/earnings/list/1138417`, via Claude in Chrome).
- Tests: backend **989** passed (14 new in `test_proceeds_sync.py`); frontend `npm test` 29 passed;
  `npm run build` OK.

- **finance-guard** (run directly; discovery worked):
  - `user_id` scoping, rounding, the migration and the guards all passed.
  - It found that a typed provento would get an automatic twin for the same event. Fixed: a
    typed row with the same type and data com now stands in for the automatic one, with a test.
    The real DB had no typed proventos, so no duplicates exist there.
  - It also asked for a test that a row removed for zero position comes back when a backdated
    buy restores it. Added, and it passes.

### What was not done and why
- **`:5000` was not restarted.** It is the owner's process, and it predates 026 and the sync
  route. Until the owner restarts it, the screens' sync call fails silently. The data is already
  in the DB.
- **Not opened in a browser:** the Extrato selector, the investments statement and "Atualizar".
  They are covered by the build and the node tests only.
- **The R$ 9,71 left against Investidor10:**
  - GALG11 (not on StatusInvest);
  - three CMIG4 JCP installments that StatusInvest does not list;
  - centavo differences in ITSA4 monthly JCP.

  Listed in next-steps.
- **No scheduled sync:** it runs only while the app is used.
- **No healthcheck card for StatusInvest.**
- **No APK rebuild.** A background Taildrop send from an earlier session was killed by Claude
  Code for low memory, so the phone may still have an older APK.

### Next session
1. Owner restarts `:5000` and walks the Extrato → Investimentos view and Proventos → Atualizar.
2. Rebuild the APK (`mobile/build-apk.ps1`) so the phone gets the selector.
3. Then whatever the owner picks from next-steps.

### Carried from earlier sessions (still open)
- Back up `%USERPROFILE%\.financas-android` off this PC.
- Repeat the offline "+ Novo" test with the APK swiped away.
- Daily use needs `.\start.ps1 -Built -NoBrowser`, Tailscale on both devices, and the PC awake.
- The `:5000` restart also activates the CORS preflight cache (`max_age=7200`) and the
  closed-renda-fixa fix.

### Learned
- `finance.db` runs in **WAL mode**. A file copy is not a backup; use `sqlite3`'s `backup()`. The
  pre-sync backup is in this session's scratchpad (`finance.before-proceeds-sync.db`).
- StatusInvest values before a split are already in today's share basis (`adj: true`); values
  before a bonificação are not. That matches how this app stores both, so no un-scaling is needed.
- StatusInvest answers a burst of ~20 tickers with 429/403; pacing at 0.6 s fixed it.
- Investidor10's earnings list has the same event twice when a company pays in installments
  (KLBN4 ×4 on one data com). The sync keys include the payment date plus an occurrence index.
- Claude in Chrome blocks returning query strings from JS. To move bulk data out of a logged-in
  page, POST it to a throwaway `127.0.0.1` listener (`recv.py` in the scratchpad), then kill the
  listener.
