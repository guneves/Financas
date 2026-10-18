# Prompt — Samsung Wallet + bank notifications + Pluggy, one purchase = one lançamento

> Hand this whole file to the AI session that does the work. It was written on 2026-10-17, after
> Samsung Wallet went back on the notification allow-list (capture only, no parser yet).
>
> **Status (2026-10-18).** Built: Part A's pure pairing rule (`notify/NotifyPairing.java`, step 2
> and the state logic of 3–4), Part B (client, 027, links, sync, Ajustes › Banco (Pluggy)) and
> Part C (attach, "Possível duplicata", the claim on creation — answered with **200
> `matched_bank`, not 409**; reasons in `docs/done-tasks.md`). Not built: the parsers, the
> detections table, the WorkManager promotion and the inbox (they wait for the owner's capture
> export), and nothing has run against the real Pluggy. What is left is in `docs/next-steps.md`.

---

You are working on **Finanças**, a single-user personal finance app (Flask 3 + SQLite backend,
React 18 + Vite frontend, Capacitor Android APK with native Java under
`frontend/android/app/src/main/java/br/financas/app/`). Before anything else, read `CLAUDE.md` in
full and follow its session process (`docs/handoff.md`, `docs/next-steps.md`,
`mobile-docs/steps-to-production.md` Phases 6–8). Every convention there binds you; the ones that
matter most here are quoted below, but CLAUDE.md wins if anything here disagrees.

## Goal

Three sources can report the same card purchase. Integrate them so **each real purchase becomes
exactly one lançamento** (or one `cc_expenses` purchase), whatever order the sources arrive in:

| Source | Where it runs | What it is good for |
|---|---|---|
| **Bank app notification** (Itaú `com.itau`, BB `br.com.bb.android`, BTG `com.btg.pactual.banking`) | Phone, native listener (`notify/`) | The issuer's own wording: card final digits, merchant, credit/debit. **Preferred** source on the phone. |
| **Samsung Wallet notification** (`com.samsung.android.spay`) | Phone, same listener | Fallback: some cards (some Itaú cards especially) send no push for a purchase. Samsung Wallet then is the only real-time signal. |
| **Pluggy** (Open Finance aggregator, https://docs.pluggy.ai) | Home server, backend | The bank's *posted* record, hours or days later. Authoritative for amount, date and installments; reconciles everything the phone produced. |

Owner's rule (2026-10-17): *"Samsung notification should be used when bank notifications don't
reach about card use."* So: bank notification wins over Samsung Wallet; Samsung Wallet is used
only when no bank notification for the same purchase arrives; Pluggy confirms or completes what
the phone wrote and adds what the phone never saw.

## What exists today (do not rebuild it)

- `NotifyRules.APPS` + the manifest `<queries>` (a JVM test keeps them equal) — Samsung Wallet is
  on it again. `BankNotificationListener` stores notifications verbatim in `financas_notify.db`
  **only in capture mode**; there are **no parsers** yet (Phase 6 step 4) and no inbox (Phase 7).
- `NotifyRules.dedupKey(package, key, postedAt)` — SHA-256, 64 hex chars, fits the server's
  `client_id` (migration 024). It deduplicates the *same posting*, not the same purchase.
- `client_id` idempotency on `POST /api/transactions`, `/api/transfers`,
  `/api/cc-expenses/purchases`; the native outbox (`outbox/`, `OutboxRules.java` ↔
  `lib/outboxRules.js`).
- Statement import idempotency (`source_type`/`source_id` + unique index
  `idx_transactions_user_source`) and the Phase 8 plan for "probable duplicate".
- The card invoice-month rule lives only in the backend (`compute_invoice_start()`).

## Hard rules

1. **Parsers are written against the owner's exported captures, never against examples from the
   web or from memory.** If you don't have an export (`Exportar JSON` from Ajustes › Notificações
   dos bancos) with real Samsung Wallet *and* bank notifications for the same purchases, **stop
   and ask for it**. Put fixtures in the repo only if the owner agreed (they contain merchants and
   amounts); otherwise keep them out and anonymize.
2. **Notification texts never leave the phone** except through the export. Not to the server, not
   to Pluggy, not to any third party. The phone sends the server only the *parsed* entry (amount,
   date, card/account, description) through the existing creation endpoints.
3. **Always confirm** is still the standing decision: a detection is a suggestion until the owner
   taps Confirmar (in-app list or the notification's button). Don't change that without asking.
4. Money through `rounded_money()`; `user_id` on every query; migrations append-only; transfers are
   one row; Portuguese user-facing strings; frontend uses only `ui.jsx` pieces.
5. Any Java the screens call ⇒ bump `frontend/native-level.txt` in the same commit. Any change to
   `outboxRules.js` ⇒ same change in `OutboxRules.java`, with a test on each side.
6. Add tests for every rule you write: JVM tests for the native rules
   (`gradlew :app:testDebugUnitTest --tests "br.financas.app.notify.*"`, or plain `javac` + JUnit +
   `org.json` when there is no Android SDK, as `docs/done-tasks.md` describes), pytest for backend,
   `node --test` for pure frontend modules.

## Part A — Phone: bank vs Samsung Wallet pairing (Phase 6 step 4 + Phase 7)

1. **Parsers** (pure Java, `notify/parse/` or similar, one per app including Samsung Wallet):
   return `Detection{ kind (CREDIT_PURCHASE, DEBIT_PURCHASE, PIX_OUT, PIX_IN, REFUND, DECLINED),
   amountCents, currency, merchant, cardLast4 (nullable), issuerHint (nullable), occurredAt }`.
   Samsung Wallet texts usually name the card or its last digits — read from the captures what it
   actually carries and map it to the owner's card (`credit_cards`) by last 4 or card name;
   unknown ⇒ the mapping screen (Phase 6 step 5).
2. **Pairing rule** (pure, `NotifyPairing.java`, JVM-tested exhaustively). Two detections are the
   same purchase when: same amount (to the cent), same card when both name one (or the Samsung
   card maps to the bank app's issuer when only one names it), and `|postedAt_a − postedAt_b| ≤
   window`. Start with **window = 10 min** and tune it from the captures (record the observed lag
   distribution in the handoff). Two genuinely separate same-amount purchases at the same shop
   within the window are possible: when one source shows 2 events and the other 1, pair one and
   keep the other.
3. **Hold-then-promote** for Samsung Wallet:
   - A **bank** detection becomes a suggestion immediately.
   - A **Samsung Wallet** detection is *held* (stored, not shown, not notified) until the window
     closes. If a matching bank detection arrives, the Samsung one is marked `superseded_by` that
     bank detection and never surfaces. If none arrives, it is **promoted** to a suggestion
     (labelled "via Samsung Wallet"). Use `WorkManager` (one-off work at `postedAt + window`) so
     promotion happens with the app closed.
   - **Late bank notification** after a Samsung detection was already promoted: if it is still an
     unconfirmed suggestion, replace its fields with the bank's and keep one suggestion. If the
     owner already confirmed it, do not create a second entry: mark the bank detection as
     `matched_entry` (same `client_id`) and drop it.
   - DECLINED from either source cancels the held/pending counterpart.
4. **One `client_id` per purchase, not per notification.** Today Phase 7 plans
   `client_id = dedupKey(notification)`. With pairing, derive it from the **first** detection of the
   pair group (store `group_client_id` on each detection row) so confirming from either the
   Samsung notification or the bank one hits the server's idempotency and writes once. Check in
   the captures whether a bank *updates* a notification (new posted time, same key); if so, build
   the key from Android key + `Notification.when` instead (open question already in Phase 7).
5. Native table changes: add a detections table in `financas_notify.db` (or `NotifyStore`) with
   `source_package`, parsed fields, `state` (HELD, SUGGESTED, CONFIRMED, DISCARDED, SUPERSEDED),
   `group_client_id`, `superseded_by`. Keep capture mode independent (still verbatim, still off by
   default).
6. Ajustes text and the Phase 6 table in `mobile-docs/steps-to-production.md`: say Samsung Wallet
   is a fallback source and how pairing works.

## Part B — Server: Pluggy

Verify every endpoint, field and limit below against https://docs.pluggy.ai before using it — this
list is a starting point, not a spec.

1. **Access.** Pluggy issues `clientId`/`clientSecret` per application; `POST /auth` returns an
   API key (short-lived, cache it and refresh). Put both in `backend/.env` (`PLUGGY_CLIENT_ID`,
   `PLUGGY_CLIENT_SECRET`) and the production `.env` on the home server — never in the repo, never
   in the frontend bundle, never in `deploy.yml` in clear text. `conftest.py` must blank them like
   `BRAPI_TOKEN` so no test reaches Pluggy. Ask the owner which plan/product they have (developer
   account, MeuPluggy for personal connections, or a paid plan): it decides how the bank
   connections ("items") are created.
2. **Client module** `backend/pluggy_client.py`: pure HTTP functions (auth, list items, accounts,
   paginated transactions by `accountId` + `from`/`to`, transactions by `ids`), with caching and
   pacing, recorded in `integrations.py` (last success/failure) so the healthcheck shows it.
   Tests patch it where the name is read (CLAUDE.md, "Patch where the name is read").
3. **Mapping** (migration `027_pluggy.sql`): a table linking each Pluggy account to a local
   `accounts.id` or `credit_cards.id` (`user_id`, `pluggy_item_id`, `pluggy_account_id`, local
   target, `since` date), plus an Ajustes screen to link them. Like `portfolio_since`, only
   transactions on or after `since` are imported — older ones are already in the opening balance.
4. **Sync** `services/pluggy_sync.py`, `POST /api/pluggy/sync` (+ run on read like
   `apply_due_autopay()`, at most every N minutes): every Pluggy transaction becomes a row with
   `source_type = 'PLUGGY'`, `source_id = 'pluggy:<transaction id>'`, so the unique index makes a
   re-sync a no-op (same shape as recurrences, autopay and statement import). Card transactions go
   to `cc_expenses` through the backend invoice-month rule (installments from Pluggy's credit-card
   metadata, all sharing one id). Skip `PENDING` until `POSTED` unless the owner prefers otherwise;
   handle Pluggy's updated/deleted transactions (follow the row, refuse to delete one with a
   receipt — same pattern as the cash link's 409).
5. **Webhooks vs polling.** The server is reachable only inside the tailnet; Pluggy webhooks need a
   public HTTPS URL. Default to **polling** (on read + the Atualizar button). Only propose Tailscale
   Funnel for webhooks if the owner asks, and then verify the webhook signature/secret.

## Part C — Reconciliation: phone entry ↔ Pluggy row

This is Phase 8's "probable duplicate" applied to Pluggy, done on the server:

1. Before inserting a Pluggy transaction, look for an existing row on the **same account/card**,
   **same amount** (for installments, the installment amount or the total), date within
   **±3 days** (tune), not already matched, with a `client_id` (typed or notification-born) or
   from a statement import. Exactly one candidate ⇒ **attach** instead of inserting: store
   `pluggy:<id>` on the existing row (a new nullable column `external_id` with a unique partial
   index — `source_type` stays what it was, so a typed row stays "Manual" and editable), and let
   Pluggy correct the date/amount only if the owner's settings say so (default: keep the owner's
   values, flag the difference).
2. Several candidates or a mismatch ⇒ insert nothing automatically; list it in a reconciliation
   inbox ("Possível duplicata") for the owner to pair or keep both. Never silently merge two
   same-amount purchases.
3. The reverse order (Pluggy first, the owner confirms a notification later) must also end in one
   row: `POST` creation with a `client_id` checks for an unmatched Pluggy row with the same
   account/amount/date window and returns a 409 with the candidate so the phone can show "já
   registrado pelo banco" instead of writing a second one. Design this carefully with the outbox
   rules: a 409 is a server response and is never retried (CLAUDE.md, the outbox convention).
4. Transfers, invoice payments, investment cash and proventos rows are out of reach of matching.

## Tests you must write (minimum)

- JVM: pairing (bank first, Samsung first, Samsung alone ⇒ promoted, late bank after promote,
  late bank after confirm, two same-amount purchases, declined cancels, different cards never
  pair, window edge exactly at the limit); parsers against each captured text.
- pytest: Pluggy sync idempotency, `since` cut-off, installments, updated/deleted, `user_id`
  isolation, attach-to-existing (one candidate), inbox (two candidates), no match across accounts,
  transfers excluded, credentials blank ⇒ no network; route map updated for the new blueprint.
- node: any new pure frontend rule module.

## Order of work and stopping points

1. Read the capture export; write parsers + pairing (Part A 1–2). Stop and show the owner the
   observed lag between Samsung and bank notifications.
2. Hold/promote + detections table + inbox (Part A 3–5, Phase 7).
3. Pluggy client + mapping + sync (Part B), behind the owner's credentials.
4. Reconciliation (Part C).

Each step is a separate commit with tests green. At the end, follow CLAUDE.md: move finished
items from `docs/next-steps.md` to `docs/done-tasks.md`, replace the entry in `docs/handoff.md`,
update `mobile-docs/steps-to-production.md` and the CLAUDE.md conventions you changed (the
"Bank notifications" bullet still says only "the same posting" is deduplicated).
