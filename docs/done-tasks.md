# Done Tasks — FinanceMVP

> Record of completed work, moved out of `docs/next-steps.md` so the plan holds only what is still
> open. When a task is finished, remove it from `next-steps.md` and add it here — newest at the
> bottom of the table, with any detail worth keeping in the notes below it. Anything left over from
> a finished task (a "not built", an owner walk-through) stays in `next-steps.md` as an open item.

---

## Completed work

| Area | When |
|---|---|
| Local auth (signup/login/JWT) | before 2026-09-15 |
| Income and expenses | before 2026-09-15 |
| Credit cards, installment purchases, invoice settlement | before 2026-09-15 |
| Normalized investments, FIFO cost basis, realized results, estimated tax | before 2026-09-15 |
| Investment ↔ cash linkage | before 2026-09-15 |
| Proceeds (dividends/JCP/amortization) with calendar and summary | before 2026-09-15 |
| Quotes with freshness status and per-asset refresh | before 2026-09-15 |
| Dashboard (net worth, balance, expenses by category, installments, next invoice) | before 2026-09-15 |
| Housekeeping: stray DBs/logs, `.gitignore`, `JWT_SECRET`, seed scripts moved to `backend/scripts/` | 2026-09-15 |
| `CATTLE` asset class — decided to keep (live, not dead code) | 2026-09-15 |
| Backend test suite (pytest, throwaway DB) | 2026-09-15 |
| Single start script `start.ps1` | 2026-09-15 |
| Automatic backup on boot with retention | 2026-09-15 |
| Invoice-month rule moved to the backend | 2026-09-15 |
| Bank accounts and transfers (§3.1) — migration 007 | 2026-09-16 |
| Categories as a table, with subcategories and management screen (§3.2) — migration 008 | 2026-09-16 |
| Editing a transaction | 2026-09-16 |
| Monthly budget by category, with rollover (§3.3) — migration 009 | 2026-09-16 |
| Recurring entries with cash-flow forecast (§3.4) — migration 010 | 2026-09-16 |
| Shared `frontend/src/lib/format.js` | 2026-09-16 |
| B3 ticker catalog, autocomplete, and guard on buys | 2026-09-16 |
| Statement search and filters (§3.7) — closes Phase 3 | 2026-09-21 |
| UX reorganization: 4 sections + Ajustes, "+ Novo" sheet, Carteira merged away, phone layout (spec in git at `9c186fe:docs/ux-reorganization.md`, file removed) | 2026-09-21 |
| Invoice payment only after closing, server-side; "Débito automático" per card — migration 011 | 2026-09-22 |
| Investimentos: "Evolução do Patrimônio" (monthly valor aplicado + ganho de capital, 6M–5A) replaces "Rentabilidade por ativo" | 2026-09-22 |
| Username (display name) on signup, editable in Ajustes → Perfil; email no longer shown as the name; privacy toggle (eye) masks money and name — migration 012 | 2026-09-22 |
| BCB fetch hardened (404 = no data yet, >10-year windows split, error payloads reported); fixed-income rate metadata validated on save; clearer provento error without a position | 2026-09-22 |
| Invoice payment: account picker (card's autopay account, else default); Início warns when an autopay account will not cover upcoming debits | 2026-09-22 |
| Statement filters in the URL; favicon; route-level `lazy()` (largest chunk 386 kB, was 737 kB) | 2026-09-22 |
| Phase 4: CSV/OFX statement import with preview and dedupe, auto-categorization rules — migration 013 | 2026-09-22 |
| Export to CSV (Excel pt-BR) of the filtered statement and of the portfolio | 2026-09-22 |
| brapi as the primary quote provider (batch + 5-min cache + dedupe + market-hours TTL), yfinance as fallback | 2026-09-22 |
| Motion pass: sheet/collapsible exit animations, sliding tab pill, count-up and chart draw-in once per page per session, reduced motion honoured in JS, new-row flash in Extrato, invoice-paid confirmation — zero new dependencies | 2026-09-22 |
| Privacy mode rework: the eye no longer remounts the page (no refetch, no empty-state flash) and hides only account balances, net worth and the investment portfolio; name and e-mail stay visible — `lib/privacy.js` | 2026-09-22 |
| Visual design pass (audit + items 1–7, decisions A–D): tabular figures and a real minus, pt-BR percentages, MetricCard that never truncates money, ~44 px table rows with right-aligned values and sticky headers, colour only with meaning, one-line chart axes, phone density, grey disabled buttons | 2026-09-22 |
| Decision 6 settled: "+ Novo" twice on Início and Extrato — the header one is gone (visual pass decision B) | 2026-09-22 |
| Início "Orçamento do mês" strip: month total spent vs. available and the categories near or over their limit; shared `components/BudgetProgress.jsx` with Orçamento | 2026-09-22 |
| Tables switch to cards below `xl` so they fit without sideways scroll; Proventos' empty calendar explains itself and opens the form | 2026-09-22 |
| Import rules: edit a rule (pattern included) and apply rules to lançamentos already recorded, with a preview and per-row confirmation | 2026-09-22 |
| Receipts per lançamento (PDF/image, several per row) from Extrato — migration 014 | 2026-09-23 |
| UI remodel, direction C, with dark mode: tokens, shell, Início, Extrato, Cartões, then Posição/Operações/Proventos, Orçamento/Recorrentes, Importar (stepper), Ajustes; kit `SummaryPanel`, `Menu`, `Toast` | 2026-09-23 |
| Phase 5 started: foundation modules, services and nine blueprints out of `app.py` (7,692 → 3,603 lines); URL-map test | 2026-09-23 |
| Phase 5 finished: investments out of `app.py` into five services and three blueprints; `app.py` is 60 lines of boot | 2026-09-23 |
| Phase 5 leftovers: the three pre-existing pyflakes warnings fixed (`create_app()` deliberately not built) | 2026-09-23 |
| Browser walk-through on scratch data (Chrome + Playwright): six bugs fixed — OFX after CSV read as CSV, Extrato columns misaligned below `xl`, header clipping "+ Novo" at 1024–1110 px, no scroll-to-top between screens, duplicate "Outros" donut slice, 0% return shown green; plus Regras padding and a doubled CSV charset | 2026-09-23 |
| `SegmentedControl` selection pill fits the active option when the options wrap onto two rows ("Novo lançamento"); container radius stays concentric | 2026-09-23 |
| UI remodel leftovers: toast after "+ Novo" and investment saves, invoice payments, recurring run and demo data (toast takes a link); every `window.confirm` replaced by a confirmation sheet (`lib/confirm.js`); Proventos form in a sheet; Início cash-flow chart fills its panel; Importar file picker with drag and drop; back/forward restores scroll (`lib/scroll.js`) | 2026-09-23 |
| Walk-through items not covered before, on scratch data: Pagar from Início, receipt "Abrir"/"Baixar", motion pass (scripted), scroll restore; signup checked through the API | 2026-09-23 |
| Open decisions 1 (card purchases count in the budget in the purchase month; invoice payment excluded), 5 (tax: support tool), 7 (Cartões keeps both buttons), 8 ("Receitas" in the cash flow), 9 (eye hides the month chip) | 2026-09-23 |
| Import rules: amount range and account conditions — migration 015 | 2026-09-23 |
| Export: real .xlsx, Operações and Proventos exports, column picker (`ExportSheet`) | 2026-09-23 |
| Receipts: mirrored in the backup (`backups/attachments`), thumbnails and inline preview, receipts on card purchases — migration 016 | 2026-09-23 |
| Frontend: server state in TanStack Query (every write invalidates the cache), loading skeletons on the heavy screens | 2026-09-23 |
| Operations: structured JSON logging (`applog.py`), integrations healthcheck (yfinance, brapi, BCB) with a panel in Ajustes; brapi's new nested payload fixed | 2026-09-23 |
| Phase 6: corporate actions (split, reverse split, bonus) — migration 017 | 2026-09-23 |
| Phase 6: multi-currency assets and accounts (USD, EUR, GBP via BCB PTAX) — migration 018 | 2026-09-23 |
| Phase 6: annual tax report (IR tab + .xlsx) | 2026-09-23 |
| Phase 6: Evolução do Patrimônio accrues fixed income month by month | 2026-09-23 |
| Open decision 2: recurring pause skips only the paused window; revival uses a stored cursor — migration 019 | 2026-09-26 |
| Carteira export: whole quantities without trailing comma in .xlsx; gross − IR = net to the cent; `rounded_money()` on portfolio totals; per-asset `total_invested` | 2026-09-26 |
| From an Investidor10 PRO survey: target allocation with contribution split (Investimentos → Alocação, migration 020), goals (Planejamento → Metas, migration 021), stock-sale exemption meter (IR tab + sale form) | 2026-09-26 |
| Proventos per asset: `services/proceeds.py` extracted, `by_asset` in the summary, per-asset proventos / 12-month DY / total return in the portfolio snapshot, Proventos "Por ativo" + Mensal/Anual, Posição columns | 2026-09-26 |
| Time-weighted return (monthly Modified Dietz, gross): `services/returns.py`, `GET /api/investments/returns`, Investimentos → Rentabilidade (TWR, YTD, % do CDI, year × month table, per asset) | 2026-09-26 |
| Aportes x resgates per month (`GET /api/investments/contributions`, chart on Operações) and concentration alerts on Alocação (asset > 10%, no exposure abroad) | 2026-09-26 |
| Rentabilidade: asset-class filter (class in the query key; FII sent as `REIT`) | 2026-09-26 |
| Carteira CSV/.xlsx export: Proventos, Proventos 12m, DY 12m (%), Rentab. c/ proventos (%) | 2026-09-26 |
| IR report reads proventos through `services/proceeds.py` (`paid_proceeds_in_year()`); its own SQL removed | 2026-09-26 |
| Rentabilidade vs benchmarks: IPCA, Ibovespa, IFIX, IDIV next to CDI (`services/benchmarks.py`, migration 023 `benchmark_closes`) | 2026-09-26 |
| Allocation by sector/segment (brapi `/quote/list`, manual override, migration 022; "Por setor" panel on Alocação) | 2026-09-26 |
| IRPF copy-paste text per section on the IR tab (`backend/irpf_text.py`, inside `GET /api/tax-report`) | 2026-09-26 |
| Proventos yield on cost fixed: each asset's cost counted once (average of its events' cost at the record date), not once per payment | 2026-09-26 |
| Posição "Evolução do Patrimônio" on the gross basis, like the headline (net in the tooltip) | 2026-09-27 |
| Rentabilidade and Evolução value the current month like Posição (`position_value_today()`) | 2026-09-27 |
| Orçamento copy: "Realizado" counts card purchases, not only account outflows | 2026-09-27 |
| "Operação anterior ao app": an investment movement that enters the portfolio without touching the balance (`metadata.skip_cash`) — replaced by the opt-in link on 2026-10-12 | 2026-09-27 |
| Ticker search and the buy guard cover the whole B3 (brapi `/quote/list`, `services/market_listing.py`); small caps used to be refused | 2026-09-27 |
| Fixed-income IR exemption follows the title type (`fixed_income_is_tax_free()`; LIG and Debênture incentivada added); IPCA+ directly in Rentabilidade; Gado no longer offered on a buy | 2026-09-27 |
| `CATTLE` (Gado) asset class removed everywhere: API refuses it, no screen lists it (the real DB had no rows) | 2026-09-27 |
| Início → "Ritmo de gastos" compares the month so far with the average of the 3 previous months at the same day | 2026-10-12 |
| Investments area separate from the banking area: the cash link is opt-in per operation (`metadata.cash_account_id`, "Lançar no extrato"), Início shows the banking area only, "+ Novo" is banking-only, a resgate is not a receita; database reset | 2026-10-12 |
| The app is reais-only on screen: no currency choice in any form and no foreign currency on any screen for data the screens can create (the backend multi-currency machinery stays, reachable only through the API) | 2026-10-12 |
| Mobile plan verified and rewritten (`mobile-docs/steps-to-production.md`); idempotent creation by `client_id` on the three "+ Novo" endpoints (migration 024); Flask serves the built frontend on one origin (`start.ps1 -Built`); offline outbox and saved read cache in the frontend, its "done when" checked in a scripted desktop browser (17 steps; two fixes from it: "+ Novo" lists load with the app, so the form works offline even if never opened before, and the offline toast no longer prints "r$") | 2026-10-13 |
| Mobile Phase 2, phone-width layout, on the PC: banking screens walked at 360/412 px; tabs fit, Cartões invoice badges no longer overlap the amount, 44 px touch targets below `lg`, "+ Novo" amount-first with a one-row type picker and the amount focused for every type, sheet stays above the keyboard, `inputMode` on numeric fields. The one-handed ten-second test waits for the phone (details in `mobile-docs/steps-to-production.md`, Phase 2) | 2026-10-16 |
| Mobile Phase 5, the APK, as code: Capacitor 8.5 in `frontend/` with `frontend/android/`; the APK's own web build (`dist-android`, API at the Tailscale address); native outbox in Java (SQLite queue, WorkManager sender, Keystore-encrypted session, the Phase 4 rules ported with JVM tests) swapped in by `lib/nativeApp.js`; back button, bars following the app theme, adaptive icon and launch screen; `mobile/new-keystore.ps1` and `mobile/build-apk.ps1` (build, sign, verify, `adb install -r`); `https://localhost` in `CORS_ORIGINS` and `JWT_EXP_DAYS=180` in `backend/.env` | 2026-10-16 |
| Mobile Phase 5, first build and install: Gradle 9.1 (Android Studio's JDK is Java 25), release key created, APK installed on the phone over USB; fixed on the phone: the bars' colour at launch, "Salvar" hanging offline (no network under the VPN: "+ Novo" queues at once, `Outbox.hasNetwork()`; otherwise `apiFetch` timeouts, 6 s for a creation, then the queue, 45 s for reads), `FitValue` cutting "R$ 1.000,00" by a sub-pixel; an offline entry sent by the WorkManager job on reconnect, once | 2026-10-16 |
| Bug pass, Android + desktop: one layer stack for overlays (`lib/layers.js`). Escape and the Android back button close only the topmost Sheet/Menu (a confirmation over "Pendentes" used to close the sheet underneath; Escape on a "⋯" inside a sheet closed the sheet). The body scroll lock is counted, so two sheets closing out of order no longer leave the page unable to scroll. Autocomplete Escape closes only its list | 2026-10-16 |
| Plano do mês (migration 025): monthly spend and invest amounts in reais on Orçamento, inherited until changed; spent/invested computed on read; flags for pace, over plan, aporte pending/done/missed, plan over income, and each dated goal covered or not by the planned aporte; comma-safe amount fields; checked at 390 px | 2026-10-16 |
| Perfil shows the login e-mail masked (`maskEmail()` in `lib/format.js`, "fu•••@g•••.com"), owner's request | 2026-10-16 |
| "Dados de exemplo" removed from Ajustes at the owner's request (`DemoDataSection.jsx` deleted; it was frontend-only). The seed scripts in `backend/scripts/` are untouched | 2026-10-16 |
| Phone load time: CORS preflights cached 2 h (`max_age=7200`; Chrome's default was 5 s, so almost every APK request was two round trips); navigation in a React transition (`v7_startTransition`) keeps the current screen until the next is ready; page chunks preloaded 1.5 s after start; query `gcTime` = the persisted cache's 14 days, so a screen not opened this session still has data on the next launch | 2026-10-16 |
| A fully redeemed renda fixa title is closed: not corrected by the BCB, not listed in Posição, out of the evolution (`closed_fixed_income_title_ids()` in `services/fixed_income.py`, half-a-centavo tolerance). Before, a full resgate left a R$ 0 row that failed/stale on every refresh | 2026-10-16 |
| A real investment history (renda variável with splits and bonificações, renda fixa, Tesouro) imported through the API; Tesouro rates from Tesouro Transparente. Data only, see the 2026-10-16 handoff | 2026-10-16 |
| Automatic proventos (026): position on each data com × StatusInvest's value per share, idempotent sync (`POST /api/investment-proceeds/sync`), edits locked and deletions remembered; JCP tax 15% → 17.5% from 2026 data com; Extrato gets a Contas / Investimentos selector with a read-only operações + proventos statement. reconciled with Investidor10 on a real history | 2026-10-16 |
| Docker deploy to the home server: `Dockerfile`, `compose.yaml` (GHCR image, localhost port, `financas_data` volume), GitHub Actions workflow (tests → GHCR → Tailscale SSH → compose pull/up), `deploy.ps1` (manual deploy, rollback by SHA, create-only), `DEPLOY.md`. Verified locally; not yet deployed (see next-steps) | 2026-10-16 |
| Home server live: owner's setup checked (tags, serve, sudoers, GHCR login, `.env`), first workflow run green, PC data imported (WAL-folded snapshot; all 26 table counts match), APK rebuilt against the server's Tailscale name and installed, GHCR package confirmed private, actions bumped to Node 24 versions (run green, no Node 20 warnings). PC retired as backend: `start.ps1` needs `-Local`, PC `tailscale serve` reset, old DB copied to `Documents\Financas-backup-pc-20261016\` | 2026-10-16 |
| Final setup check, all green; `origin` switched to HTTPS with `gh auth setup-git` (fetch and push work); reboot test passed (container healthy and `tailscale serve` back without help, app answering ~1 min after boot); APK signing key confirmed backed up off the PC by the owner | 2026-10-16 |
| APK screens update themselves from the server: the image carries the APK build of the frontend with `bundle.json` (content-hash version, native level, API address); `GET /api/app-bundle` and `/api/app-bundle/<version>.zip` (public, deterministic zip); native `AppBundle` plugin downloads, checks SHA-256, stages and opens it on the next start on trial, falls back to the APK's screens without `ready()`; Ajustes › Versão do app (APK version, native level, screen version, check / apply / go back). Phone check open (next-steps) | 2026-10-17 |
| APK updates from CI (option 2): `apk` job in `deploy.yml` (native changes only, `android-release` environment, key decoded to the runner and deleted, certificate checked against `mobile/release-cert-sha256.txt`, `versionCode = 10000 + run number`), APK + `version.json` copied to `/srv/apps/financas/apk` and served at `/apk/` by `tailscale serve`; native `AppUpdate` plugin (download, SHA-256/package/versionCode check, Android installer, "install unknown apps" once); "Nova versão disponível" banner and in Ajustes; bundle native level is now a minimum; "Verificar atualizações" / "Reiniciar agora". Phone check open (next-steps) | 2026-10-17 |
| Self-update checked on the phone: first CI APK (10009) installed over the USB build by `adb install -r` (same key, data kept); a screen-only push (`79d111c`, bundle `adaeed3`) reached the phone by "Verificar atualizações" → "Reiniciar agora"; APK 10011 offered as "Nova versão disponível" and installed from the app, data kept. CI APK job fixed: build-tools 37 prints `V2 Signer: …`, the certificate check now reads either format | 2026-10-17 |
| Phase 6, first half: native bank-notification listener (`android/.../notify/`, Java): allow-list of Samsung Wallet, Itaú, Itaú Cartões, BB, Ourocard and BTG Banking (`NotifyRules`, JVM tests incl. manifest `<queries>` parity), capture mode off by default writing each notification word for word (title, text, bigText, every textual extra, posted time, key) to `financas_notify.db`, dedup key = SHA-256 of package+key+posted time; Ajustes › Notificações dos bancos (access, restricted-settings steps, capture switch, counts per app, last 20, export JSON/text via share sheet, delete); debug build = package `br.financas.app.debug` accepting `com.android.shell`, built and published by CI as `/apk/financas-debug.apk`; native level 2. Parsers and mapping screen deliberately not built; phone check open (next-steps) | 2026-10-17 |
| Investments check, errors fixed: weighted average cost instead of FIFO (realized result, Bens e Direitos) and one cost for Posição and the evolution whatever price a SELL row stores; ETFs/BDRs without the R$ 20 mil exemption (15%, same loss pool), fixed-income ETFs out of the DARF, ETF/BDR Bens codes; per-sale IR = the sale's share of the month's tax (an exempt sale showed IR in Operações); tributação exclusiva at the net value on the IR tab and in the export; proventos cost no longer counts buy fees twice; Posição quantities in pt-BR; Rentabilidade notes with accents; brapi batch size configurable (`BRAPI_MAX_SYMBOLS_PER_REQUEST`) | 2026-10-17 |
| Posição › Variável split by kind of paper: Ações, ETFs, BDRs, Fundos Imobiliários, Outros. STOCKS still holds ação/ETF/BDR; each position now carries `market_kind`, the IR's `market_listing.tax_kind` (ETF_RF shown as ETF) via `asset_market_kind()` in `services/portfolio.py`, tested in `test_portfolio_market_kind.py` | 2026-10-17 |
| BTG Investimentos (`com.btg.pactual.digital.mobile`) added to the notification allow-list and the manifest `<queries>` at the owner's request, so brokerage operations can later be suggested; JVM test updated. No native-level bump: no screen calls anything new | 2026-10-17 |
| The portfolio account: a Corretora account is linked to the portfolio and every new operation comes out of it (sale/redemption into it) unless "Não descontar de nenhuma conta" is ticked (`cash_account_id: null`). API default for a POST without the key (`portfolio_cash_account_id()`), screens refuse a new operation until one exists (`lib/portfolioAccount.js`), "Vincular à carteira" and a "Carteira" badge in Ajustes › Contas. Tests: 9 backend (`TestThePortfolioAccount`), 7 node | 2026-10-17 |
| Paid proventos into the portfolio account: one INCOME row per provento paid (≤ today) on or after the day the account became Corretora (`metadata.portfolio_since`), materialized on read (`services/proceeds_cash.py`), source_type `INVESTMENT_PROCEED`, locked in the Extrato ("Provento"), follows edits/deletes. `test_proceeds_cash.py`, 8 tests | 2026-10-17 |
| Corretora balance only in Investimentos: out of "Saldo em conta" (Início), the Extrato's "Saldo em contas", Ajustes › Contas ("Em Investimentos"), the invoice-payment sheet and the autopay warning; Início turns a transfer into the Corretora into an aporte; Posição shows "Saldo na corretora". `lib/transactions.test.js` (6 tests); phone-width walk on a scratch database; APK screen bundle built at native level 2 | 2026-10-17 |
| Samsung Wallet, Itaú Cartões and Ourocard off the notification allow-list (owner: they repeat purchases the bank apps already notify): `NotifyRules.APPS`, the manifest `<queries>`, a JVM test that they are ignored, the Ajustes text | 2026-10-17 |
| Samsung Wallet back on the notification allow-list as a fallback source (capture only; pairing with the bank app planned in `mobile-docs/steps-to-production.md`, "One purchase, one entry") | 2026-10-17 |
| Bank × Samsung Wallet pairing rule, pure Java (`notify/NotifyPairing.java`): same amount to the cent, card that does not contradict, 10-min window (inclusive); Samsung held then promoted, bank wins and takes the suggestion's place with the first detection's `client_id`, late bank after confirm is MATCHED, a bank decline cancels an unconfirmed Samsung. 30 JVM tests (`NotifyPairingTest`). **Not wired**: no parser, store table or WorkManager yet | 2026-10-18 |
| Operação form: the "Ativo" suggestions list only the assets of the chosen type (the catalog search already did) | 2026-10-18 |
| Posição: each category (Ações, ETFs, FIIs, CDB…) is a toggle, collapsed by default, header keeps count and total | 2026-10-18 |
| Pluggy removed from the app (owner: the free plan gives no access): client, sync, routes, Ajustes › Banco, the Extrato's bank mark, the "+ Novo" bank claim, Aprovar's bank source; migration 029 drops `pluggy_*`, `external_id` and `cc_expenses.source_type/source_id` (a pending Aprovar item only the bank brought is REMOVED, a Pluggy-born lançamento becomes manual) | 2026-10-17 |
| Pluggy out of the migrations too (owner): 027/029 reserved and empty, 028 without its Pluggy lines, 030 renames their `schema_migrations` rows (session financas-5e) | 2026-10-17 |
| Notification auto-identifier: Java parsers per bank on the phone, every money notification sent to Aprovar (parsed fields only), own-account transfer vs Pix to someone else by the counterparty (migration 031), the bank's double posting dropped, nothing matched without Aprovar | 2026-10-17 |
| TWR like Investidor10: daily returns chained instead of monthly Modified Dietz, Yahoo's bonus-as-split price adjustment undone (`restore_quantity_basis()`), a bonificação is no flow, Rentabilidade › "Tudo" (`?months=all`, since the first operation); the evolution reads the same restored closes | 2026-10-18 |
| Expense sharing (032): a lançamento or card purchase can be the owner's, split (`SPLIT`, others' part in `share_others_amount`) or someone else's (`OTHERS`), with the person's name. Balances are untouched; budget, monthly plan, Despesas por categoria and the Início cash flow count only the owner's part, the flow shows "Outras pessoas" apart. Lançamentos › A receber lists the others' part of each expense until marked paid (`/api/receivables`, `/settle`); a card purchase's share is set for every installment (`PATCH /api/cc-expenses/<id>/share`). `services/sharing.py`, `lib/sharing.js`, `lib/cashFlow.js`; `test_expense_share.py`, `sharing.test.js` | 2026-10-18 |
| Card refunds (033, estorno): `POST /api/cc-expenses/refunds` writes a `kind = 'REFUND'` row (positive amount, 1/1, never shared) that lowers its invoice — the date's invoice, or the next open one if that one is paid. A zeroed invoice is settled with no lançamento; one left in credit is not payable and its credit lowers the next payment (`invoice_open_lines()`). Budget, monthly plan, Início's flow and Despesas por categoria subtract it in its month. Cartões: "Registrar estorno" in a purchase's ⋯ menu and an "Estorno" button on top (`CardRefundSheet.jsx`); `cardSignedAmount()` in `lib/transactions.js`. `test_cc_refund.py` | 2026-10-18 |
| Início's "Disponível por dia" = what is left to spend in the month's plan (Orçamento › Gastar) ÷ days left in the month, today included; without a plan it keeps the old rule (balance − next invoice) | 2026-10-18 |
| Aprovar × Recorrentes (034): a pending item flags the recurrence occurrence it looks like (a subscription's card purchase, the salary's Pix); approving writes the notification's lançamento and marks that occurrence done (`recurring_settlements`), so `/run` never writes it, it is not pending and leaves the forecast. "Não é esta" on the item opts out, also for "Aprovar todos". Calendar moved to `services/recurring.py`. `test_inbox_recurring.py`, `recurringText()` in `lib/inboxRules.js` | 2026-10-18 |
| Orçamento › "Ver lançamentos" per category: `GET /api/budgets/<id>/lines` lists the rows behind the realizado (category + unbudgeted subcategories; a card purchase is one line with all its installments, a refund negative, a shared row the owner's part). `budget_month_lines()` is the single source: `budget_spend_by_category()` sums it. `components/BudgetLines.jsx`, `test_budget_lines.py` | 2026-10-18 |
| Phone layout pass (Galaxy S25, 360 px, seeded demo data): Início's balance block compact below `sm` (~430 → ~260 px), bottom bar in five equal columns with the "+" centred and short names "Planejar"/"Investir", section tabs scroll the active one into view, smaller `PageHeader`/`SummaryPanel` on phones, inputs/selects 44 px. Lançamento amounts ("+ Novo", Extrato edit, Aprovar) accept "45,90", "45.90", "1.234,56" via `parseMoneyInput()` | 2026-10-18 |
| Bug: typing a transfer that waited in Aprovar returned 500 and saved nothing (`_absorb()` called with an extra argument in `absorb_created()`); the phone's queue retried it forever. Now it takes the item's place. `test_inbox.py` | 2026-10-18 |
| Bug: Início and the bell looked at "next month's invoice", so a card closing before its due day (3/10, 13/20) never got "Pagar fatura" and "Próxima fatura" showed the wrong one. One rule for the three screens: each card's open invoice with the earliest due date from today on (`nextInvoices()` / `nearestOpenInvoice()` in `lib/attentionRules.js`); "Disponível por dia" without a plan subtracts those plus any overdue one; Cartões says "Em atraso" only after the due day. `attentionRules.test.js` | 2026-10-18 |
| Bug: categories matched by name ("Outros" at the root and under two parents): every category select sends the id ("+ Novo", Extrato edit, Importar, Aprovar, Ajustes › Regras); card purchases store `category_id` (migration 035, backfilled) and the budget counts them by it; an edit that resends the name keeps the id; a bare name means the root; rules compare by id. `test_category_identity.py` | 2026-10-18 |
| Bug: renaming a category only rewrote `transactions`: now card purchases, recurrences, import rules and Aprovar items too (by id), and a row with only the old text keeps counting where it counted. `test_category_identity.py` | 2026-10-18 |
| Bug: two identical card purchases (same card, description, date, category) were one — sharing, A receber, delete, receipts and the Cartões row merged them. The purchase is its `client_id` now; every purchase has one (migration 035 gives the old ones `legacy:<id>`, identical ones split by write order); `/api/cc-expenses/candidates?id=`. `test_cc_purchase_identity.py`, `transactions.test.js` | 2026-10-18 |
| Aprovar, ambiguous target: a notification with no card final, when 2+ active accounts (or cards) carry that bank in their bank field, is never remembered nor guessed — it asks every time, an older remembered choice stops deciding, and "Lembrar a escolha" is hidden. `test_inbox_ambiguous.py` | 2026-10-18 |
| Aprovar shows every item's target ("→ Itaú Conta corrente"), remembered ones too, with "Trocar" opening the picker in place | 2026-10-18 |
| Ajustes › Aprovar: "Sempre perguntar a conta/cartão" (off by default, server-side in `user_settings`, migration 036): every item asks to confirm its target and "Aprovar prontos" takes none. `test_inbox_ambiguous.py` | 2026-10-18 |
| Charts faster: Rentabilidade fetches prices, CDI, IPCA and index closes at once instead of in sequence, and the price/BCB caches cover every period and class (one download per TTL) — cold 6 s → 1 s, period/class switch ~4 s → < 0.1 s on the 1 s-latency harness. `test_history_fetch.py` | 2026-10-18 |
| Investimentos › Calculadora: compound interest simulator (initial amount, monthly contribution at the end or start of the month, rate per year or month by equivalent rate, period in years or months, optional inflation → value in today's reais). Pure rule in `lib/compoundInterest.js`, 12 node tests | 2026-10-18 |
| Card history no longer disappears (migration 037): deleting a purchase removes only its open installments (the API refuses a paid one, 409); a purchase or refund dated into an already-paid invoice — typed or approved in Aprovar — starts at the first unpaid one; a card with open items is not deleted, one with history is archived (`credit_cards.archived_at`), an empty one is deleted; an invoice payment can be undone (`DELETE /api/cc-expenses/payments/<id>`, Extrato › "⋯" › Desfazer pagamento). `test_card_history.py` (19) | 2026-10-18 |
| Owner's review, items 4–21: card edit (name, due and closing day); account edit on screen (name, institution, initial balance, default, unlink from the portfolio, reactivate); the default account never lost (archived or turned Corretora → another takes the mark; a 409 no longer clears it; never a Corretora); lançamento of an archived account editable, its name shown; `account_id: ""` on edit refused; a transfer edit across currencies refused; import rules skip paid proventos; CSV type "d"/"Depósito"/"Devolução"; OFX "-42,90", CSV "1.500", a repeated FITID; recurrences skip archived accounts (`blocked`); closing day 29–31 in a short month; old card endpoints (`/status`, `/invoice-status` removed; list POST rounded, no `PAID`, a `client_id` per purchase); dates and months stored zero-padded; no third category level or archived parent; `JWT_SECRET` never the public default (generated into `.jwt_secret`), signup closed once a user exists (`ALLOW_SIGNUP`); Aprovar "Nx de R$" read as the installment; `parseMoneyInput` "1,234.56"/"0.500"; `round()` on quotes; a hand-written button height. `test_card_edit.py`, `test_signup_and_secret.py` and cases in the existing files (1305 pytest), 108 node, 52 JVM | 2026-10-18 |
| Início's account strip opens at the far left on the phone: `scroll-px-4` on the strip, so `snap-start` stops snapping the first account to 16 px (Chromium, 390 px: `scrollLeft` 0 with 1 and 8 accounts, cold load, back and in-app navigation) | 2026-10-19 |
| The monthly plan starts from income — backend + migration 038: the plan is Renda (R$, required) + Investir % + Gastar % of it, each category a % of Gastar; every R$ computed on read (`percent_of()`), percentages stored as six-decimal text read as `Decimal`; over 100% refused at both levels; Sem destino / Sem categoria returned; a month inherits the previous plan *with its categories*; Saldo do plano = Gastar − spent (one number in the plan, its progress and the budget) and Disponível por dia; the migration converts plans with income and their months' categories, the rest is `needs_income` until the PUT brings the income. Budget logic moved to `services/budgets.py`. Interim screens only (redesign next). `test_monthly_plan_income.py` (21) + the budget files rewritten (1343 pytest), 108 node | 2026-10-19 |
| Planejar › Orçamento redesigned around the income-based plan: Saldo do plano as the headline with Disponível por dia (privacy mode hides both), Renda do mês ("Recebido X de Y esperados") with Investir / Gastar / Sem destino rows (%, R$, realizado, progress, "Falta investir" + "Como dividir" → Alocação), the plan flags, Categorias do mês with % + live R$ and Sem categoria; one "Plano do mês" sheet (Renda, Investir %, Gastar %, live totals, save blocked over 100% or without income) for the empty state, editing and `needs_income`. Only `GET /api/monthly-plan` is read; no financial rule changed. `percentOf()`, `livePlanTotals()`, `unallocatedText()` in `lib/monthlyPlan.js` (115 node), 1343 pytest | 2026-10-19 |
| Início: the month's movement leaves the hero for its own card "Resumo do mês" (Resultado do mês, Entrou, Saiu, Investido when there was an aporte or resgate, "Você pagou por outras pessoas" / "Outras pessoas te pagaram" → A receber), in the place of "Disponível por dia", which left Início (it lives in Orçamento). Same `currentMonth` numbers, no rule changed; privacy masks every value | 2026-10-19 |
| Plano do mês: each flag gets an X ("Dispensar"), dismissed per device (`lib/planFlags.js`); the key is `planFlagKey()` (code + month + goal), tested in `monthlyPlan.test.js` (117 node); nothing goes to the server | 2026-10-19 |
| Investimento is no longer a category (039): aporte/resgate/provento by `source_type` or a bank ↔ Corretora transfer; typed "Investimento" rows became transfers to the Corretora, the category archived, its import rules switched off; 1349 pytest, 118 node | 2026-10-19 |
| Extrato deletes operações: Contas › an aporte/resgate row ("Pela carteira") › "⋯" › Excluir operação deletes its movement, and Investimentos › each operação (not a bonificação) has the same; `DELETE /api/investments/<id>` already removed the linked lançamento. 122 node | 2026-10-19 |
| Operações › Editar: a sale shows its quantity without "-" and is saved as a sale (the screen puts the sign back, and `PATCH /api/investments/<id>` keeps the stored operation's sign: a positive quantity on a sale stays a sale, a negative one on a buy stays a buy); "Salvar" no longer waits for the quote refresh, which left it spinning on the next edit until the screen was left. `test_investment_edit_sign.py` (5) | 2026-10-19 |
| Fixed-income coupons and amortizations typed ahead (040): new provento type `INTEREST` ("Juros (cupom)"; table rebuilt for the CHECK), no data com for INTEREST/AMORTIZATION (payment date used), the coupon's default IR from the regressive table since the title's first purchase (0 if tax-free or not fixed income), `repeat: {every_months, count}` on the POST writes every payment at once (each with its own date's rate), paid ones land in the Corretora as "Juros: <título>", IR report: coupon with IR → 06, without → 12, amortization out. Proventos' form switches to Pagamento / Valor bruto / IR / Repetir for a fixed-income asset. `test_fixed_income_interest.py` (24), 1381 pytest, 122 node; clicked through in Chromium | 2026-10-19 |
| Investir charts fast and the index comparison fair: history caches copied to disk (`history_store.py`, `history_cache.json` next to the DB) so a deploy no longer waits for Yahoo/BCB; stored index closes served while they refresh in the background; proventos' sync invalidates only when it changed something; `accrual_factor_until()` by cumulative products, one pass for every asset's TWR, outputs identical. Rentabilidade starts the portfolio, the CDI and every index at 0% at the same point (the month before the period, or before the first operação) and the cards cover the same months. 1392 pytest, 122 node; Chromium screenshots | 2026-10-19 |
| Asset categories, proventos by type, asset search: ETFs are "ETFs" and Tesouro Direto its own category (computed on read, `services/asset_categories.py`; the DB class is unchanged), fixed income's sector is its indexer (Pré-fixado / Pós-fixado / IPCA+), Registrar provento asks the type first and searches only the assets that can pay it (`lib/proceedsRules.js`), the sale picks its asset by typing (`AssetPicker`), the buy offers ETFs and Tesouro Direto | 2026-10-19 |
| Tesouro Direto marked to market and grouped: the Tesouro Transparente price file (`tesouro_client.py`, cached in memory and as `tesouro_precos.csv` next to the DB, never blocking a read) gives each purchase its number of titles (amount ÷ the purchase day's PU at the contracted rate, or the typed "Quantidade de títulos") and today's PU de venda; purchases of the same title are one position with the rate that gives the same value at maturity; net = gross − B3 custody (0.20% a.a. pro rata die from D+1, not before 2025; Selic exempt to R$ 10 mil) − IOF − IR per purchase (`services/treasury.py`). Evolution, Rentabilidade and "Atualizar cotações" (source `tesouro`) read the same PU; the redemption of a grouped title goes oldest purchase first (PEPS, `lib/treasury.js`). Posição › Tesouro Direto shows Vencimento, Quantidade, PU, Saldo líquido, Saldo bruto and "Detalhes do título". `test_treasury.py` (36), 1448 pytest, 136 node; Chromium screenshots on a synthetic price file | 2026-10-19 |
| BCB and Tesouro downloads through `gov_http.py` (verified chain without Python 3.13+'s strict X.509 mode, one retry on timeouts/429/5xx, the cause named in the error), the BCB health probe waits 30 s instead of 6 s, Tesouro prices downloaded at boot and checked hourly (`tesouro_client.start_auto_refresh()`), "Quantidade de títulos" editable on an existing Tesouro purchase | 2026-10-19 |
| Saving and editing an operação without waiting: "Registrar operação" closes as soon as the POST answers (the quote refresh runs behind, `refreshQuotes()` in `lib/dataApi.js`, and refreshes the screens only when a quote changed); a screen's `invalidateServerData()` joins the refetches a write already started instead of restarting them (`cancelRefetch: false`; the write's own listener still cancels); quote writes no longer schedule the proventos sync (`changesPositions()` in `lib/proceedsRules.js`); writes no longer rebuild `investment_positions` (only its own GET does) and `investment_realized_results` is rewritten only when it changed; JSON responses ≥ 1 KB go gzip when accepted (`gzip_responses.py`). POST 61 → 22 ms, PATCH 67 → 24 ms on a synthetic 350-operation portfolio; `test_write_speed.py` | 2026-10-19 |
| Planejar's "Investir" realized = Início's "Investido": money that left the accounts for the Corretora (transfers, or a movement's cash in a non-Corretora account) minus what came back, instead of the portfolio's buys − sales; a buy paid from cash already in the Corretora no longer counts (`month_investment_flow()` in `services/monthly_plan.py`, tests in `test_monthly_plan.py`) | 2026-10-19 |
| Renda variável quotes refreshed by the server every hour (`services/quote_refresh.py`, `QUOTE_AUTO_REFRESH_SECONDS`, 0 = off; the same `refresh_market_prices(force=True)` as "Atualizar cotações", for every user; started in `app.py` next to the Tesouro thread). `test_quote_auto_refresh.py` | 2026-10-22 |
| Card débito function (041: `credit_cards.debit_account_id`, `credit_enabled`): a card is Crédito, Débito or Os dois; a débito purchase in "+ Novo › Cartão" is an EXPENSE in the card's account; a debit-only card (the Flash) has no invoice, installments, refund or autopay and stays out of Cartões and Aprovar's card list; Aprovar sends a purchase on a debit card to its account (`debit_card_for()` in `services/inbox.py`). `test_card_debit.py` (21), `lib/cardFunctions.js` + test | 2026-10-22 |
| Flash Benefícios and the second parser pass (capture of 2026-10-22, 60 notifications): `br.com.flashapp` in the allow-list and the server's issuers; Samsung Wallet's "<LUGAR> R$ <valor>" with the card name as title (card_name → issuer; "Card used for Meal and Voucher" = the Flash) and its U+00A0; BB's "Pix Recebido" names the sender. 12 new `NotifyParsersTest` cases from the capture | 2026-10-22 |
| Bug hunt by fuzzing every route (about 7,000 odd requests): a JSON body that is not an object, a date or month outside 1900–2199, an amount that rounds to 0 or above R$ 1 trilhão, `credit_enabled`/`fixed_income_type` as a list or object, an invoice year out of range, an operation's quantity/price of 1e308 or a bad date in its `metadata`, and a purchase with fewer cents than installments are a 400 now — before, a 500, a wrong value stored, or a row that broke later reads (Cartões, the IR report, every later operação). `rounded_money()` no longer turns ≥ 1e26 into 0. `parse_money()` in `money.py`; `test_input_edges.py` (41) | 2026-10-22 |
| A new APK on every deploy (owner: "preciso apenas poder baixar o app a cada deploy automaticamente"): the `apk` job of `deploy.yml` no longer depends on `frontend/android/`, `native-level.txt` or `capacitor.config.json` changing (the change-detection step and the `apk` input of `workflow_dispatch` removed); every push to `main` publishes a signed APK with a higher versionCode, offered by "Nova versão disponível". DEPLOY.md, CLAUDE.md and the mobile plan updated. Phone check open (next-steps) | 2026-10-22 |
| Native phone app, step 0 (owner: phone native, desktop its own interface; `mobile-docs/native-app.md`): Kotlin Gradle plugin + Compose compiler plugin (2.3.20), Compose BOM, Material 3 and `activity-compose` in the Android project, JVM target 21; `ui/theme/Tokens.kt` (the web's colour tokens by CSS name) + `Theme.kt` (`FinancasTheme`, `Palette`, `ShellPrefs`); `ShellPlugin.setTheme` stores the web's theme for native screens; `TokensTest` reads `index.css`; `.github/workflows/android-check.yml` builds the debug APK and runs the JVM tests on branch pushes. No screen yet, no native-level bump | 2026-10-22 |
| Native migration documentation (owner: "faça toda a documentação para o novo projeto"): `mobile-docs/native/` — README (index, status), architecture (packages, native beside the WebView through a `NativeScreens` plugin, session, cache/offline, mirrored settings, an in-house Compose chart kit), conventions, build-and-test (the CI loop from a session), migration-order (steps 0–9 + desktop, what runs in parallel), rules-port (every `lib/` module: port or endpoint), findings (endpoints to add, inconsistencies, possible bugs), desktop (principles, layout, plan per screen), agents (workflow, parallel rules, prompts) and 16 screen specs from one template, written by four parallel agents against the code. Six agents in `.claude/agents/`: `screen-spec-writer`, `rule-porter`, `native-screen-builder`, `native-parity-reviewer`, `android-ci-watcher`, `desktop-screen-builder` | 2026-10-22 |
| Native step 1's foundation (no screen): `core/Format.kt` + `MoneyInput.kt` (all of format.js, `parseMoneyInput`/`moneyInputValue`), `rules/CardFunctions.kt` (all of cardFunctions.js), `rules/Sharing.kt` (`shareFormFrom`/`shareFormError`/`sharePayload`), each with the node cases; `data/` (ApiClient on OkHttp + kotlinx.serialization with the token from `Session`, ReadCache, repositories for accounts/categories/cards, AppGraph); the `NativeScreens` plugin registered (`routes()` empty, `open()` a stub, `dataChanged`/`navigate` declared). 64 new JVM tests; no native-level bump | 2026-10-22 |
| Native "+ Novo" (step 1's screen): `ui/newentry/` (`NewEntryActivity`, a translucent Compose bottom sheet with despesa, receita, transferência and cartão crédito/débito, amount first; Corrigir from Pendentes too), the save of `createEntry()` with the item kept in the outbox during the POST, `buildItem`/`newClientId`/`editedItem` in `OutboxRules.java` (+ `editedItem` in `outboxRules.js`), `rules/EntryOptions.kt`, `rules/InboxNotice.kt`, the first `ui/components/`; `NativeScreens` lists `new-entry`, the React layout opens it when listed (`lib/nativeScreens.js`, `nativeScreensRules.js`), `native-level.txt` 3. 51 JVM tests, web 144 → 150. Owner's phone check open | 2026-10-22 |
| `findings.md` triage, possible bugs and stale texts (web and backend): Metas edit after the target month, Recorrentes account edit, Extrato transfer destination, investment statement same-day order, refund prefill cents, A receber "pago em" local day — each reproduced by a test, then fixed; login "Finanças" + "Criar acesso" only when `GET /api/auth/signup` says open; Metas/Integrações/Notificações texts, `CASH_WITHOUT_AMOUNT_MESSAGE`, `Orcamento.jsx` comment | 2026-10-23 |
| Native migration session 5: the proposal `mobile-docs/native/proposals/home-attention-invoices.md` (home, attention, invoices, purchase delete, transactions paging; routes, JSON, reused functions, web switch, pytest cases for every `transactions.test.js` / `attentionRules.test.js` case plus 18 new for `cashFlow.js`, behaviour changes B1–B9) — proposal only, nothing implemented; the pending-balance rules of `outboxRules.js` (`pendingAccountDeltas`, `applyPendingToAccounts`, `pendingAsTransactions`, `countByStatus`) ported to `rules/OutboxPending.kt`, 11 JVM tests, android-check green | 2026-10-23 |
| Native migration session 6: the proposal's §1–4 built — `GET /api/home` (`services/home.py`), `GET /api/attention` (`services/attention.py`), `GET /api/cc-invoices` (`services/card_invoices.py`), `DELETE /api/cc-expenses/purchases/<id>`; Início, the bell, the Extrato's "Saldo em contas" and Cartões switched with no visible change; `applyPendingToHome()` in `outboxRules.js` and `rules/OutboxPending.kt`; `cashFlow.js`, the rule half of `attentionRules.js` and `consolidatedBalance`/`openingBalanceTotal` deleted, their node cases moved to pytest. pytest 1536 → 1603, node 164 → 160 | 2026-10-23 |
| Native migration session 7 (step 3): Início and the bell native — `ui/home/` reading `/api/home?months=12` and `/api/attention` with the pending overlay (`OutboxItems` → `applyPendingToHome()`, "Saldo estimado"), attention cards with Pagar/Lançar and per-device dismissal, the bell sheet, Fluxo de caixa / Orçamento / Evolução do saldo (`ui/charts/`), privacy mirrored both ways (`Shell.setValuesHidden`/`getValuesHidden` → `ShellPrefs`), the web Início tab opening it (`NativePage`, `?web=1`), native-level 4 → 5; `mobile/inicio-snapshot.py` to compare native and web; 39 new JVM tests, node 160 → 176 | 2026-10-23 |
| Native migration session A (step 4): Extrato (both views) and Cartões native — paging on `GET /api/transactions?limit=&cursor=` (keyset, `items`/`next_cursor`/`count`/whole-filter `totals`/`day_totals`, `services/transaction_pages.py`, `test_transactions_paging.py`) with the web's filtered Extrato on "Carregar mais" (`lib/transactionPages.js`); `projections` on `/api/home`; `ui/extrato/`, `ui/cartoes/`, `ui/lancamentos/` (receipts with camera/file picker, export through the share sheet, "De quem é?"), `rules/InvestmentStatement.kt`, `ExtratoRules.kt`, `CardRules.kt`, the rest of `sharing.js` (`shareSummary`, `settlePayload`), `NativeLinks`; Aprovar's writes on `writeApi`; native-level 5 → 6. pytest 1603 → 1615, node 176 → 180, JVM 348 | 2026-10-24 |
| Native migration session B (Investimentos backend and ports, no screen): `client_id` on investment, provento and corporate-action creations (042); `POST /api/investments/redemptions` (PEPS and the proportional cost on the server) and `DELETE /api/investments/by-assets` (atomic grouped Tesouro delete); `realized_result`, `by_year` and `net` read by Operações, Proventos and IR with no visible change; SERIES/FLOW as CSS variables and in `Tokens.kt`; `ui/charts/` donut, signed bars and gap lines; six rule ports (`PortfolioAccount`, `AssetSearch`, `FixedIncome`, `TreasuryLabels`, `ProceedsRules`, `CompoundInterest`). pytest 1603 → 1636, node 176 → 185, JVM 361 | 2026-10-24 |
| Native migration session C (steps 5–6): Orçamento, Recorrentes, Metas, A receber and Ajustes native — `rules/MonthlyPlan.kt` (the input side of `monthlyPlan.js`), `Recurring.kt`, `Goals.kt`, `Receivables.kt`, `Settings.kt`, `NotifyTexts.kt`, `ApkUpdateTexts.kt`, `Sharing.groupReceivables`; `frequencyLabel` and the goal forecast texts moved to `lib/recurring.js` / `lib/goals.js` with node tests first; `ui/components/PercentSlider.kt`; `ui/orcamento/`, `ui/recorrentes/`, `ui/metas/`, `ui/areceber/`, `ui/ajustes/` (Regras and Integrações stay web); theme and Sair handed to the WebView through `ShellPrefs` (`Shell.takeThemePreference`/`takeSignOut`); native-level 6 → 7. node 185 → 196 | 2026-10-24 |
| Native migration session D (step 7): Investimentos native, all seven tabs — `ui/investimentos/` (Posição, Operações with Registrar operação and corporate events, Proventos, Rentabilidade, Alocação read-only with the aporte split, IR meter and DARF months, Calculadora), `data/InvestimentosDtos.kt` + `InvestimentosRepository.kt`, rules `PortfolioView`, `Operations`, `ProceedsForm`, `ReturnsRules`, `AllocationRules`, `CompoundInterest.chartPoints`, `ui/charts/StackedAreaChart`; the outbox's `INVESTMENT` and `PROCEED` kinds on both sides (`outboxRules.js`, `OutboxRules.java`, `OutboxPending.kt`, `PendingSheet.jsx`, `EntrySaver.createJson`); the web routes in `NativePage`; native-level 7 → 8. node 196 → 198, full JVM suite 500 green | 2026-10-24 |

---

## Notes on completed work

Detail that used to sit in `next-steps.md` and is still useful as reference — mostly for the owner
walk-through, which remains open there.

### Visual design pass — 2026-09-22
The audit and plan from the same day were approved with decisions A–D; all seven items shipped as
one commit per theme (`a9d2422`..`d3a20be`), checked with Playwright screenshots at 1280 px and
390 px on scratch data. What changed:
- **Numbers:** tabular figures app-wide; `formatCurrency` prints a real minus (U+2212);
  `formatSignedCurrency` for lists of entradas/saídas (sign glued to the value); `formatPercent` in
  pt-BR ("1,29%") and the only copy; `shortMonthLabel` ("out/25") on every chart axis.
- **MetricCard:** icon beside the label, value on one line that shrinks to fit (`FitValue` in
  `ui.jsx`), no hover lift. Two across on phone.
- **Tables** (Extrato, Posição, Operações, Proventos; Cartões purchases as a list): right-aligned
  values, ~44 px rows, truncation with a title, sticky header (no `overflow-x` wrapper — keep it that
  way), `IconButton size="sm"` for row actions. Extrato dropped the Tipo column (only transfer and
  investment keep a neutral tag) and shows 100 rows + "Mostrar mais" (D). On phone an Extrato row
  opens the edit form on tap; Excluir lives inside it.
- **Colour:** green/red/amber/sky only for gain/loss/warning/info; labels, counts, statuses that are
  the normal state, and open invoices are neutral. Archive buttons are neutral, delete stays red.
- **Chrome:** flat background (A), no eyebrow and no page-level "+ Novo" on Início/Extrato (B;
  Cartões keeps "Nova compra", which preselects the card type), 256 px sidebar (C).
- **Kit:** grey disabled `Button`, lighter `Badge`, `SegmentedControl` with the `Tabs` sliding pill
  (shared `useSlidingPill`), `Expand` with a `minmax(0,1fr)` column, `.app-table` rules under
  `:where()` so utilities win.
- **E** (dark mode) shipped with the UI remodel below.

### UI remodel — direction C "Cartões" + dark mode — 2026-09-23
Owner picked **C with dark mode** on 2026-09-23 (audit and mocks:
`git show 36e0164:docs/ui-remodel-audit.md`; canvas https://claude.ai/artifact/DPSbd7JxFULWe4r9z36tto).
- **Tokens + dark mode + font**, **shell + kit**, **balance bug** (consolidated balance includes
  opening balances), **Início**, **Extrato**, **Cartões** — see the handoffs of 2026-09-23 in git.
- **Kit:** `SummaryPanel` (one headline figure and up to three beside it — replaces rows of
  `MetricCard`s; `ProjectionHeader` uses it), `Menu` (the "⋯" row menu), `Toaster` + `toast()` in
  `lib/toast.js` (short success notices; errors stay in `AlertMessage`).
- **Posição:** summary panel (carteira, aplicado, resultado with %, líquido estimado — from the
  backend's totals, masked by the eye). The per-row quote input is gone: the quote is read-only with
  its status dot; "Editar cotação" and "Atualizar cotação" are in the row `Menu` and editing opens a
  sheet. Fixed-income partial redemption is a sheet instead of two `window.prompt`s and an `alert`
  (same payload). Ticker and title names wrap instead of truncating.
- **Operações / Proventos:** summary panel instead of four cards; row actions in `Menu`; success
  notices are toasts; the `alert()` on a failed delete is now the page's warning banner.
- **Orçamento / Recorrentes:** summary panel; Editar/Remover (and Pausar/Retomar) in `Menu`, the
  Acumula toggle stays on the row; Recorrentes' notices are toasts.
- **Importar:** three-step stepper (Arquivo → Conferir → Importado) above the two panels, the
  preview rows run edge to edge. Fixed along the way: the "N lançamento(s) importado(s)" banner was
  cleared by the preview reload the instant it appeared — it had never shown until then.
- **Ajustes:** section chips in the pill style; Categorias and Regras row actions in `Menu` (Regras
  keeps "Aplicar" as a button); Contas and Cartões keep their single icon button (one action is not
  worth a menu); notices are toasts; inner boxes rounded like the rest.
- **Extrato:** Editar/Excluir in `Menu`; the paperclip stays visible beside it.

### Phase 4 — Reduce friction — 2026-09-22
- **CSV statement import** — `backend/statement_import.py` parses the file (delimiter sniffing,
  pt-BR and en-US numbers, the usual date shapes), `POST /api/import/preview` shows what would enter
  without writing, `POST /api/import/commit` writes it. Dedupe is `source_type='STATEMENT_IMPORT'`
  plus a hash of account + date + amount + normalized description, so the unique index from 007
  makes a re-import a no-op; identical rows inside one file get an occurrence suffix and survive.
- **Auto-categorization rules** — `import_rules` (migration 013), `/api/import-rules`, applied in
  the preview only. Managed in Ajustes → Regras de importação, or created straight from a preview row.
- **OFX import** — hand-rolled SGML reader in the same module (no `ofxparse` dependency); the bank's
  `FITID` becomes the dedupe key when the file carries one.
- **Rules on lançamentos already recorded** — `POST /api/import-rules/apply/preview` lists what
  would change category (never writes); `POST /api/import-rules/apply` rewrites `category` and
  `category_id` only for the confirmed `transaction_ids`, re-checking each against the rule, and adds
  to the rule's `hits`. With `rule_id` it runs just that rule (even inactive); without, all active
  rules in import priority. TRANSFER, investment cash and invoice payments are never touched.
  Ajustes → Regras: "Aplicar ao extrato" (all rules) and "Aplicar" per rule open a sheet with every
  row ticked; the pencil edits a rule in the same form as "Nova regra". Tests in
  `backend/tests/test_rule_apply.py`.

### Export to CSV — 2026-09-22
`GET /api/transactions/export` (the same filters as the statement list) and
`GET /api/investments/portfolio/export`. The file is what Excel in pt-BR opens on a double click:
BOM UTF-8, `;` as the separator, comma as the decimal mark. Formatting lives in
`backend/export_csv.py` (pure functions, no DB — the `statement_import.py` shape). The statement has
both `Valor` (magnitude) and `Valor com sinal`, and a TRANSFER leaves the signed column empty so
summing it cannot turn moving money between your own accounts into an expense. Buttons: Extrato →
"Exportar" (exports exactly what the filters show) and Investimentos → Posição → "Exportar".

### Receipts per lançamento — 2026-09-23
Table `transaction_attachments` (migration 014) rather than a path in `metadata`: several files per
row, and `metadata` is rewritten by the investment cash sync. Files live in
`ATTACHMENTS_DIR/<user_id>/<generated name>` (default `backend/attachments/`, gitignored); the type
is sniffed from the bytes (PDF, JPG, PNG, GIF, WEBP, HEIC), 10 MB and 20 files per lançamento.
Routes are nested under the lançamento (`/api/transactions/<id>/attachments`, `.../<aid>/file`,
`DELETE .../<aid>`), so the ids must match. Deleting a lançamento removes its files; files orphaned
by other paths (an investment movement deleted takes its cash row) are swept at boot.
`GET /api/transactions` carries `attachment_count`. Any row takes receipts, including investment
cash and invoice payments. Tests in `backend/tests/test_attachments.py`.

### Budget strip on Início — 2026-09-22
"Orçamento do mês" panel reading `GET /api/budgets` for the current month; status rule mirrors
`serialize_budget()` (`budgetStatus()` in `components/BudgetProgress.jsx`).

### Phase 5 — Backend refactor, first part — 2026-09-23
Code moved verbatim, suite green and one commit per step. `tests/test_route_map.py` pins the 60
routes (rule, methods, token) from before the split.
- Foundation: `config.py`, `db.py`, `validators.py`, `auth.py`, `money.py`, `dates.py`,
  `source_types.py`.
- Services: `services/accounts.py`, `services/invoices.py`, `services/attachments.py`.
- Blueprints: system, auth, accounts (+ transfers, categories), transactions (+ CSV export),
  attachments, budgets, recurring, imports (+ rules), cards (+ cc-expenses, pay-invoice).
  `app.py` 7,692 → 3,603 lines.

### Phase 5 — Backend refactor, investments — 2026-09-23
Same rules: 133 definitions moved byte-identical (checked by script against `363e518`), the only
edit `@app.route` → `@bp.route`; suite green and one commit per step (`93fe66a`..`a06b3f1`).
- `asset_classes.py` (the class constants and `parse_asset_class_filter`), `responses.py`
  (`csv_response`, out of `routes/transactions.py` so no blueprint imports another).
- `services/prices.py` (caches, executor, brapi/yfinance, `record_price_quote`),
  `services/fixed_income.py` (indexers, BCB, accrual, the two-half refresh),
  `services/investments.py` (movements, assets, cash link, backing validation),
  `services/realized_results.py` (tax rates, FIFO, realized results — split out of investments,
  which would otherwise have been ~1,000 lines), `services/portfolio.py` (snapshot, materialized
  positions, market refresh, evolution). Import order: prices ← fixed_income ← investments ←
  realized_results / portfolio.
- Blueprints `routes/investments.py`, `routes/proceeds.py` (proceeds helpers live in the blueprint,
  their only caller), `routes/market.py`.
- Tests reach moved code through fixtures `prices_module`, `fixed_income_module`,
  `realized_results_module`, `portfolio_module`; `yf` is patched in `services.prices` *and*
  `routes.investments` (the history route reads it too).
- Leftovers, same day: removed the unused `time` import in `brapi_client.py` and the `f` prefix
  from two strings without placeholders (`fetch_investment_rows`, a budgets test). pyflakes is
  now clean over every tracked `.py`. `create_app()` was left out on purpose — see the known
  limits in `next-steps.md`.

### Browser walk-through on scratch data — 2026-09-23
Seeded scratch DB (`seed_three_years_mock`, scale 0.5) on :5002/:5175; the real `finance.db` was not
touched. What was clicked through is listed at the top of `next-steps.md`. Fixes:
- **Importar:** `runPreview` read `file?.name` from the render *before* `setFile`, so a second file
  was previewed under the first file's name — an `.ofx` picked after a `.csv` went through the CSV
  parser (17 "lines", 15 errors). `handleFile` now passes `picked.name`.
- **Extrato between `md` and `xl`:** `<col className="hidden …">` does not remove a column from a
  `table-fixed` table, and the day row's `colSpan={5}` added a phantom column — header cut short and
  the day total outside the Valor column. The Conta column is now rendered only at `xl`
  (`useIsXl()`, `matchMedia` through `useSyncExternalStore`) and the colSpan follows it.
- **Header 1024–1110 px:** brand `w-44` + `px-8`/`gap-4` did not fit; "+ Novo" was cut off (79 px at
  1024). Below `xl` the brand takes its natural width, `gap-3 px-6`; `main` uses the same gutter.
- **Scroll between screens:** nothing reset it, so a new screen opened at the old scroll offset.
  `Layout` scrolls to the top on a new pathname, except on back/forward and `#anchor` links.
- **Donut:** a real category named "Outros" (the importer's default) collided with the grouped
  "Outros" slice (duplicate React key, two identical legend entries). The bucket is "Demais" then.
- **Rentabilidade 0%** was green; now neutral in Posição and Operações (green means gain).
- Ajustes → Regras had no panel padding; CSV exports sent `text/csv; charset=utf-8; charset=utf-8`
  (Flask appends the charset itself) — tests now assert the exact header.

### Segmented control on two rows — 2026-09-23

Reported by the owner: in "Novo lançamento" the selection pill had the wrong proportions. The five
types wrap onto two rows in the sheet; `useSlidingPill()` measured only `left`/`width` and the
pill ran `top-1 bottom-1`, so it spanned both rows, and the `rounded-full` container became a tall
stadium. The pill now measures `top`/`height` too and moves with `translate(x, y)`; the
`SegmentedControl` container uses a fixed 22px radius (h-9 button + p-1), identical to
`rounded-full` on one row and concentric with the pill on two. `Tabs` shares the hook and still
works (it never wraps). Checked in Chrome on the owner's dev server: pill and a second-row button
measured the same box (174×36).

### Section 1 finished — 2026-09-23 (evening)

Everything under "Open work" in `next-steps.md` was built in one session; the owner walk-through on
real data is the part that stays open. Notes worth keeping:

- **Decision 1 — card purchases in the budget.** A purchase counts in full, in its category, in the
  month it was made (all installments), the same rule as Início's "Despesas por categoria". Invoice
  payments (`CC_INVOICE_PAYMENT`, `CC_AUTOPAY`, or the legacy "Pagamento Fatura…" category) no
  longer count. Budgets planned under the old rule will read as overrun for card-heavy categories.
- **Decisions 7–9.** 7: Cartões keeps "Pagar fatura" and "Nova compra" side by side. 8: the cash
  flow says Receitas (legend, averages, tooltip, patrimônio chip); the "+ Novo" labels stay and
  wrap onto two lines. 9: the eye masks the "+R$ X no mês" chip and drops its colour.
- **Decision 5 — tax.** Support tool, not source of truth: the IR tab carries the disclaimer and
  does not separate day trade (the app stores no time of day).
- **Confirmations.** `confirmAction({ title, message, confirmLabel, tone })` from `lib/confirm.js`
  returns a promise; `<ConfirmHost />` sits in Layout next to the Toaster. No `window.confirm` left.
- **TanStack Query.** `lib/queries.js` owns the `QueryClient`. `apiFetch` calls a mutation listener
  after any successful non-GET (except `/preview` and login/signup) and the listener invalidates
  every query, so no write path can forget to refresh. The cache is cleared on auth change; the old
  `@financeMVP:*` localStorage caches are deleted on load. `dataVersion` survives only for the
  Extrato "arrived" flash.
- **Import rules 015.** `amount_min`/`amount_max` compare the absolute value, inclusive;
  `account_id` is the destination account in the preview and the row's account in "Aplicar". The
  unique index now includes the conditions (COALESCE, since SQLite treats NULLs as distinct).
- **Exports.** `export_csv.py` describes each export as typed `Column`s; the same table becomes CSV or
  `.xlsx` (`export_xlsx.py`, hand-written OOXML over `zipfile`, no dependency; checked with openpyxl
  in a scratch folder — there is no Excel on this machine). CSV headers now carry accents.
- **Receipts.** `db.mirror_attachments()` runs with every backup: one copy per file in
  `backups/attachments/`, deleted receipts moved to `backups/attachments-removed/AAAAMMDD/` and
  expired with the backup retention. Card-purchase receipts (016) hang on the installment they were
  attached to and list across all installments of the purchase (card + description + date +
  category, the `/candidates` key).
- **Healthcheck found a real bug.** brapi now returns each quote under `data`; the parser read
  nothing and every B3 quote silently fell back to yfinance. `StockQuote.from_payload` reads both.
- **Corporate actions 017 — adjust on write.** Earlier movements are rescaled in place (originals in
  `metadata.corporate_adjustments`), earlier quotes too; a bonus is a zero-cash BUY row. Guards: no
  movement dated (or moved) before the asset's latest event; bonus rows only go through the event;
  events in date order; undo only the latest, and only with nothing after its ex date. After an
  event the asset's quote is refreshed (the ex-date quote can be on either side of it).
- **Multi-currency 018.** Native values stored; `fetch_investments()` converts to BRL (cost at each
  movement's `metadata.fx_rate`, value at today's PTAX); the cash link is in BRL; foreign stocks
  skip the B3 catalog and brapi; accounts get `balance_brl`; transfers between currencies refused.
  Proventos of foreign assets are taken as BRL (not converted).
- **Evolução.** Past months use `accrual_factor_until()` with CDI/IPCA from `index_history()`; the
  current month uses the stored BCB quote, or the series when the title has none yet.

### Recurring pause window — 2026-09-26

- **Decision 2, settled in code.** Pausing stores `paused_at` (the day). Resuming appends the window
  `(paused_at, resume day)` to `pause_gaps` (JSON `[[start, end]]`), exclusive at both ends, and
  leaves `next_run_date` where it was: an occurrence due before the pause (or on the pause day)
  stays pending, occurrences strictly inside the window are never due. `/run`, the pending count and
  the forecast all skip windows through `recurring_occurrence_dates()`; `/run` drops a window once
  the cursor has passed it. Pause and resume on the same day skip nothing.
- **Stored cursor.** `last_occurrence_date` is the last date `/run` walked (never moved back, even by
  a rewound `next_run_date`); reviving a finished recurrence starts after it, so deleting the last
  generated lançamento no longer brings it back. 019 backfills it from the materialized rows.
- **Edges.** A recurrence paused before 019 has no `paused_at` and resumes the old way (walks to
  today). An explicit `next_run_date` in a PATCH clears the windows — the user took the cursor.
  Recorrentes shows "pausada desde dd/mm" for a paused row.

### Carteira export fixes — 2026-09-26

From the owner's first real carteira `.xlsx`. Notes worth keeping:

- **Whole quantities.** Excel always prints the decimal separator of `#,##0.######`, so `3024`
  showed as `3.024,`. `export_xlsx.value_cell()` gives a whole quantity (after `round(n, 6)`) the
  built-in `#,##0` (style `STYLE_QUANTITY_WHOLE`); fractional ones keep 165.
- **IR per asset** is now `rounded(gross) − rounded(net)`, not the rounded raw tax, so the three
  columns always add up (one CDB was off by R$ 0,01). Screen and export read the same.
- **Portfolio totals** (`total_invested`, `current_balance`, `current_net_balance`) round through
  `rounded_money()`; they used `round()`.
- **Valor investido.** The snapshot exposes `total_invested` per asset, and the export reads it
  instead of quantity × the rounded average price (which drifted by cents on stocks); the
  `investment_positions` cache (`GET /api/investment-positions`) stores the same value.

### Allocation, goals and exemption meter — 2026-09-26

Picked from a walk through Investidor10 PRO's screens (Resumo, Posições, Proventos,
Patrimônio, Rentabilidade, Análise, Lançamentos, DARFs, IRPF, Metas), as the three features that
reuse what the app already computes and need no new external data.

- **Allocation (020, `services/allocation.py`).** Two levels: class = % of the portfolio, asset = %
  of its class (changing the Ações target doesn't force redoing each stock's). `GET /api/allocation`
  returns actual vs target, the gap in R$ and, with `?contribution=`, the split: with the portfolio
  after the contribution, each class needs `target × new total − current`; the amount is divided in
  proportion to the positive shortfalls, then again among the class's assets. Cents left by rounding
  go to the largest shortfall, so the split adds up exactly. "Oportunidade de compra" (as on
  Investidor10) = below its target in the class *and* quoted below the average price. An asset with
  a target and no position still appears (that is where the money should go).
- **Goals (021, `services/goals.py`).** Kinds: NET_WORTH (portfolio net + accounts in BRL, same as
  Início), PORTFOLIO, ASSET_CLASS, MONTHLY_INCOME (net proventos of the last 365 days / 12). The
  forecast iterates months with the contribution and the expected annual return turned into a monthly
  rate (capped at 100 years); an optional target date gives the monthly contribution needed
  (annuity formula, `rounded_money()`), and "No prazo / Fora do prazo".
- **Exemption meter (`exemption_meter()` in `services/tax_report.py`).** `GET
  /api/tax-report/exemption?month=&planned_sale=` returns the month's stock sales, what still fits
  under R$ 20 mil (≤ 20.000 is exempt, same as the report), the estimated tax if over, and the loss
  balance up to that month (the apuração is cut at the month, so a month without sales still shows
  it). `planned_sale` powers the warning in "Registrar operação" → Venda before saving.
- The rest of the survey is listed in `next-steps.md` ("Ideas from the Investidor10 survey").

### Proventos per asset, TWR and contributions — 2026-09-26
Built by three subagents in parallel git worktrees, merged into main (`3c6ac06`, `bfec9d5`, `a70edcf`).
- **Total return per asset** (`asset_total_return()` in `services/portfolio.py`): numerator = net
  value − current cost + proventos received + realized profit after estimated tax; denominator =
  all money ever put in (current cost + FIFO cost of the shares sold). Current cost is *not* the
  snapshot's `total_invested`, which subtracts the sale value, not its cost (buy 100 at 10, sell 40
  at 15 → 400 instead of 600). `profitability_percent` is unchanged.
- **12-month window** for proventos is `payment_date` in (today − 365, today], as in goals. In
  `by_asset`, `net_12m` follows the asset/type filters but not the period filter, so the page's
  default current-year filter doesn't cut it. Fixed-income titles get every paid provento pointing
  at their asset; two open titles on one asset → the first gets it all (never counted twice).
- **TWR**: monthly Modified Dietz, chained, on gross values. A buy is quantity × price; a sale or
  redemption is the net cash received. A month with no starting value is measured from the first
  buy (and ends at the last sale after a full exit), otherwise a day-30 buy would have its gain
  multiplied by 30. Empty months are skipped. The backend always evaluates the whole current year
  so YTD and the year table are complete. `PRICES_ARE_DIVIDEND_ADJUSTED` in `returns.py` guards
  against counting proventos twice if prices ever become adjusted. `build_portfolio_evolution()`
  is now a sum over `iter_portfolio_months()` (per-position values, gross and net); its output is
  unchanged. `load_history_inputs()` in `routes/investments.py` is shared by history and returns.
- **Contributions**: aportes = buys at quantity × price (no fees, the cash-link figure); resgates =
  sells and fixed-income redemptions/maturities, gross. Amortizations are proventos, not resgates.
  Bonus rows (`is_bonus_movement`) excluded. Every month in the window is listed.
- **Concentration** (`concentration` in the allocation response): an asset strictly above 10% of
  the net total; "abroad" = held in a foreign currency (there is no foreign asset class).
- Chart colours: `CHART` holds only grid/axis/tick/ink; series colours come from `FLOW` / `SERIES`
  in `charts.jsx`, as on the Dashboard.

### Investments follow-ups — 2026-09-26 (evening)
Three subagents in parallel worktrees, merged into main (`4ff8a10`, `258a1d2`, `11b719a`).
- **Rentabilidade filter:** `ASSET_CLASSES` is now shared in `pages/investimentos/helpers.js`
  (AportesChart uses it too). The chosen class is not persisted; the period still is. An unknown
  class is not rejected — `parse_asset_class_filter()` falls back to the whole portfolio, as on the
  contributions endpoint; `test_asset_class_filter_scopes_assets_and_proventos` pins that.
- **Carteira export:** the four columns sit right after "Rentabilidade (%)", in Posição's order.
  The export sheet's column picker reads `GET /api/exports/columns`, so they appear there without a
  frontend change. Percentages are written to .xlsx as fractions with the percent style. The
  12-month window reads the real `date.today()` (no clock hook), so tests date proventos relative
  to today.
- **IR proceeds:** `paid_proceeds_in_year()` wraps `fetch_investment_proceeds()` with the year's
  ISO range, `status=PAID`, ascending. `fetch_investment_proceeds()` gained
  `asset.user_id = proceeds.user_id` in its join (the old tax-report SQL had it). Same-day ties are
  now ordered by `created_at` (were undefined). Four characterization tests written against the old
  SQL first: year boundaries, ordering, amortization and scheduled excluded, foreign taken as BRL,
  user isolation.

### Investidor10 ideas: benchmarks, sectors, IRPF text — 2026-09-26 (night)
Three worktree subagents, merged into main; 836 tests.
- **Benchmarks** (`58f5092`): `GET /api/investments/returns` now carries `benchmarks[]` (code,
  totals, `difference_pp` only when the index covers the whole window, note) and per-month
  `benchmarks.{IPCA,IBOV,IFIX,IDIV}`; a month without data is `None` so the line breaks. IPCA from
  BCB (SGS 433), Ibovespa from yfinance `^BVSP` (brapi fallback, free plan = 3 months). IFIX/IDIV
  have **no free history** (yfinance and brapi give only today's value): every close seen is stored
  in `benchmark_closes` (per user, like `fx_rates`), so they build history from 2026-09 on; a month's
  close is the last one seen. Chart cards toggle lines (choice in `localStorage`). Test patch points:
  `services.benchmarks.download_monthly_history`, `brapi_client.get_history` / `is_configured`,
  `services.fixed_income.fetch_bcb_series`; call `services.benchmarks.reset_fetch_throttle()`.
- **Sectors** (`e74ec70`): migration 022 adds `sector`, `segment`, `sector_source` (`BRAPI`/`MANUAL`),
  `sector_checked_at` to `assets` (per user, so a manual correction is the owner's). brapi's quote
  endpoint has no sector; `/quote/list` does (English sector, Portuguese subsector; ~2,330 tickers,
  2 pages, cached 24h in memory). Stocks: translated sector (`SECTOR_LABELS`, our own translation) +
  subsector as segment; FII: sector = its segment. Only BRL stocks/FIIs are looked up; manual is
  never overwritten. Breakdown computed on read from `build_portfolio_snapshot()`. Routes:
  `GET /api/allocation/sectors`, `POST /api/allocation/sectors/refresh`,
  `PATCH /api/assets/<id>/sector`.
- **IRPF text** (`e4c34b4`): `backend/irpf_text.py` is pure formatting over the report — no tax rule
  of its own. Sections: Bens e Direitos (IRPF 2024/2025 code table), isentos (09, 12, 20, 99 for FII),
  exclusiva (10, 06), renda variável month by month with opening loss and DARF 6015. CNPJ, custodian
  and foreign location always "(preencher)" — never invented. Report gained
  `rendimentos_por_fonte`, `renda_variavel.opening_loss_balance`, `bens_e_direitos[].name`,
  `irpf_text`. Privacy mode hides the Bens preview; Copiar still copies.
- Merge fix (`f6690fc`): both branches added a `_request_json` to `brapi_client.py` with different
  signatures; the sector one is now `_request_list_json`.

### Yield on cost fix — 2026-09-26 (late)
Found in a Chrome walk-through on scratch data: Proventos showed yield on cost 1,29% for 2026
where R$ 2.576 on ~R$ 44k of cost is ~5,9%. `build_proceeds_by_asset()` and the summary summed
`cost_basis_at_record_date` over **events**, so an asset paying monthly divided its income by 12×
its cost (the old test even asserted 7,125% for R$ 142,50 on R$ 1.000). Now an asset's
`cost_basis` is the **average** of its events' cost at the record date (events with cost > 0 —
a position that grows between payments averages), and the summary's `cost_basis` is the sum of
the per-asset costs, so `summary.yield_on_cost_percent` and the by-asset column use the same
denominator. Per-event YOC is unchanged. This matches the portfolio's `dividend_yield_12m` basis
(one cost per asset). Tests: corrected expectation + monthly payer + growing position.

### Walk-through inconsistencies — 2026-09-27
Three small mismatches from the 2026-09-26 Chrome walk-through, fixed by three worktree subagents.
- **Posição chart gross.** `build_portfolio_evolution()` already built a gross value per position
  and dropped it when summing; each month now also carries `patrimonioBruto` and
  `ganhoCapitalBruto` (net fields unchanged). The bars use gross, so chart, "Carteira" headline and
  allocation donut share one basis; the tooltip adds "Líquido de IR estimado" when it differs.
- **Rentabilidade = Posição today.** The monthly valuation (`portfolio_month_positions()`) priced
  the current month its own way: fixed income without a stored BCB quote re-accrued from the series
  to today, and stocks/FIIs took the yfinance month close instead of the stored quote. Both now go
  through `position_value_today()` in `services/portfolio.py`, which `build_portfolio_snapshot()`
  also uses; the current month's estimated IR uses today, like Posição. Past months unchanged.
  Reproduced at seed scale 10: after "Atualizar cotações" the whole gap was stocks/FIIs (R$ 254,01,
  ~R$ 25 at scale 1) — so the walk-through's "all in fixed income" was probably a misreading.
  Trade-off: a fixed-income title never refreshed from the BCB now dips in the current TWR month
  until quotes are refreshed (it sits at its stored price, as in Posição). `current_price_from_position()`
  and `quote_source` were removed (no other callers). Tests: `TestCurrentMonthMatchesThePosition`
  (4) and `TestGrossAndNet` (2).
- **Orçamento copy.** "Realizado" hint → "Saídas e compras no cartão no mês"; page and panel
  descriptions now say what `budget_spend_by_category()` counts (lançamentos without transfers, card
  purchases in full in the purchase month, invoice payments never).

### Operação anterior ao app — 2026-09-27

Asked by the owner: a first-time user has to enter investments bought years ago, and every buy used
to create an EXPENSE in the default account, so the balance went deeply negative. Now a movement
with `metadata.skip_cash = true` gets no linked lançamento — `sync_investment_cash_transaction()`
checks `investment_skips_cash()` first and deletes any linked row (so an edit can toggle it both
ways, and no PTAX is fetched for a foreign movement that has no cash). FIFO, portfolio, IR and TWR
are untouched: they read movements, not cash. The flag is per movement, so a later sale of an old
position still brings cash in unless it is flagged too. UI: a checkbox "Operação anterior ao app"
in "Registrar operação" (buy and sell) and in the operation edit form; the Operações list tags the
row "anterior ao app". No migration (metadata is JSON). Tests: `TestPositionBeforeTheApp` in
`test_investment_cash_link.py`. Not built: the flag on the fixed-income redemption form in Posição
(the backend honours it, the form does not send it), and a bulk "mark everything before date X".
Superseded on 2026-10-12: the link became opt-in and `skip_cash`, the checkbox and the tag were
removed ("Investments separate from banking", below).

**Fixed-income exemption by title type (2026-09-27).** `fixed_income_is_tax_free()` in `services/fixed_income.py` is the one rule: LCI, LCA, LIG, CRI, CRA and `DEBENTURE_INCENTIVADA` are exempt; a stored `is_tax_free` is still honoured for old rows. Net value, realized tax, the portfolio flag and the IR Bens code all read it. The form has no checkbox any more: it shows "Isento de IR" / "Tributado" from the type and writes `is_tax_free` accordingly; an old `DEBENTURE` flagged exempt opens for editing as `DEBENTURE_INCENTIVADA`. "Rentabilidade" offers Pós (CDI), IPCA+ and Pré; IPCA+ is still stored as `rate_type POS` + `indexer IPCA`. `CATTLE` stays a live class (existing positions show and can be sold); only the buy picker hides it. Superseded the same night: the owner asked to remove `CATTLE` everywhere — `ALLOWED_ASSET_CLASSES`, labels, its tax rate, the mortality rule in the portfolio value, the GCAP filter (now `OTHER` only) and every frontend class list. The real `finance.db` had 0 CATTLE movements and 0 targets. The migrations' CHECK constraints still list it; not worth a table rebuild.

**Ritmo de gastos against the 3-month average (2026-10-12).** Asked by the owner: "am I spending too much?" The Início panel used to draw this month against last month only. Now `spendingPace` in `pages/Dashboard.jsx` averages the cumulative spending of the `PACE_MONTHS = 3` previous months day by day (same `buildSpending()` definition: account expenses without invoice payments and investment outflows, card purchases in full on the purchase date). The panel shows the amount above/below the average up to today's day, the percentage badge, the average full-month total, one figure per month at the same day, and the average as the grey line. A month with no spending at all is left out of the average (it is a month before the app was in use); a month shorter than today's day counts by its total. "Até hoje" is now the cumulative up to today, not the whole month's total (they differ only with future-dated lançamentos). Frontend only, no endpoint. Checked with Playwright on a scratch database with known values (desk 1400 px and phone 390 px).

### Investments separate from banking — 2026-10-12

Asked by the owner: the investments area and the expenses area should be separate, with the option
of creating the lançamento in the banking area per operation. Investigated first (the coupling was
one function, `sync_investment_cash_transaction()`, and no financial calculation read the linked
rows), planned in `docs/areas-separation.md` (deleted once built — `git log` has it), then built
the same day by three subagents on disjoint files.

- **The rule.** A movement writes a lançamento only when `metadata.cash_account_id` names one of the
  user's active BRL accounts: exactly one linked row in that account, same shape as before
  (`source_type = 'INVESTMENT_TRANSACTION'`, id `cash:<movement>`, category "Investimento"). Absent,
  nothing is written. `investment_cash_account_id()` is the rule; `resolve_investment_cash_account()`
  validates before any write (unknown or another user's account, archived, non-BRL and non-string
  values are refused with a 400, and nothing of the request is written). Changing the account on an
  edit moves the same row. On `PATCH` an omitted key keeps the link — a form that rebuilds the
  metadata cannot delete a lançamento by accident — and `null` removes it, refused with 409 while
  the linked row has a receipt. An account archived after linking does not block later edits.
  A linked movement always has its row: one that asks for the Extrato with no cash amount to write
  (price zero, costs above the sale) is refused with a 400 and the whole request is undone —
  `finance-guard` found that such an edit used to delete the row and its receipt past the guard.
  `metadata.skip_cash`, `investment_skips_cash()` and the silent default-account link are gone.
- **Forms.** `components/CashLinkField.jsx` ("Lançar no extrato" + account picker, BRL accounts
  only, default account preselected, off by default) in "Registrar operação", the Operações edit
  sheet and the Posição redemption sheet. Operações tags linked movements "no extrato". Edit errors
  now show inside the sheet (the page alert sat behind it).
- **Início is banking-only** — the owner reversed the plan's decision 2 so the headline is never
  read as money to spend. The hero is "Saldo em conta" (consolidated balance, account tiles); the
  portfolio query, the "Em conta / Investido" bar and Patrimônio are gone. The "no mês" pill is the
  accounts' net movement, equal to the chart's "Resultado".
- **A resgate is not a receita.** A linked or typed-in-"Investimento" INCOME is kept apart like the
  aporte already was (`isInvestmentInflow()` in `lib/transactions.js`): Início's cash flow (one net
  investment series, shown only when the window has such rows; the tooltip says "Investido" or
  "Resgatado"), Extrato totals and badge ("Resgate"), Recorrentes label.
- **"+ Novo" is banking-only**; inside `/investimentos` the same button opens "Registrar operação".
- **Not built, on purpose** (the owner allowed a database reset instead): migration 024 and the
  bulk "Desvincular do extrato" tool of the plan. `backend/finance.db` was moved to
  `backend/backups/finance-pre-areas-separation-20261012-224633.db` (verified after the move: same size,
  same row counts, integrity ok; a name the retention never prunes) and the app starts from an
  empty database built by the migrations.
- **Also changed:** `scripts/seed_three_years_mock.py` asks for the link on every operation (its
  mock models someone who records them in the main account); `lib/portfolio.js` deleted (unused).
- Tests: `test_investment_cash_link.py` rewritten around the opt-in; six files that read linked rows
  now send the key (`test_attachments`, `test_accounts_and_transfers`, `test_corporate_actions`,
  `test_transaction_edit`, `test_multicurrency`, `test_rule_apply`); 908 in the suite. Frontend
  checked with Playwright on a scratch database (desk 1400 px and phone 390 px): Início, "+ Novo"
  in both areas, the three forms, untick/re-tick on an edit, and a ticked redemption.

### Reais-only on screen — 2026-10-12

The walk-through of Início on a scratch database surfaced a dollar account whose tile printed the
dollar amount labelled R$. A first fix showed US$; the owner corrected it twice — "The app is in
brazilian reais", then "Everything on the app should be reais". The owner's own data had never used
another currency (2 accounts and 24 assets, all BRL; no movement with an exchange rate).

- **No currency choice.** "Moeda" and "Câmbio" are gone from "Registrar operação"; "Moeda" is gone
  from Ajustes › Contas. The operation form always says "Preço em R$" and no longer sends
  `currency` or `fx_rate`.
- **No foreign amount.** An account balance on any screen goes through `accountBalanceBrl()` in
  `lib/transactions.js` (the converted `balance_brl`, or "sem câmbio hoje" when there is no rate):
  Início's account tiles and débito-automático warning, Ajustes › Contas, the "Pagar fatura" account
  picker and its balance check. Posição no longer prints the native quote under the price.
- **No foreign wording.** Removed: the "Nenhum ativo em moeda estrangeira" note in Alocação, the
  "Moeda" column of the IR `.xlsx`, the "Ativo no exterior" note in Rentabilidade, and
  `formatMoney()`. The IR tab's "Aplicações no exterior" panel and the "Exterior" row of the IR
  export used to be printed for everyone with zeros; they now appear only when the year has a
  foreign result. `finance-guard` caught the first version, which dropped both outright: with a
  foreign sale in the database (only the API can create one) the 15% estimate would have been
  shown nowhere. Test: `test_the_export_carries_the_foreign_result_only_when_there_is_one`.
- **Still printed if a foreign row exists** (API-only): "(exterior)" in the Bens e Direitos label
  and "Custodiado no exterior, em USD" in its description and in the IRPF paste text.
- **Kept on purpose:** the backend machinery of migration 018 and its tests. No screen reaches it;
  the API still accepts a currency. Removing it is listed in `next-steps.md` as the owner's call.
  A foreign asset already in a database could not be sold from the form any more (the API refuses
  a movement in a different currency from the asset's) — none exists.
- Checked with Playwright on a scratch database that holds a dollar account created through the
  API: all 14 screens, every collapsed block opened, searched for US$, €, £, Dólar, Euro, Libra,
  "moeda estrangeira", "exterior" and PTAX — none; Ajustes shows that account as R$ 500,00. Then a
  dollar buy and sale posted through the API: the IR panel stays hidden for the year without the
  sale and shows R$ 1.000,00 / R$ 150,00 for the year with it. 909 tests in the suite.

### Automatic proventos — 2026-10-16
- **Source.** brapi's dividends module answers 403 on the free plan ("requer o plano Startup").
  StatusInvest's `companytickerprovents` is public JSON with data com, payment date, type and
  value. Investidor10's own earnings API needs a logged-in session, so it was used only to check.
- **Basis.** StatusInvest marks pre-split values `adj: true` (already in today's basis, like our
  rescaled quantities) and leaves pre-bonificação values unadjusted (our bonificação is a buy on the
  ex date). Quantity on the data com × value matched Investidor10 on assets with splits and
  with bonificações.
- **Tax.** Investidor10's net/gross ratios: JCP 0.85 for data com up to 2025, 0.825 from 2026;
  "Rend. Trib." 0.775. That is the rule now.
- **Reconciliation** against Investidor10 on a real history: all but a handful of rows matched
  (see next-steps.md), each with the same quantity. A renamed FII needed an entry in
  `TICKER_ALIASES`. One StatusInvest row (paid before its own data com) is dropped as a typo.

### Screen self-update — 2026-10-17
- **Why hand-written.** Capacitor's `Bridge` already reads `CapWebViewSettings`/`serverBasePath` when
  it loads the WebView and wipes it when the APK changes (`isNewBinary`). Plugins' `load()` runs
  before that read, so `BundlePlugin.load()` decides which screens open on the same start. That
  left only download, verify, trial and rollback to write — no third-party updater, no telemetry.
- **Version = content hash, target = whatever the server serves.** No ordering between versions:
  a revert pushed to `main` takes the phone back, to the APK's own screens when the hash matches.
- **The native level is manual** (`frontend/native-level.txt`, also `BuildConfig.NATIVE_LEVEL`).
  Nothing checks that a native change bumped it; CLAUDE.md says when to.
- Details and the rollback rules are in `mobile-docs/steps-to-production.md`.

### Bank-notification listener — 2026-10-17
- **No parser yet, so nothing is kept with capture off.** The listener drops anything off the
  allow-list without reading it; with capture off it stores nothing, because no code would read
  it. When parsers come (Phase 6 step 4) the listener feeds them whatever the capture switch says.
- **Every textual extra is captured**, not only title/text/bigText: one week of capture is the
  fixture set for the parsers, and a field left out would cost another week.
- **Nothing is deduplicated across apps.** A Samsung Pay purchase is expected to notify from
  Samsung Wallet and from the bank; both are kept with posted times to the millisecond. Picking
  one source per purchase is Phase 6/7 work, written from the export.
- **The test APK is a separate package** (`applicationIdSuffix ".debug"`): the release build never
  accepts `com.android.shell`, and an adb test can never replace the real app or its queue. CI
  signs it with the same key so each new one installs over the last; it is not in `version.json`
  and `AppUpdate` never offers anything to it.
- **Checked in the cloud session without an Android SDK** (dl.google.com is blocked there): the
  JVM tests ran with plain `javac` + JUnit from Maven Central; the Android classes were compiled
  against Robolectric's `android-all` (API 36) and Capacitor 8.5.3's `classes.jar`, with stubs
  for three androidx methods. The Gradle build first ran in CI after the merge (PR
  guneves/financas#1, deploy run 13): green, APK 10013 and the test APK, both with the phone's
  certificate. The screen was opened in Chromium at 360 px (light and dark, with and without
  access) with the plugin mocked.

### Investments check — 2026-10-17
Asked by the owner as "check the investments area, fix every error, open a PR". Done on a
scratch database seeded with `seed_three_years_mock.py`, the backend and a built frontend, in
Chromium at 360 and 1280 px; no provider is reachable from the cloud container, so prices were
the stored ones.
- **Three costs for one position.** The realized result and Bens e Direitos used FIFO lots;
  Posição and the evolution subtracted whatever price the SELL row stored (the screen sends the
  position's average, the seed and the API sent the sale price). The seed's WEGE3 showed a
  R$ 77,11 FIFO *loss* that the average cost (the Receita's rule, Lei 8.981/1995 art. 72 §2º; IN
  RFB 1.585/2015 art. 58) makes a R$ 12,89 exempt *gain*, and three different remaining costs.
  Now `apply_average_cost()` computes the cost server-side for everything. The old next-steps
  item "a position with applied value ≤ 0 drops out of the monthly valuation" was this bug.
- **ETFs and BDRs were "ações" for the IR**: their sales counted toward the R$ 20 mil and their
  gains could be exempt. The exemption is for ações only (Lei 11.033/2004 art. 3º I). The kind
  comes from the catalog (`market_catalog.tax_kind`), so the asset class on screen stays "Ações".
- **The per-sale IR was a second copy of the rule**: 15% of each FIFO lot, ignoring the
  exemption and the loss pool (PETR4's exempt sale showed IR R$ 20,58; a loss-making sale showed
  IR). The monthly rule now lives in `services/variable_income_tax.py` and each sale stores its
  share, so Operações and the IR tab agree.
- JCP's 17,5% from 2026 (LC 224/2025) and the MP 1.303/2025 lapse were checked; the rate stays.
- False alarm worth knowing: in a downscaled full-page screenshot "R$ 0,00" read as "R$ 0.00";
  reading the cell text showed the formatting was right.

### Samsung Wallet pairing — 2026-10-18
Done in the cloud container: no Android SDK (pure Java compiled with `javac` + JUnit 4.13.2 +
`org.json` from Maven Central).
- **Bank decline vs Samsung decline**: the prompt said a DECLINED from either source cancels the
  counterpart; the rule lets only the bank's decline cancel (an unconfirmed Samsung), because the
  bank wins and a lost real purchase costs more than one extra suggestion.

### Notification auto-identifier — 2026-10-17
Owner: "identify and insert under approve every notification that refers to a transaction …
recognize when a transaction is made between my accounts and with external accounts"; "every
transaction identified through a notification should end up in aprovar"; Samsung Wallet only
handles card payments and is a fallback — on a duplicate the bank's notification wins.

- **Source**: the owner's capture export (10 notifications, 2026-10-17). The test fixtures in
  `NotifyParsersTest` keep each text's shape with the name and CPF digits swapped.
- **Phone** (`android/.../notify/`): `NotifyParsers` (pure, 17 JVM tests) reads title, text/bigText,
  `android.infoText` (where BTG puts everything) and text lines; negatives first (declined,
  refund, cancelled/scheduled/fatura ignored), the amount anchored to the movement phrase (not a
  balance or limit), merchant by fragment (`em <local>`, `Local:`), card `final 1234`,
  installments, and for Pix/transfers the counterparty name, the masked CPF's six visible digits
  and the institution. Samsung yields only card purchases or declines. The listener parses every
  allowed notification, capture on or off; `DetectionQueue` (`financas_detections.db`) holds the
  parsed fields, `DetectionWorker`/`DetectionSender` POST them in batches to
  `/api/inbox/detections` with the app closed (also scheduled at login). No native-level bump:
  no screen calls the new Java.
- **Server** (`services/inbox.py`, migration 031): detections carry `counterparty`,
  `counterparty_doc`, `counterparty_bank`. "It's me" is **learned** (`inbox_hints` keys
  `self:doc:<digits>` / `self:name:<name>`): when an OUT leg and an IN leg of the same amount pair
  into a transfer, and when the owner approves an item as a transfer. Then a single leg whose
  counterparty is the owner becomes a TRANSFER draft, the other account guessed from the cited
  institution (or asked); the other leg, if it arrives, fills that side. A counterparty that is
  not the owner gives a despesa/receita "Pix para/de <nome>" with reason `external_transfer`. Two
  legs whose CPFs (or first names) differ never pair. The same notification posted twice by the
  bank (BTG: 24 ms apart, same `when`) is `repeated`, not a second item. The remembered-choice
  shortcut that matched an existing lançamento without an item is gone: it is a pending item
  with the lançamento as candidate. 17 tests in `test_inbox_counterparty.py`.
- **Second export, same night** (BTG Banking -> BTG Investimentos, R$ 5,08): the bank says only
  "Sua transferência de R$ 5,08 foi confirmada." (no direction word: "confirmada" now reads as
  outgoing) and the brokerage "Recebemos sua transferência no valor de R$ 5,08…" (TRANSFER_IN).
  Neither names a counterparty, so a transfer seen by the brokerage app is always the owner's own,
  the other side guessed as the BTG bank account; with both legs it is one transfer
  bank -> Corretora.

### TWR against Investidor10 — 2026-10-18
Owner: Investidor10 shows 25,48% (12 months) and 57,42% (total) and asked for the same
behaviour. Compared on the PC's dev copy (the 2026-10-16 snapshot the server imported) against
Investidor10's own API, read from the owner's logged-in Chrome tab.
- **Entries**: the 555 imported operations match Investidor10 by id — date, type, quantity and
  value — and so do the 8 bonificações. Missing here: AMER3 (two buys on 16/08/2024, R$ 16,80,
  the 100:1 grupamento of 26/08/2024, a sale of R$ 5,75 on 10/04/2025); the owner said exact
  parity isn't needed. Proventos per asset match Investidor10's "earnings received" (net).
- **The big error was bonificações, not the method.** Yahoo records a B3 bonificação as a split
  (KLBN4 1.1 on 2024-05-07, SOJA3 1.048629 on 2025-12-19, ITSA4, SLCE3, GOAU4…) and divides
  every earlier close by it; our earlier quantities are not rescaled (a bonus is its own BUY
  row), so every purchase before a bonus looked like an instant loss of 1 − 1/factor, and the
  bonus row counted as an aporte at its IR cost (GOAU4: R$ 398 that never moved). FESA4 −33%,
  SOJA3 −28%, KLBN4 −14% per asset came from this. `restore_quantity_basis()` multiplies the
  closes before each Yahoo event back, except an event matching a registered SPLIT /
  REVERSE_SPLIT (±7 days, ratio within 2%), whose rescaling already put our quantities in
  Yahoo's basis. Applied to the daily closes the returns read and to the monthly closes the
  evolution reads (derived from the same daily download, `monthly_closes()`).
- **Daily chaining**: Investidor10's FAQ says the weighted return is computed once a day.
  r = (V1 + sales + proventos) / (V0 + buys) − 1. Results on the dev copy: total 48,13% →
  56,45% (Investidor10 57,42%); years 10,77 / 3,97 / 18,47 / 14,67 vs 10,66 / 1,98 / 19,59 /
  16,64. Per asset, BBSE3 84,7 vs 85,4, SAPR4 75,5 vs 77,6, SLCE3 23,3 vs 23,6, ITSA4 110,9 vs
  115,8. FESA4 stays −38% vs Investidor10's −0,7%: a small 2023 position lost 35% before the big
  2025–26 buys, which TWR weights fully; Investidor10's per-asset figure behaves differently
  there, and its portfolio figure agrees with ours.
- Proventos on the ex date instead of the payment date: total 58,98%, years further off — kept
  the payment date.
- Fixed income per day: exact accrual at each month end (and today), geometric interpolation in
  between (`FixedIncomeCurve`), because the full series per day is quadratic.
- `?months=all` starts at the month of the first operation (of the class, with the filter),
  capped at 60. The 3A window missed Oct/2023, so nothing on screen matched "Rentabilidade total".

### Five bugs from the owner's review — 2026-10-18
Reported as a numbered list, each already confirmed by the owner; every fix has a test that fails on
the old code. One PR.
- **Transfer vs Aprovar**: `absorb_created()` passed `"transfer"` as a sixth argument to
  `_absorb()` (from the 028 commit). Any typed transfer matching a pending TRANSFER item (both
  legs notified, same accounts, amount, ±`INBOX_MATCH_DAYS`) raised `TypeError`; the request
  rolled back. The outbox's 5xx = retry rule is unchanged: a transfer stuck in a phone's queue is
  delivered (same `client_id`) once the fix is deployed.
- **Invoices**: the invoice month is the due month (`invoice_closing_date()`), so "the invoice of
  next month" is right only for cards that close after their due day. The rule now lives in
  `lib/attentionRules.js`; Início's projection starts at the first next invoice's month, leaves
  overdue rows out and highlights each card's next invoice; the tile reads "Fatura de <mês>", or
  "Próximas faturas" when cards fall in different months.
- **Categories**: `resolve_category()` took `LIMIT 1` on the name, the budget mapped card purchases
  by name (root first), and the Extrato edit always sent the name back. Migration 035 adds
  `cc_expenses.category_id`, filled by name in the budget's own order (root first, then the oldest
  subcategory), so no budget changes on the migration itself. The import commit accepts a rule's
  archived category (it always did, by name); "+ Novo" still sends the name next to the id so a
  pending outbox row shows it; a refund takes the purchase's category id when it sends the
  purchase's name with `refund_of`.
- **Rename**: `rename_category_rows()` walks `CATEGORY_NAME_TABLES`. A row with no id and the old
  name adopts the id only when that name resolved to this category before the rename — renaming
  "Lazer › Outros" leaves bare "Outros" rows with the root.
- **Purchase identity**: `same_purchase_sql()` is the one definition (client_id, or the old key for
  rows without one). Migration 035 numbers each legacy row within its (card, description, date,
  category, kind, installment) group by `created_at` and joins the k-th of each installment into
  purchase k. The Cartões delete keeps its ±1 cent / installment-count guard for rows with no
  `client_id`.

### Aprovar: ambiguous target, "Trocar", "Sempre perguntar" — 2026-10-18
- **Ambiguous** = `ambiguous_target()` (`services/inbox.py`): the hint key's card part is `-` (no
  final, no card name), the app has an issuer, and more than one active account (BRL; Corretora
  only for the brokerage app) — or card, for a CARD item — has that issuer in its bank field
  (`bank_of_row()`: a `bank` column if one exists, else `accounts.institution`; never the name).
  Checked at every use, not stored: `resolve_detection` (no hint, no guess), `remember_choice`
  (no hint, also for a transfer's side keys), `apply_hint_to_pending`, and `serialize_item`
  (`ambiguous`, read by the screen). Accounts with no bank, and cards (no bank field yet), don't
  count, so with fewer than two at the bank everything works as before.
- **Always ask** = `confirm_targets(item, always_ask)`: the relevant guesses plus, with the setting
  on, the target fields the owner did not pick on this item (`edited`). Read on every list, so
  toggling it applies to items already waiting; `approve_ready` uses the same function. The
  remembered choice still fills the item — approving it one by one is the confirmation.
- `GET/PATCH /api/inbox/settings` `{always_ask}`; `user_settings` (036) is a generic
  `(user_id, setting_key) → value` table for future account-wide preferences.

### Chart loading speed — 2026-10-18
- **Coverage caches.** Daily closes are cached per ticker (`_daily_history_cache` in
  `services/prices.py`) and the BCB series per series (`_index_history_cache["cdi" | "ipca"]` in
  `services/fixed_income.py`), each with the date it covers from. A request starting on or after
  it is served from the cache, sliced at its start, so it equals a download from that start (the
  Yahoo split events too). A miss downloads from `history_fetch_floor()` (day 1 of the month 63
  months back: 60-month windows + the V0 month + the indices' previous close), so the first load
  covers every later period. The index closes fetch (`refresh_benchmark_closes()`) starts at the
  same floor and throttles on it.
- **Parallel fetches.** `start_index_history()` returns `(future, deadline)`;
  `wait_index_history()` waits only what is left of that deadline, so starting early never adds a
  second timeout. Returns: window CDI and `load_benchmarks()` are started first, then
  `load_history_inputs()` (which starts the fixed-income BCB fetch before the Yahoo download); in
  `load_benchmarks()` the IPCA runs during the closes fetch. The response waits for the slowest
  fetch, not the sum.
- Today's value in TWR and the evolution comes from the stored quote, never the history, so the
  history only carries past closes.

### Compound interest calculator — 2026-10-18
Owner: "Em investimentos crie uma sessão calculadora, quero uma calculadora de juros compostos".
A seventh tab, `/investimentos/calculadora` (`pages/investimentos/Calculadora.jsx`). It reads and
writes nothing on the server; the last inputs are kept on the device (`localStorage`,
`@financeMVP:calculadoraJuros`, wrapped in try/catch).
- Rule (`lib/compoundInterest.js`, pure, `compoundInterest.test.js`): month by month,
  `VF = VP·(1+i)^n + PMT·((1+i)^n − 1)/i`, ×(1+i) when the contribution is at the start of the
  month; the schedule is checked against that closed form. An annual rate becomes monthly by the
  **equivalent** rate `(1+ia)^(1/12) − 1` — the same as `monthly_rate()` in `services/goals.py`,
  never `ia/12`. Inflation deflates each month by `(1+π)^(k/12)` and the real rate is Fisher's
  `(1+i)/(1+π) − 1`. Limits: 100 years, rate > −100% and ≤ 1000%.
- Screen: the form, a `SummaryPanel` (valor final, total investido, juros, and either "Em reais de
  hoje" with inflation or "Rende por mês no fim" without), a stacked area chart of invested vs
  interest (monthly up to 5 years, yearly after; the real value as a dashed line) and a year-by-year
  table (the last year may be partial: "Ano 3 (6 meses)"). Values are hypothetical, so privacy mode
  does not mask them. No IR on the result (it depends on the product).

### Card history (037) — 2026-10-18
Three bugs from the owner's review, all reproduced first:
1. **Deleting an installment purchase deleted the paid installments.** Cartões asked for every
   installment; the paid invoice's payment kept the old amount, locked (409), and the purchase left
   past budgets and cash flow. Now Cartões sends only the `OPEN` ones (`candidates` carries the
   status) and the confirmation says how many paid ones stay; `DELETE /api/cc-expenses` refuses
   (409) any `PAID` id.
2. **A purchase landing in an invoice autopay had already paid stayed open forever** (the autopay
   `source_id` was taken, so it never re-ran) and later showed as overdue. `first_unpaid_invoice()`
   (`services/invoices.py`, the refund's old loop) now places the first installment of every new
   purchase — `POST /api/cc-expenses/purchases` and Aprovar's `create_entry()` — and every refund in
   the first invoice from its date that is not paid (paid = has a `PAID` item and no `OPEN` one).
   A closed but unpaid invoice still takes it. The old list `POST /api/cc-expenses` (explicit
   month, no screen) is unchanged.
3. **Deleting a card cascaded all its purchases** and stranded its invoice payments in the Extrato.
   `DELETE /api/credit-cards/<id>` now refuses while the card has any `OPEN` item (those
   installments will still be charged), archives a card with history (paid items or payments in
   the Extrato; autopay is switched off), and really deletes only an empty card. An archived card
   is out of `GET /api/credit-cards` (`?include_archived=1` brings it), refuses purchases, refunds,
   autopay changes and Aprovar approvals, and is never offered or guessed by Aprovar. Its name stays
   taken (its old purchases show it); creating a card with that name gets a 409 that says so.
   **Undoing a payment**: `settle_invoice()` writes `cc_expenses.paid_by` (the payment's
   transaction id); `undo_invoice_payment()` deletes the lançamento, reopens the items with that
   `paid_by` (including the earlier credit invoices the payment took along) — or, for a payment from
   before 037 (no item points at it), the `PAID` items of its invoice without `paid_by` — and writes
   `cc_invoice_manual`, so `apply_due_autopay()` never debits that invoice again: it goes back to the
   Pagar button. Refused (409) while the payment has a receipt. A payment whose card was deleted
   before 037 can be undone too (it is only removed). The status PATCHes clear `paid_by`.

### Início's account strip opened scrolled — 2026-10-19
The strip under "Saldo em conta" is `-mx-4 px-4` (bleeds to the green block's edge, content inset
16 px) with `snap-x` and `snap-start` on each account. A snap position aligns the item's edge with
the *snapport*, which is the scroll container minus `scroll-padding` — the ordinary padding does not
count. So the first account's snap position was `scrollLeft` 16, and Chromium snaps there on layout
(16 px is inside proximity): with enough accounts to overflow, Início opened with the first account
flush against the block's rounded edge, on every open. Not `lib/scroll.js` (window only) and not a
late width change (same result after the data settled). Fix: `scroll-px-4`, scroll-padding equal to
the padding; the first snap position is 0 and the next account still snaps 16 px from the edge.
`sm` and up is a grid with `overflow-visible`, not a scroll container, so it is unchanged.

### The monthly plan starts from income (038) — 2026-10-19
- **Shape.** `monthly_plans` keeps `income_amount` (the only typed R$) and gains `invest_percent`
  / `spend_percent`; `budgets` gains `planned_percent` (% of Gastar). Text with six decimals
  ("33.333333"): Python reads them as `Decimal` (`to_percent()` in `validators.py`), so 33,33 × 3
  is 99,99 exactly, and six places keep an old plan's R$ to the cent up to R$ 1 million of income.
  `percent_of()` (`money.py`) is `rounded_money()`'s ROUND_HALF_UP applied to the exact Decimal
  product. The old R$ columns stay (append-only, NOT NULL): new rows write 0 there and a converted
  row never reads them.
- **Levels.** Gastar R$ = income × Gastar %; category R$ = Gastar R$ × its %; Sem destino R$ =
  income − Investir R$ − Gastar R$ (so the three add up to the income to the cent); Sem categoria
  = Gastar R$ − the categories' R$. Realizado unchanged: the plan's spent rule, the budget's rule
  per category (rollover, subcategory into the parent), aportes − resgates.
- **Inheritance.** A month's plan is the latest plan row ≤ it (as before); its categories come from
  the latest month ≤ it with a plan row *or* budget rows (`category_source_month()`). Any category
  write in an inherited month (`POST`, `PATCH`/`DELETE ?month=`, copy) first copies the inherited
  plan and categories into the month (`materialize_month()`), so the change does not leak back and
  deleting the last category does not bring the inherited ones back. A PUT that creates a month's
  plan copies the inherited categories into it. `DELETE /api/monthly-plan` removes the month's
  plan *and* its categories — the month goes back to the previous plan, whole.
- **Rollover** reads the previous month's effective category and its own Gastar: the leftover is
  previous Gastar R$ × previous % − previous spent (one level, never negative, as before).
- **Saldo do plano** (`plan_balance`) = Gastar R$ − the month's spent; `progress.spend_remaining`
  and `spend.remaining` are the same number, and `GET /api/budgets` returns it as
  `totals.plan_balance` (Orçamento's "Saldo do plano" reads it). `totals.remaining` stays the
  categories' own leftover (Início's budget strip). `daily_available` = Saldo ÷ days left with
  today (`days_remaining`; 0 and null in a past month, all days in a future one).
- **Conversion.** 038: a plan with income > 0 → invest% = invest ÷ income, spend% = spend ÷ income;
  a budget whose month's effective plan has income > 0 and Gastar > 0 → planned% = planned ÷ that
  Gastar. Anything else stays NULL = `needs_income`: no R$ is computed from it (status
  `NEEDS_INCOME`, the old R$ in `plan.legacy` / `legacy_amount`). The PUT that brings the income
  converts the plan (percentages may be omitted then: they come from the old R$) and every NULL
  category in the months the plan governs (its month up to the next plan row), with the same
  formulas. A plan converted over 100% is kept and flagged (`PLAN_OVER_INCOME`, and
  `CATEGORIES_OVER_SPEND` for categories); a later write may lower a category but not raise it.
- **API.** `PUT /api/monthly-plan` takes `income_amount` (required, > 0), `invest_percent` and
  `spend_percent` (required, 0–100, sum ≤ 100); `spend_amount`/`invest_amount` are no longer
  read. `POST/PATCH /api/budgets` take `planned_percent` (no R$ option); PATCH/DELETE/lines take
  `?month=`. `GET /api/monthly-plan` adds `needs_income`, `income {planned, received}`,
  `invest`/`spend` `{percent, amount, realized, remaining, progress_percent}`, `unallocated`,
  `categories {items, assigned_*, unassigned, totals, source_month, inherited}`, `plan_balance`,
  `daily_available`, `days_remaining`; `plan`, `actual`, `progress` and `flags` keep their old keys.
- **Checked:** 1343 pytest, 108 node, `vite build`; the three-year seed (now one plan + seven
  category percentages, inherited) run on a throwaway DB, and Orçamento driven in Chromium on it
  (save the plan, edit a category's %, Início) with no console error.


### Orçamento redesigned around the income-based plan — 2026-10-19
- **One read.** The page reads only `GET /api/monthly-plan` (query key `['plano-do-mes', month]`,
  shared with Início). Its `categories.items` is the same list `GET /api/budgets` returns, so the
  categories, Saldo do plano and Disponível por dia come from one response; `/api/budgets` is still
  read by Início's budget strip and written by the category form.
- **Top to bottom:** month picker → `SummaryPanel` (lead Saldo do plano = `plan_balance`, red when
  negative; figure Disponível por dia = `daily_available`, "Mês encerrado" in a past month, where
  the API returns null) → `MonthlyPlanPanel` (Renda do mês; Investir, Gastar, Sem destino only when
  its % > 0; flags; the definitions of gasto and investido) → Categorias do mês (each % · R$, status,
  progress, remaining, gasto de disponível; Sem categoria at the bottom; "Copiar mês anterior",
  "Gerenciar categorias"). Saldo, Disponível and the categories appear only when the plan has
  figures; with no plan the empty state "Comece pelo plano do mês", with `needs_income` "O plano
  precisa da renda" — both open the same sheet, focused on Renda.
- **The sheet** (`MonthlyPlanSheet`, exported from `components/MonthlyPlanPanel.jsx`): Renda,
  Investir %, Gastar %; the live line "Investir R$ X · Gastar R$ Y · Sem destino Z%" comes from
  `livePlanTotals()` / `livePlanText()`, which also give the reason saving is blocked (no income,
  a missing %, over 100%). Percentages are summed as integer millionths, so 33,33 + 66,67 is 100.
  In a `needs_income` month the two % may stay blank (the server converts the old R$, 038); the
  live line then shows the old R$ and the share of the income they make, and a conversion over
  100% is *not* blocked — the backend keeps it and flags it (`PLAN_OVER_INCOME`). The form resets
  only when the sheet opens, so a background refetch never wipes what is being typed.
- **Live R$ of a category %** (`categoryAmountPreview()`, `percentOf()`): Gastar R$ × % in integer
  cents × millionths with ROUND_HALF_UP — the same as the backend's `percent_of()` — beside the
  add field and the inline edit. Only a preview; the server's figure is what the row shows.
- Checked in Chromium at 390 px, light and dark: with a plan (the seed's inherited plan), no plan
  (a month before it), `needs_income` (a legacy row inserted by hand) and its conversion on save
  (R$ 40.000 income over the old R$ 8.000 / 30.000 → 20% / 75%, Disponível R$ 967,74 = 30.000 ÷ 31),
  privacy mode; no console errors.


### Início's "Resumo do mês" and dismissible plan flags — 2026-10-19
- **Hero.** `BalanceHero` keeps only "Saldo em conta", the balance and the account strip; the
  month pills are gone. The strip has `mt-auto`, so on desktop (where the hero stretches to the
  height of the right column) the accounts sit at the bottom of the block.
- **"Resumo do mês"** (`MonthSummary`, `pages/Dashboard.jsx`) takes `DailyTile`'s slot, above
  "Próxima fatura" (side by side from `sm`, stacked in the right column at `xl`). Rows: Resultado do
  mês = `income − |expense|` of `currentMonth` (signed, emerald/rose); Entrou = income; Saiu =
  |expense| (despesas + card purchases on the purchase day, the owner's part); Investido = invested
  − redeemed with "Aportes X · Resgates Y", only when either is non-zero; the others row only when
  `currentMonth.others` ≠ 0 — below zero "Você pagou por outras pessoas", above "Outras pessoas te
  pagaram", value `abs()`, hint link "Ver em A receber" (`/lancamentos/a-receber`). Resultado is
  *not* `currentMonth.net` (that one also subtracts investment and adds others; it stays the cash
  flow chart's "Resultado"). Privacy mode masks every value (hint amounts included) and drops
  Resultado's colour.
- **Removed:** `DailyTile`, `MonthProgress`, `getDaysRemainingInMonth`, the `plano-do-mes` query in
  Início (it only fed the tile) and the client-side fallback balance − invoices. The skeleton now
  mirrors the hero + right column.
- **Plan flags.** `MonthlyPlanPanel` filters `sortFlags(data.flags)` through `visibleFlags(…,
  data.month, useDismissedPlanFlags())`; each `AlertMessage` gets `onDismiss` and the new
  `dismissLabel="Dispensar"` prop (`ui.jsx`, default "Fechar aviso"). Keys `plan:<AAAA-MM>:<code>`
  or `…:<goal_id>` in localStorage `@financeMVP:planFlagsDismissed`, capped by `addDismissed()`
  (200). `spendStatus()` still reads all flags, so the Gastar bar stays amber after SPEND_PACE is
  dismissed.
- Checked in Chromium on the seed: Início at 390 px and 1440 px, light and dark, without and with a
  split expense (R$ 900, R$ 600 others → Saiu +300, "Você pagou por outras pessoas R$ 600,00"),
  privacy on; Orçamento at 390 px: X on SPEND_PACE → 2 flags to 1, still 1 after reload. No console
  errors. 1343 pytest, 117 node, `vite build`.


### Investimento is no longer a category (039) — 2026-10-19

Owner: "investimentos should not be a category". The meaning used to come from three places, one of
them the category's *name* (renaming or archiving it made every typed aporte count as spending).
Now only the row's origin decides:
- `INVESTMENT_SOURCE_TYPES` (`source_types.py`, `lib/transactions.js`): the movement's cash and
  the paid provento. The plan's spent/income (`services/monthly_plan.py`) and the budget's lines
  (`budget_month_lines()`, which also used to list linked aportes) skip them.
- Seen from the banking area, a transfer bank ↔ Corretora (`bankingTransactions()`, which now marks
  it `portfolio_transfer` and labels it "Aporte"/"Resgate").
- The cash rows are written with a label, no `category_id`: "Aporte"/"Resgate"
  (`INVESTMENT_CASH_LABELS`), "Provento" (`PROCEED_LABEL`).
- The share guard on the category is gone (linked rows are 409 before it; a typed aporte is a
  transfer). Recorrentes no longer labels a recurrence "Investimento"/"Resgate".
- Migration 039: typed EXPENSE/INCOME in "Investimento" (any source but the two above, imports
  included) → TRANSFER with the portfolio Corretora (`portfolio_cash_account_id()`'s order); a user
  with rows to convert and no active BRL Corretora gets "Corretora" (or "Corretora (carteira)"
  when the name is taken), balance 0, not default. Left as they were: rows already in that
  Corretora, rows in a non-BRL account. Shares on converted rows are cleared. The root
  "Investimento" category is archived; import rules choosing it get `active = 0`; PENDING Aprovar
  items in it go to "Outros"/"Receita". No recurrence was in it (owner); one that exists posts a
  plain despesa in the archived category.
- New users are seeded with nine categories.


### Chart speed and the fair comparison — 2026-10-19

Owner: "updating every chart of Investir takes 5 s or more" and "the comparison should start at 0%
for the portfolio and the index". Measured on a synthetic portfolio (27 tickers, 59 fixed-income
titles, 354 operations since 2021, `scratchpad` harness with the network patched and 2–3 s latency):
- Before: Rentabilidade 1A 312 ms / 5A 900 ms of CPU when everything was cached, 2.3 s whenever the
  15-min TTL of the index closes had passed (a blocking yfinance call), the full download after
  every restart, and every open of Investimentos computed each chart twice (the proventos sync is a
  POST, so it invalidated the whole cache).
- After: 1A ~100 ms, 5A ~300 ms, Evolução 5A ~90 ms; after a restart with a 3 s network the first
  Rentabilidade answers in ~150 ms. Responses compared field by field with the old code: identical
  (tolerance 1e-9) for returns 12/60/all/classes and history 60/12-renda-fixa.
- Where the CPU went: `accrual_factor_until()` re-filtered and re-multiplied the CDI series for
  every title × month (3.6k calls × ~1.8k days); the per-asset TWR walked all days once per asset
  (87 × 1.8k); `FixedIncomeCurve.factor()` recomputed month ends per day; `investment_movement_date()`
  parsed each date once per day/month (26k `strptime`).
- Found while testing: two threads of one request (CDI and IPCA) loading the disk copy at once —
  the second saw the flag set and an empty cache, and went to the network. The load now holds a
  lock for its whole duration.
- The fair comparison is in `CLAUDE.md` ("Rentabilidade compares from the same 0%").

### Asset categories and proventos by type (2026-10-19)

- **Why a category and not a new class.** `assets.asset_class` has a `CHECK` in 003 (and
  `investments`, `allocation_targets`, `investment_goals` copy it); a new class means rebuilding
  `assets`, and with `PRAGMA foreign_keys = ON` inside the migration's transaction a `DROP TABLE
  assets` cascades into seven tables. The category is computed on read instead
  (`category_fields()`): ACAO/ETF/BDR from `market_listing.tax_kind`, TESOURO from the title type
  `TESOURO` (new in `FIXED_INCOME_TYPES`, taxed by the regressive table) or a typeless title named
  "Tesouro…", RENDA_FIXA otherwise. `/api/assets`, `GET /api/investments`
  (`asset_category_label`), the portfolio positions and the sector rows carry it.
- **Fixed income's sector** is `rate_kind()`: the BUY's `rate_type`/`indexer` (no rate needed), or
  the Tesouro title's name. Source `INDEXER`, never written; a manual sector still wins; a title
  with no remuneration at all stays "Sem setor".
- **Proventos.** The server refuses only what the class never receives (coupon outside fixed income,
  dividend/JCP on fixed income, JCP on a FII), and only when the asset or the type changes. The
  screen is finer: JCP only for ações, dividends for ações/ETFs/BDRs/FIIs, amortization for
  FIIs/ações/fixed income and the Tesouro titles that pay in installments (Renda+, Educa+), the
  coupon for fixed income and the Tesouro titles with semiannual coupons (NTN-B/NTN-F); a Tesouro
  name that says nothing fits both.
- Two tests changed with the rule: a coupon on a stock is now 400 (it was accepted with IR 0), and
  the "amount per unit on a CDB" case uses an amortization instead of a dividend.

### Tesouro Direto marked to market (2026-10-19)

- **Source.** The BCB has no Tesouro Direto prices (SGS carries the CDI, the Selic and the IPCA);
  the official daily PU and rate of every title since 2002 is the Tesouro Nacional's CSV on Tesouro
  Transparente ("Taxas dos Títulos Ofertados pelo Tesouro Direto"), read by header (`;`, decimal
  comma, dd/mm/aaaa). If the direct resource URL answers 403/404/410, the client asks the CKAN
  package for the CSV's new address. The file is tens of MB: it is downloaded at most every 6 h,
  in the background on a read (a read never waits — no prices means the curve), synchronously on
  "Atualizar cotações"; prices older than 10 days are not used.
- **Titles from purchases.** A purchase stays stored as 1 × the amount (no migration). Titles =
  (amount − other costs) ÷ PU de compra of the purchase day (the row on or before the date); for a
  zero-coupon title (IPCA+, Prefixado) the PU is moved from the file's rate to the contracted rate,
  PU × ((1 + file rate) / (1 + contracted))^(du/252), when they differ by ≤ 1.5 pp — the owner
  types the rate the broker showed, the file has the morning price. du ≈ weekdays × 252/261. The
  typed `metadata.treasury_units` wins.
- **Matching a name.** Type from keywords (Selic/LFT, Prefixado/LTN, NTN-F, IPCA/NTN-B Principal,
  "com Juros"/NTN-B, IGPM, Renda+, Educa+) and the first year in the name; Renda+ and Educa+ are
  named by the conversion year and mature 19 and 4 years later (Renda+ 2065 → 15/12/2084).
- **Average rate.** The t with Σ C_i (1 + t)^T_i = Σ C_i (1 + t_i)^T_i (C remaining cost, T years
  to maturity): the yield of the whole position held to maturity; slightly above the cost-weighted
  mean (convexity), equal to it without a maturity.
- **Custody.** B3 OC 014/2024-VPC: since 31/12/2024 the 0.20% a.a. is provisioned daily from D+1 and
  charged at the sale, maturity or a coupon; the January 2025 semiannual charge was cancelled, so
  the provision counts from 01/01/2025 at the earliest. Computed on each day's market value from the
  file. Tesouro Selic: exempt on the first R$ 10 mil (all Selic titles together). Renda+/Educa+ pay
  it only on an early sale or above the income limit — a "sell today" net includes it; the exact
  early-sale rule for those two was not confirmed. IR base is the income after custody and IOF.
- The evolution's net now matches Posição for Tesouro (same per-purchase calculation at each month
  end); TWR reads the same daily PU.

### Card débito, Flash and hourly quotes — 2026-10-22

- **Why a function, not a card type.** Brazilian cards are often "múltiplo" (crédito + débito), so
  the débito is a property of the card: the account it debits (`debit_account_id`). A card without
  credit (`credit_enabled = 0`) is the benefits card or a pure debit card; its `due_day` and
  `closing_day` (NOT NULL since the original table) store 1 and are never read. No table rebuild.
- **Gates.** `require_active_card()` (every credit path: purchase, the old list POST, refund,
  Aprovar's CARD approval) refuses a debit-only card. The POST/PATCH refuse a card with no function,
  autopay on a debit-only card, a Corretora as the debit account, and removing credit while an
  `OPEN` item exists (409); removing credit turns autopay off; giving credit back needs both dates.
- **Aprovar.** `debit_card_for()` picks a debit card the notification names (card final, the
  Samsung card name, the issuer — never "the only card"). A debit-only card turns a method-less
  PURCHASE into an EXPENSE in its account; a combo card prefills its debit account and still asks
  "crédito ou débito?". The account is a guess the owner confirms once; then the hint remembers.
- **Samsung's issuer** comes from the card name in `parse_detection()` (`issuer_of_institution()`),
  so a Flash purchase and a BTG purchase of the same amount no longer pair, while Samsung + BTG of
  the same purchase still do.
- **The capture** showed the old Samsung parser read *no* purchase: the text has no "compra", only
  "CANTINA DO VALE R$ 14,20", and Java's `\s` does not match the U+00A0 after "R$". Fixed by
  normalizing U+00A0/U+202F to a space in `textOf()` and a Samsung-only line pattern.


### Bug hunt by fuzzing — 2026-10-22

- **How.** Two throwaway pytest files (not committed): one sent ~13 junk values for every key a
  blueprint reads, alone, to every route; the other took a valid payload per write route (36 of
  them, investments and Aprovar included) and broke one field at a time, nested `metadata` too, then
  read every screen's endpoint. Network was patched out (`urlopen`, `yf`). A 500 was logged with its
  traceback through `flask.got_request_exception` with `PROPAGATE_EXCEPTIONS` off. The final run of
  the second: 3,784 requests, no 500.
- **What was really wrong, beyond the 500s.** Three inputs were *stored* and broke reads later:
  a refund dated 9999-12-31 (its invoice is year 10000, so every `GET /api/cc-expenses` and card
  PATCH answered 500), an operation with quantity or price 1e308 (cost infinite → realized result
  NaN → SQLite stores NULL → the `NOT NULL` refused the rewrite of the realized results, so *every
  later operação* of the owner failed), and an operation dated "0999-01-01" (Linux's `strftime`
  writes "999-01-01"; the IR report's `int(date[:4])` failed). Silent wrong values: `rounded_money()`
  returned 0.0 for ≥ 1e26 (Decimal's default 28-digit precision), an amount of 0.004 passed "> 0"
  and was stored as R$ 0,00, and an operation date that was not a date became today's.
- **The rules now.** Every typed date and month is in 1900–2199 (`MIN_YEAR`/`MAX_YEAR` in
  `validators.py`; Aprovar's date-only field also checks its 2000–2100); every typed amount goes
  through `parse_money()` (rounded first, then ≥ R$ 0,01 unless zero is allowed, ≤ `MAX_MONEY` =
  R$ 1 trilhão; the initial balance may be negative); an operation's quantity and prices and the
  numbers in its `metadata` are finite and ≤ 1e12 (`validate_movement_metadata()`); a card purchase
  must have at least one cent per installment.

### Native step 1's foundation — 2026-10-22
- Four branches merged into `claude/native-foundation`, each green on `android-check.yml` on its own
  (`-cards` 39878478611, `-format` 39879129355, `-sharing` 39879583998, `-data` 39879956700): three
  `rule-porter` runs and one `native-screen-builder`, each in its own worktree.
- `core/`: top-level functions with the JS names (`formatCurrency(BigDecimal?)`,
  `formatSignedCurrency`, `formatPercent`, the dates on `LocalDate`, `monthLabel`, `shiftMonth`…).
  The strings are built by hand (U+00A0 after "R$", U+2212 for the minus), so the JVM's locale data
  plays no part. `parseMoneyInput()` returns a sealed `MoneyInput` (`Empty` = JS null, `Invalid` =
  NaN, `Amount`). Known differences, on purpose: BigDecimal is exact past 2^53, and
  `moneyInputValue` never writes an exponent. format.test.js covers only `maskEmail` and
  `formatQuantity`, so the Kotlin side has extra native-only cases taken from running the JS in node.
- `rules/`: `object CardFunctions` / `object Sharing` (`@JvmStatic`, small data classes, payloads as
  `Map<String, Any?>` in the JS key order: a JS null is a null value, an absent key a missing key).
  `toCents` copies `Math.round` (.5 toward +∞); with 3+ decimals it can differ from the JS by a cent,
  never with 2.
- `data/`: money read from the JSON text into `BigDecimal` (never via `Double`), flags accept
  true/false and 0/1, unknown keys ignored. ApiClient tells apart no connection, 401/no session
  (the outbox's `LoginNotifier` path), the server's refusal (its `error` text kept) and an
  unexpected body; reads wait 45 s, no redirects. ReadCache keys include the user id, writes are
  atomic. A repository emits the cached copy, then the fresh one; on failure the error carries the
  cached copy, and a body that does not parse never replaces a good copy.
- Libraries (`variables.gradle`): OkHttp 4.12.0 (+ mockwebserver), kotlinx-serialization-json 1.9.0
  with the serialization Gradle plugin at the project's Kotlin 2.3.20, kotlinx-coroutines-android
  1.10.2 (+ -test), lifecycle-viewmodel-compose 2.9.2.

### Native "+ Novo" — 2026-10-22
- Branch `claude/native-novo`, built by `native-screen-builder` in two rounds, both green on
  `android-check.yml` the first time (39884267832 on `e641424`, 39884996021 on `4144bf8`), reviewed
  by `native-parity-reviewer` between them and again after.
- **The save** (`ui/newentry/EntrySaver.kt`) follows `createEntry()`: one `client_id` per Salvar;
  no real network (`OutboxPlugin.hasRealNetwork()`, the outbox's own check) queues at once; else a
  6 s POST with no redirects. It differs on purpose in two places, both from the review:
  - the `buildItem()` item is written to `OutboxStore` **before** the POST (worker not scheduled)
    and removed on a creation 2xx, a refusal or a 401; it stays and the worker is scheduled on a
    network error, a timeout, a 3xx (captive portal) or a 2xx that is not the creation. A process
    killed mid-POST leaves a pending item that `OutboxPlugin.load()` sends on the next start with
    the same `client_id`, instead of the owner retyping it under a new one.
  - the save runs in `AppGraph.appScope`, not the ViewModel's, so closing the sheet mid-save
    never cancels the request; a result after the sheet closed goes through `EntryDelivery.kt`
    (to the WebView as `dataChanged` with its toast, or an Android Toast).
- **The bridge**: `dataChanged` can carry a toast; the web (`nativeApp.js`) reloads the outbox,
  so the pill updates, calls `invalidateServerData()` and shows it. An APK without the plugin or
  with an empty `routes()` keeps the React sheet (`routesFrom()` falls back on a rejection).
- **Required fields**: the web relies on the browser's `required` popup; native says "Preencha este
  campo: Descrição." / "Selecione um item na lista: Categoria." in the error box (in the spec).
- Rule and toast texts are Kotlin constants (the `CardFunctions` pattern, so tests check the exact
  wording); screen labels are in `strings.xml` (`newentry_*`).

### `findings.md` possible bugs and stale texts — 2026-10-23
- Branch `claude/mobile-docs-bugs-stale-text-u8ylzb`, one commit per bug. Each bug got a test first
  and every one failed, so none was marked "not reproducible". Outcomes per bug are in
  `mobile-docs/native/findings.md` › Possible bugs.
- New pure modules, all tested with `node --test`: `lib/recurring.js` (the recurrence's inline
  edit), `lib/transactionEdit.js` (the Extrato's edit form and PATCH, moved out of `Extrato.jsx`),
  `lib/cardPurchase.js` (a purchase's installments from `/candidates`, the refund prefill);
  `localDateOfTimestamp()` joins `lib/format.js`.
- `GET /api/auth/signup` is public and answers `{open}` (`signup_open()` in `routes/auth.py`, the
  same rule the POST uses); the login hides "Criar acesso" when closed or unreachable.
- pytest 1536 (was 1534), `npm test` 164 (was 150).

### Home, attention and invoice endpoints — 2026-10-23 (native session 6)

- **One rule for three screens.** `services/card_invoices.py` (`open_invoices()`) groups the
  open rows per card and invoice in `Decimal` (refunds subtract), and flags `past_due`, `closed`,
  `payable`, `next`, `nearest` and `future`. `/api/home` takes its `next` invoices, `/api/attention`
  its overdue and payable ones, `/api/cc-invoices` all of it. Lists keep the old client's order (the
  rows' order, then a stable sort by due date), so ties land where they used to.
- **The flow in integer cents.** `services/home.py` sums `CAST(ROUND(x * 100) AS INTEGER)` per row
  in SQL, the client's `Math.round(x * 100)`. Others' part is rounded on its own and subtracted, as
  `ownAmount()` did. The "Pagamento Fatura" prefix is compared with `substr()`, case-sensitive like
  `startsWith`, not with `LIKE` as `month_banking_totals()` does.
- **The keys did not change**: `fatura-vencida:<card>|2026-9` keeps the unpadded month, so the
  dismissals stored on devices still match (`test_overdue_key_month_is_not_zero_padded`).
- **Parity check**: a database seeded through the API (accounts with a Corretora and an archived
  one, 12 months of rows, transfers both ways, shared rows, two cards with overdue, closed, paid,
  installment, refund and autopay-shortfall cases, a pending recurrence, two over-budget
  categories). Chromium captured Início, the bell, Extrato and Cartões at 1440 px and 390 px before
  and after on copies of it. The page text was identical on all eight, and six screenshots were
  pixel-identical. Two differed in about 110 anti-aliased pixels, at most 2/255.
- **Moved, not deleted**: the 11 rule cases of `attentionRules.test.js` and the
  `consolidatedBalance`/`openingBalanceTotal` asserts of `transactions.test.js` have the pytest
  twins named in the proposal. The two `buildMonthlyFlow` cases of `sharing.test.js` are
  `test_home.py::test_from_sharing_*`. The node files keep the dismissals,
  `overdueDetail`, `isPastDue`, `isInvoicePayment` and the banking-view predicates.
- **Not built**: paging (§5), by the proposal's own order. Início's history panels need
  `home-panels.md` (next-steps).

### Native Início and the bell — 2026-10-23 (native session 7)

- **What native reads**: `GET /api/home?months=12`, `GET /api/attention`, `GET /api/budgets?month=`
  (the strip) and the accounts for the pay sheet; writes `POST /api/cc-expenses/pay-invoice`
  (sequential, one per invoice) and `POST /api/recurring/run` through a `writeApi` with no read
  timeout (a write that may have gone through is never reported as offline by a timeout).
- **Ports with the node cases**: `rules/HomeFlow.kt` (`lib/homeFlow.js` — the flow averages and
  taxa de poupança, moved out of `Dashboard.jsx` — and `chartFormat.js`), `rules/AttentionRules.kt`
  (`attentionRules.js`: `overdueDetail`, `undismissedItems`, `addDismissed` keeping the last 200,
  and the texts now in `attentionRules.js` instead of `Attention.jsx`), `rules/HomeRules.kt`
  (`blockedRecurringMessage`, `budgetStatus`), `rules/OutboxItems.kt` (the `OutboxStore` JSON item
  → `PendingItem`). Chart colours moved into `index.css` (`--flow-*`, `--series-0`) and
  `Tokens.kt`; `chartColors.test.js` keeps `charts.jsx` on the variables.
- **Leaving native**: a link finishes `NativeActivity` with the route and `NativeScreens` emits
  `navigate`. When no WebView is listening (the process was killed and Android restored the native
  screen alone), the route is stored for 2 minutes and the web takes it once at start
  (`NativeScreens.takePendingRoute()`), so the link lands where it points instead of looping back
  to native Início. `/inicio?web=1` is the web Início that does not redirect (the four history
  panels, and the login after a 401).
- **Privacy**: the web calls `Shell.setValuesHidden` on toggle and at start, and reads
  `getValuesHidden` on resume; an older APK rejects the calls and nothing changes. With values
  hidden, a negative account chip and the Evolução badge are not coloured red (the web leaks the
  sign there; kept native-only on purpose).
- **Review**: `native-parity-reviewer` found no blockers and two majors — the blocked-recurrence
  message wiped by the refetch (read error and action error are now separate states,
  `HomeLogic.bannerDetail`) and the process-death loop above — plus minors (write timeout, two
  offline banners, info toast, lowercase month); fixed in one round. The re-verification caught
  three more minors (the toast's surface must be the web's dark one for every tone, only the icon
  changes; the start route expires on the web side too; `PendingRoute.kt` tested); fixed.
- **Not built**: the four history panels (they wait for `home-panels.md`), a Pendentes pill in the
  native top bar (the shell, step 8), one dismissal list shared by web and native.

### Investimentos backend and ports — 2026-10-24 (native session B)
- **Decisions given**: `client_id` yes (the owner: "keep the offline queue"); all five endpoints
  (the prompt's field was blank, the step listed five).
- **042** adds `client_id` + `client_part` to `investment_transactions` and `investment_proceeds`
  (unique on user, id, part: a list, a redemption and a `repeat` are one request with several
  rows) and `client_id` to `corporate_actions`. A list must carry one id (400 otherwise). The
  lookup runs before validation; a concurrent second delivery is caught on the unique index.
- **Redemption** (`redeem_fixed_income()` in `routes/investments.py`): finds the position in
  `build_portfolio_snapshot()` by its `id`, splits with `redemption_parts()` (lots → PEPS, else
  `average_price × amount / current_value`), and writes through `create_movements()` — the old
  POST body, extracted so both share validation, cash link and atomicity. The cost stays
  unrounded, as the client sent it. Walked in Chromium: 1800 on two curve-valued lots of 1000 and
  2200 → parts (1000, cost 1000) and (800, cost 800), both into the Corretora.
- **Grouped delete**: `delete_assets()` runs every asset in one transaction; a missing asset (404)
  or a class mismatch (409) rolls all back. `DELETE /by-asset/<id>` goes through it too.
- **Screens unchanged**: before/after Chromium shots on a seeded scratch server — Operações and
  Proventos (annual) byte-identical, IR identical to the eye, Posição differs only by chart
  animation timing. Proventos stayed identical after the colour change too (its bars use FLOW).
- **Ports**: same cases, same order, on both sides; `assetSearch.test.js` and the new
  `fixedIncome.test.js` cases were written first on the node side. Display numbers go through
  `ptBrNumber()` (`rules/FixedIncome.kt`): half-up on the shortest decimal, as ICU does.

### Planning screens and Ajustes native — 2026-10-24 (native session C)
- **Decision field left blank** (installments 48 or 72, description required): both stay as today.
- **Ports**: same cases, same order, as JVM tests; what the screens did inline and untested
  (`AReceber.jsx`'s grouping per person, the account menu, the closing-day auto-fill, the autopay
  toast, the signed initial balance, the username Salvar) got a pure Kotlin home with tests.
  Percentages are `BigDecimal` end to end; the slider's `Float` is only the finger's position.
- **A local JVM harness** (not committed): a plain Kotlin/JVM Gradle project compiling `core/`,
  `rules/` and the DTOs with their tests, so the pure code was green before CI. The Maven proxy
  answered 404/429 at random; the jars came by `curl` from repo1 and a `file://` repo.
- **Shared Java made reusable instead of copied**: `NotifyPlugin` (status, latest, export, clear,
  open settings) and `ApkUpdatePlugin` (`latestState`, `installPrecheck`, `installNow`; the
  download guard is now static, so web and native never download twice) are static helpers the
  plugin methods and `AjustesViewModel` both call.
- **Theme and Sair**: the WebView owns `localStorage`, so a native change is left in `ShellPrefs`
  and taken by the web on start and on every resume (before `syncSession()`, so a signed-out
  token is never pushed back). The web now sends its `preference` with `setTheme`, so the native
  Aparência shows the web's choice. Sair also clears `Session` (the outbox stops) and the read cache.
- **Ajustes routes**: `/ajustes#<section>` opens the native section; `#regras-de-importacao` and
  `#integracoes` (and `?web=1`) keep the React page (`wantsWebPage(search, hash)`).

### Investimentos native — 2026-10-24 (native session D)
- **Order and scope**: the prompt allowed closing after Proventos; context held, so Rentabilidade
  and spec 16's native part were built too. Targets, sectors and the full IR report stay web
  (`?web=1`), as `16-…` recommends.
- **Offline**: session B's `client_id` made the two creations safe to resend, so Registrar
  operação and Registrar provento save through the same `EntrySaver` as "+ Novo" (item stored
  before the POST, 6 s, then `OutboxWorker`). `EntrySaver.createJson()` takes a built body
  because `payloadJson()` drops nulls and `cash_account_id: null` means "Não descontar". The
  item's `title` (outside the payload) names a provento in Pendentes. Both kinds are out of
  `pendingAccountDeltas`, `pendingAsTransactions` and `applyPendingToHome` (an `ACCOUNT_KINDS`
  list on both sides) and are never Corrigir'd (`isEditableKind`). Redemptions and corporate
  events stay online but carry a `client_id` so a double tap writes once.
- **Rules**: what the React pages did inline and untested got pure Kotlin homes with JVM tests
  written from the web's code (no node twin): Posição's grouping/menu/donut/bars, Operações'
  movement reading and every payload, Proventos' payload, Rentabilidade's CDI card, Alocação's
  gap/drift, IR's active months. Money is `BigDecimal`; the buy's average price is 6 places
  HALF_UP (the web's `toFixed(6)`).
- **Privacy**: every R$ of the portfolio is masked natively, Operações and Proventos included
  (the web masks less there); the owner decides whether the web follows (`next-steps.md`).
- **Found**: the main tree's `frontend/node_modules` had lost `.bin` and several packages (a
  peer worktree's junction cleanup, most likely); `npm ci` restored it before `npm run build`.
