# Next Steps — FinanceMVP

> The open work a session should know about, **in priority order, kept under ~150 lines**. Finished
> work leaves this file for `docs/done-tasks.md` (no ticked boxes, no "done" sections). Lower-priority
> and older open items (owner checks, known limits, leftovers) live in `docs/backlog.md`: grep it when
> you touch an area, move an item up here only when it becomes the next thing to do. The rules
> themselves are in `docs/domain-rules.md`.

---

## 1. Open work, in priority order

### APK pull to refresh (2026-11-26) — owner check after the deploy
- [ ] On the phone, right after opening the app, pull Início: the spinner stays until the data lands, and a
  movement Pluggy already has (its `lastUpdatedAt` moved) shows up. On the server, the log shows
  `POST /api/open-finance/refresh`.


### Architecture audit (`docs/audit.md`) — what is left
Both stacks (#76–#93) are merged and deployed. The owner's decisions of 2026-11-13: the month's
spending is one rule on every screen (#95, deployed) and the web Início reads `GET /api/home/panels` (#96).
- [ ] **Owner, on the PC**: delete `%TEMP%\financas-tests-*` by hand. Every test run before #91 left 3.7 GB there.
- [ ] **Owner walk-through of the web Início** after #96, on the real data: Despesas por categoria, Ritmo de
  gastos, Parcelamentos abertos and the purchases under each invoice now come from the server. Checked in a
  browser only on the 3-year seed (text and chart paths identical to the old page).
- [ ] **Not done: the five long views** (R8's other half): `investment_detail` (219 lines), `create_movements`
  (172), `cc_expenses` (148), `update_transaction` (141), `account_detail` (127). A view decides and answers in
  the same breath, and several read names the tests patch on the route module (`refresh_market_prices`,
  `local_today`, `settle_invoice`). Each is a rewrite of money-moving code: one view per PR, a response-shape
  test first (status, keys and types for every branch), then split into "decide" (service, raises) and
  "answer" (route).
- [ ] **Not done: the engine knot of `open_finance_inbox.py`** (1654 lines). Its sections (placing,
  reconciliation, succession, near match, auto-record) call each other in both directions, so no section can be
  moved out; it needs a redesign (probably an explicit pipeline object passed down) with the identity suite
  (`test_notify_pluggy_identity.py`, the fuzz and plans tests) as the net. Same for the 1072 lines left in
  `inbox.py` (notifications ↔ Open Finance pairing).
- [ ] **Decided against**: merging `auto_record.py` and `open_finance_auto.py`. Their `one_side_now` /
  `hold_reason` / `record_item` look alike but decide from different evidence (a phone detection vs a Pluggy
  row) with different category and amount sources; unifying them would change behaviour.
- [ ] Import sorting (ruff I001) and a `ruff.toml`: one PR once nothing else is open (it touches ~90 files).
  Ruff counts: 349 from `backend/` after #92 (354 before the second stack).
- [ ] **Audit findings left open**: no attempt limit on login and a 6-character password floor (C3); an unhandled
  exception answers HTML, not JSON (C4); `recurring.settled_dates()` is read once per recurrence (14 statements);
  the other check-then-write guards (budget sum ≤ 100%, card delete, signup "closed once a user exists") have the
  window `db.begin_write()` closed for invoices: use it there too if one ever bites.
- [ ] Four routes no current client calls (`POST /api/database/backups`, `GET /api/database/status`,
  `DELETE /api/investments/by-ticker/<ticker>`, `PATCH /api/investments/price-by-ticker`) and 12 frontend exports
  used only by their own tests were kept: remove only once no installed APK can call the routes.
- [ ] The clock sweep (suite re-run with Python's clock at +30/+90/+400 days) cannot move SQLite's `now` or file
  mtimes: 10 tests fail under it for that reason only. A test that compares a fixed date with `created_at` is
  still a possible calendar bomb; `dates.now_source` is the way to freeze.

### Remote access: Funnel :8443 behind Google / device key — built (2026-11-06); rollout open
Code merged with branch `feat/funnel-auth` (README "Remote access", DEPLOY.md "Remote access: the auth
proxy on :8443"). Nothing is public yet: Funnel is off.
- [ ] **Rollout, in order, each `sudo`/Tailscale step approved by the owner** (DEPLOY.md steps 1–10):
  Google OAuth client (Testing, one test user); `OAUTH2_ALLOWED_EMAILS` in the server `.env`
  (`oauth2.env`/`proxy.env` already exist); `tailscale serve --https=8443` before the merge; merge;
  `curl` checks on 8102; tailnet tests (Google + app login, receipt, CSV, Pluggy "Atualizar" and
  quote refresh timed, sign-out reload with a "+ Novo" landing once); phone installs the new APK
  **over the VPN from 443** and pastes the key; the `funnel` nodeAttr; `tailscale funnel --https=8443`;
  public tests on mobile data; LAN ports closed.
- [ ] Not checked on a real device yet: the APK's login key field, the shell's "Chave de acesso
  inválida ou ausente" dialog and Ajustes › Perfil › "Trocar chave de acesso" (JVM tests and the
  build only). The web reload on a proxy 401 was only unit-tested (`proxySession.test.js`).
- [ ] Known limits to watch: Funnel's timeout is undocumented (gunicorn caps at 120 s); the Pluggy
  Connect widget through :8443 is unchecked; `rd={uri}` may drop a query string after the Google
  login; logs may show 127.0.0.1 as the client. 443 (tailnet, no proxy) can be retired once every
  phone is on the :8443 APK.

### Detection bug hunt (2026-11-20) — branch `fix/detection-bughunt`, not merged
B1–B13 fixed on the branch, one commit each (handoff 2026-11-20). Owner's rules taken: B3 "meio-termo" (own
transfer needs both ends to be the owner), B10 "update in place".
- [ ] **Owner's OK to merge and deploy** (the branch is pushed only when asked). Gates passed: backend in 4
  chunks, the card / Open Finance / identity / fuzz suites, and the replay over a copy of the server's database.
- [ ] After the deploy, watch on real data: a reviewed purchase posted next day keeps its id and leaves Revisar
  (B10); a "compra aprovada" without credit/debit from BTG ends as one row of the bank's type (B2: 25 of the
  owner's BTG notices are `PURCHASE`); an estorno naming a card lands on the card (B6, none in the data yet).
- [ ] B14 (not fixed, by design of the brief): the APK ignores "compra cancelada" (`NotifyParsers.kindOf()`
  returns null for "cancelad"), and a card is list-only, so a notified purchase cancelled before it posts stays
  in the invoice as a ghost. Needs the APK to send a `DECLINED`-like kind for a cancellation, and a server rule
  for a recorded card purchase (`undo_declined()` handles only the Flash/Samsung decline today).
- [ ] B15 (not fixed): `inbox.is_auto_invest()` checks only the notice's merchant, never the counterparty, so a
  Pix notice whose counterparty is "RENDE FACIL" would not be ignored. Never seen on real data.

### Notifications + Pluggy, one movement one row — built and verified (2026-11-05); owner checks open
The rules as built are in docs/domain-rules.md ("Notifications are fast, Pluggy is the record", "Auto-record →
reconcile → review", "The inbox engine"); the tests are `test_notify_pluggy_identity.py`,
`test_notify_pluggy_fuzz.py`, `test_notify_pluggy_plans.py`, `test_notification_policy.py`,
`test_quiet_review.py`, `test_twins.py`, `test_open_finance_orphans.py`, `test_notify_pluggy_audit.py`.
- [ ] **Owner, with the new APK installed**, in order:
  1. an Itaú card purchase shows up in seconds;
  2. after the next pull it is still one row;
  3. a Pix to BTG Investimentos gives one transfer;
  4. a week later, `scripts/check_identity.py` prints nothing.
  The real notice texts of the brokerage app and of an invoice payment are not captured yet: if one
  of them reaches the Extrato, export it from Ajustes › Notificações do celular (modo captura) and
  adjust `NotifyParsers`.
- [ ] **Owner, after the next pull**: run
  `sudo docker compose exec -T -w /app/backend app python scripts/position_fields.py --email <email>`.
  Until then nobody knows whether MeuPluggy fills `rateType`/`rate`/`fixedAnnualRate`/`dueDate` for BTG,
  so whether held fixed-income lines fill themselves on real data is unknown. If the keys are missing,
  the lines stay `HELD missing:<field>` with "Lançar". If the unit of `rate` is not percent, widen nothing:
  fix `title_terms()` with the real shape and a test.
- [ ] **Owner, review and twins**: look at Revisar after a few pulls — only Pluggy-tree/default
  categories, the Flash and the Conta global should be there. A "2× igual" pair should be real twins.
- [ ] Weekly: run
  `sudo docker compose exec -T -w /app/backend app python scripts/check_identity.py --email <email>` on
  the server; it must print nothing.
- [ ] The APK's "Lançar" opens only operations (coupon and redemption: web). The web's one-tap
  redemption needs exactly one fixed-income position with the same name.
- [ ] Orphans by balance: cards are list-only (a card balance mixes the used limit, pending holds and
  BB's rounding). With `include_pending` on, a pending Pluggy row the bank's balance doesn't count makes
  the difference never equal an orphan, so nothing is removed (safe side). Watch the Conferência's
  "Confirmado pelo saldo" list on real data.
- [ ] Owner's call (audit, 2026-11-13): a Pluggy **purchase** with the same cents, on the same day and account as
  a notified own transfer, can take that transfer's Pluggy slot (`open_finance_fits_item()` accepts any row for a
  TRANSFER item). Requiring a Pix/TED mark would double a transfer whose bank row has none; left as is.
- [ ] Watch after the deploy: `near_match` in the pull log now also counts `late_near_pass()` joins (a
  Pluggy-recorded row removed in favour of the notice's row). A pull that fails with "a Pluggy repetiu o
  cursor" is the new refusal of a cut history: it retries by itself.
- [ ] Known limits, kept on purpose; revisit only if real data shows them: a card with a single sandbox-sign
  purchase learns the docs' sign (+) and reads it as a refund; card twins (`card_twin_keys()`) read the card
  rows through a bounded subquery. (An account with no Pluggy history now looks back the owner's first window,
  B12 of 2026-11-20.)

## 2. Open decisions

3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
