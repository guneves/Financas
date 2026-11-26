# Next Steps — FinanceMVP

> What to do next, in priority order, **≤ ~60 lines**. Finished work leaves for one row in
> `docs/done-tasks.md`. Everything else that is open (refactors, known limits, older owner checks) is in
> `docs/backlog.md`: grep the area you touch; move an item up here only when it becomes next.

## Now

1. **Deploy and check pull to refresh** (2026-11-26, commits b02a6ff + docs): with the owner's OK push `main`;
   then on the server the log shows `POST /api/open-finance/refresh`, and the owner pulls Início right after
   opening the app (the spinner stays until the data lands).
2. **Make server testing possible** (owner 2026-11-26, CLAUDE.md › Testing on the server): the owner adds an
   allow rule for `ssh guilherme@guilhermeserver` (auto mode refused it); then a session confirms the SSH
   read path works.
3. **Server checks a session now runs itself** (read-only, per CLAUDE.md):
   - `scripts/check_identity.py --email <owner>` must print nothing (weekly).
   - `scripts/position_fields.py --email <owner>`: does MeuPluggy fill `rateType`/`rate`/`fixedAnnualRate`/
     `dueDate` for BTG? If not, held fixed-income lines stay `HELD missing:<field>` ("Lançar"); if `rate` is not
     percent, fix `title_terms()` with the real shape and a test.
   - After #104 (detection bug hunt), on real data: a BTG "compra aprovada" without credit/debit ends as one row
     of the bank's type (B2); an estorno naming a card lands on the card (B6).
4. **Remote access rollout** (built 2026-11-06, Funnel still off): DEPLOY.md "Remote access" steps 1–10, each
   `sudo`/Tailscale step approved by the owner; details and limits in the backlog.
5. **Owner, on the PC:** delete `%TEMP%\financas-tests-*` (22 folders from test runs before #91).

## Open decisions

- **Single-user or multi-user?** The schema is ready for either; SQLite is enough for personal use.
