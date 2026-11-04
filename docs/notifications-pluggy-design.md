# Notifications + Pluggy: one movement, one row

> Design, 2026-11-04. Owner's request: integrate phone notifications with Pluggy with **no overlap and
> no duplicates**; when a real purchase really happens twice, the app must **recognize both**;
> **investments are Pluggy-only**, and notifications deliver only **transfers to and from BTG
> Investimentos**. The owner's decisions are in §7 (least friction). Nothing here is built yet: the phased plan is in `docs/next-steps.md` and
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
| I | Own Pix Itaú → BB, each bank's notification in a **separate upload** (the normal case: the phone sends as they arrive) | **INCOME + EXPENSE**: both totals inflated. In one upload: 1 transfer |

So the engine already keeps twins apart and pairs across sources in either order. **A** is the only
duplicate, and the default settings make it likely: pending rows have come in by default since 052,
cards always bring them, and a reviewed row is the normal state after a day of use.

**I** happens because the first side is recorded the moment it arrives, as a despesa. The second
side's notification only looks for *pending* items (`transfer_partner()`) or recorded *transfers*
(`approved_transfer_awaiting()`), so it becomes a receita. Pluggy's absorb step
(`_absorb_recorded_pix()`) only runs for a Pluggy row that found no notification partner. Each Pluggy
side then pairs with its own notification row first, so by reading the code, the split stays (not
probed).

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
   **New (fixes I):** also absorb a *recorded*, untouched despesa/receita when all of these hold:
   - it goes the opposite direction, on another reais account;
   - same cents, ±`TRANSFER_MATCH_DAYS`;
   - the counterparties can be one person.

   That row becomes the transfer, one row. This is the same rule as `_absorb_recorded_pix()`, moved
   into one helper that both paths call.
5. **Pluggy already has it** (`open_finance_item_for_detection()`). Join that movement if its
   `NOTIFY_BANK` slot is free; the notification's cleaner merchant name replaces the description if
   untouched.
6. **New movement.** Its candidates come from `existing_rows(claimed_by=NOTIFY)`: rows with no live
   notification claim. A typed look-alike is linked, never duplicated.
7. **Record at once** (`auto_record.record_notifications()`), with a snapshot. **Nothing waits**: a
   one-sided own transfer is recorded as the despesa/receita of the side seen, the way Pluggy's
   `one_side_now()` does, and step 4 turns it into the transfer when the other side arrives from
   either channel. Today it waits in "Não gravou sozinho", which is friction. The Conta global
   keeps its own rule.

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
(`newer_than_bank()`).

**Orphan rule (decided: the balance decides, no prompt).** An orphan is a row that Pluggy still
hasn't listed once `bank_refreshed_since()` holds for its date + `OPEN_FINANCE_LATE_POST_DAYS`. A
missing Pluggy line does not mean the money did not move: Pluggy has left real lines out before,
e.g. R$ 41,89 of BTG's August bill. So the **bank's balance** is the arbiter:
- **Remove** the orphan when the account's (or card's) balance difference app − bank equals exactly
  the orphan's effect, so removing it makes the app match the bank. That is the released
  pre-authorisation, or the estimate of a foreign purchase that Pluggy posted with IOF as a
  different amount. Several orphans are tried oldest first, each only while it brings the
  difference to zero exactly. Removal is done like `undo_declined()` and counted in the pull log.
- **Keep it silently** when the balances already agree, or when they can't decide (no balance, or
  other differences), because the bank's balance counts it. The Conferência lists it as
  "confirmado pelo saldo"; nothing goes to Revisar.

Reviewing or categorising a row does not protect it: the category of money that never moved is
meaningless. Only what the owner added and could not get back protects it: a receipt, a share
(A receber), a conversion into a transfer, or "Aconteceu" in the Conferência.

### 3.5 Real duplicates: kept and recognised

- **Kept**: I2 guarantees it. Tests D, E and G become permanent.
- **Recognised (decided: passive, no prompt)**: two lançamentos are marked "2× igual" in the
  Extrato and in Revisar when all of these hold:
  - they are on the same target, with the same cents and the same normalised merchant;
  - they come from **two distinct same-channel observations**;
  - they are ≤ 60 min apart (same day when only Pluggy dates exist).

  It is a quiet badge, with no attention card, nothing to dismiss and no question. A second coffee
  costs no tap, and a merchant's double charge is visible where the owner already looks. If the
  bank reverses it, the refund nets it like any other. The app never decides which one is wrong.

### 3.6 Review only what is a guess (decided)

Today every auto-recorded row waits for "É meu"; only the rebuild skips confident ones. A row
**leaves review by itself** when Pluggy is its source (or confirms its notification) and either:
- its category comes from `CONFIDENT_CATEGORY_SOURCES` (the owner's rule, the merchant table, the
  CNAE); or
- it is a transfer whose two sides are in the app.

Revisar keeps only rows whose category is a broad guess (Pluggy's tree or the default), and rows on
an account without Pluggy (the Flash), because there no second source confirms them. A
notification-only row stays out of Revisar while it is `awaiting_bank`, so it costs no tap before
Pluggy confirms it.

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
per-user `bank_notifications` setting in `GET/PATCH /api/inbox/settings`, **on by default**
(decided). It ships only after Phase 1, so the defaults never meet A or I. Off means today's
behaviour: Flash only. Samsung Wallet stays **Flash card only** (decided): a third channel for bank
cards would only add pairs to get wrong, and the bank app already notifies.

## 5. Investments: Pluggy only

- **Operations**: BUY and SELL come from `open_finance_investments.py` (BTG `/investments`), as
  today. A **typed** operation whose cash account is the Pluggy-fed Corretora is refused (400,
  "A Pluggy traz as operações da corretora"). Assets Pluggy cannot see (crypto) stay typed with
  another cash account or none, the same way the Flash stays typed.
- **`HELD` lines fill themselves where Pluggy has the data (decided).** Fixed income, Tesouro and
  INTEREST wait today because the *operation* lacks the indexer, the rate and the title type.
  Pluggy's *Investment* object, as documented, carries `subtype`, `rate`, `rateType`, `fixedAnnualRate`, `dueDate`
  and `issuer`, but `_save_positions()` keeps only code, name, type, subtype, quantity, value,
  balance and date. Phase 3 plan:
  - save those fields;
  - record the operation with them when they are complete (the redemption lot is the buy of the
    same Pluggy investment id; the coupon's tax start is that title's first buy);
  - hold only what is still missing, pre-filled, one tap to finish, carrying its `op_key`.

  **First step: one real GET** of BTG's `/investments`. Whether MeuPluggy fills these fields for BTG
  is unknown; until then they are assumed missing.
- **Proventos**: StatusInvest-computed ones are forecasts ("em trânsito"). The paid credit on the
  broker statement takes over, as today (bank value and day, `sync_locked`). A typed provento on the
  Corretora is refused like an operation.
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
- One-sided own transfers never wait, and the other side absorbs a recorded despesa/receita
  (§3.2 steps 4 and 7): `_absorb_recorded_pix()` becomes a helper in `services/inbox.py` that
  `_ingest_alone()` and `place()` both call; `auto_record.hold_reason()` no longer holds
  `awaiting_transfer`, except for the Conta global.
- Tests `test_notify_pluggy_identity.py`: matrix A–I as written in §1 (A and B must give one row
  with the **same id**; I must give one transfer in separate uploads), plus:
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

**Phase 3: investments Pluggy-only.**
- First, one real GET of BTG's `/investments` to see which of `rate`, `rateType`, `fixedAnnualRate`,
  `dueDate` and `issuer` MeuPluggy fills.
- Save them in `open_finance_positions` (migration).
- `decide()` records fixed income, Tesouro and INTEREST when they are complete.
- The guard in `POST /api/investments` and the proventos route refuses typing on the Pluggy-fed
  Corretora.
- A still-incomplete `HELD` line opens pre-filled (web and APK).

**Phase 4: quiet review.**
- §3.6: Pluggy-confirmed rows with a confident category, and two-sided transfers, leave review by
  themselves (`services/review.py`, called after `reconcile_recorded()` and `record_item()`).
- §3.5: the "2× igual" badge in the Extrato and Revisar (web `ReviewPanel`/Extrato rows, APK
  `ReviewSection`/Extrato); a `twin` flag on `GET /api/transactions` and the card statement.

**Phase 5: orphans by balance.**
- The sweep after each pull (§3.4), using the Conferência's balance difference (`open_finance_check`).
- Remove only when the balance difference equals the orphan's effect; otherwise "confirmado pelo
  saldo".
- Counted in the pull log.

**Observability (with Phase 1).** `scripts/check_identity.py` runs the I1/I2 check read-only on
the server database and lists any lançamento that two live observations of one channel claim. In
normal operation it must print nothing. Run it after the first week with the gate open.

## 7. Decisions (owner, 2026-11-04: "the best scenario for each, no friction")

The rule for every choice: the owner types nothing, answers nothing and cleans nothing, and the
balances stay right.

| # | Question | Decided | Why it has the least friction |
|---|----------|---------|-------------------------------|
| 1 | Notification rows Pluggy never lists | **The bank's balance decides** (§3.4): removed when the balance proves the money never moved; kept silently when the balance counts it | No prompt either way. A plain "remove after 5 days" would delete real purchases that Pluggy fails to list (it has happened) and leave the owner to retype them |
| 2 | Samsung Wallet | **Flash card only** | Fewer channels, fewer pairs to get wrong; the bank app already notifies and Pluggy brings the rest |
| 3 | Typed investments | **Refused on the Corretora**; `HELD` lines fill themselves from Pluggy's position data, and only what is truly missing waits, pre-filled | Nothing to type for anything Pluggy sees |
| 4 | Twins | **Both kept, quiet "2× igual" badge**, no card | A real second coffee costs no tap; a double charge is visible where the owner already looks |
| 5 | `bank_notifications` default | **On**, shipped after Phase 1 | Works without a setting |
| 6 | Review (found while deciding) | **Only guesses are reviewed** (§3.6) | The Revisar queue shrinks to rows whose category is a broad guess |
| 7 | One-sided own transfer (found while deciding, defect I) | **Never waits**; recorded as the side seen, turned into the transfer by the other side | Nothing in "Não gravou sozinho"; no income/expense split |

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
