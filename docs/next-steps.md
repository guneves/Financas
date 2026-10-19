# Next Steps — FinanceMVP

> Active work plan for a **personal finance manager for my own use** (single-user, running locally).
> Implementation details and the reasoning behind past decisions live in `docs/handoff.md` and
> `CLAUDE.md`. This file holds **only open work**: when a task is finished, remove it from here and
> record it in `docs/done-tasks.md` — no ticked boxes, no "done" sections.

---

## 1. Open work, in priority order

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
  stop earlier, cap the retries of a plain 500 in `outboxRules.js` and `OutboxRules.java` together
  (native-level bump).
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
- [ ] **Self-update, what the phone check left out** (the basic paths passed on 2026-10-17, see
  `docs/done-tasks.md`): a lançamento queued offline before a screen switch is sent after it; a
  push that bumps `native-level.txt` shows the banner as *required* and the old screens are kept
  until the APK is installed; the 30 s fallback with a broken bundle (needs a deliberately broken
  push — only if the owner wants it proven).
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
- [ ] **Keep capturing, then a second parser pass.** The parsers were written against 10
  notifications (BB Pix out, Itaú Pix in/out, BTG Pix in, one BTG purchase, Samsung noise).
  Still unseen: any **Samsung Wallet** purchase text (its parser is generic: an amount plus
  "compra/aprovada", merchant from the title), a credit/debit purchase with "final 1234", Itaú
  and BB purchases, an estorno, a declined purchase, a boleto payment, BTG Investimentos' buy
  and sell (only its "Transferência recebida" has been seen). Keep
  capture on and bring a new "Exportar JSON"; anything mis-read becomes a `NotifyParsersTest`
  case first. Not answered by the export either: whether a bank *updates* a notification (new
  posted time, same key).
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

### Investments separate from banking — what is left
Built on 2026-10-12 and 2026-10-17 (see `docs/done-tasks.md`): every operation comes out of the
portfolio account (a Corretora account) unless "Não descontar de nenhuma conta" is ticked,
Início shows the banking area only, and "+ Novo" is banking-only. Open:
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

### Chart loading speed (2026-10-18) — what is left
- Owner check on the server: open Investimentos › Rentabilidade, switch 6M → 1A → Tudo and a
  class; after the first load each switch should be instant. Not measured against the real
  yfinance/BCB, only a 1 s-latency harness.
- Stale-while-revalidate: after the 15-min TTL the next open pays one round trip (now parallel).
  Serving the stale daily history, BCB series and index closes while refreshing in the background
  is safe (past closes don't change; today's value is the stored quote), but must be done in all
  three places to help, and a failed background download must not overwrite good data.

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
- Multi-currency lives only in the backend now (the screens are reais-only, see section 1): USD,
  EUR and GBP by BCB PTAX; a transfer between accounts in different currencies is refused; fixed
  income and FII are BRL.
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
- **Tesouro Direto is valued by accrual, Investidor10 marks it to market.** Each Tesouro purchase
  is stored as 1 title × the amount paid (the Investidor10 import did that); Investidor10 keeps
  the fractional quantity (5.95 × R$ 168,02) and the daily PU. On 2026-10-17 our Renda+ 2065 was
  R$ 8.122 vs R$ 9.365 there, and that is most of the remaining TWR gap (2026: 14.67% vs
  16.64%). Needs: the fractional quantity (amount ÷ PU of the purchase day, or re-import), and the
  Tesouro Transparente PU history as the price source for Tesouro titles.
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
