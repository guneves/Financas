# Prompt — Conta global em dólar (Wise via Pluggy)

Paste everything below the line into a new session.

---

Build a **"Conta global"** for dollar accounts and move the owner's Wise account into it. Follow
the session process in `CLAUDE.md` (read `docs/handoff.md` first; end with next-steps/done-tasks/
handoff and a commit). Work on a branch from `main`; don't merge or deploy without asking.

## The owner's decision (2026-10-27) — a deliberate exception to "reais-only"

- The owner opened a **Wise USD account**, now connected in Pluggy (MeuPluggy item
  `52632759-2058-4a3e-b1a3-50e3d32da75c`). It is a dollar account: its saldo em conta is in **US$**
  and must be shown in US$, never relabelled R$ and never shown as a converted number in its own
  screen.
- Everywhere else the app stays in reais (CLAUDE.md › "The app is reais-only on screen", memory
  `app-is-in-reais`). The exception is **one place**: an entry the owner taps (e.g. "Conta global"
  under the accounts on Início and in Ajustes › Contas) that opens the dollar account's own screen:
  balance in US$, its statement in US$, and a small "≈ R$ …" line from today's rate (`services/fx.py`,
  BCB PTAX) or "sem câmbio hoje". Update CLAUDE.md and the memory note to say exactly this.
- Início's consolidated balance and "Resumo do mês" keep their rules: decide (and write down) whether
  Wise counts in the consolidated balance converted to reais (recommended: yes, converted, like
  `accountBalanceBrl()` already does) — but a BRL → USD transfer is never income or expense.

## What exists (verify before relying on it)

- Migration 018 + `services/fx.py`: `accounts.currency`, `fx_rates`, `rate_on()`, USD/EUR/GBP via
  BCB, `CURRENCY_SYMBOLS`. API-only today; no screen offers a currency.
- `frontend/src/lib/transactions.js` › `accountBalanceBrl()` (converted or "sem câmbio hoje"), used
  by Dashboard, ContasSection, PayInvoiceSheet.
- Pluggy: `services/open_finance.py` reads `currencyCode` per account, but mapping refuses a non-BRL
  account (`"Conta nao e em reais."`, ~line 590) and auto-suggestion skips non-BRL;
  `open_finance_inbox.py` (~line 213) converts a row to BRL when `amountInAccountCurrency` is present
  (that is for card purchases abroad — for a USD *account* the row's amount is already US$). The
  Conferência (`open_finance_check.py`) compares cents with no currency.
- Transfers are one row (`account_id` → `transfer_account_id`, one `amount`). A BRL → USD transfer
  has two amounts: find whether 018 stored a second amount/rate on transfers; if not, add it
  (append-only migration) so the BRL side leaves the BRL account and the USD side lands in Wise.

## Build

1. **Backend**: allow mapping a Pluggy account whose currency matches the app account's currency
   (USD ↔ USD; still refuse a mismatch). Keep Pluggy rows of that account in its own currency end to
   end (item, lançamento, snapshot, Conferência, balance difference). Pair a BRL Pix to Wise with the
   Wise deposit as one cross-currency transfer (same day ±1, by counterparty "Wise", not by cents).
   Gravar sozinho/needs_review/GET-only rules stay as they are.
2. **Web**: the "Conta global" entry and screen (ui.jsx pieces only, emerald accent, `FitValue`,
   privacy mode via `usePrivateFormatter()` with a US$ formatter, `.num`, 44 px targets). Creating
   such an account: Ajustes › Contas gets a "Conta global (US$)" type — the only place a currency
   appears.
3. **APK** (native Kotlin/Compose, read `mobile-docs/native/` first): the same entry and screen;
   rules in `rules/` with JVM tests.
4. **Tests**: pytest for mapping USD↔USD (and refusal of a mismatch), USD rows not converted, the
   cross-currency transfer (both amounts, balances, never in spent/income), Conferência in US$;
   node tests for any formatter/rule; JVM tests on the phone.

## Adapt the owner's data (wgrrodrigues6@gmail.com) — after the code is deployed

Production lives on the home server; the harness refused SSH reads last time, so use the app's API
from the owner's logged-in Chrome tab (claude-in-chrome), with the owner's OK for each write batch.
Report before/after balances.
- The app has an account **"Wise"** created 2026-10-27 as BRL (balance R$ 559,43) holding three
  transfers from "BTG conta corrente": 2026-10-06 R$ 253,53, 2026-10-06 R$ 101,43,
  2026-10-07 R$ 204,47, description "Pix para Wise". They are the Pluggy BTG Pix to "WISE BRASIL
  CORRETORA DE CAMBIO LTDA." (BTG's side must keep matching Pluggy: BTG conta corrente = R$ 170,00).
- Turn "Wise" into the USD Conta global (or create it and move the transfers), map the Pluggy Wise
  account to it, pull, and make each transfer carry the US$ amount Wise actually credited (from the
  Pluggy Wise rows); anything else Wise shows becomes its own US$ rows. The Wise balance must equal
  Pluggy's US$ balance; BTG and the October Gastar (R$ 1.172,73) must not change.
- Don't touch the other accounts; they were aligned with Pluggy on 2026-10-27 (see handoff).
