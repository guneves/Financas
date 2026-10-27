# Prompt — bring Pluggy (Open Finance) back as a source for Aprovar

> Paste everything below the line into a new session. It is written for a cold start: it says what
> exists, what was tried before, and the order to work in. Owner's decisions still open are marked
> **(owner)** — ask before deciding them yourself.

---

Implement a **Pluggy** integration so the app gets my bank accounts' and credit cards'
transactions through **Open Finance** without me typing them. Read `CLAUDE.md`, `docs/handoff.md`
and `docs/next-steps.md` first, as usual.

## Background you must know

- **Pluggy was in this app once and was removed on 2026-10-17** (`docs/done-tasks.md`, rows
  "Pluggy removed from the app" and "Pluggy out of the migrations too"): the free plan gave no
  access to real banks. Migrations 027 and 029 are empty placeholders and 030 renames their
  `schema_migrations` rows — **never touch them**; this work gets a new numbered migration (043 or
  whatever is next). The old code is not in this clone's history; do not try to restore it, design
  it again against today's code.
- **Access is settled (owner, 2026-10-27):** I have a Pluggy account whose free plan works for
  **one CPF** — mine. The app is single-user, so that is all it needs. Consequences: connect only
  my own banks (one CPF); if Pluggy refuses a connection because of the CPF limit, show its
  message in Ajustes rather than retrying. Still check Pluggy's current docs (`docs.pluggy.ai`)
  for the free plan's other limits (connectors, request/refresh rate, history window) and keep the
  sync within them. Development and tests use Pluggy's **sandbox** connectors and mocked HTTP,
  never my real data; the first real connection is my check, after the deploy.
- **The server is reachable only inside my tailnet** (`DEPLOY.md`: `tailscale serve`, no public
  URL). Pluggy's webhooks cannot reach it, so the sync is **pull**: on demand ("Atualizar" button)
  and in a background thread like `services/quote_refresh.py` (every few hours, configurable,
  `0` = off — and `0` in `conftest.py`). Webhooks are out of scope.
- **The APK is native Kotlin/Compose with no WebView** (`mobile-docs/native/`). Connecting a bank
  (Pluggy Connect widget) happens **on the web only** (Ajustes); the APK only shows the result and
  can trigger "Atualizar". Do not add a WebView.

## What it must do

1. **Connect** (Ajustes › a new "Open Finance" section): the backend creates a Pluggy connect token
   (`POST /connect_token`, using the API key from `POST /auth`, cached until shortly before it
   expires) and the frontend opens the Pluggy Connect widget with it (official npm package, pinned
   version). On success the frontend sends the `itemId`; the backend stores the item. List items with
   their status, last sync and error, with "Atualizar" (`PATCH /items/{id}` then pull) and
   "Desconectar" (`confirmAction()`, deletes the item at Pluggy and archives ours — rows already
   recorded stay).
2. **Map Pluggy accounts to mine** (once per Pluggy account): each Pluggy `BANK` account to one of my
   active accounts (never the Corretora), each `CREDIT` account to one of my active cards with
   credit enabled. An unmapped account is pulled but produces nothing until mapped. Never guess the
   mapping silently — a suggestion by bank name/last digits is fine, confirmed by me.
3. **Pull transactions** (`GET /transactions?accountId=&from=`, paginated) from the last sync minus
   a safety overlap (e.g. 7 days; first sync: a window I choose, default 30 days **(owner)**). Skip
   `PENDING` status unless I decide otherwise **(owner)**.
4. **Everything goes to Aprovar, nothing is recorded directly.** CLAUDE.md: "nothing is recorded
   without approval, and a look-alike of an existing lançamento is a pending item with a
   candidate". A Pluggy transaction is one more *source* for `inbox_items`, beside the phone's
   notification detections (`services/inbox.py`, `ingest_detections()`, `notify_detections`):
   - Reuse the inbox machinery — pairing with an existing item (a notification already seen for
     the same purchase becomes the **same** item, not a second one), `suggest_for_item()` for
     recurrences, `inbox_hints`, `ambiguous_target()`, "Sempre perguntar". Decide whether Pluggy
     rows live in `notify_detections` with a new source or in their own table with the same role,
     and say why in the migration's comment. A Pluggy item knows its account/card from the mapping,
     so it should usually arrive with the target already set.
   - **Idempotent by Pluggy's transaction id**: a unique key like `pluggy:<transaction id>` per
     user, so a re-pull, the overlap window and a re-connect never duplicate anything. When I
     approve, the lançamento gets `source_type`/`source_id` under `idx_transactions_user_source`
     (new constant in `backend/source_types.py`), or the card purchase its own `client_id` rule
     (035) — keep the shape described in CLAUDE.md "Idempotency".
   - A Pluggy transaction that disappears or changes amount before approval: follow what the
     inbox already does when a source vanishes (`REMOVED`) — don't invent a second rule.
5. **Mapping Pluggy fields to the app's rules** — each of these needs tests:
   - Money in cents → `rounded_money()`; dates normalized (`require_date()`, local `-03:00`
     offset like `occurred_at`). Verify in Pluggy's docs and with the sandbox the **sign
     convention** per account type (bank vs credit) and `type` `DEBIT`/`CREDIT` — don't assume.
   - **Card installments**: `creditCardMetadata` (`installmentNumber`, `totalInstallments`,
     `totalAmount`, `purchaseDate`). The app creates all installments from the purchase
     (`POST /api/cc-expenses/purchases`), so only the **first** installment (or the purchase
     total) becomes an inbox item; the later installments Pluggy sends each month must be
     recognized as already covered and never become new items. The invoice month is still
     `compute_invoice_start()`'s (backend-only) — never Pluggy's bill.
   - **Card refunds** → `kind = 'REFUND'` (033); card **invoice payments** seen on the bank
     account are not expenses — never create a payment from Pluggy; at most offer the existing
     "Pagar fatura" flow (`POST /api/cc-expenses/pay-invoice`, only after closing).
   - **Transfers between my own accounts** (both sides connected) become **one** TRANSFER item
     (031's own-transfer rule; transfers are one row).
   - **Corretora / investment movements** are out of reach (CLAUDE.md: rules never touch
     investment cash, proventos, invoice payments). Pluggy's investments API is out of scope.
   - Pluggy's own category may be used only as a *suggestion* through `import_rules` / hints;
     categories are decided by id (035), and "Investimento" is not a category (039).
6. **Balance check** (read-only): show, per mapped account, Pluggy's balance next to mine
   (`consolidated_balance` rule — never sum `transactions`), so I see drift. Never adjust a balance
   automatically.

## Security and config

- `PLUGGY_CLIENT_ID`, `PLUGGY_CLIENT_SECRET` in the environment only (read in `config.py`, documented
  in `DEPLOY.md` and the compose file as secrets); never in the frontend, logs, API responses or
  the repo. The integration is **off** when they are missing (Ajustes says so; no errors at boot).
- HTTP to Pluggy in a client module (`pluggy_client.py`, pure, like `brapi_client.py`) with
  timeouts, one retry on network errors, `applog` logging without tokens or transaction
  descriptions, and `integrations.record_provider_result("pluggy", ...)` so the healthcheck shows it.
- Every new table has `user_id`, every query filters by it; every route has `@token_required`
  (`test_route_map.py`); destructive endpoints take a confirmation guard.
- Layering: `pluggy_client` ← `services/open_finance.py` (or similar) ← `routes/open_finance.py`,
  added to `app.py`'s blueprint list; no blueprint imports another.

## Order of work (one PR per phase is fine)

1. A short design note in `docs/next-steps.md`: tables, the inbox source
   decision, the sign convention verified in the sandbox.
2. Migration + `pluggy_client` + connect/item/account-mapping endpoints + tests with mocked HTTP.
3. Sync → Aprovar (dedup, pairing with notifications, installments, refunds, transfers) — the
   bulk of the tests: re-pull is a no-op, overlap window, a notification and a Pluggy row for the
   same purchase are one item, installments 2..n never become items, a vanished transaction,
   another user's data never touched.
4. Web: Ajustes › Open Finance (connect, map, status, Atualizar, Desconectar), following the UI
   rules (`ui.jsx` only, `toast()`/`AlertMessage`/`confirmAction()`, privacy mode on balances).
   Aprovar shows the source ("Open Finance" vs notification) on each item.
5. APK: show the source in Aprovar and the item status/"Atualizar" in Ajustes (no connect flow).
6. Background pull thread, `DEPLOY.md` (secrets, how to connect, how to disconnect), and the
   session end per CLAUDE.md.

## Done means

`pytest` and `npm test` green with new tests for every rule above; `vite build` ok; the sandbox
connector connected end to end in Chromium (screenshot); `docs/` updated; a clear list in the
handoff of what still needs my check with a real bank.
