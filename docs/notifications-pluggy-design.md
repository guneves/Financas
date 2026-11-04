# Notifications + Pluggy: one movement, one row

> Design, 2026-11-04. Owner's request: integrate phone notifications with Pluggy with **no overlap and
> no duplicates**; when a real purchase really happens twice, the app must **recognize both**;
> **investments are Pluggy-only**, and notifications deliver only **transfers to and from BTG
> Investimentos**. Nothing here is built yet: the phased plan is in `docs/next-steps.md` and
> CLAUDE.md changes with each phase, never ahead of the code.

## 1. Where we start

Since 2026-10-30 the server answers `ignored` to every notification except the Flash
(`notification_wanted()` in `services/inbox.py`), and the APK hears only the Flash app and Samsung
Wallet's Flash card (`NotifyRules.APPS`). The engine below the gate is still the 043/045 one:
`inbox_items` (one per movement), `notify_detections` and `open_finance_transactions` (the
evidence), `reconcile_recorded()` (Pluggy takes over what a notification recorded) and
`free_candidates()` (link, never duplicate). Opening the gate re-enables all of it.

A probe against that engine (the gate opened by the `any_bank_notifications` fixture; Itaú mapped
in `FakePluggy`, `include_pending` on) gave:

| # | Scenario | Result |
|---|----------|--------|
| A | Notification records R$ 45,90 → owner reviews it → Pluggy brings it `PENDING` (id P1) → next pull it is `POSTED` under a **new id** P2 | **2 rows: duplicate** |
| B | Same as A, but the row was never touched | 1 row, but the notification's row is **deleted and re-created** (new id) |
| C | Two identical 3× purchases on one card, same day | 6 installments: correct |
| D | Two R$ 8,00 coffees, both notified, then two Pluggy rows | 2 rows: correct |
| E | Two coffees, only one notified, two Pluggy rows | 2 rows: correct |
| F | Pluggy first, the notification later (phone offline) | 1 row: correct |
| G | Two coffees from Pluggy first, then two notifications | 2 rows: correct |
| H | Pix Itaú → BTG Investimentos, both apps notify, then both Pluggy sides | 1 transfer: correct |

So the engine already keeps twins apart and pairs across sources in either order. **A** is the only
duplicate, and the default settings make it likely: pending rows have come in by default since 052,
cards always bring them, and a reviewed row is the normal state after a day of use.

**Why A happens** (checked on the probe's rows). Because the row was reviewed,
`reconcile_recorded()` only links P1 to it (role `MATCHED`). On the next pull P1 is gone, but
`vanish_missing()` only looks at `SOURCE` and `UNMAPPED` rows (and the broker's `MATCHED` ones). So
P1 stays a **live** `MATCHED` claim on the row, forever. Then P2 arrives:
- `notification_item_for_open_finance()` skips the item because it already has a Pluggy source
  whose role is not `REMOVED` (P1).
- `new_item_for_row()` → `existing_rows(for_notification=True)` → `_explained_by_notification()`
  drops the row, because a **notification** detection targets it, and so does P1.
- So P2 opens a new item, and `record_pending()` records a second row.

Underneath this are two flaws:
- a row claimed by *any* source blocks *every* source, when a notification's claim should never
  stop a Pluggy row;
- an id that left Pluggy keeps its claim, when it should hand the claim to its successor.

**B** has the same cause in a milder form. `apply_vanish()` deletes the untouched row that P1 had
taken over from the notification, and P2 records a fresh one.

A second risk is in the parser, not the server. `NotifyParsers.kindOf()` makes any text with
"compra" a `PURCHASE`, so a BTG Investimentos "ordem de compra executada, R$ 1.234,00" would become
a card purchase: `fill_defaults()` falls back to the issuer's card. The gate in §4 stops it.

## 2. The model

A **movement** is one real economic event. Today it is an `inbox_item`, and it has at most one
**lançamento**. An **observation** is one piece of evidence of a movement. Each observation belongs
to exactly one **channel**:

| Channel | Observations | Identity of one observation |
|---------|--------------|-----------------------------|
| `NOTIFY_BANK` | Itaú, BB, BTG Banking and BTG Investimentos apps; the Flash app | `dedup_key` (package + Android key + posted time); a repost is the same observation (`_repeated_posting()`, same app, kind, amount, `when` and merchant within 60 s; BTG posts twice, 24 ms apart) |
| `NOTIFY_WALLET` | Samsung Wallet, Flash card only (§4) | `dedup_key` |
| `PLUGGY` | `open_finance_transactions` | Pluggy id, **plus succession**: a `PENDING` id that leaves the pull while a matching id arrives is the same observation (§3.3) |
| `TYPED` | "+ Novo" (Flash and transfers with a non-Pluggy side) | `client_id` |

### Invariants

- **I1. One row per movement.** A movement has at most one lançamento, and a live observation
  points to at most one movement.
- **I2. Channel uniqueness.** A movement holds at most one live observation per channel **and
  side**. A purchase, despesa or receita has one side. A transfer between the owner's accounts has
  two, outgoing and incoming: Itaú's "Pix enviado" and BTG Investimentos' "recebemos" are one
  movement, one observation per side. Two observations from the same channel on the same side are
  two movements, unless the table above says they are the same observation (same key, repost,
  Pluggy succession).
- **I3. Cross-channel fill.** A new observation joins an existing movement only through that
  movement's empty slot for its own channel, inside the window for that pair of channels (§3.1).
  Otherwise it opens a new movement.
- **I4. Truth precedence.** On a Pluggy-fed account or card, Pluggy's amount, date and target win
  while the row is untouched (`notification_untouched()`). Once the owner has touched it, Pluggy only
  links, and the Conferência shows any difference. Notifications are the fast, provisional source;
  Pluggy is the source of record.
- **I5. Investments are Pluggy's.** Only Pluggy creates investment operations, proventos and
  broker-statement lines. A notification creates at most the `TRANSFER` between a reais account
  and the Corretora (an aporte/resgate by origin, 039).

### What the invariants guarantee about twins

Take a cluster of identical movements: same target, same cents, same day. Let *n_N* be the number
of notification observations and *n_P* the number of Pluggy observations.

- By I2, each Pluggy observation occupies a different movement's `PLUGGY` slot, so there are at
  least *n_P* movements. The same holds for notifications, so there are at least max(*n_N*, *n_P*).
- By I3, a notification creates a movement only when no movement has a free `NOTIFY_BANK` slot,
  and the same goes for Pluggy. So there are at most max(*n_N*, *n_P*).
- Hence **#rows = max(*n_N*, *n_P*)**. Two real coffees stay two (D, E, G). One coffee notified once
  and posted once stays one (F).

If *n_N* > *n_P* after the bank has refreshed past the late-post window, the extra row is an
**orphan**: authorised but never posted, such as a released pre-authorisation (§3.4).

The observations inside such a cluster are exchangeable. Same account, cents and direction means
any one-to-one assignment gives the same balances and totals; only descriptions or times could swap.
So the existing greedy nearest-first pairing (`_pick_closest()`) is optimal for the ledger, and an
optimal-assignment solver (Hungarian method, ref. 4) would only change cosmetics. This is the
classic record-linkage setup (refs. 1–3): blocking keys (target, direction, cents) plus comparison
windows (date, time). The added rule is the one-to-one constraint per channel, which keeps true
duplicates and is the weak point of naïve dedup.

## 3. Rules

### 3.1 Windows (existing constants, plus one new rule: succession)

| Pair | Same movement when |
|------|--------------------|
| bank app ↔ Samsung Wallet | same cents, compatible card, ≤ `NOTIFY_WINDOW_MS` (10 min), one to one, bank wins |
| notification ↔ Pluggy | same cents, or `rounded_up()` on BB; installment ↔ total on cards; same target per mapping; Pluggy date within notification date −1…+1 (`OPEN_FINANCE_PAIR_DAYS`) for any state, and +2…+5 (`OPEN_FINANCE_LATE_POST_DAYS`) for an already recorded one |
| Pluggy ↔ Pluggy (succession, **new**) | same Pluggy account, direction and cents (or rounded up), predecessor missing from this pull, date ±3 days |
| own transfer sides | same cents, ±`TRANSFER_MATCH_DAYS` (1), counterparties not in conflict |
| typed look-alike | same cents, ±`INBOX_MATCH_DAYS` (3) |

### 3.2 A notification arrives (`ingest_detection()`)

1. **Gate (§4).** If the app and kind are not in the policy, answer `ignored` and keep nothing.
2. **Same observation.** Same `dedup_key` → `known`; a repost → `repeated`.
3. **Wallet pair.** Join the bank notification or Samsung detection of the same purchase (I2: one
   to one).
4. **Other side of an own transfer.** Join a pending one-sided transfer, or confirm an approved one.
5. **Pluggy already has it** (`open_finance_item_for_detection()`). Join that movement if its
   `NOTIFY_BANK` slot is free; the notification's cleaner merchant name replaces the description if
   untouched.
6. **New movement.** Its candidates come from `existing_rows(claimed_by=NOTIFY)`: rows with no live
   notification claim. A typed look-alike is linked, never duplicated.
7. **Record at once** (`auto_record.record_notifications()`): `needs_review = 1`, with a snapshot.
   Only a one-sided own transfer waits, and only while the other side cannot be guessed.

### 3.3 A Pluggy row arrives (`place()`), in the order of one pull

0. **Succession (new).** Before ingesting, the pull computes *missing*: the account's live rows in
   the window that Pluggy did not return. "Live" means every role except `REMOVED`, including
   `MATCHED` and `PAIRED`, which `vanish_missing()` skips today (the root of A). A new row that
   matches a missing one (§3.1) **takes over its slot in place**:
   - the new row gets the old row's role, `item_id`, target and snapshot;
   - the old row becomes `REMOVED` with `superseded_by`;
   - `transactions.source_id` (or the card purchase's `client_id`) moves to the new id when it was
     the old one's;
   - nothing is deleted.

   Only the missing rows that nothing took over then go through `vanish()` / `apply_vanish()`.
   A missing `MATCHED` row without a successor gets `conflict = 'vanished'`, so the Conferência
   sees it. Today it stays silently live. This fixes A and B, and makes pending → posted a
   non-event for every source.
1. **Invoice payment, Corretora statement, installments 2..n, auto-invest**: unchanged.
2. **A notification already has it** (`notification_item_for_open_finance()`). Its `PLUGGY` slot
   must be free; a `vanished` or `REMOVED` source does not occupy it. Then `reconcile_recorded()`
   runs as today (untouched: Pluggy becomes the source; bank disagrees: re-record its way; touched:
   link only).
3. **Recorded transfer, Conta global, own-transfer pairing**: unchanged.
4. **New movement.** Its candidates come from `existing_rows(claimed_by=PLUGGY)`: rows without a
   **live Pluggy** claim. A notification claim no longer hides a row from Pluggy, which is the
   second half of the fix for A.

### 3.4 Lifecycle of a notification-recorded row on a Pluggy-fed target

`provisional` (notification only, `needs_review`) → `confirmed` (Pluggy source attached, by
§3.3.2) → reviewed by the owner.

While provisional, the Conferência already lists it as `awaiting_bank`, not `app_only`
(`newer_than_bank()`). **Orphan rule (new, owner to confirm):** once `bank_refreshed_since()` holds
for the row's date + `OPEN_FINANCE_LATE_POST_DAYS` and Pluggy still has no row for it, the untouched
row is removed the way `undo_declined()` removes a declined one, and the pull log counts it. A
touched row stays and is listed `app_only`.

### 3.5 Real duplicates: kept and recognised

- **Kept**: I2 guarantees it. Tests D, E and G become permanent.
- **Recognised (new)**: "Precisa de atenção" gets a `twin:` card for two lançamentos when all of
  these hold:
  - they are on the same target, with the same cents and the same normalised merchant;
  - they come from **two distinct same-channel observations**;
  - they are ≤ 60 min apart (same day when only Pluggy dates exist).

  Text: "Duas compras iguais em PADARIA (R$ 8,00, 08:00 e 08:04). Cobrança em dobro?" Actions:
  "São duas" (dismiss, per device like the other cards) or open the Extrato on them. This covers a
  real second coffee and a merchant's double charge to contest. The app never decides which one is
  wrong.

## 4. Channel policy (server `notification_wanted()` and APK `NotifyRules`)

| App | Accepted kinds | Target | Notes |
|-----|----------------|--------|-------|
| Flash app, Samsung Wallet (Flash card) | outgoing only, no `CREDIT_PURCHASE`; `DECLINED` | the Flash account | as today |
| Itaú, BB, BTG Banking | `CREDIT_PURCHASE`, `DEBIT_PURCHASE`, `PURCHASE`, `PIX_*`, `TRANSFER_*`, `REFUND`, `DECLINED` | as today (remembered, guessed, then corrected by Pluggy) | invoice-payment and investment texts ignored (below) |
| **BTG Investimentos** | **only** `PIX_IN`, `PIX_OUT`, `TRANSFER_IN`, `TRANSFER_OUT` | the Corretora, always an own transfer (`is_self_counterparty()` already says so) | an order, provento, fixed-income application or fee is `ignored` |
| Samsung Wallet, any other card | none | — | the bank app already notifies, and Pluggy brings the rest; a third channel only adds overlap |
| any other app | none | — | |

Text filters, on the phone (where the text is) and repeated on the server over `merchant` and
`counterparty`:
- `is_auto_invest()` (Rende Fácil, conta remunerada), as today;
- **investment words (new)**: aplicação, resgate, CDB, LCI, LCA, Tesouro, fundo, ordem, provento,
  dividendo, JCP;
- invoice payments: Pluggy records them through `settle_invoice()`.

An old APK that still sends anything is safe, because the server gate decides. The brake is a
per-user `bank_notifications` setting in `GET/PATCH /api/inbox/settings`, defaulting to on once
Phase 2 ships. Off means today's behaviour: Flash only.

## 5. Investments: Pluggy only

- **Operations**: BUY and SELL come from `open_finance_investments.py` (BTG `/investments`), as
  today. A **typed** operation whose cash account is the Pluggy-fed Corretora is refused (400,
  "A Pluggy traz as operações da corretora"). There is one exception: **completing a `HELD`
  Pluggy operation** (fixed income, Tesouro, INTEREST, unknown asset). The form opens pre-filled
  from it and carries its `op_key`, so the effect still originates in Pluggy and the owner only adds
  what Pluggy lacks (indexer, title, coupon start). Assets Pluggy cannot see (crypto) stay typed with
  another cash account or none, the same way the Flash stays typed.
- **Proventos**: StatusInvest-computed ones are forecasts ("em trânsito"). The paid credit on the
  broker statement takes over, as today (bank value and day, `sync_locked`). A typed provento on the
  Corretora follows the `HELD` rule above.
- **Cash**: the Corretora's balance is its statement (`broker_statement.py`), unchanged.
- **Notifications**: only the transfer between a bank and the Corretora (test H). It is recorded at
  once when both sides notify. With one side, it is the despesa/receita of the side seen until
  Pluggy brings the other (`_absorb_recorded_pix()`).
- The old plan "Brokerage operations from notifications" (next-steps, Mobile app section) is
  withdrawn by this rule.

## 6. Changes, by phase

**Phase 1: engine invariants (server only; no visible change while the gate is closed).**
- `services/open_finance.py` (pull): compute *missing* (every live role, `MATCHED` and `PAIRED`
  included) → ingest with succession → vanish what is left.
- `services/open_finance_inbox.py`: `successor_for()` and `hand_over()`; step 0 in `place()`;
  `superseded_by` (new migration, next free number after merging main).
- `services/inbox.py`: `existing_rows(claimed_by=…)` replaces `for_notification`;
  `_explained_by_notification()` splits into a Pluggy claim and a notification claim;
  `notification_item_for_open_finance()` ignores vanished and removed sources.
- `services/inbox_defaults.free_candidates()` and `open_finance_auto._linked_elsewhere()` use the
  same claim helpers, so there is one definition of "claimed".
- Tests `test_notify_pluggy_identity.py`: matrix A–H as written in §1 (A and B must give one row
  with the **same id**), plus:
  - succession on a card purchase;
  - succession with BB rounding;
  - two pending rows → two posted rows (twins through succession);
  - an invariant helper asserting I1/I2 after every scenario (no lançamento targeted by two live
    observations of one channel; no live observation targeting two lançamentos).

**Phase 2: open the gate (server + APK).**
- `notification_wanted()` → `NOTIFICATION_POLICY` (§4) and the `bank_notifications` setting;
  `test_flash_only.py` becomes `test_notification_policy.py`.
- APK: `NotifyRules.APPS` adds `com.itau`, `br.com.bb.android`, `com.btg.pactual.banking` and
  `com.btg.pactual.digital.mobile`. `NotifyParsers.parse()` returns null for a non-transfer kind
  from the brokerage app and for investment words. JVM tests in `NotifyRulesTest` and
  `NotifyParsersTest`, including "ordem de compra executada" → null.
- Ajustes › Avisos do celular: the switch and its text.
- CLAUDE.md: "Open Finance is the only banking source" becomes "Notifications are fast, Pluggy is
  the record"; `manual_entries.py` (typing) is unchanged.

**Phase 3: investments Pluggy-only.** The guard in `POST /api/investments` (and the proventos
route) with the `HELD` completion path; web and APK forms open from a `HELD` line.

**Phase 4: twins recognised.** `services/attention.py` `twin:` key, `components/Attention.jsx`, APK.

**Phase 5: orphans.** The sweep after each pull (§3.4), counted in the pull log.

**Observability (with Phase 1).** `scripts/check_identity.py` runs the I1/I2 check read-only on
the server database and lists any lançamento that two live observations of one channel claim. In
normal operation it must print nothing. Run it after the first week with the gate open.

## 7. Owner decisions (recommendation first)

1. **Orphan rows**: remove untouched ones automatically after the bank refreshed past +5 days
   (recommended), or only list them in the Conferência.
2. **Samsung Wallet**: Flash card only (recommended), or bank cards too.
3. **Typed investments**: refused on the Corretora except completing a `HELD` line (recommended,
   as the request says), or still allowed and linked.
4. **Twin card**: on (recommended), or off.
5. **Default of `bank_notifications`**: on when Phase 2 ships (recommended), or off until the owner
   turns it on.

## References

1. Fellegi IP, Sunter AB. A theory for record linkage. *J Am Stat Assoc*. 1969;64(328):1183–1210.
2. Elmagarmid AK, Ipeirotis PG, Verykios VS. Duplicate record detection: a survey. *IEEE Trans Knowl
   Data Eng*. 2007;19(1):1–16.
3. Christen P. *Data Matching: Concepts and Techniques for Record Linkage, Entity Resolution, and
   Duplicate Detection*. Berlin: Springer; 2012.
4. Kuhn HW. The Hungarian method for the assignment problem. *Nav Res Logist Q*. 1955;2(1–2):83–97.
5. Kleppmann M. *Designing Data-Intensive Applications*. Sebastopol: O'Reilly; 2017. Ch. 11
   (idempotence and exactly-once processing through deduplication keys).
6. Pluggy API reference, Transaction object (`status` PENDING/POSTED, `creditCardMetadata`),
   docs.pluggy.ai.
