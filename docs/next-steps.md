# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`. This file holds **only open work**: when a task is finished, remove it from here and
> record it in `docs/done-tasks.md` — no ticked boxes, no "done" sections.

---

## 1. Open work, in priority order

### Open Finance only (2026-10-30) — what is left
- [ ] Início's "Despesas por categoria" sums R$ 1.397,14 in October against R$ 1.365,41 spent: a refund in category "Estorno"
  (R$ 31,73, AliExpress) has a negative total and is dropped. Net it from the purchase's category.
- [ ] Owner, on the phone: update to APK 10109+, then the dropdown under "Fatura de <mês>" and the Investir tab from a sub-tab.
- [ ] **Provisional buys** (2026-10-31): 20 BBAS3, 23 ITSA4, 10 LEVE3 at the position's price, no cash. Pluggy's
  next operations replace them; check Operações has the real prices and cash after that pull (a linked one keeps
  the estimated price: fix it).
- [ ] **R$ 41,89 in the August BTG bill** that Pluggy does not list: lines 1.274,21, charged 1.316,10 (paid 1.313,88 + 2,22).
  The card balance is right; the invoice's purchases are short. **R$ 16,90 of BB's 2025-11 bill** is before Pluggy's window.
- [ ] eslint has no config file, so it cannot run in `frontend/`.
- [ ] Screens not seen until the deploy: Conferência without Diferença, Ritmo, Evolução do saldo, the invoice dropdown
  (web at 390 px and APK), Revisar's "É repasse", "+ Novo" with the Flash only.
- [ ] The Itaú salary is ported to BTG (owner, 2026-10-31): Itaú's `PENDING` row and BTG's "TedSalary" are one salary; Itaú posted
  nothing in August or September. Only an Itaú salary that posts beside a TedSalary would be a double count.
- [ ] The APK has no "Lançar" / "Aconteceu" in the Conferência (web only).
- [ ] Items already pending from before this deploy (a TED salary saved as a one-sided transfer) stay as they
  are: tap "Não é entre minhas contas" once; new ones are income straight away. A salary with no salary text
  and no Pluggy `01` category, marked same-person by Pluggy, still arrives as a one-sided transfer.
- [ ] The APK does not list `awaiting_bank` rows of the Conferência (the web does).
- [ ] A card purchase cannot become a transfer (it moves no account).
- [ ] Fixed income, Tesouro, funds and INTEREST stay HELD: Pluggy's operations lack indexer, title type,
  redemption lot and coupon tax start. So later fixed-income buys, IR and fees are `COVERED`, and the
  Corretora can drift from BTG's cash after a rebuild. `cash_check()` shows it.
- [ ] Some test writes to `backend/finance.db` (the PC's dev copy): `user-…@example.com` rows since
  2026-10-27 (453 users), against the rule that tests never touch it. Find it; the data is not real.
- [ ] Tune the merchant table with `--report-categories` on real rows.

### Conta global (047, 2026-10-27) — what is left
Code on `main` and deployed (2026-10-27); the last code gaps were closed 2026-10-28 (see
`done-tasks.md`). Prompt: `docs/prompts/global-account-usd.md`.
- **Owner's data, after deploy** (through the API from the owner's Chrome tab, OK per batch):
  1. Read balances before (BTG conta corrente 170,00, Wise R$ 559,43, October Gastar 1.172,73).
  2. `PATCH /api/accounts/<Wise> {"currency": "USD"}` (allowed: it only received the three BTG Pix);
     Wise shows US$ 0 until step 4.
  3. Map the Pluggy Wise account (MeuPluggy item `52632759-…`) to it; pull that item.
  4. Check each of the three transfers got the US$ Wise credited (`transfer_amount`), every other
     Wise row became its own US$ row, Wise = Pluggy's US$ balance; BTG and Gastar unchanged.
     A transfer still without `transfer_amount` (no credit within ±1 day): set it by hand with
     `PATCH /api/transactions/<id> {"transfer_amount": …}` from the Wise statement.
- Owner: walk `mobile-docs/native/screens/17-conta-global.md`'s Acceptance on the phone.
- Owner, on the phone after the APK update: "Pix para cá" saves one transfer (R$ out, US$ in);
  "Carregar mais" at the end of the statement; a waiting Pix to Wise asks "Quanto entrou (USD)".
  (The APK changes of 2026-10-28 were not compiled here: no Android SDK in the cloud container;
  the pure rules ran on a plain JVM. CI's apk job is the first full build.)
- Not built: a waiting **dollar** credit (Wise side, no reais side) can't be paired by hand with a
  reais account (the server refuses an origin in another currency than the item); it becomes a
  US$ receita after the hold, and the reais Pix, when it arrives, turns it into the transfer.

### Auto-record → reconcile → review (045, 2026-10-27) — what is left
The paradigm (CLAUDE.md › "Auto-record → reconcile → review"): every notification is recorded at
once, Pluggy reconciles it (and feeds Investimentos), the owner only confirms and categorizes in
the Extrato's Revisar panel. Built on `main` for the server and the web; see `done-tasks.md`.

**Owner, after the deploy:**
- [ ] Both switches come **on by default** (`AUTO_RECORD_DEFAULT`): the first phone upload records
  every pending notification, and the first Pluggy pull records the Pluggy backlog of mapped
  accounts. Check the card purchase sign first (the item below in the 044 section), or turn
  Ajustes › Open Finance › Gravar sozinho off until then.
- [ ] Ajustes › Avisos do celular: "Gravar sozinho" on. Make a Flash and an Itaú purchase; each must
  appear in Extrato › Revisar within seconds, then disappear with "É meu".
- [ ] After a Pluggy pull, the same purchases must still be **one** row each (now marked
  `OPEN_FINANCE` in the database) and the Conferência must read "Confere".
- [ ] Decide whether "Ignorar avisos dos bancos conectados" stays: with notifications recording
  first, leaving it off is the new default flow (on, connected banks are recorded by Pluggy only).

**Not built / limits:**
- [ ] **APK on the phone (built 2026-10-27, not run on a device)**: install the update after the PR
  merges (the deploy's apk job; the app offers it). Walk: a Flash/Itaú purchase appears in Extrato ›
  Revisar within a minute (the pill "N para revisar" too); "É meu" clears it; a card purchase shows in
  the timeline with "Cartão · Nx" and no day total of its own; tapping it opens Cartões; no Aprovar
  anywhere (tabs, Início, notifications); an own Pix with one side shows under "Não gravou sozinho"
  and "Gravar" with the other account makes one transfer. Light and dark.
- [ ] An own transfer with one side waits until the other side arrives (the Extrato says
  "N movimentos não puderam ser gravados sozinhos · Ver"). A transfer to an account that is neither
  connected nor notifies (another bank) needs the owner there.
- [ ] Review has no "não é meu" action: an error is deleted with the row's normal Excluir (a
  Pluggy row deleted this way is not re-recorded: its item stays decided). A fraud is real money:
  keep the row and contest with the bank.
- [ ] Pluggy corrects a notification-recorded row only when it is untouched; amounts are matched
  exactly (or installment vs total), so a different amount (IOF, foreign purchase) is a second
  movement, not a correction.
- [ ] Editing a row (PATCH) does not clear `needs_review`; only Revisar does.
- [ ] "Sempre perguntar a conta/cartão" only matters with Gravar sozinho off (disabled in Ajustes
  otherwise); `inbox_hints` are no longer learned while auto-recording (`remember: False`).

### Open Finance as the only source for connected banks (044, 2026-10-27) — what is left
Built on `main` (see `done-tasks.md`, CLAUDE.md › "Gravar sozinho", DEPLOY.md › Open Finance). The
owner's decisions: Pluggy (MeuPluggy, free plan) is the only source for Itaú, BTG and BB, recorded
automatically; Aprovar stays for Flash and what only the owner decides; GET only, never more often
than every 6 h; BTG Investimentos goes into Investimentos.

**Owner, after the deploy (in this order; nothing of it ran on real data yet). Since 045 the
Pluggy switch is on by default and Aprovar is out of the tabs — read the 045 section first:**
- [ ] Ajustes › Open Finance (web): map every account. Expected: Itaú → "Itaú"; BTG Banking →
  "BTG conta corrente"; Cartão BTG BLACK → "BTG black"; **BTG Investimentos → "BTG Corretora"** (now
  allowed: it is the broker's cash); BB checking → "BB"; OUROCARD FACIL VISA → "BB ourocard"; the
  second Ourocard → **"Não usar"**. Suggestions now come from the account name.
- [ ] "Atualizar" each connection, then turn on **Gravar sozinho** (refused with the reason while an
  account lacks a destination or a connection has no pull in 48 h). The toast says how many of the
  ~210 waiting items were recorded/linked; what stays in Aprovar should be only transfers missing
  their other side and investments on a bank account.
- [ ] Before that, in Aprovar, check once that **card purchases come as −R$ purchases, not +
  credits/"Estorno"** (`SELECT name, charge_sign, charge_sign_source FROM open_finance_accounts`):
  the auto engine records whatever sign was learned.
- [ ] Turn on **Ignorar avisos dos bancos conectados**; check a Flash purchase still reaches Aprovar
  and an Itaú/BTG/BB notification does not.
- [ ] **Histórico**: "Ver prévia" with 365 days, read the counts per account, then "Trazer o
  histórico". Afterwards every account should read "Confere"; if not, "Ver a conferência" now says
  why per line and how the balance difference splits (only bank / awaiting / only app / before the
  window — the last one is the account's initial balance in the app).
- [ ] Investimentos: after a pull, Ajustes › Open Finance › "Carteira da corretora" shows quantities
  per asset and the cash (with "a liquidar" for D+1/D+2). The BTG operations of the last months may
  link to typed ones (same asset, quantity, ±2 days) or be recorded; check the Extrato
  (investimentos) for duplicates before trusting it.

**Unknown until the first real pull (code has fallbacks; adjust on the real rows):**
- [ ] Whether MeuPluggy's investment transactions have an `id` (the key falls back to investment +
  trade date + type + quantity + amount), the shape of `expenses` (number or object; both handled),
  and whether `/investments/{id}/transactions` paginates as assumed (`page`/`totalPages`).
- [ ] Whether ETFs/FIIs come as `EQUITY` (the probe said all 17 equities are `EQUITY/STOCK`); the
  app's own class (or the B3 catalog) decides; an unknown ticker is `HELD unknown_asset`.
- [ ] The Pluggy category table (`open_finance_categories.py`) was written from Pluggy's public tree;
  tune it on what the owner's rows actually carry.
- [ ] The BTG Investimentos account's own categories: only `04…`/Pix/TED rows become transfers;
  if aportes arrive with another category they will be `COVERED` and the bank side will wait in
  Aprovar as a one-sided transfer.

**Not built / limits:**
- [ ] Fixed income, Tesouro, custody `TRANSFER` and `INTEREST` operations are `HELD` and only listed
  ("operações para você lançar"); recording them needs per-title metadata (`services/treasury.py`,
  coupons 040).
- [ ] A `conflict` (the bank changed/dropped a row the owner had edited) has no "resolvido" action:
  the owner edits or deletes the lançamento; the line stays in the Conferência.
- [ ] A transfer to an account that is not connected (Flash, another bank) stays in Aprovar for the
  owner; a Pix to someone else is held 2 days (`TRANSFER_HOLD_DAYS`) and then recorded as
  despesa/receita.
- [ ] The APK shows the switches, reasons and the balance explanation, but not the history preview,
  the portfolio check or "Não usar" (web only, like mapping).
- [ ] The web screen was not opened in a browser this session (vite build and node tests only).
- [ ] Carried over from 043: a posting dated older than the 7-day overlap is never pulled (widen
  `OVERLAP_DAYS` or use the history); a mapping change does not move items already pending;
  connectors send no `totalAmount` (R$ 100 in 3× arrives as R$ 99,99); learning "it's me" (031)
  from a Pluggy counterparty; Conferência matching limits (same signed cents ≤ 3 days, n-cents
  tolerance on installments; it starts at the first row Pluggy brought).

### Plano do mês a partir da renda — what is left
The backend (038) and the Orçamento redesign are in (see `done-tasks.md`, 2026-10-19). Open:
- [ ] Owner check on the phone: Orçamento's sliders (plan sheet and categories) — is a 1-point
  step with − / + fine on the touch screen, and is the "free" part of the track (lighter grey)
  readable in dark mode? Only tried in Chromium at 390 px, light.
- [ ] Owner check after the deploy: Evolução do Patrimônio should open at once after the first
  load of the day (stale history served, refreshed behind). The first open after a server restart
  still waits for Yahoo/BCB; if that is still too slow, warm the cache at boot.
- [ ] Owner check on the phone: Início's new "Resumo do mês" card (in place of Disponível por dia)
  against a real month, with a shared expense; dismiss one of Orçamento's plan flags and confirm it
  stays gone until next month. Both only tried in Chromium on the seed.
- [ ] Inheritance is new for categories: a month without its own rows now shows the previous
  plan's categories (it used to show none). Editing a category in such a month (`?month=`) makes
  the month its own plan first. Check on the server after the deploy that past months read as
  expected; `DELETE /api/monthly-plan` now removes the month's categories with it.
- [ ] Owner check after the deploy, on the phone: open Orçamento in a month planned before 038. A
  plan that had income comes back in % with the same R$; one without income shows "O plano precisa
  da renda" and converts on save (the % left blank). Not tried on a phone yet.
- [ ] Optional, owner's call: "Sem categoria" shows only its % and R$ of Gastar, not what was spent
  outside the categories (the API returns no such figure; month spent − categories' spent is not
  the same rule once subcategories roll up, so it was not computed on the client).

### Home server — what is left
The server is the only backend since 2026-10-16 (`DEPLOY.md`; see `docs/done-tasks.md`). Open:
- [ ] **Daily encrypted cloud backup of the database** (the owner will do it). Today the backups
  share the volume's disk. Plan: `rclone` on the server with a `gdrive` remote and a `crypt`
  remote over it; a systemd timer runs once a day, copies a fresh snapshot of `finance.db` (and
  `attachments/`) out of the `financas_data` volume through a throwaway container, and uploads it
  to the crypt remote; keep 30 days (`rclone delete --min-age 30d`). Done only after a **tested
  restore**: download, decrypt, open with SQLite, `pragma integrity_check`, compare table counts.
- [ ] Delete the PC's old `backend\finance.db*` once the owner is sure; the copy is in
  `Documents\Financas-backup-pc-20261016\`. The PC's `backend\backups\` (15 files) was left as is.
- [ ] `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19: check that the first workflow run on
  Ubuntu 26 after that date is green (test, build, deploy; `setup-python` 3.14 and `setup-node` 24
  on the new image).

### Bug fixes of 2026-10-18 — what is left
Five bugs from the owner's review were fixed in one PR (see `docs/done-tasks.md`): the transfer
500 against Aprovar, the next invoice per card, categories by id, the rename everywhere, each card
purchase its own `client_id` (migration 035). Open:
- [ ] **Owner, after the deploy:** open Cartões once (035 runs at boot) and check that two identical
  purchases on one day are two rows; on a day between a 3/10 card's closing and due day, Início
  shows "Fatura de <mês>" with that invoice and "Pagar fatura", and Cartões agrees. Tested in
  pytest/node and built; not clicked through in a browser.
- [ ] Card purchases already moved out of their category by a rename made before this fix keep
  the old text and count in no budget: the backfill cannot know where they belonged, and a card
  purchase's category cannot be edited on screen. Either an "Editar categoria" on a card purchase
  (every installment, by `client_id`) or a one-off repair on the server.
- [ ] Identical purchases shared or marked paid together before the fix are split into two by the
  backfill, each keeping the share fields the pair got (the split was spread over both). Check
  A receber after the deploy and redo the share on the purchase it was meant for.
- [ ] Início's "Despesas por categoria" still groups by the name, so the root "Outros" and
  "Lazer › Outros" are one slice there (the budget is per id). Owner's call whether that view should
  show the parent.
- [ ] The outbox retries any 5xx (server down or restarting), so a 500 from a bug is retried until
  the fix is deployed — then it goes through with the same `client_id`, as the transfer will. To
  stop earlier, cap the retries of a plain 500 in `outboxRules.js` and `OutboxRules.java` together.
- [ ] The old list `POST /api/cc-expenses` (no screen uses it, tests do) now gives each purchase a
  `client_id`, rounds and refuses `PAID`, but still takes the invoice month as sent (so it can
  write into a paid invoice). Give it the unpaid-invoice rule, or remove it with the tests that
  use it as a fixture.

### Card history (037, 2026-10-18) — what is left
Purchase deletion, purchases into paid invoices, card deletion and payment undo were fixed (see
`docs/done-tasks.md`). Open:
- [ ] **Owner, after the deploy:** look in Cartões for an old invoice already paid by autopay that
  still shows an item "Em atraso" (a purchase entered after the debit, before this fix). It is not
  moved automatically — nothing tells a late purchase from an item reopened by hand. Either pay it
  with "Pagar" (a second payment for the rest), or Extrato › the autopay's "⋯" › Desfazer
  pagamento and pay the whole invoice again.
- [ ] Cards deleted before 037 took their purchases with them; their payments are still in the
  Extrato. Each can now be removed by "Desfazer pagamento" (the money returns to the account
  balance) — the owner decides whether those payments are history to keep.
- [ ] No list of archived cards and no "unarchive". If a card is deleted by mistake, its name
  cannot be reused; reactivating it needs a SQL `UPDATE credit_cards SET archived_at = NULL`.
- [ ] Cartões shows only open invoices, so "Desfazer pagamento" lives only in the Extrato.

### Owner's review, "Média" and "Baixa" (2026-10-18 night) — what is left
Items 4–21 of the review were fixed in one PR (see `docs/done-tasks.md`). Open:
- [ ] **Aprovar, "3x de R$ 50,00"** (item 19): `NotifyParsers` now reads that R$ as the
  installment and records 3 × 50 (or the total when the text also has one). Written against
  hand-made texts, not a capture — the convention asks for a capture first. On the first real
  installment notification, export it and turn it into a `NotifyParsersTest` case.
- [ ] **Server, after the deploy:** if the server's `.env` still has an example `JWT_SECRET`
  (`troque-esta-chave-em-producao`, empty…), the app now generates one into `/data/.jwt_secret`
  (next to the DB) and every device has to log in once. Signup is closed while a user exists; set
  `ALLOW_SIGNUP=1` in `.env` only to add a second user.
- [ ] Dates already stored without the leading zero ("2026-1-5") before the fix stay as they are.
  A one-off check on the server: `SELECT COUNT(*) FROM transactions WHERE length(date) < 10` (and
  `cc_expenses.purchase_date`, `recurring_transactions.start_date`); fix by hand if any.
- [ ] A recurrence in an archived account no longer posts; `/run` returns it in `blocked` and the
  screens say so. Its occurrences stay pending until the owner edits it and picks another account.
- [ ] **Owner walk-through:** Ajustes › Contas (Editar conta, Tornar padrão, Desvincular da carteira,
  Arquivadas › Reativar), Ajustes › Cartões › "⋯" › Editar cartão, editing a lançamento of an
  archived account in the Extrato. Clicked through in Chromium (390 px and desktop) on a throwaway
  DB; not on the phone or on real data.

### Aprovar: ambiguous target and "Sempre perguntar" (2026-10-18) — what is left
- [ ] **Depends on the bank field (owner's "Prompt 1"):** the rule counts only accounts whose bank
  is set. Today that is `accounts.institution`, now editable in Ajustes › Contas › "⋯" › Editar
  conta (2026-10-18 night); existing accounts read as "Sem banco" until the owner fills it.
- [ ] **Owner, after the deploy and the bank field:** set each account's bank. With two Itaú accounts, a Pix from Itaú
  should ask every time and offer no "Lembrar a escolha". Try "Trocar" on a remembered item and the
  Ajustes › Aprovar switch. Tested in pytest/node and screenshotted at 390 px; not on the phone.
- [ ] Cards have no bank field, so two cards at one bank still remember as before. When a bank
  field lands for accounts and cards (a `bank` column), `bank_of_row()` already reads it first;
  check that its values name the bank in a way `issuer_of_institution()` recognizes.

### Native phone app and the desktop redesign (owner, 2026-10-22)
Decisions in `mobile-docs/native-app.md`; the project docs (architecture, conventions, build,
order, rules, one spec per screen, desktop, agents and prompts) in `mobile-docs/native/`. Step 0
(Kotlin + Compose in the Android project, the native theme from the web's tokens,
`android-check.yml`) is done. Open, in order:
- [ ] **Steps 1–2 — "+ Novo" and Aprovar native, owner's phone check**: both are merged (PRs #32
  and #33) but no session recorded a phone check. Run each spec's Acceptance list
  (`screens/01-novo.md`, `screens/02-aprovar.md`) on the debug APK, online and in airplane mode,
  light and dark. Known, minor: an item left by a save killed mid-POST is sent on the next app open
  (`OutboxPlugin.load()` schedules the worker), not while the app stays closed.
- [ ] **The web's `createEntry()` can still duplicate after a killed tab**: it queues only after
  the failure, so a page closed mid-POST and a second Salvar make two lançamentos under two
  `client_id`s. Native now writes the item to the outbox before the POST and removes it on an
  answer (`EntrySaver.kt`); do the same in `lib/outbox.js` (IndexedDB), with a node test.
- [ ] "+ Novo" leftovers: the launcher shortcut "Novo lançamento" (and later a Quick Settings tile);
  Corrigir on an item the worker already sent still says "pendente atualizada" (web and native
  alike; say "já foi enviado" instead).
- [ ] **The sharing form refuses a comma** (found by the port, same on web and native):
  `shareFormError()` reads the other person's part with `Number()`, so "12,5" gets "Informe a
  parte…" while every other money field takes a comma (`parseMoneyInput()`). Fix both sides with a
  test each (the port mirrors the JS on purpose). Native Extrato and Cartões already read the part
  with `parseMoneyInput()` before `shareFormError()` (`normalizedShare()`); the web still refuses.
- [ ] **pytest fails between 21:00 and midnight local time**:
  `test_fixed_income_interest.py::TestTheCouponReachesTheAccount::test_paid_lands_in_the_portfolio_account_and_scheduled_waits`
  (`assert 0 == 1`) — at that hour UTC is already the next day, so the test's `days(0)` and
  `apply_paid_proceeds()`'s "today" disagree. Seen 2026-10-22 21:43 local; find which side uses
  UTC and make both the local date, as everything else does.
- [ ] **Step 3 — Início and the bell native, owner's phone check** (built 2026-10-23, PR #38,
  native-level 5): run `screens/03-inicio.md`'s Acceptance on the debug APK and compare with the
  web on the same data (the spec's "Comparing native and web"). Open from that session:
  - toggling the eye natively and then following a link can show the web's values unmasked for a
    moment, until the web reads `getValuesHidden()` on resume (reviewer's minor 6);
  - native and web keep separate dismissed-card lists (one per store; the bell lists all anyway).
- [ ] **Step 4 — Extrato and Cartões native, owner's phone check** (built 2026-10-24 on
  `claude/native-session-a`, native-level 6): run `screens/04-extrato.md` and `05-cartoes.md`'s
  Acceptance on the debug APK (camera receipt, export to WhatsApp/Drive, pay and "Desfazer
  pagamento", a refund in a paid invoice, "De quem é?" with "12,5"). Left from that session:
  - not built natively: swipe-to-delete and a long-press menu, the flash on rows just written,
    attaching a PDF from another app's share sheet, the card carousel, the "Próxima fatura" widget,
    refunds queued offline (owner decision: they carry `client_id`, so they could be);
  - a day that has pending outbox rows shows the server's day total (without them);
  - the web Extrato's unfiltered list and its projections still read the whole history
    (`useLancamentos()`); switch them to the pages and to `/api/home`'s `projections`;
- [ ] **Steps 5–6 — Orçamento, Recorrentes, Metas, A receber and Ajustes native, owner's phone
  check** (built 2026-10-24 on `claude/practical-hamilton-e6nxfi`, native-level 7): run the
  Acceptance of `screens/08-orcamento.md`, `09-recorrentes.md`, `10-metas.md`, `06-a-receber.md`
  and `11-ajustes.md` on the debug APK, light and dark, online and in airplane mode. Left from
  that session:
  - not built: month swipe and pull to refresh in Orçamento, swipe/long-press menus, the widgets
    (Saldo do plano, a pinned goal), "Sempre perguntar" inside native Aprovar, the biometric gate
    on Sair, the listener-lost notification;
  - privacy is as on the web (Recorrentes and A receber mask nothing; Metas masks Atual, Faltam,
    Objetivo): the owner may want more masked;
  - the native and web dismissed plan-flag lists are separate (like Início's cards).
- [ ] **Step 7 — Investimentos native, owner's phone check** (built 2026-10-24 on
  `claude/native-session-d`, native-level 8: all seven tabs): run the Acceptance of
  `screens/12-…` to `16-…` on the debug APK, light and dark, online and in airplane mode, and
  compare with the web on the same data. Left from that session:
  - **offline**: a buy/sale and a provento are queued (kinds `INVESTMENT`, `PROCEED`); check that
    one saved in airplane mode lands once after reconnecting, with its Extrato row in the
    Corretora, and that Pendentes shows it with only "Descartar". The web itself still
    sends no `client_id` on investment creations and never queues them (owner: want that too?);
  - **privacy**: owner chose 2026-10-24 to mask every R$ of Operações and Proventos on both
    sides (the web follows since `claude/web-privacy-investments`); check it on the phone too;
  - not built natively: pull-to-refresh, swipe on cards, a press-and-drag chart crosshair (a tap
    selects), landscape charts, the shell "+" opening Registrar operação inside Investimentos
    (`NativeScreens.open("investment-entry")`), remembering the last asset type, the "próximos 30
    dias" total and a payment-day notification in Proventos, the DARF reminder, copying a
    suggested aporte into Registrar operação;
- [ ] **Session E — the native shell and no WebView, owner's phone check** (built 2026-10-25 on
  `claude/affectionate-thompson-3vd16f`; the PR body has the full checklist). Install the debug APK
  first, then the release one over the WebView app from its banner: fresh login, every section,
  offline entry with the app closed, bank notifications reaching Aprovar, the APK banner. Left:
  - the "+" inside Investimentos opens "+ Novo", not Registrar operação (that sheet lives in the
    Posição/Operações view models); the launcher shortcut "Novo lançamento";
  - "Sem conexão" in the pill is the phone's network (no non-VPN network), not the server's
    reachability: with Tailscale down and Wi-Fi up it stays hidden until a request fails;
  - Importar, Regras de importação, Integrações, the full IR report and editing allocation
    targets/sectors are desktop-only (owner, session E): the desktop redesign gives them a home;
  - `GET /api/home/panels` feeds only the native Início: the web Início still computes the same
    four panels from the whole history (`useInicioMovements()`); switch it over and drop
    `buildSpending()` from `Dashboard.jsx`.
- [ ] **Desktop redesign** for ≥ 1280 px (sidebar, tables, columns, analysis first): a plan per
  screen here before it starts.
- [ ] **Session containers cannot build an APK**: `dl.google.com` is blocked by the environment's
  network policy. The owner can allow it (environment settings › Network access › Allowed
  domains); until then every native change is first compiled by `android-check.yml` on the branch.
  (A session on the owner's PC can: `gradlew.bat --offline testDebugUnitTest assembleDebug` with
  Android Studio's JDK, as session A did.)
- [ ] Plus Jakarta Sans in the native screens (needs the `.ttf` in `res/font`; the web ships woff2).
- [ ] **`findings.md`, what is left** (its possible bugs and stale texts were fixed 2026-10-23,
  the grouped Tesouro delete made atomic 2026-10-24, `done-tasks.md`): the native shell's 401
  handling is done (session E). Inconsistencies waiting on the owner
  (questions in `docs/handoff.md`): Corretora accounts offered in banking forms and autopay; Início
  groups categories by name; privacy mode uneven across screens; the Extrato vs Início
  classification of a transfer to the Corretora; a débito purchase reopened as Despesa by
  Corrigir; 48 vs 72 installments and the required description; the two `/api/credit-cards`
  cache keys; cards without a bank field.
- [ ] **Investimentos native, what session B left** (2026-10-24, backend, chart kit and ports
  done, `done-tasks.md`):
  - **Not clicked through**: the grouped delete (`DELETE /api/investments/by-assets`) is covered by
    pytest and the screen's call is one line, but the session's walk ran out of grouped lots after
    the redemption. Owner: delete a Tesouro title with two buys once on the server.
  - The CDI on `benchmarks[]` (`14-…`) is still an open endpoint choice: session D builds the CDI
    card on the client in both (`comparisonItems()` / `ReturnsRules.comparisonItems()`).
- [ ] **What the home/attention/invoices proposal left open** (§1–4 built in session 6,
  `done-tasks.md`):
  - **B2, owner decision**: the plan's "spent" (`month_banking_totals()`) still counts a despesa
    typed in a Corretora account; Início's "Saiu" (`/api/home`) does not. Make the plan follow
    Início (one rule) or keep both?
  - **The web Início and Extrato still read the whole history**: the four history panels are
    served since session E (`GET /api/home/panels`, read by the native Início), but the web
    Início still computes them (`['inicio','movimentos']`) and the web Extrato's projections still
    read `GET /api/cc-expenses?status=OPEN` in `useLancamentos()` (native reads `/api/home`'s
    `projections`). Switch both; then Início stops calling `GET /api/transactions` and
    `bankingTransactions()` / `isPastDue()` leave the client.
  - **Owner, after the deploy**: open Início, the bell, Extrato and Cartões on the real server once
    and compare with the day before (the parity check ran on a seeded database, not on real data).
- [ ] **Owner decision**: may `android-check.yml` upload a branch's debug APK as a workflow
  artifact, to try a branch on the phone before the merge? (CLAUDE.md says APKs never go to GitHub.)

### Mobile app — an Android APK with offline entry and bank notifications
The plan, its decisions and the status of each phase are in `mobile-docs/steps-to-production.md`.
Phase 3 (idempotent creation) and the PC halves of Phases 1 and 4 were built on 2026-10-13, Phase 2
on the PC and Phase 5 (built, installed on the phone) on 2026-10-16, and Phase 6's listener and
capture mode on 2026-10-17 (see `docs/done-tasks.md`). Open, in order:
- [ ] Phase 5, the last phone checks. The APK is built, signed and installed on the owner's Galaxy
  S25; login, real data, the bars in the theme and the offline queue work there. Left:
  - the "done when" with the app really **closed** (swiped from recent apps): airplane mode,
    three entries, close, reconnect without opening it, all three on the server once. On 2026-10-16
    one offline entry was sent by the WorkManager job (logcat: `OutboxWorker` RETRY, then
    SUCCESS 30 s later) and arrived once, but the app was still on screen. If Samsung's battery
    management holds the job with the app closed, set the app's battery use to "Sem restrições";
  - the back button, the theme choice (Ajustes › Aparência), the keyboard over "+ Novo" (and whether the decimal
    keypad's comma is accepted by the amount field), the notification permission prompt.
- [ ] Native sender backoff (`OutboxWorker`): `Result.retry()` with EXPONENTIAL from 30 s, which
  WorkManager caps at 5 h. With the server off or Tailscale down for an hour or two, the job is
  already waiting about an hour between tries, so with the app closed an entry can sit that long
  after the server is back. Opening the app sends at once (the screen's flush). Consider LINEAR
  backoff or a cap (re-enqueue with a fixed delay after N tries) and test it on the phone.
- [ ] Native `OutboxWorker.schedule()` uses `ExistingWorkPolicy.KEEP`: an item put just as a
  running job finishes its last pass is not picked up until the next trigger (app opened, the
  screen's 30 s flush). A small window; `APPEND_OR_REPLACE` would close it.
- [ ] Browser outbox (`lib/outbox.js` `flush()`): it writes the result back from the item it sent,
  so an item corrected or discarded during that one request can be overwritten, removed or
  brought back. The native sender compares versions first (`OutboxStore.removeIfUnchanged`); do
  the same on the web side, with a rule test. A small window, found by `finance-guard` on 2026-10-16.
- [ ] Owner look at Phase 4 on the PC. Its "done when" passed in a scripted desktop browser on a
  scratch database (2026-10-13, see `docs/done-tasks.md`); nobody has yet judged the screens by
  eye: the "Pendentes" sheet, the pending rows in the Extrato, the estimate labels. With the
  backend stopped a browser cannot load a screen it has not visited (each screen's code comes from
  the server on first visit, and there is no service worker), so only the APK opens cold offline.
- [ ] Phase 1, phone half: the APK reaches the server (`https://<server>.<tailnet>.ts.net`)
  from the phone, so the tailnet path works. Left only the phone's *browser* on mobile data, which
  matters little now that the APK exists.
- [ ] Phase 4, step 7, partly built: with the server unreachable a pill in the header says so and
  an online-only action fails with "Sem conexão com o servidor. Esta ação só funciona conectado.",
  but the buttons themselves are not disabled screen by screen.
- [ ] A pending item's "Corrigir" reopens the "+ Novo" sheet; a pending card purchase has no row
  on the Cartões screen (it is listed only in "Pendentes").
- [ ] Início's notice counts only the pending items that move a balance ("Saldo estimado: 2
  lançamentos…" beside a header pill saying "3 pendentes" when the third is a card purchase).
  Correct, but the two numbers side by side may read as a mismatch; owner's call.
- [ ] Phase 2's "done when", on the phone once Phase 1's phone half works: enter a despesa
  one-handed in under ten seconds. The comma is settled for lançamentos (2026-10-18: "+ Novo",
  Extrato edit and Aprovar are text fields parsed by `parseMoneyInput()`, checked on the phone).
  The layout itself was fixed on the PC on 2026-10-16 (see `docs/done-tasks.md`).
- [ ] The other money fields are still `type="number"` (Metas, Orçamento, Recorrentes, Ajustes ›
  Contas' initial balance, ShareFields, Extrato's min/max filter, the investment forms): give them
  the same `type="text" inputMode="decimal"` + `parseMoneyInput()` swap.
- [ ] Phone layout leftovers seen 2026-10-18 at 360 px: Início's attention cards ~170 px each;
  "indisponível" benchmark cards in Rentabilidade take a full card each; charts are 286 px wide
  (page gutter + panel padding).
- [ ] **Phase 6 on the phone** (listener, capture mode and Ajustes › Notificações dos bancos built
  2026-10-17, see `docs/done-tasks.md`; native level 2). CI published APK 10013 and the test APK
  `/apk/financas-debug.apk` the same day (deploy run 13, green). Check: the real app updates to
  10013 by "Nova versão disponível"; notification access granted to it (if Android says "Configuração restrita", the
  steps are on the screen); the test APK installed with `adb install -r financas-debug.apk`, logged
  in, access granted to "Finanças debug", capture on; the screen's adb command makes the
  notification appear in the test APK's capture — and **not** in the real app's; one export (JSON
  and text) opens the share sheet. If the adb notification does not appear, `adb logcat -s
  FinancasNotify` names the package it came from.
- [ ] **Install the APK with the parsers and check Aprovar** (owner; built 2026-10-17, see
  `docs/done-tasks.md`, "Notification auto-identifier"). CI builds it on the push; update by
  "Nova versão disponível". Then a Pix between two of your accounts, a Pix to someone else and a
  card purchase: each must appear in Lançamentos › Aprovar (the first as one transfer, the second
  as a despesa "Pix para …", the third with "crédito ou débito?"). The first own-account Pix must
  have **both** banks notify (or be approved as a transfer once) before a single-leg Pix to
  yourself is recognised: the "it's me" CPF digits are learned, never typed.
- [ ] **Keep capturing, then a third parser pass.** The second pass (2026-10-22, 60 notifications)
  fixed the Samsung Wallet purchase ("<LUGAR> R$ <valor>" with the card name as the title, never
  read before) and BB's "Pix Recebido" sender name. Still unseen: any **Flash** app notification
  (the app was added to the allow-list on 2026-10-22 and its texts go through the generic parser —
  capture one purchase and one benefit credit, "você recebeu R$ … de benefício" is not a detection
  today), a credit/debit purchase with "final 1234", Itaú and BB purchases, an estorno, a declined
  purchase, a boleto payment, BTG Investimentos' buy and sell. Keep capture on and bring a new
  "Exportar JSON"; anything mis-read becomes a `NotifyParsersTest` case first. Not answered by the
  export either: whether a bank *updates* a notification (new posted time, same key) — BTG posts
  "Compra autorizada" twice, ~25 ms apart, with different keys; the server folds them as `repeated`.
- [ ] **Confirm the Flash package name** (owner). `br.com.flashapp` comes from two third-party app
  listings (the Play Store page could not be opened from the cloud session). Ajustes › Notificações
  dos bancos shows whether "Flash" is installed: if it says not installed while the app is on the
  phone, the package is different — fix `NotifyRules.APPS`, the manifest `<queries>`,
  `NotifyPairing.issuerOf()` and `FLASH_APP` in `services/inbox.py` together.
- [ ] **"Card used for Meal and Voucher" is assumed to be the Flash.** Samsung Wallet's generic
  label for a meal/voucher card maps to the issuer `flash` (`ISSUER_ALIASES`). If the owner ever
  adds a second benefits card (Alelo, VR…) to Samsung Wallet, both would read as the Flash: then
  the label stops being enough and the pick goes to the hint (the owner chooses once per card name).
- [ ] **Card estorno from Aprovar.** A card refund exists now (033, `POST /api/cc-expenses/refunds`),
  but an estorno detection still drafts an INCOME lançamento. Once a real estorno capture shows
  the card final, approve it as a card refund instead.
- [ ] **Aprovar × Recorrentes, what is left** (034, 2026-10-18). Owner walk-through: a Netflix
  (or similar) recurrence, its card purchase notification → the item says "Recorrente: ao aprovar…"
  → approve → Recorrentes shows the next month as próxima and no pending; the salary's Pix the same
  way. Not built: (1) an occurrence `/run` **already wrote** is a candidate only at the exact amount
  — at a new price the notification is approved as a second lançamento; (2) a price change is not
  carried back into the recurrence's amount; (3) a settlement is not undone if the approved
  lançamento is deleted (same as a `/run` row). Tune `RECURRING_MATCH_DAYS` / the 20% tolerance
  from real use.
- [ ] **Bank × Samsung Wallet window**: the server pairs them (`services/inbox.py`, 10 min, bank
  wins). From an export with both notifications of the same purchase, show the owner the lag and
  tune `NOTIFY_WINDOW_MS` (and `NotifyPairing.DEFAULT_WINDOW_MS`, kept equal). The phone-side
  `NotifyPairing` stays unwired: the phone sends every detection at once and the server pairs,
  so a held Samsung detection needs no WorkManager timer.
- [ ] **Mapping screen** (Phase 6 step 5) — not built: Aprovar's remembered choices
  (`inbox_hints`) already do the job of "this card final / this app is that card or account",
  learned on the first approval. Build it only if the owner wants to set them up front.
- [ ] Unrecognised text from an allowed app (Phase 6 step 6) is **not** sent: the texts never
  leave the phone. Only the capture export shows what the parsers missed.
- [ ] `DEPLOY.md` ("Updating the phone") does not mention `/apk/financas-debug.apk` or the
  `.debug` package; left alone because another session owns that file.
- [ ] Brokerage operations from notifications (owner, 2026-10-17; plan in
  `mobile-docs/steps-to-production.md`, "Brokerage notifications" and Phase 7 step 7): a BTG
  Investimentos detection becomes a "Registrar operação" suggestion cash linked to the brokerage
  account; `POST /api/investments` needs a `client_id` first. The owner needs a BRL account for
  the brokerage in Ajustes › Contas.
- [ ] Phases 7 to 9 (inbox, statement dedup, hardening).
- [ ] **APK on every deploy — phone check** (2026-10-22): after the next push to `main`, the
  `apk` job must run even with no change under `frontend/android/` (Actions › deploy), and the
  phone must show "Nova versão disponível" and install it from the app, data kept. Each deploy now
  adds ~5 min of runner time and a new `financas-<code>.apk` (the last three stay on the server).

### Card purchase edit and debit on Cartões (049, 2026-10-28) — what is left
- **APK not compiled**: `PurchaseEdit.kt`, `CartoesScreen/ViewModel.kt`, `ExtratoScreen/ViewModel.kt`
  were checked by reading; only `rules/`/`data/` ran (JVM). CI's apk job is the first real build.
- Owner: walk Cartões on the phone — tap a purchase → category; Flash and the BTG debit list.
- Old debit purchases of a card with **both** functions have no `card_id` (only new ones from
  "+ Novo"/Aprovar); a debit-only card lists all expenses of its account. A Pluggy-recorded debit
  purchase never gets `card_id` (Pluggy doesn't say the card).

### Card débito and hourly quotes (2026-10-22) — what is left
- [ ] **Owner walk-through.** Ajustes › Cartões: create the Flash as "Débito" with a "Flash" account
  (any type but Corretora), give the BTG card "Os dois" with BTG Banking as the debit account. Then
  "+ Novo › Cartão": the BTG card offers Crédito/Débito, the Flash is débito only; a débito
  purchase must land in the account (Extrato), never in Cartões. In Aprovar, the Samsung "Card used
  for Meal and Voucher" purchase must arrive as a despesa in the Flash account, confirmed once.
- [ ] **A débito purchase does not remember its card.** It is a plain EXPENSE in the card's account
  (`transactions` has no card column); the Extrato shows the account, not "Flash". Add a
  `metadata.card_id` (or a column) only if the owner wants to filter by card.
- [ ] **Benefit credits of the Flash** (the monthly VR/VA deposit) are not detected: no capture yet.
  Until then, register the deposit as a receita in the Flash account (or a recurrence).
- [ ] **Hourly quotes and brapi's quota.** `services/quote_refresh.py` runs every
  `QUOTE_AUTO_REFRESH_SECONDS` (3600) around the clock, weekends included (crypto moves). With
  `BRAPI_MAX_SYMBOLS_PER_REQUEST=1` each run costs one brapi request per held ticker (~720 runs a
  month × tickers). If brapi's monthly limit is reached, raise the interval in the server's `.env`
  or skip runs outside B3 hours (not built: the owner asked for every hour).

### Bug hunt by fuzzing (2026-10-22) — what is left
- [ ] **Rows already stored with absurd values are not cleaned.** The fixes refuse new ones; a
  production row with a year outside 1900–2199, an amount of 0 or a 1e308 operation (none expected)
  would still break its reads. If a screen ever answers 500, look for such a row first.
- [ ] **Not fuzzed:** the frontend (no runner), the Java listener and parsers, the import's CSV/OFX
  content itself (only the route's fields), and the file uploads (receipts).
- [ ] **The proceeds' amounts** (`gross_amount`, `tax_amount`, `amount_per_unit`) and the corporate
  action ratios have no upper bound; nothing broke in the run, so they were left alone.

### Investments separate from banking — what is left
Built on 2026-10-12 and 2026-10-17 (see `docs/done-tasks.md`): every operation comes out of the
portfolio account (a Corretora account) unless "Não descontar de nenhuma conta" is ticked,
Início shows the banking area only, and "+ Novo" is banking-only. Since 039 (2026-10-19)
Investimento is not a category: a typed aporte is a transfer to the Corretora. Open:
- [ ] Owner, after the deploy that runs 039: the old "Investimento" lançamentos are transfers to the
  Corretora (bank balances unchanged); if no Corretora existed, one named "Corretora" (balance 0)
  appeared — its "Saldo na corretora" is the net of those old aportes until its initial balance is
  set; Ajustes › Regras: rules that chose "Investimento" are switched off — point them elsewhere
  or delete them. Not run on the owner's data (the counts are unknown here).
- [ ] Left by 039 as they were, and now counted as despesa/receita: an "Investimento" row typed
  inside the portfolio Corretora itself, or in a non-BRL account. Check on the server:
  `SELECT COUNT(*) FROM transactions WHERE category = 'Investimento' AND type <> 'TRANSFER'`.
- [ ] The Extrato shows a transfer to the Corretora as "Transferência" (its badge and totals), not
  "Aporte"; Início already reads it as an aporte. Owner's call whether the Extrato should too.
- [ ] Imports and Aprovar have no "transfer to the Corretora" target: a BTG transfer seen in a bank
  statement imports as a despesa ("Outros") and must be recorded as a transfer by hand (Aprovar's
  own-account pairing already drafts one when both legs are seen).
- [ ] Owner, on the server: Ajustes › Contas → "Vincular à carteira" on the brokerage account (or
  create one of type Corretora with its current balance); register one operation as is and one
  with "Não descontar de nenhuma conta"; check the brokerage balance, the Extrato and Operações
  ("no extrato"). Clicked through on a scratch database only.
- [ ] Owner, on the server: after linking the account, a provento paid from that day on appears
  in the Extrato as "Provento" in the brokerage account on its payment day (not before). Tested
  in the backend only; no screen walk.
- [ ] Owner's call — the "no mês" pill on Início is now the accounts' net movement (receitas −
  despesas − aportes + resgates, the chart's "Resultado"). It used to be receitas − despesas,
  which read as "how much net worth moved". Say so if the old meaning is the wanted one.
- [ ] Owner's call — goals: a `NET_WORTH` goal (Planejamento → Metas) still adds accounts and
  portfolio. It is the one place left where the two areas are summed. Related: moving Metas to
  Investimentos.
- [ ] Owner's call: the same opt-in for proventos (they never reach an account); remembering the
  checkbox's last choice on this device.
- [ ] Not guarded: deleting a movement (or its whole asset) removes the linked lançamento together
  with its receipts, as before. The explicit unlink and an edit that would leave nothing to write
  are refused.
- [ ] No migration was written: a database from before 2026-10-12 restored into this code keeps its
  linked rows while its movements carry no `cash_account_id` — each row goes away on the next edit
  of its movement. Write a data migration first if the old data
  (`backend/backups/finance-pre-areas-separation-20261012-224633.db`) is ever brought back.
- [ ] Owner's call — the backend still carries multi-currency (migration 018: `services/fx.py`,
  conversion in `services/investments.py`, the IR report's exterior apuração, about a dozen
  modules). The screens are reais-only since 2026-10-12, so nothing reaches it, but the API still
  accepts `currency` on an account or an operation. Removing it means refusing the field, deleting
  `test_multicurrency.py` and unpicking the conversion from the stream FIFO and IR read — a real
  refactor with no visible change. Until then a lançamento posted into a foreign-currency account
  is not converted (no currency check in `routes/cards.py` or `routes/transactions.py`).
- [ ] Tests, low: pin that a refused edit also undoes the price quote and the quantity, the
  redemption branch of the "nothing to write" refusal, and a batch `POST` whose second item is
  refused. All three behave correctly in `finance-guard`'s scratch tests.

### Investments check (2026-10-17) — what is left
The check fixed the cost rule (weighted average instead of FIFO, one cost for Posição, evolution,
realized result and Bens e Direitos), ETFs/BDRs without the R$ 20 mil exemption, the per-sale IR
(the sale's share of the month's tax) and smaller screen errors — see `docs/done-tasks.md`. Open:
- [ ] **Owner, after the deploy:** open IR 2025 again. Cost and realized results changed from FIFO
  to the average cost, so a sale after buys at different prices has a different result, and the
  loss balance can change. Compare Posição's preço médio with the broker's or Investidor10's.
- [ ] ETF de renda fixa: only the tickers in `market_catalog.FIXED_INCOME_ETFS` are known (LFTB11
  included). Another one would be taxed as an ETF de ações (15% via DARF) — add it to the list.
  Its per-sale IR still shows the 15% estimate; the real rate (15/20/25% by the fund's term) is
  withheld by the administrator.
- [ ] Bens e Direitos: ETFs now get **07.09** (from a 2022 source) and BDRs **04.04**; confirm
  both codes in the 2026 program.
- [ ] A bonificação with an attributed cost (`bonus_unit_cost`) does not produce the isentos line
  **18** (incorporação de reservas/bonificações).
- [ ] Units (TAEE11…) count as ações for the exemption, the common reading; say so if the owner's
  accountant disagrees.
- [ ] Sales of foreign assets and of "outros" keep a per-sale 15% estimate in Operações; the IR
  tab has the annual (exterior) and GCAP views.

### Operações edit and fixed-income coupons (2026-10-19) — what is left
- [ ] After the deploy: open Proventos once so 040 runs (it rebuilds `investment_proceeds`; the
  boot backup is the way back), then register a real coupon. In Operações, edit a sale (the
  quantity shows without "-") and then another operação straight away: "Salvar" must be free.
- [ ] **An amortization does not lower the title's value in Posição.** It is a provento (cash in,
  counted in total return), as it was before 040; the title keeps its full principal accruing. To
  follow a debênture that amortizes, register the payment and adjust the title (or record the
  amortization as a partial resgate instead). Modelling amortization as principal returned is an
  owner decision.
- [ ] Proventos' history filter opens on the current year: coupons scheduled for later years show
  in the 180-day calendar but not in the list until "Fim" moves. Consider defaulting "Fim" further.
- [ ] Editing a coupon sends its stored IR back, so moving its payment date keeps the old IR; blank
  the IR field to recompute it from the regressive table.
- [ ] A coupon with IR 0 goes to "12 - Rendimentos de LCI, LCA, CRI e CRA" (the resgate's rule). An
  incentivized debênture's interest may belong in another isentos line; check with the accountant.

### Asset categories and proventos by type (2026-10-19) — what is left
- [ ] Owner walk-through after the deploy: Registrar provento (type first, then the asset search),
  a sale picked by typing, a buy as "ETFs" and as "Tesouro Direto" (the title name fills
  Rentabilidade), Posição › Tesouro Direto, Alocação › Por setor (renda fixa by indexer).
- [ ] **Old Tesouro titles registered as CDB (or another type) stay in Renda fixa** — the name only
  decides for a title without a type. Fix each in Operações › Editar › Tipo de título → "Tesouro
  Direto". No migration rewrites them.
- [ ] **Alocação › Por classe, the class targets, the goals and Rentabilidade's class filter still
  use the four DB classes** (ETFs inside Ações, Tesouro inside Renda Fixa). Targets per category
  would need `allocation_targets` to accept them (its `CHECK` lists the classes) — an owner
  decision, with a table rebuild. Posição's donut, its tabs, Operações, Proventos and the sectors
  already show the categories.
- [ ] Tesouro Selic is modelled as % of the CDI (Selic ≈ CDI + ~0.1 pp); a Selic indexer (BCB
  series 11) would be exact.
- [ ] The Proventos filter panel's "Ativo" is still a plain select; the search is in the form only.
- [ ] Not tried on the phone (the asset list now opens in the flow of the sheet, not floating).

### Tesouro Direto marked to market (2026-10-19) — what is left
- [ ] **Owner, after the deploy:** Ajustes › Integrações › "Verificar agora" shows "Banco Central
  (SGS)" and "Tesouro Transparente" ok. The likely cause of both failing (2026-10-19, second
  session) was Python 3.13+'s strict X.509 mode refusing the gov.br chains, fixed in
  `gov_http.py`, plus the BCB health probe's 6 s limit — **never confirmed against the real hosts**
  (this cloud container is refused both). If either still fails, the detail now names the cause
  ("certificado recusado (...)", "sem resposta em 30 s", "respondeu HTTP 406", DNS): fix from that.
  Then compare Posição › Tesouro Direto with the BTG statement (2026-10-19: IPCA+ 2045 0,85 títulos
  líq. R$ 1.144,07 / bruto R$ 1.188,36; Renda+ 2065 42,79 títulos líq. R$ 8.881,46 / bruto
  R$ 9.240,47). If the quantity differs, type it in Operações › Editar › "Quantidade de títulos"
  on each purchase. A title that shows "valor segue a curva" has a name without type + year, or
  the file is missing.
- [ ] Renda+/Educa+ custody on an early sale: modelled as the regular 0.20% a.a. from D+1 (not
  before 2025). Confirm with BTG's líquido; if BTG shows less, the rule is different for them.
- [ ] Names stay upper-case (the asset's ticker); BTG shows "Tesouro IPCA+ 2045 (NTNB Princ...)".
- [ ] A redemption of a grouped title writes one row per purchase it touches (oldest first) in
  Operações; the IR report still reads each as a fixed-income sale.
- [ ] The Investidor10 TWR gap (2026: 14.67% vs 16.64%) was mostly this; re-check after the deploy.

### Automatic proventos and the investments Extrato (2026-10-16) — what is left
- [ ] Owner walk-through: Lançamentos → Extrato → "Investimentos" (operações + proventos, search,
  Tudo/Operações/Proventos), and Investimentos → Proventos → "Atualizar". Register a buy with a
  date last year on a stock that paid since, and check its proventos appear within a few seconds;
  delete it and check they go. Tested in pytest and node only; not opened in a browser.
- [ ] The sync only runs while the app is open (screen open or an investment write). A provento
  announced while nobody opens Investimentos lands the next time someone does. A daily job would
  need a scheduler the app does not have.
- [ ] Left after the reconciliation with Investidor10: a few proventos StatusInvest does not list
  (an FII it does not cover, JCP installments with later payment dates) and monthly JCP values
  that differ by centavos between the two sources. Type them by hand if they matter.
- [ ] A ticker that changes code needs a line in `TICKER_ALIASES` (`statusinvest_client.py`);
  until then its proventos stop at the old code. No screen says so.
- [ ] StatusInvest is not in the integrations healthcheck (`services/health.py`): its result is
  recorded (`record_provider_result("statusinvest", ...)`) but no card shows it.
- [ ] Proventos of ETFs and some units are not on StatusInvest's endpoints; none were expected
  for these.

### Plano do mês (2026-10-16) — owner checks
- [ ] Set a plan on the phone (income in reais with a comma, percentages) and confirm the flags make
  sense against a real month.
- [ ] Decide whether Início should show a one-line plan strip (spent / invested vs plan).
- [ ] Confirm on real data that Planejar's Investir realized now matches Início's "Investido" for
  the same month (both count conta → Corretora, 2026-10-19).

### Chart speed and the fair comparison (2026-10-19) — what is left
- Owner check on the server, after the deploy: open Investimentos › Posição and Rentabilidade twice
  (the first open after the deploy writes `/data/history_cache.json`; from then on a restart
  reads it), switch 6M → 1A → 5A → Tudo and a class. Measured only on a synthetic 354-operation,
  5-year portfolio with a simulated 2–3 s network, not against real yfinance/BCB.
- Owner check: Rentabilidade's lines all start at 0% on the left; with a class bought after the
  window's start (e.g. FIIs bought 4 months ago, 1A) the chart starts at that month and the
  Ibovespa/CDI cards cover the same months ("desde a 1ª operação" in the hint).
- The first compared month is still not exact: the portfolio counts from the purchase day, the
  Ibovespa/IFIX/IDIV the whole month (only month-end closes are stored). The CDI could start on the
  purchase day (it is daily); not done.
- A ticker past the 7-day stale limit whose download comes back empty still replaces its old
  history with nothing (as before; the stale path already keeps it).
- Still CPU-bound on a large portfolio: ~0.1 s for 1A, ~0.3 s for 5A on the harness. If the real
  portfolio is much larger, the next step is caching the computed response per (user, period,
  class) keyed by a data version — not built.

### Saving and editing operações without waiting (2026-10-19) — what is left
- Owner check on the server and on the phone: Registrar operação closes right after "Salvar"; an
  edit in Operações closes in under a second; the new quote shows up a few seconds later on its
  own. Measured only on a synthetic portfolio (350 and 1500 operações) in the test client, without
  the real yfinance/BCB or the home server's CPU.
- Not built: the frontend's static files (`/assets/*.js`, 384 KB) still go uncompressed when Flask
  serves them (`routes/frontend.py` uses `send_file`, which `gzip_responses.py` skips on purpose). If
  the first open on the phone is slow, gzip them at build time or behind `tailscale serve`.
- Rentabilidade's daily loop (`daily_group_values()` in `services/returns.py`) scales with open
  positions × days: ~0.23 s on 350 operações, ~0.8 s on 1500 with 225 open CDBs. Off the save path
  now; the response cache in the section above is still the next step if it bites.

### Compound interest calculator (2026-10-18) — what is left
- Owner check: Investimentos › Calculadora on the phone (seven tabs now; the row scrolls).
- Not built, owner's call: IR on the simulated gain (regressive table for fixed income, 15% for
  stocks), a "start from my portfolio" button prefilling the current value, and a reverse mode
  ("how much per month to reach R$ X").

### Owner walk-through on real data
Everything below was built and clicked through on a seeded scratch database (Chrome + Playwright,
2026-09-23); none of it has been used on the owner's real data yet. What each item does is in
`docs/done-tasks.md`.
- [ ] Signup with a username (typed in the browser — Claude only checked it through the API), then
  Ajustes → Perfil.
- [ ] Open an exported `.xlsx` and a `.csv` in Excel (no Excel on the dev machine; the `.xlsx` was
  validated with openpyxl): extrato with filters, operações, proventos, IR. Carteira `.xlsx` was
  checked by the owner 2026-09-26 and its fixes are in; re-export it once to see whole quantities
  without the trailing comma.
- [ ] Budgets under decision 1: card purchases now count in the purchase month and the invoice
  payment no longer counts, so card-heavy categories may read as overrun — re-plan them.
- [ ] Import rules with amount/account conditions on a real bank file.
- [ ] Receipts: a phone photo (HEIC only opens in Safari), a receipt on a card purchase, and after
  the next backup check that `backend/backups/attachments/` holds the files.
- [ ] Ajustes → Integrações: all green? (`BRAPI_TOKEN` is set in `backend/.env`.)
- [ ] Corporate actions: register one real past event (if any) and compare quantities and average
  price with the broker.
- [ ] IR tab for the last year against the broker's informe de rendimentos.
- [ ] Motion and phone layout by eye (scripted checks passed: sheets animate out, count-up only on
  first visit, reduced motion, tab pill).
- [ ] Recorrentes after migration 019 (2026-09-26): pause one, check "pausada desde", resume it
  later — only the paused weeks/months are skipped; anything due before the pause stays pending.
  A recurrence paused *before* 019 still resumes the old way (skips everything up to today).
- [ ] Allocation, goals and the exemption meter (2026-09-26, migrations 020–021): in Investimentos →
  Alocação, set the class targets (and per-asset ones where you have them) and try "Quanto vai
  aportar?" with the next contribution — does the split match what you would do? In Planejamento →
  Metas, recreate the goals kept in Investidor10 and compare the
  estimated dates (theirs seem to assume a return; set "Rentabilidade esperada"). On the IR tab,
  the current month's meter should match Investidor10's "isentômetro" once the same sales are
  recorded here. Open "Registrar operação" → Venda on a stock to see the warning.
- [ ] Proventos por ativo, Rentabilidade (TWR) and Aportes (2026-09-26, built in parallel by three
  subagents, **none opened in a browser yet**): Investimentos → Proventos "Por ativo" table and the
  Mensal/Anual toggle; Posição's new "Proventos" and "Rentab. c/ proventos" columns (9 columns now —
  check the 1280px layout and decide whether "Rentab. c/ proventos" should replace "Rentab.");
  the new Investimentos → Rentabilidade tab (TWR vs Investidor10's "Rentabilidade" and "% do CDI");
  Operações' "Aportes e resgates" chart; Alocação's concentration warning (asset > 10%, no
  exposure abroad). Also: Rentabilidade's class filter, and the four new provento
  columns in the carteira export (open the `.xlsx`).

### Benchmarks, sectors and IRPF text (2026-09-26 night) — owner checks
Built by three subagents, tested with mocks and one live provider run, **not opened in a browser**.
- [ ] Rentabilidade: the benchmark cards and lines (CDI, IPCA, Ibovespa on by default); compare
  Ibovespa's period total with Investidor10.
- [ ] Alocação → "Por setor": press "Buscar setores" once (needs `BRAPI_TOKEN`), check the stock
  sectors and FII segments, fix the wrong ones with the pencil (brapi files some FIIs under the wrong segment).
- [ ] IR tab → "Para colar no programa do IRPF": paste each section into the 2026 program and check
  the FII payouts under isentos **99** "Outros". Fill the "(preencher)" CNPJs. (Tributação
  exclusiva — JCP 10, aplicações 06 — is declared at the net value; the tab, the text and the
  export agree since 2026-10-17.)

### brapi plan allows 1 ticker per request
Found 2026-09-26: a 2-ticker quote call returns 400 `QUOTES_PER_REQUEST_EXCEEDED`, so every
multi-ticker refresh failed on brapi and fell back to yfinance. Since 2026-10-17 the batch size is
`BRAPI_MAX_SYMBOLS_PER_REQUEST` (default 20, as before) and the Integrações card says what to do.
- [ ] Owner's call: set `BRAPI_MAX_SYMBOLS_PER_REQUEST=1` in the server's `.env` (one credit per
  ticker per refresh) to make brapi answer, or leave it and keep yfinance as the de facto source.

### Found while fixing the walk-through inconsistencies (2026-09-27)
- **Budgets on income categories.** Orçamento offers income categories when adding a budget and the
  backend accepts them; their "spent" is the category's income, and `build_budget_month()` adds it
  to `totals.spent`, so the "Realizado" tile and the Início budget strip mix income into "gasto".
  Since 038 a category is a % *of Gastar*, which makes an income category even less meaningful.
  Owner's call: refuse income categories in budgets, or keep them out of the totals.

### Fixed-income form (2026-09-27 night) — leftovers
Exemption by title type, IPCA+ in Rentabilidade and the removal of Gado are built (see
`docs/done-tasks.md`); what it left open:
- [ ] Owner check in the browser: Registrar operação → Renda Fixa, pick LCA / CDB / IPCA+.

### Ritmo de gastos against the 3-month average (2026-10-12) — leftovers
The Início panel now compares the month so far with the average of the 3 previous months at the same
day (see `docs/done-tasks.md`); what it left open:
- [ ] Owner check on real data: Início → Ritmo de gastos. Do the three months' figures look right?
- [ ] "Despesas por categoria" still compares each category with last month's **whole** total, so
  its arrows and the pace panel answer different questions. Owner's call: move the category arrows
  to the same 3-month, same-day average (it would say *where* the overspending is).
- [ ] A month only partly recorded (the app started mid-month) still enters the average and pulls
  it down; only a month with no spending at all is left out.

### Ideas from the Investidor10 survey (2026-09-26, not prioritized)
Seen in Investidor10 PRO and not built; each needs the owner's call first.
- Fundamentals columns (Bazin ceiling price, P/L, P/VP, 5-year DY) — external data.
- B3 import of trades (the investor-area spreadsheet, via the existing import). Proventos are
  automatic since 2026-10-16.
- Sector targets/rebalancing (today the sector view is a breakdown only).

### Known limits, accepted for now
- Privacy mode hides balances, net worth and the portfolio only — lançamentos, faturas, orçamentos,
  operações and proventos stay visible by the owner's choice. Percentages stay visible; chart
  shapes still show relative sizes. A sensitive value must go through `usePrivateFormatter()`.
- IPCA+ is an **estimate**: purchase month pro rata by calendar days, the unpublished month missing.
- Lançamentos from before the fixed-income type change have no `fixed_income_type`; a title without
  any rate (manual price) is still accepted on save.
- Autopay still debits into the negative; the Início warning is the mitigation (today's balance,
  not a projection).
- No `create_app()` factory: only worth it together with moving config into the app object.
- Import is capped at 2,000 rows per file, and the rules apply-preview at 2,000 rows.
- IR report: day trade is not separated (no time of day stored); the R$ 20 mil exemption (ações
  only), ETFs/BDRs and the loss pools follow the simplified rules in
  `services/variable_income_tax.py`; the IRRF "dedo-duro" (0,005%) is not deducted from the DARF;
  proventos of foreign assets are taken as BRL.
- Multi-currency: USD, EUR and GBP by BCB PTAX; the screens are reais-only except the Conta
  global (USD, 047); a transfer between currencies carries `transfer_amount`; fixed income and FII
  are BRL. The Conta global's own US$ despesas/receitas are outside every reais total (not
  converted into the month); the phone's "Pix para cá" needs a connection (never queued).
- Corporate actions: nothing can be entered before an asset's latest event — undo the event, enter
  the movement, register the event again.
- Receipts: no server-side thumbnails (the browser scales the file); the backup mirror copies each
  receipt once, deleted ones are kept for the backup retention.
- Allocation: the contribution split is proportional to each shortfall (not "fill the furthest
  behind first") and never sells. A class without per-asset targets gets its share at class level
  only. Values are net (after estimated IR on fixed income), like the Posição distribution.
- Goals: the forecast is deterministic (constant monthly contribution and return, compounded
  monthly); monthly income has no forecast. Income counts net proventos paid in the last 365 days,
  foreign ones taken as BRL like the IR report.
- Rentabilidade (TWR): daily returns chained (Investidor10's method), on **gross** values; a
  buy enters at the price paid, a sale leaves at what it paid, proventos count on the payment
  date (the ex-date variant fit Investidor10 worse), a bonificação is no flow. Unquoted classes
  (OTHER, manual prices) sit at cost, so their gain lands today or on the sale; fixed income is
  exact at each month end and interpolated in between; a ticker with no Yahoo history (delisted:
  GALG11, JBSS3, MALL11, NEOE3) sits at cost; a provento paid while the position is empty is
  dropped. The response's `notes[]` lists these.
- **"Últimos 12 meses" differ by definition**: Investidor10 chains 13 calendar months (from the
  start of the month a year ago — Oct/2025–Oct/2026 = 25.46%), our 1A is 12 (Nov–Oct). Decide
  with the owner whether 1A should follow Investidor10.
- Total return per asset ("Rentab. c/ proventos"): base is all money ever put in (current cost +
  cost of shares sold), so an asset that paid back most of its capital isn't overstated.
- Benchmarks: IFIX and IDIV have no free monthly history — they accumulate from the closes the app
  stores when the screen is opened (stale if not opened near month-end); IPCA lacks the current
  month; brapi fallback covers 3 months only.
- Sectors: brapi data is imperfect (244 tickers without sector, ETFs as "Miscellaneous"); a FII
  segment and a stock sector with the same name merge; fixed income, foreign assets are
  "Sem setor" until filled by hand.
- IRPF text: no CNPJ/custodian/country stored ("(preencher)"); no paste text for foreign assets
  (Lei 14.754) or GCAP; imposto pago is the app's estimate.
- Exemption meter: stocks in BRL only (FII has no exemption, foreign assets are annual); it reads
  realized results, so a sale shows up once recorded — the form's warning covers the sale being typed.

---

## 2. Open decisions

3. **Single-user or multi-user?** Schema is ready for either; SQLite is enough for personal use.
