# Notifications + Pluggy: one movement, one row

> Design, 2026-11-04. Owner's request: integrate phone notifications with Pluggy with **no overlap and
> no duplicates**; when a real purchase really happens twice, the app must **recognize both**;
> **investments are Pluggy-only**, and notifications deliver only **transfers to and from BTG
> Investimentos**. The owner's decisions are in §7 (least friction). **Built** in Phases 1–5
> (2026-11-04/05, PRs #67 and #68) and verified in session 5 (2026-11-05). §1–§7 are the design as
> decided; §8 says what was really built, every deviation and why. CLAUDE.md holds the rules as they
> are now.

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
| R | Only the BTG Investimentos app notifies R$ 500 in; the app guesses the origin "BTG conta corrente"; Pluggy then shows it left **Itaú** | 1 row, but **the origin stays BTG conta corrente**: Itaú +500 and BTG conta corrente −500 wrong |

So the engine already keeps twins apart and pairs across sources in either order. **A** is the only
duplicate, and the default settings make it likely: pending rows have come in by default since 052,
cards always bring them, and a reviewed row is the normal state after a day of use.

**R** happens because `open_finance_fits_item()` accepts the Itaú row for the transfer: its origin
was only a guess. Then `reconcile_recorded()` only *links* any `TRANSFER`, so the guessed side is
never corrected. The fix: on an untouched recorded transfer whose side was guessed (`guessed`, not
`edited`), the bank's account replaces the guessed one on that side.

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

The near match (§3.7) only pairs leftovers, and only when the pair is unique, so it never changes
these counts.

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

### 3.1 Windows (existing constants, plus two new rules: succession and near amount)

| Pair | Same movement when |
|------|--------------------|
| bank app ↔ Samsung Wallet | same cents, compatible card, ≤ `NOTIFY_WINDOW_MS` (10 min), one to one, bank wins |
| notification ↔ Pluggy | same cents, or `rounded_up()` on BB; installment ↔ total on cards; same target per mapping; Pluggy date within notification date −1…+1 (`OPEN_FINANCE_PAIR_DAYS`) for any state, and +2…+5 (`OPEN_FINANCE_LATE_POST_DAYS`) for an already recorded one |
| notification ↔ Pluggy, **near amount** (**new**, §3.7) | only after the exact pass, only purchases, same target, same merchant, the **only** leftover on each side; amount within ±10% (international) or ±30% (domestic); same date window as above, except international: up to `LATE_POSTING_DAYS` (35) after the notification |
| Pluggy ↔ Pluggy (succession, **new**) | same Pluggy account and direction; same cents (or rounded up), or a near amount with the same merchant when it is the only candidate (a tip, a pre-authorisation that settles); predecessor missing from this pull, date ±3 days |
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
5b. **Pluggy has it with another amount (new, §3.7).** A purchase with no exact partner tries the
   near-amount rule against Pluggy-recorded rows with a free `NOTIFY_BANK` slot. If it fits, it
   joins that row (no new row; the merchant name may improve the description).
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
3b. **Near-amount pass (new, §3.7).** Steps 1–3 run for every row of the pull first, so all exact
   pairs are settled. Only then do the purchases still without a partner try the near-amount rule
   against notification rows with a free `PLUGGY` slot. A row that fits joins that movement, and
   Pluggy's amount wins. Only what is left after this pass goes to step 4, so a near pair is never
   recorded twice, not even for a moment.
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
  pre-authorisation that never posted. A purchase that posted with another amount is caught earlier,
  by the near match (§3.7), unless it was ambiguous. Several orphans are tried oldest first, each only while it brings the
  difference to zero exactly. Removal is done like `undo_declined()` and counted in the pull log.
- **Keep it silently** when the balances already agree, or when they can't decide (no balance, or
  other differences), because the bank's balance counts it. This includes an international
  purchase still "em processamento", which the bank has already taken from the balance (the
  Claude case, §3.7). The Conferência's difference is **bank − app**
  (`account["balance"] - app_balance`), so removing an expense orphan of X fixes a difference of
  +X. The Conferência lists it as
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

### 3.7 Same purchase, different amount (decided, near match)

The exact rule misses a purchase whose notified amount differs from the one the bank posts:
- an international purchase, where the bank notifies an estimate in reais and posts the converted
  amount, often with IOF;
- a tip or a pre-authorisation that settles for another value (hotel, car rental, some restaurants);
- a foreign-currency notification on a reais card.

Without a fix, both rows live until the orphan rule (§3.4) removes the notified one, up to 5 days
after the bank refreshes. BB's rounding (`rounded_up()`) is the one near amount already handled; this
generalises it, with stricter conditions because the difference can be larger.

**When a notification and a Pluggy row are the same purchase despite the amount.** All must hold:
1. **Leftovers only.** The exact pass found no partner for either one, over the whole pull and over
   every pending notification. So two identical purchases, which pair exactly, never reach this rule.
2. **Purchases only.** Card credit or debit purchases (`CREDIT_PURCHASE`, `DEBIT_PURCHASE`,
   `PURCHASE`). A Pix, a transfer, a refund or an invoice payment has an exact amount by nature, so
   it never near-matches.
3. **Same target and direction**, as the mapping says; same date window as the exact rule, except
   for international purchases: up to `LATE_POSTING_DAYS` (35) days after the notification. An
   international purchase stays "em processamento" at the bank, already taken from the balance,
   and Pluggy lists it only when the bank posts it, sometimes weeks later. That was the owner's
   Claude charge on 2026-11-04: R$ 110 gone from the balance, no line in Pluggy, and the Conferência
   said "Movimentos conferem" beside a R$ 110 difference.
4. **Same merchant.** The notification's merchant and Pluggy's `merchant_name` or description agree:
   a shared normalised word of 4+ letters, or the same CNPJ-based name (050). A notification
   without a merchant never near-matches.
5. **Amount band.** ±10% when either side is international: the notification text says
   "internacional"/"exterior"/a foreign symbol (new `international` flag from the parser), or
   Pluggy converted it (`amountInAccountCurrency`; the original currency is stored, new column).
   ±30% otherwise (tips). Both are config values, to tune on real rows.
6. **Unique on both sides.** Exactly one candidate each way on that target in the window. With
   two notifications or two bank lines that could fit, no near pair is made; the normal path and
   the orphan rule decide. This is what keeps twins and different purchases at the same merchant
   apart.

**What happens then.**
- The two are one movement, and **the bank's amount wins**. The row keeps its id, so a receipt,
  share or review stays attached. Date and target follow `reconcile_recorded()` as for an exact
  pair.
- The bank's amount wins even when the owner reviewed or re-categorised the row: "É meu" and a
  category say nothing about the amount.
- Only an **amount the owner typed** stands. Then Pluggy only links, and the Conferência shows the
  difference. This needs a per-field check on the snapshot ("amount changed by the owner") instead
  of today's all-or-nothing `notification_untouched()`.
- **Why a wrong near pair is harmless.** Say a notified R$ 30 at a supermarket meets a bank line of
  R$ 34 from another purchase at the same place, while the real R$ 30 has not posted yet. The row
  becomes R$ 34; when the R$ 30 posts, it finds no free notification and becomes its own row. The
  ledger ends equal to the bank's lines, so only a description could be on the wrong row.
- **Reverse order** (Pluggy first, notification later): §3.2 step 5b, the same conditions. The
  notification joins and adds nothing.

**The Claude case, end to end, once the phases are built:**
1. The bank app notifies "Compra internacional … R$ 110,00 CLAUDE.AI". The row is recorded at once,
   so the app balance equals the bank's, which already took it.
2. While Pluggy lists nothing, the orphan rule keeps the row, because the balance counts it, and
   the Conferência shows it as "confirmado pelo saldo".
3. When the bank posts it (days later, R$ 110 or another amount), the exact or near match makes it
   the same row, and the bank's amount wins.
4. Without a notification (phone off), only the balance difference shows it. The text "em
   processamento no banco" (main, 2026-11-04) is the right answer there.

**A foreign-currency notification** on a reais account or card is recorded at once in reais at the
day's PTAX, marked as an estimate, instead of waiting in "Não gravou sozinho" (`hold_reason()`
returns `foreign_currency` today). It is international by definition, so Pluggy's posting replaces
the estimate through this rule. The Conta global (USD) keeps its own rules.

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

**Phase 1: engine invariants (server only; no visible change while the gate is closed).** Run as
two sessions: 1a (claims, succession, R) and 1b (absorb, nothing waits, near match). The prompts
are in `docs/prompts/notify-pluggy/`.
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
- A guessed side of an untouched recorded transfer is replaced by the account Pluggy shows (fixes
  R): in `reconcile_recorded()`, before the "a transfer only links" rule.
- Near match (§3.7): a second pass at the end of each pull, after the exact pairing and before
  `record_pending()`, plus step 5b for a late notification. Helpers `merchant_agrees()` and
  `near_amount()` live in `services/inbox.py`. A migration adds `original_currency` to
  `open_finance_transactions`. A per-field snapshot check ("amount typed by the owner") is added.
  `auto_record.hold_reason()` records a foreign-currency notification at PTAX instead of holding
  it. Succession accepts a near amount under the same conditions.
- APK parser (ships with Phase 2): an `international` flag from the notification text.
- Tests `test_notify_pluggy_identity.py`: matrix A–I as written in §1 (A and B must give one row
  with the **same id**; I must give one transfer in separate uploads), then the near-match cases:
  - **J**, international: notified R$ 52,30 "internacional" → bank R$ 55,10 → one row of R$ 55,10;
  - **K**, tip: notified R$ 100 → bank R$ 112 → one row, R$ 112;
  - **L**, Pluggy first: bank R$ 55,10, then the notification of R$ 52,30 → still one row;
  - **M**, ambiguous: two notifications at one merchant (R$ 30 and R$ 40) and one bank line of
    R$ 34 → no near pair;
  - **N**, Pix: a Pix of R$ 100 and a bank Pix of R$ 105 never near-match;
  - **O**, the owner typed the amount: the row keeps it, and the Conferência shows the difference;
  - **P**, pending → posted: pending R$ 100 → posted R$ 112 under a new id → same row, R$ 112;
  - **Q**, USD notification: recorded at PTAX at once; Pluggy's posting replaces the estimate;
  - **R**, guessed origin: only BTG Investimentos notifies R$ 500 in, then Pluggy shows Itaú →
    Corretora → one transfer **Itaú → Corretora**.

  Plus:
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
| 8 | Same purchase, different amount (owner, 2026-11-04: "add the fix") | **Near match** (§3.7): exact pass first; then purchases only, same merchant, unique on both sides, ±10% international / ±30% domestic; the bank's amount wins; a foreign-currency notice is recorded at PTAX | No double row for days; nothing to delete; an amount the owner typed is never overwritten |

## 8. What was built (verified 2026-11-05)

Each phase followed its prompt in `docs/prompts/notify-pluggy/`; the rules as built are in CLAUDE.md
("Notifications are fast, Pluggy is the record", "Auto-record → reconcile → review", "The inbox
engine"). Tests: `test_notify_pluggy_identity.py` (matrix A–S, regressions, interleaving, one world
with A–S), `test_notify_pluggy_fuzz.py` (200 generated worlds), `test_notify_pluggy_plans.py`,
`test_notification_policy.py`, `test_quiet_review.py`, `test_twins.py`, `test_open_finance_orphans.py`,
`test_open_finance_fixed_income.py`.

### 8.1 Deviations from §1–§7, with the reason

| Where | Design said | Built | Why |
|-------|-------------|-------|-----|
| §3.3 step 0 | compute *missing*, then vanish what nobody took over | the same, but `vanish_missing()` used to run **before** ingest; now the missing rows stay live during the batch and `vanish_rows()` runs after it | succession needs the old row to hand over; the price is that a not-succeeded missing row still occupies its item's Pluggy slot during that one batch (not seen in 200 generated worlds) |
| §3.3 step 2 | "its `PLUGGY` slot must be free" | one free Pluggy slot **per side** of a transfer | a transfer has an OUT and an IN Pluggy row |
| §3.2 step 4 / §6 | the absorbed side's item has exactly one side source | at most **one observation per channel** on that side, all movements (Phase 4); a notice that joined an item Pluggy recorded has no snapshot and doesn't decide (session 5) | a despesa notified *and* confirmed by Pluggy is still one side; without this the own transfer split into despesa + receita |
| §3.4 orphans | "the account's (or card's) balance" | **bank accounts only**; cards are list-only | a card's balance mixes the used limit, pending holds and BB's rounding |
| §3.4 orphans | runs after the pull | runs **last**, after `record_bank_payments()`, `mark_bank_investments()` and the `last_sync_at` stamp, and only when `bank_refreshed_since(date + 5 d)` holds for **every** active connection | the stamp makes this pull count as read; one stale connection must not let a row go |
| §3.4 wording | "app − bank equals the orphan's effect" (first bullet) | bank − app, the Conferência's own `balance_difference()`; an expense orphan of X fixes +X, an income −X | the second paragraph of §3.4 already said bank − app; one formula, extracted, used by the screen and the sweep |
| §3.6 / Phase 4 | "untouched" | snapshot equality only, everywhere; "É meu" is not a touch | otherwise clearing review would silence the bank's later corrections; consequence: a row the owner only reviewed is redone by the bank (date, card) and removed by a Flash decline or a vanish |
| §4 investment words | Tesouro, fundo, ordem, ... | whole words over `normalized()`: aplicação, resgate, CDB, LCI, LCA, **tesouro direto**, **fundo de investimento**, **ordem de compra/venda**, provento, dividendo, JCP; applied to Pix/TED and the brokerage app, **never** to a card purchase's merchant | "FUNDO DE QUINTAL BAR" and "TESOURO DO MAR RESTAURANTE" are restaurants; a Pix to a person named "Resgate" is ignored, and Pluggy still brings it |
| §4 / APK | invoice-payment texts ignored | the APK drops "fatura" + pago/paga/pagamento/quitada **before** `kindOf()` | "Pagamento da fatura aprovado" matched the purchase regex |
| §5 / Phase 3 | first, one real GET of BTG `/investments` | not done (production data is off-limits); `scripts/position_fields.py` lists which keys MeuPluggy fills, for the owner to run; Pluggy's `rate`/`fixedAnnualRate` are assumed to be percent (the docs); outside `CDI_PERCENT_RANGE`/`ANNUAL_PERCENT_RANGE` the line is held | never guess a rate; a held line fills itself when the position completes |
| §5 | typed provento on the Corretora refused | refused on the routes only; `proceeds_sync`, `apply_paid_proceeds()` and `open_finance_investments` still write | the server's own writers are the record |
| §3.7 near pass (session 5) | — | `near_notification_items()` starts from the window's SOURCE notifications (`CROSS JOIN`), not from every item | it runs once per new Pluggy purchase; a first pull of 3000 rows went 5.1 s → 12.6 s with Phase 1, and is 6.0 s now |

### 8.2 Bugs found by the verification (session 5), each with its test and fix commit

1. **A late notice of a transfer side Pluggy already completed opened a second transfer**
   (`approved_transfer_awaiting()` treated a side as taken when any channel observed it).
   `TestFuzzRegressions::test_a_late_brokerage_notice_joins_the_transfer_pluggy_completed`.
2. **The near pass scanned every inbox item once per new row** (2.4× slower first pull).
   `test_notify_pluggy_plans.py::test_the_near_pass_costs_the_notifications_not_the_pluggy_items`.
3. **An own transfer split into despesa + receita** when Pluggy recorded the first side and its
   notice joined. `TestFuzzRegressions::test_a_pluggy_side_confirmed_by_its_notice_still_becomes_the_transfer`.

### 8.3 Known limits (not bugs, kept on purpose)

- An account with **no** Pluggy history looks back only `OVERLAP_DAYS` (7), so an international
  purchase posted weeks later with its purchase date isn't seen on a just-connected account. Every
  real account has history from its first pull (30 days); the generator gives each account one old
  line for the same reason.
- A card with a single sandbox-sign purchase learns the sign as the docs' (+) and reads it as a
  refund; real cards have the invoice payment or a majority (`learn_charge_sign()`).
- Card twins (`card_twin_keys()`) read the user's card rows through a bounded subquery; fine at
  this size, the only twin query not driven by an index range.

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
