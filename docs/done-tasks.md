# Done Tasks — FinanceMVP

> Finished work, one line per task, oldest first. When a task is finished, remove it from
> `docs/next-steps.md` and add one row here (≤ ~110 characters). Detail lives in the commits; the long
> notes this file used to hold are in git history (`git show a79c731:docs/done-tasks.md`).

| Task | When |
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
| `CATTLE` asset class — decided to keep | 2026-09-15 |
| Backend test suite (pytest, throwaway DB) | 2026-09-15 |
| Single start script `start.ps1` | 2026-09-15 |
| Automatic backup on boot with retention | 2026-09-15 |
| Invoice-month rule moved to the backend | 2026-09-15 |
| Bank accounts and transfers | 2026-09-16 |
| Categories as a table, with subcategories and management screen | 2026-09-16 |
| Editing a transaction | 2026-09-16 |
| Monthly budget by category, with rollover | 2026-09-16 |
| Recurring entries with cash-flow forecast | 2026-09-16 |
| Shared `frontend/src/lib/format.js` | 2026-09-16 |
| B3 ticker catalog, autocomplete, and guard on buys | 2026-09-16 |
| Statement search and filters | 2026-09-21 |
| UX reorganization: 4 sections + Ajustes, "+ Novo" sheet, Carteira merged away, phone layout | 2026-09-21 |
| Invoice payment only after closing, server-side | 2026-09-22 |
| Investimentos: "Evolução do Patrimônio" | 2026-09-22 |
| Username (display name) on signup, editable in Ajustes → Perfil | 2026-09-22 |
| BCB fetch hardened (404 = no data yet, >10-year windows split, error payloads reported) | 2026-09-22 |
| Invoice payment: account picker | 2026-09-22 |
| Statement filters in the URL | 2026-09-22 |
| Phase 4: CSV/OFX statement import with preview and dedupe, auto-categorization rules | 2026-09-22 |
| Export to CSV (Excel pt-BR) of the filtered statement and of the portfolio | 2026-09-22 |
| brapi as the primary quote provider | 2026-09-22 |
| Motion pass: sheet/collapsible exit animations, sliding tab pill, count-up and chart draw-in once per page… | 2026-09-22 |
| Privacy mode rework: the eye no longer remounts the page | 2026-09-22 |
| Visual design pass (audit + items 1–7, decisions A–D) | 2026-09-22 |
| Decision 6 settled: "+ Novo" twice on Início and Extrato | 2026-09-22 |
| Início "Orçamento do mês" strip | 2026-09-22 |
| Tables switch to cards below `xl` so they fit without sideways scroll | 2026-09-22 |
| Import rules: edit a rule | 2026-09-22 |
| Receipts per lançamento (PDF/image, several per row) from Extrato | 2026-09-23 |
| UI remodel, direction C, with dark mode | 2026-09-23 |
| Phase 5 started: foundation modules, services and nine blueprints out of `app.py` | 2026-09-23 |
| Phase 5 finished: investments out of `app.py` into five services and three blueprints | 2026-09-23 |
| Phase 5 leftovers: the three pre-existing pyflakes warnings fixed | 2026-09-23 |
| Browser walk-through on scratch data | 2026-09-23 |
| `SegmentedControl` selection pill fits the active option when the options wrap onto two rows | 2026-09-23 |
| UI remodel leftovers: toast after "+ Novo" and investment saves, invoice payments, recurring run and demo data | 2026-09-23 |
| Walk-through items not covered before, on scratch data | 2026-09-23 |
| Open decisions 1 (card purchases count in the budget in the purchase month | 2026-09-23 |
| Import rules: amount range and account conditions | 2026-09-23 |
| Export: real .xlsx, Operações and Proventos exports, column picker | 2026-09-23 |
| Receipts: mirrored in the backup | 2026-09-23 |
| Frontend: server state in TanStack Query | 2026-09-23 |
| Operations: structured JSON logging | 2026-09-23 |
| Phase 6: corporate actions | 2026-09-23 |
| Phase 6: multi-currency assets and accounts | 2026-09-23 |
| Phase 6: annual tax report | 2026-09-23 |
| Phase 6: Evolução do Patrimônio accrues fixed income month by month | 2026-09-23 |
| Open decision 2: recurring pause skips only the paused window | 2026-09-26 |
| Carteira export: whole quantities without trailing comma in .xlsx | 2026-09-26 |
| From an Investidor10 PRO survey | 2026-09-26 |
| Proventos per asset: `services/proceeds.py` extracted, `by_asset` in the summary, per-asset proventos /… | 2026-09-26 |
| Time-weighted return (monthly Modified Dietz, gross) | 2026-09-26 |
| Aportes x resgates per month | 2026-09-26 |
| Rentabilidade: asset-class filter | 2026-09-26 |
| Carteira CSV/.xlsx export | 2026-09-26 |
| IR report reads proventos through `services/proceeds.py` | 2026-09-26 |
| Rentabilidade vs benchmarks | 2026-09-26 |
| Allocation by sector/segment | 2026-09-26 |
| IRPF copy-paste text per section on the IR tab | 2026-09-26 |
| Proventos yield on cost fixed | 2026-09-26 |
| Posição "Evolução do Patrimônio" on the gross basis, like the headline | 2026-09-27 |
| Rentabilidade and Evolução value the current month like Posição | 2026-09-27 |
| Orçamento copy: "Realizado" counts card purchases, not only account outflows | 2026-09-27 |
| "Operação anterior ao app" | 2026-09-27 |
| Ticker search and the buy guard cover the whole B3 | 2026-09-27 |
| Fixed-income IR exemption follows the title type | 2026-09-27 |
| `CATTLE` (Gado) asset class removed everywhere | 2026-09-27 |
| Início → "Ritmo de gastos" compares the month so far with the average of the 3 previous months at the same day | 2026-10-12 |
| Investments area separate from the banking area | 2026-10-12 |
| The app is reais-only on screen | 2026-10-12 |
| Mobile plan verified and rewritten | 2026-10-13 |
| Mobile Phase 2, phone-width layout, on the PC | 2026-10-16 |
| Mobile Phase 5, the APK, as code | 2026-10-16 |
| Mobile Phase 5, first build and install | 2026-10-16 |
| Bug pass, Android + desktop | 2026-10-16 |
| Plano do mês (migration 025) | 2026-10-16 |
| Perfil shows the login e-mail masked | 2026-10-16 |
| "Dados de exemplo" removed from Ajustes at the owner's request | 2026-10-16 |
| Phone load time: CORS preflights cached 2 h | 2026-10-16 |
| A fully redeemed renda fixa title is closed | 2026-10-16 |
| A real investment history | 2026-10-16 |
| Automatic proventos (026) | 2026-10-16 |
| Docker deploy to the home server | 2026-10-16 |
| Home server live: owner's setup checked | 2026-10-16 |
| Final setup check, all green | 2026-10-16 |
| APK screens update themselves from the server | 2026-10-17 |
| APK updates from CI (option 2) | 2026-10-17 |
| Self-update checked on the phone | 2026-10-17 |
| Phase 6, first half: native bank-notification listener | 2026-10-17 |
| Investments check, errors fixed | 2026-10-17 |
| Posição › Variável split by kind of paper | 2026-10-17 |
| BTG Investimentos (`com.btg.pactual.digital.mobile`) added to the notification allow-list and the manifest… | 2026-10-17 |
| The portfolio account: a Corretora account is linked to the portfolio and every new operation comes out of it | 2026-10-17 |
| Paid proventos into the portfolio account | 2026-10-17 |
| Corretora balance only in Investimentos | 2026-10-17 |
| Samsung Wallet, Itaú Cartões and Ourocard off the notification allow-list | 2026-10-17 |
| Samsung Wallet back on the notification allow-list as a fallback source | 2026-10-17 |
| Bank × Samsung Wallet pairing rule, pure Java | 2026-10-18 |
| Operação form: the "Ativo" suggestions list only the assets of the chosen type | 2026-10-18 |
| Posição: each category (Ações, ETFs, FIIs, CDB…) is a toggle, collapsed by default, header keeps count and… | 2026-10-18 |
| Pluggy removed from the app | 2026-10-17 |
| Pluggy out of the migrations too | 2026-10-17 |
| Notification auto-identifier | 2026-10-17 |
| TWR like Investidor10: daily returns chained instead of monthly Modified Dietz, Yahoo's bonus-as-split… | 2026-10-18 |
| Expense sharing (032): a lançamento or card purchase can be the owner's, split | 2026-10-18 |
| Card refunds (033, estorno) | 2026-10-18 |
| Início's "Disponível por dia" = what is left to spend in the month's plan | 2026-10-18 |
| Aprovar × Recorrentes (034) | 2026-10-18 |
| Orçamento › "Ver lançamentos" per category | 2026-10-18 |
| Phone layout pass (Galaxy S25, 360 px, seeded demo data) | 2026-10-18 |
| Bug: typing a transfer that waited in Aprovar returned 500 and saved nothing | 2026-10-18 |
| Bug: Início and the bell looked at "next month's invoice", so a card closing before its due day | 2026-10-18 |
| Bug: categories matched by name | 2026-10-18 |
| Bug: renaming a category only rewrote `transactions` | 2026-10-18 |
| Bug: two identical card purchases | 2026-10-18 |
| Aprovar, ambiguous target | 2026-10-18 |
| Aprovar shows every item's target | 2026-10-18 |
| Ajustes › Aprovar: "Sempre perguntar a conta/cartão" | 2026-10-18 |
| Charts faster: Rentabilidade fetches prices, CDI, IPCA and index closes at once instead of in sequence,… | 2026-10-18 |
| Investimentos › Calculadora | 2026-10-18 |
| Card history no longer disappears | 2026-10-18 |
| Owner's review, items 4–21 | 2026-10-18 |
| Início's account strip opens at the far left on the phone | 2026-10-19 |
| The monthly plan starts from income | 2026-10-19 |
| Planejar › Orçamento redesigned around the income-based plan | 2026-10-19 |
| Início: the month's movement leaves the hero for its own card "Resumo do mês" | 2026-10-19 |
| Plano do mês: each flag gets an X | 2026-10-19 |
| Investimento is no longer a category | 2026-10-19 |
| Extrato deletes operações | 2026-10-19 |
| Operações › Editar: a sale shows its quantity without "-" and is saved as a sale | 2026-10-19 |
| Fixed-income coupons and amortizations typed ahead | 2026-10-19 |
| Investir charts fast and the index comparison fair | 2026-10-19 |
| Asset categories, proventos by type, asset search | 2026-10-19 |
| Tesouro Direto marked to market and grouped | 2026-10-19 |
| BCB and Tesouro downloads through `gov_http.py` | 2026-10-19 |
| Saving and editing an operação without waiting | 2026-10-19 |
| Planejar's "Investir" realized = Início's "Investido" | 2026-10-19 |
| Renda variável quotes refreshed by the server every hour | 2026-10-22 |
| Card débito function (041 | 2026-10-22 |
| Flash Benefícios and the second parser pass | 2026-10-22 |
| Bug hunt by fuzzing every route | 2026-10-22 |
| A new APK on every deploy | 2026-10-22 |
| Native phone app, step 0 (owner | 2026-10-22 |
| Native migration documentation | 2026-10-22 |
| Native step 1's foundation | 2026-10-22 |
| Native "+ Novo" (step 1's screen) | 2026-10-22 |
| `findings.md` triage, possible bugs and stale texts | 2026-10-23 |
| Native migration session 5 | 2026-10-23 |
| Native migration session 6 | 2026-10-23 |
| Native migration session 7 | 2026-10-23 |
| Native migration session A | 2026-10-24 |
| Native migration session B | 2026-10-24 |
| Native migration session C | 2026-10-24 |
| Native migration session D | 2026-10-24 |
| Native migration session E | 2026-10-25 |
| Native Aprovar: back (arrow and system back) goes to Extrato, not Início | 2026-10-25 |
| Quotes: "Tempo limite ao consultar yfinance" fixed | 2026-10-25 |
| Open Finance (Pluggy) as a source for Aprovar, designed anew | 2026-10-27 |
| Open Finance settings and Conferência | 2026-10-27 |
| Open Finance as the only source for connected banks | 2026-10-27 |
| Auto-record → reconcile → review | 2026-10-27 |
| APK on the 045 paradigm: Aprovar removed from the phone | 2026-10-27 |
| Owner's data aligned with Pluggy | 2026-10-27 |
| Conta global (047): Wise USD account with its own screen in US$ | 2026-10-27 |
| No duplicate when Pluggy brings what a notification recorded | 2026-10-27 |
| Conta global, the rest: the dollars that arrived | 2026-10-28 |
| Trade cash on the liquidation date | 2026-10-28 |
| Cartões: edit category/description of a card purchase | 2026-10-28 |
| Conta global out of "Saldo em contas" | 2026-10-28 |
| The app waits for Pluggy: a pending item is flagged only after every connection refreshed without… | 2026-10-30 |
| Spending corrected: Inter line | 2026-10-31 |
| Anticipated installments follow the bank's discount credit | 2026-10-31 |
| Duplicate invoice payments root-caused | 2026-10-31 |
| Repasse in Revisar; settled shares cut income | 2026-10-31 |
| Only the Flash is typed (`manual_entries.py`) | 2026-10-31 |
| Início: invoice tile with a dropdown per invoice, no open-items panel | 2026-10-31 |
| A receber: "Pago" asks which income paid it | 2026-11-02 |
| Open Finance pull window: `LATE_POSTING_DAYS` | 2026-11-04 |
| Design: notifications + Pluggy, one movement one row | 2026-11-04 |
| Notifications + Pluggy Phase 1 | 2026-11-04 |
| Notifications + Pluggy Phase 3 | 2026-11-04 |
| Notifications + Pluggy Phase 2 | 2026-11-04 |
| Notifications + Pluggy Phase 4 | 2026-11-05 |
| Notifications + Pluggy Phase 5 | 2026-11-05 |
| Notifications + Pluggy final verification | 2026-11-05 |
| Manual entry everywhere + the APK "+" in the bottom bar | 2026-11-05 |
| Autopay on the due day with a balance check, Pluggy-mapped cards included | 2026-11-05 |
| Docs cleanup: removed `docs/notifications-pluggy-design.md`, `docs/no-vpn-access.md`, the finished session… | 2026-11-06 |
| Remote access behind a login | 2026-11-06 |
| Extrato opens without filters | 2026-11-11 |
| Architecture audit and the first refactoring stack | 2026-11-12 |
| Second refactoring stack (PRs #88–#93, not merged yet when written) | 2026-11-13 |
| The month's spending is one rule on every screen | 2026-11-13 |
| Web Início reads `GET /api/home/panels` | 2026-11-13 |
| Everything automatic, phase 1 | 2026-11-18 |
| Everything automatic, phase 2 | 2026-11-19 |
| Everything automatic, phase 3 | 2026-11-19 |
| Everything automatic merged and deployed once | 2026-11-19 |
| Detection bug hunt B1–B13 | 2026-11-20 |
| No Revisar: the confirmation is automatic (web and APK) | 2026-11-22 |
| APK pull to refresh on Início fixed | 2026-11-26 |
