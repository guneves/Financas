# Backlog — FinanceMVP

> Open items that are not next: bugs, known limits, owner decisions, ideas. One line each; grep the area
> you touch. An item that becomes next moves to `docs/next-steps.md`; a finished one leaves for
> `docs/done-tasks.md`. The long version of each item (pruned 2026-11-26) is in git history:
> `git show a79c731:docs/backlog.md` and `git show b02a6ff:docs/next-steps.md`.

## Bugs and gaps
- Web `createEntry()` can duplicate after a killed tab (queues only after the failure); write to the outbox before the POST, as `EntrySaver.kt` does.
- Web outbox `flush()` writes back from the item it sent: an item corrected/discarded during the request can be overwritten; compare versions like `OutboxStore.removeIfUnchanged`.
- Web sharing form refuses a comma ("12,5"): `shareFormError()` uses `Number()`; use `parseMoneyInput()` (native already does).
- Other money fields still `type="number"` (Metas, Orçamento, Recorrentes, initial balance, ShareFields, Extrato min/max, investment forms).
- Início's "Despesas por categoria" drops a refund in its own category (negative total) and groups by name (root "Outros" = "Lazer › Outros").
- Card purchases moved out of their category by a rename before the 2026-10-18 fix keep the old text and count in no budget.
- `POST /api/cc-expenses` (no screen uses it) takes the invoice month as sent, so it can write into a paid invoice: add the unpaid-invoice rule or remove it.
- Outbox retries any 5xx until the fix deploys; cap a plain 500 in `outboxRules.js` and `OutboxRules.java` together.
- `OutboxWorker`: EXPONENTIAL backoff reaches ~1 h waits after an outage; `ExistingWorkPolicy.KEEP` can miss an item put as a job ends.
- B14: the APK ignores "compra cancelada", so a notified card purchase cancelled before posting stays as a ghost (needs a DECLINED-like kind + a server rule).
- B15: `inbox.is_auto_invest()` checks only the merchant, never the counterparty (a Pix to "RENDE FACIL"; never seen).
- A Pluggy purchase with the same cents/day/account as a notified own transfer can take that transfer's Pluggy slot (owner's call, left as is).
- Pluggy: a posting > `LATE_POSTING_DAYS` (35) before the last pull is never pulled; `synced_until` advances while `lastUpdatedAt` is stale; connectors send no `totalAmount` (R$ 100 in 3× → 99,99).
- A card with a single sandbox-sign purchase learns the docs' sign and reads it as a refund.
- `changed` conflicts take the bank's amount but never its date; an unmatched equity INTEREST waits `proceed:unmatched`.
- Four portfolio lines stay HELD on real data (two LCA Original sells 2026-05-05, LCI BRB sell 2026-08-20, CRA Camil coupon 2026-11-16): Ajustes › Open Finance › Lançar, or leave.
- Some test once wrote to the PC's `backend/finance.db` (453 `user-…@example.com` users since 2026-10-27): find it.
- pytest may fail 21:00–midnight local (`test_fixed_income_interest.py` coupon test, UTC vs local day); possibly fixed, not re-run at that hour.
- The clock sweep can't move SQLite's `now`: a test comparing a fixed date with `created_at` is a calendar bomb.
- Rows stored before the validators with absurd values (year out of range, 0, 1e308) would break their reads; look for one first on a 500.
- Old dates stored without the leading zero: check `length(date) < 10` on the server once.
- eslint has no config file in `frontend/`.

## APK gaps (web has them)
- Conferência: no "Lançar"/"Aconteceu", no `awaiting_bank` rows; Open Finance: no history preview, portfolio check, "Não usar"; investments "Lançar" opens operations only.
- Not built natively: swipe/long-press menus, Orçamento month swipe, pull to refresh outside Início, widgets, chart crosshair drag, launcher shortcut "Novo lançamento", Plus Jakarta Sans.
- The "+" inside Investimentos opens "+ Novo", not Registrar operação; "Sem conexão" reflects the phone's network, not the server.
- Importar, Regras, Integrações, the full IR report and allocation targets are web-only (desktop redesign, plan per screen first).

## Refactors (no visible change)
- Five long views to split decide/answer, one per PR with a response-shape test first: `investment_detail`, `create_movements`, `cc_expenses`, `update_transaction`, `account_detail`.
- The engine knot of `open_finance_inbox.py` (1654 lines) and `inbox.py` (1072) needs a redesign (pipeline object) with the identity suite as the net. Decided against: merging `auto_record.py` and `open_finance_auto.py`.
- Ruff import sorting + `ruff.toml`: one PR when nothing else is open (~90 files).
- Audit leftovers: login has no attempt limit and a 6-char floor (C3); an unhandled exception answers HTML (C4); `recurring.settled_dates()` per recurrence; other check-then-write guards could use `db.begin_write()`.
- Routes no client calls (`POST /api/database/backups`, `GET /api/database/status`, `DELETE /api/investments/by-ticker/<t>`, `PATCH /api/investments/price-by-ticker`): remove once no old APK can call them; same for `POST /api/review`, `review_count`.
- Multi-currency in the backend (018) is reachable only through the API; removing it is a real refactor.
- Static `/assets/*.js` go uncompressed from Flask; Rentabilidade's daily loop scales with positions × days (cache per user/period if it bites).

## Server and ops
- Daily encrypted cloud backup (rclone + crypt, 30 days), only after a tested restore (owner).
- Remote access rollout: DEPLOY.md steps 1–10; unchecked on a device: the APK key field, the "Chave de acesso inválida" dialog, Pluggy Connect through :8443, Funnel's timeout, `rd=` dropping a query.
- `BRAPI_MAX_SYMBOLS_PER_REQUEST=1` in the server `.env` (brapi takes 1 ticker per request; hourly quotes then cost one request per ticker).
- Delete the PC's old `backend\finance.db*` once the owner is sure (copy in `Documents\Financas-backup-pc-20261016\`).
- Tune the merchant table with `--report-categories` on real rows.

## Notifications
- Captures still missing: Flash purchase and benefit credit, "final 1234" purchases, Itaú/BB purchases, estorno, declined, boleto, brokerage app, invoice payment; each mis-read becomes a `NotifyParsersTest` case.
- Confirm the Flash package `br.com.flashapp`; "Card used for Meal and Voucher" is assumed to be the Flash.
- "3x de R$ 50,00" parsing was written against hand-made texts: turn the first real one into a test.
- Recurrence × notification: an occurrence `/run` already wrote matches only at the exact amount; a price change isn't carried back.
- Tune `NOTIFY_WINDOW_MS` (bank × Samsung) from an export with both notices.

## Investments
- Amortization doesn't lower the title's principal in Posição (it's a provento); modelling it as principal returned is the owner's call.
- Editing a coupon keeps its stored IR (blank the field to recompute); coupon IR 0 goes to isentos 12 (check incentivized debêntures).
- Old Tesouro titles typed as CDB stay in Renda fixa (fix the type in Operações); Selic modelled as % of CDI.
- Alocação/targets/goals use the four DB classes, not the categories (owner decision + table rebuild).
- Unknown fixed-income ETFs are taxed as ETF de ações: add them to `FIXED_INCOME_ETFS`.
- Bens e Direitos codes 07.09 (ETF) / 04.04 (BDR) to confirm in the 2026 program; a bonificação with cost doesn't produce isentos 18.
- Renda+/Educa+ custody on an early sale modelled as 0.20% a.a.; confirm with BTG.
- Proventos: a ticker that changes code needs `TICKER_ALIASES`; StatusInvest isn't in the health check; some FII/JCP values differ by centavos.
- Deleting a movement removes its linked lançamento and receipts (not guarded).
- Proceeds' amounts and corporate-action ratios have no upper bound.

## Owner decisions open
- Budgets accept income categories (and mix them into "gasto"): refuse them, or keep them out of the totals?
- The Extrato shows a transfer to the Corretora as "Transferência", Início as an aporte: align?
- "Despesas por categoria" arrows vs Ritmo's 3-month same-day average: same rule?
- Rentabilidade 1A is 12 months; Investidor10 chains 13: follow it?
- Calculadora: IR on the simulated gain, "start from my portfolio", reverse mode.
- Investidor10 ideas: fundamentals columns, B3 trade import, sector targets.
- Privacy covers balances and the portfolio only (owner's choice); more masking?
- Single-user or multi-user (schema ready for either).

## Known limits, accepted
- IPCA+ is an estimate; day trade isn't separated; the "dedo-duro" isn't deducted; foreign proventos taken as BRL.
- Autopay never debits without the balance (owner 2026-11-05); nothing can be entered before an asset's latest corporate action.
- Import capped at 2,000 rows per file; no server-side receipt thumbnails.
- Allocation split is proportional and never sells; goals' forecast is deterministic.
- TWR on gross values, proventos on the payment date, unquoted/delisted assets at cost (`notes[]` lists them).
- The Conta global's own US$ rows are outside every reais total; "Pix para cá" needs a connection.
