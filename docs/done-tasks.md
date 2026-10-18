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
| "Precisa de atenção" dismissable and in a header bell: Início's X hides the current items on this device (per case key, so a new case comes back); the bell, where the theme toggle was, lists every current item with a link to its screen; the theme moved to Ajustes › Aparência (Sistema / Claro / Escuro). `lib/attentionRules.js` (pure, `attentionRules.test.js`), `lib/attention.js`, `components/Attention.jsx`, `pages/ajustes/AparenciaSection.jsx` | 2026-10-18 |

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
