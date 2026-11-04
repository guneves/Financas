# Phase 2: open the gate for bank notifications (server + APK)

Read `00-common.md` first. Design: §4 (channel policy), §5 (the brokerage app delivers transfers
only), §7 decisions 2 and 5. After this phase, the owner's phone sends Itaú, BB, BTG Banking and BTG
Investimentos notices, and they are recorded at once. **Phase 1 (1a + 1b) must be merged first**:
without it, defects A, I and R hit real data.

**Prerequisites** (stop if any fails):

```bash
grep -n "def pluggy_claimed\|def merchant_agrees\|def near_amount" backend/services/inbox.py
```

```bash
grep -rn "superseded_by\|original_currency" database/migrations/
```

```bash
grep -n "international" backend/services/inbox.py | head -3
```

## Server

1. **Policy table** in `services/inbox.py`. `notification_wanted(detection)` **keeps its signature
   and stays pure**: the fixture `any_bank_notifications` replaces it with
   `lambda detection: True`, and every engine test depends on that.

   | App | Accepted kinds |
   |-----|----------------|
   | Flash app; Samsung Wallet with the Flash card (`is_flash_detection()`) | as today: outgoing only, no `CREDIT_PURCHASE`, plus `DECLINED` |
   | Samsung Wallet, any other card | none |
   | `com.itau`, `br.com.bb.android`, `com.btg.pactual.banking` | every kind in `KIND_SHAPES`, plus `DECLINED` |
   | `com.btg.pactual.digital.mobile` (BTG Investimentos) | **only** `MOVEMENT_KINDS` (Pix/TED in and out) |
   | anything else | none |

   **Investment-word filter**:
   - applies to `MOVEMENT_KINDS` (counterparty and merchant) and to everything from the brokerage
     app, **never** to a card purchase's merchant. "FUNDO DE QUINTAL BAR" and "TESOURO DO MAR
     RESTAURANTE" are restaurants;
   - words, with word boundaries over `inbox.normalized()`: aplicacao, resgate, cdb, lci, lca,
     tesouro direto, fundo de investimento, ordem de compra, ordem de venda, provento, dividendo,
     jcp;
   - `is_auto_invest()` stays as it is.
2. **The brake**: `bank_notifications` in `user_settings`, read with `inbox.setting_value()`.
   - Default from a new `config.BANK_NOTIFICATIONS_DEFAULT` (env, default on), read once at import.
     Test it with the switch both on and off.
   - In `ingest_detection()`, right after `notification_wanted()`: a non-Flash detection with the
     setting off answers `ignored` and keeps nothing.
   - `GET/PATCH /api/inbox/settings` (`routes/inbox.py:116`) returns and accepts
     `bank_notifications` (booleans only, 400 otherwise, like `auto_record`).
3. **Tests**: rename `test_flash_only.py` to `test_notification_policy.py`. Keep every Flash case,
   and add:
   - each bank app's kinds are accepted;
   - the brokerage app: `PURCHASE` ("ordem de compra") ignored, `TRANSFER_IN` accepted and
     recorded as a transfer into the Corretora;
   - Samsung with a BTG card ignored;
   - an unknown app ignored;
   - the setting off: only the Flash passes;
   - a Pix whose counterparty is "TESOURO DIRETO" ignored, while a card purchase at "FUNDO DE
     QUINTAL BAR" is accepted;
   - an old APK sending a bank `PURCHASE` with the setting off is ignored.

   Do **not** use `any_bank_notifications` in this file: it bypasses the policy.

## APK (Java, `frontend/android/app/src/main/java/br/financas/app/notify/`)

There is no Android SDK in the container. Push and read `android-check` with the GitHub MCP
actions tools.

1. **`NotifyRules.APPS`**: add `com.itau` "Itaú", `br.com.bb.android` "Banco do Brasil",
   `com.btg.pactual.banking` "BTG Pactual" and `com.btg.pactual.digital.mobile` "BTG
   Investimentos". The names match the server's `APP_LABELS`/`ISSUER_OF_APP`.
2. **`AndroidManifest.xml` `<queries>`**: add the same four packages.
   `NotifyRulesTest.theManifestCanSeeEveryHeardApp` fails if the lists differ.
3. **`accepts()`**: Samsung Wallet stays Flash-only.
4. **`NotifyParsers.parse()`**, applied in this order:
   1. **An invoice payment is never a movement.** A text with "fatura" plus
      pagamento/pago/paga/quitada returns null for every app. This must come **before** `kindOf()`,
      whose purchase regex matches a bare "aprovad", so "Pagamento da fatura aprovado" would
      otherwise become a `PURCHASE`.
   2. **The brokerage package** returns null for any kind but `PIX_*`/`TRANSFER_*`, and null for
      the investment words.
   3. **`Parsed.international = true`** when the text has internacional, exterior, US$, USD, EUR,
      € or £. `toDetection()` (line ~167) puts `"international": true` only when true.
5. **JVM tests** (`NotifyRulesTest`, `NotifyParsersTest`):

   | Text | Expected |
   |------|----------|
   | BTG Investimentos: "Sua ordem de compra de PETR4 foi executada. Valor R$ 1.234,00" | null |
   | BTG Investimentos: "Recebemos sua transferência no valor de R$ 5,08" | `TRANSFER_IN` |
   | Itaú, BB and BTG: "Pagamento da fatura aprovado R$ 1.234,56" | null |
   | "Compra internacional aprovada R$ 52,30 AMAZON" | purchase, international |
   | a purchase at "FUNDO DE QUINTAL" | parsed normally |
   | Samsung with "BTG Pactual Banking" | still rejected |
6. **Ajustes**: a switch "Avisos dos bancos" bound to `bank_notifications`.
   - **APK**: `ui/ajustes/` (`AjustesViewModel.kt` already reads the inbox settings; DTOs in
     `data/InboxDtos.kt`).
   - **Web**: there is no notification section since 2026-10-31 (Aprovar was removed). Add a small
     one under Ajustes using only `ui.jsx` pieces, with the API call in `lib/dataApi.js`.
   - **Text**: "Itaú, BB e BTG gravam na hora pelo aviso do celular; a Pluggy confere depois."
     Node test for any pure rule you add.

## CLAUDE.md

Rewrite **"Open Finance is the only banking source"** as "Notifications are fast, Pluggy is the
record". Fix every sentence that says bank notices are ignored ("Phone notices of banks are
ignored", "the server enforces it for old APKs", "notifications exist only for the Flash"). Keep:
- **Only the Flash is typed** (`manual_entries.py` is unchanged);
- Rende Fácil's notice is `ignored`.

Add the policy table in short form.

## Pitfalls

- `test_auto_record.py`, `test_inbox*.py` and `test_card_debit.py` use `any_bank_notifications`
  and must stay green unchanged.
- A detection from an allowed bank app with the setting **off** must leave no row in
  `notify_detections` (the "ignored, no trace" rule), so a later switch-on can't record old
  notices in bulk.
- The APK only sends after the owner installs the update. Old APKs keep sending the Flash only, so
  nothing breaks before the update.

## Done when

The server suite is green on a tree merged with `origin/main`, android-check is green on your
branch, and CLAUDE.md is updated.

**Owner, after merge and APK update**, in this order, in Portuguese in your final message:
1. an Itaú card purchase shows up in seconds;
2. after the next pull it is still one row;
3. a Pix to BTG Investimentos gives one transfer;
4. a week later, run `scripts/check_identity.py`; it must print nothing.

Then run `06-verify-and-fix.md` for Phase 2.
