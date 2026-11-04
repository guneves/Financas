# Notifications + Pluggy: session prompts

Design: `docs/notifications-pluggy-design.md`. Every session reads `00-common.md`, then its own
prompt file, then the design.

## The flow (12 sessions, one at a time)

Every phase is checked by a verification session **before** it reaches `main`. A merge into `main`
deploys to the server, and Phase 1a already changes how real Pluggy pulls are placed.

For each phase:
1. **Phase session**: builds the phase, pushes its branch, opens a PR to `main` and does not merge
   it.
2. **Verify session**: starts from that branch, hunts and fixes bugs, then opens its own PR to
   `main`, which contains the phase plus the fixes.
3. **Owner**: merges the verify PR and closes the phase PR (if GitHub doesn't mark it merged by
   itself). The next phase starts from `main`.

| # | Session | Prompt file | Starts after |
|---|---------|-------------|--------------|
| 1 | Phase 1a: per-channel claims, Pluggy succession, guessed transfer side | `01a-claims-succession.md` | — |
| 2 | Verify 1a | `06-verify-and-fix.md` | session 1's PR is open |
| 3 | Phase 1b: absorb across channels, nothing waits, near match, PTAX | `01b-absorb-near-match.md` | verify-1a PR merged |
| 4 | Verify 1b | `06-verify-and-fix.md` | session 3's PR is open |
| 5 | Phase 2: open the gate (server + APK) | `02-open-the-gate.md` | verify-1b PR merged |
| 6 | Verify 2 | `06-verify-and-fix.md` | session 5's PR is open |
| 7 | Phase 3: investments only from Pluggy | `03-investments-pluggy-only.md` | verify-2 PR merged |
| 8 | Verify 3 | `06-verify-and-fix.md` | session 7's PR is open |
| 9 | Phase 4: review only guesses, "2× igual" | `04-quiet-review-twins.md` | verify-3 PR merged |
| 10 | Verify 4 | `06-verify-and-fix.md` | session 9's PR is open |
| 11 | Phase 5: orphans decided by the bank's balance | `05-orphans-by-balance.md` | verify-4 PR merged |
| 12 | Verify 5 + final pass | `06-verify-and-fix.md` | session 11's PR is open |

After Phase 2 is merged and the phone has the new APK, run `scripts/check_identity.py` on the
server once a week (command in `01a-claims-succession.md`). It must print nothing.

## What to send to each session

Copy one block per new session. Fill in `<...>` in the verify prompts with the branch name the
phase session reported.

### 1. Phase 1a

```text
You are implementing Phase 1a of the "Notifications + Pluggy" plan in this repository.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (setup, hard rules, how to finish)
2. docs/prompts/notify-pluggy/01a-claims-succession.md (this phase)
3. docs/notifications-pluggy-design.md (the design; section 7 holds my decisions, which are final)

Scope: claims scoped per channel, Pluggy succession (a PENDING row that posts under a new id keeps the same lançamento), the guessed side of a recorded transfer corrected by Pluggy (defects A, B and R), the identity invariant helper and scripts/check_identity.py. Server only. Do not start Phase 1b work.

Non-negotiables: never push to main and never merge; never read or write production data; pick a migration number only after merging origin/main, then rerun the full suite on the merged tree; every rule you touch gets a test; keep the signature notification_wanted(detection); existing tests in test_auto_record.py and test_open_finance_auto.py must stay green unchanged.

When everything is green: update CLAUDE.md and the docs as the session process says, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 1a". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added and what I must check.
```

### 2. Verify 1a

```text
You are verifying Phase 1a of the "Notifications + Pluggy" plan in this repository. The work is on branch <PHASE 1a BRANCH> (PR <link or number>), not merged yet.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job)
3. docs/prompts/notify-pluggy/01a-claims-succession.md (what the phase was supposed to build)
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the full suite, go through the "Phase 1a" checklist in 06-verify-and-fix.md line by line, and build the seeded scenario generator, limited to what Phase 1a covers (claims, succession, guessed transfer side). Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features and do not change any decision in section 7 of the design; if a fix needs a design change, stop and tell me.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 1a" (it carries the phase plus your fixes; I will merge it and close the phase PR). Do not merge it. Reply to me in Portuguese with the PR link, each bug found (severity, test, fix commit), what you checked and found fine, and what only I can check.
```

### 3. Phase 1b

```text
You are implementing Phase 1b of the "Notifications + Pluggy" plan in this repository. Phase 1a is already merged into main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/01b-absorb-near-match.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

First run the prerequisite checks at the top of 01b-absorb-near-match.md; if any fails, stop and tell me.

Scope: one absorb helper so the other side of an own transfer turns a recorded expense or income into the transfer from either channel (defect I); a one-sided own transfer never waits (except the Corretora and the Conta global); the near match for the same purchase with a different amount (purchases only, same merchant, unique both ways, ±10% international, ±30% domestic, the bank's amount wins unless I typed the amount; for an international purchase the window reaches LATE_POSTING_DAYS after the notification, because the bank keeps it "em processamento" and Pluggy lists it weeks later — my Claude R$ 110 charge of 2026-11-04 is test S); a foreign-currency notification recorded at PTAX at once. Server only.

Non-negotiables: never push to main and never merge; never touch production data; migrations numbered after merging origin/main, then the full suite again; "untouched" is decided by the snapshot, never by needs_review; the near-match pass runs after the batch ingest and before record_pending(); keep notification_wanted(detection)'s signature; every rule gets a test.

When everything is green: update CLAUDE.md and the docs, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 1b". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added and what I must check.
```

### 4. Verify 1b

```text
You are verifying Phase 1b of the "Notifications + Pluggy" plan in this repository. The work is on branch <PHASE 1b BRANCH> (PR <link or number>), not merged yet; Phase 1a is already on main.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job)
3. docs/prompts/notify-pluggy/01b-absorb-near-match.md (what the phase was supposed to build)
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the full suite, go through the "Phase 1a" and "Phase 1b" checklists in 06-verify-and-fix.md, and build or extend the seeded scenario generator over everything Phase 1 covers: twins, own transfers notified in separate uploads, pending→posted with new ids, near amounts, international purchases. Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features or change section 7 decisions; if a fix needs a design change, stop and tell me.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 1b". Do not merge it. Reply to me in Portuguese with the PR link, each bug (severity, test, fix commit), what you checked and found fine, and what only I can check.
```

### 5. Phase 2

```text
You are implementing Phase 2 of the "Notifications + Pluggy" plan in this repository: opening the gate so Itaú, BB, BTG Banking and BTG Investimentos notifications are recorded. Phases 1a and 1b are already merged into main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/02-open-the-gate.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

First run the prerequisite checks at the top of 02-open-the-gate.md; if any fails, stop and tell me.

Scope: the server policy table (the BTG Investimentos app delivers only Pix/TED transfers; Samsung Wallet stays Flash-only; investment words never block a card purchase's merchant); the bank_notifications switch, on by default, leaving no trace when off; the APK allow-list plus the manifest <queries>, the parser filters (invoice payments and brokerage orders are never movements) and the international flag, with JVM tests; the Ajustes switch on web and APK; and the CLAUDE.md rewrite of "Open Finance is the only banking source".

Non-negotiables: never push to main and never merge; never touch production data; notification_wanted(detection) keeps its signature and stays pure; the container has no Android SDK, so push and read the android-check workflow result with the GitHub MCP actions tools, and a red android-check means not done; every rule gets a test.

When the backend suite, npm test and android-check are green: update the docs, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 2". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added, and the exact phone checks I must do after merging and installing the new APK.
```

### 6. Verify 2

```text
You are verifying Phase 2 of the "Notifications + Pluggy" plan in this repository. The work is on branch <PHASE 2 BRANCH> (PR <link or number>), not merged yet; Phase 1 is already on main.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job)
3. docs/prompts/notify-pluggy/02-open-the-gate.md (what the phase was supposed to build)
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the backend suite, npm test, and android-check on your pushed branch. Go through the "Phase 2" checklist in 06-verify-and-fix.md. Extend the seeded scenario generator so detections go through the real policy, without the any_bank_notifications fixture: a brokerage "ordem de compra" text, an invoice-payment text, Samsung Wallet with a bank card, and the switch off. Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features or change section 7 decisions.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 2". Do not merge it. Reply to me in Portuguese with the PR link, each bug (severity, test, fix commit), what you checked and found fine, and the phone checks only I can do.
```

### 7. Phase 3

```text
You are implementing Phase 3 of the "Notifications + Pluggy" plan in this repository: investments come only from Pluggy. Phases 1 and 2 are already merged into main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/03-investments-pluggy-only.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Scope: store the whole Pluggy position (raw JSON) and add scripts/position_fields.py (read-only, key names only, never imports app); record held fixed income, Tesouro and INTEREST only from exact data, holding anything that cannot be mapped exactly (never guess a rate); refuse typed operations, redemptions and proventos whose cash account is the Pluggy-fed Corretora, except when completing a HELD operation of this user by its op_key; guard only the HTTP routes, never proceeds_sync, apply_paid_proceeds() or open_finance_investments; the "Lançar" from a HELD line and the cash default on web and APK.

Non-negotiables: never push to main and never merge; never touch production data; migrations numbered after merging origin/main, then the full suite again; MANUAL_ONLY_OFF_PLUGGY is off in conftest, so turn it on per test with monkeypatch at services.manual_entries; every rule gets a test.

When everything is green: update CLAUDE.md and the docs, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 3". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added, and the exact position_fields.py command I must run on the server after the merge.
```

### 8. Verify 3

```text
You are verifying Phase 3 of the "Notifications + Pluggy" plan in this repository. The work is on branch <PHASE 3 BRANCH> (PR <link or number>), not merged yet.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job)
3. docs/prompts/notify-pluggy/03-investments-pluggy-only.md (what the phase was supposed to build)
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the full suite and go through the "Phase 3" checklist in 06-verify-and-fix.md. Add tests that try to break the guard: an op_key replayed twice, another user's op_key, a PATCH moving a typed operation onto the Pluggy-fed Corretora, a redemption without a matching buy, and a position with a partially filled raw. Check that no fixed-income rate is ever inferred. Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features or change section 7 decisions.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 3". Do not merge it. Reply to me in Portuguese with the PR link, each bug (severity, test, fix commit), what you checked and found fine, and what only I can check.
```

### 9. Phase 4

```text
You are implementing Phase 4 of the "Notifications + Pluggy" plan in this repository: review only what is a guess, plus a quiet "2× igual" badge for twins. Phases 1–3 are already merged into main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/04-quiet-review-twins.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Do "The trap to avoid first" before anything else. Redefine "untouched" as snapshot equality everywhere, and refresh the snapshots in the same transaction whenever the server changes a recorded row. Then prove with tests that the bank's later changes (amount, vanish, the other side of a transfer, the near match) still apply after review was cleared automatically. Only then clear review for Pluggy-confirmed rows with a confident category (rule, merchant, CNAE) and for two-sided transfers, and add the twin flag on the server and the neutral badge on web and APK. No attention card.

Non-negotiables: never push to main and never merge; never touch production data; the Flash and the Conta global keep their review; the twin query always has user_id and a bounded date range; every rule gets a test.

When the backend suite, npm test and android-check are green: update CLAUDE.md and the docs, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 4". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added and what I must check.
```

### 10. Verify 4

```text
You are verifying Phase 4 of the "Notifications + Pluggy" plan in this repository. The work is on branch <PHASE 4 BRANCH> (PR <link or number>), not merged yet.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job)
3. docs/prompts/notify-pluggy/04-quiet-review-twins.md (what the phase was supposed to build)
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the backend suite, npm test, and android-check on your pushed branch. Go through the "Phase 4" checklist in 06-verify-and-fix.md. Grep every remaining use of needs_review, review.awaiting(), notification_untouched() and untouched(), and prove with a test for each that an automatic review clear no longer stops a later bank correction. Extend the seeded scenario generator with automatic review clears between pulls. Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features or change section 7 decisions.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 4". Do not merge it. Reply to me in Portuguese with the PR link, each bug (severity, test, fix commit), what you checked and found fine, and what only I can check.
```

### 11. Phase 5

```text
You are implementing Phase 5 of the "Notifications + Pluggy" plan in this repository: a notified row that Pluggy never lists is decided by the bank's balance. Phases 1–4 are already merged into main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/05-orphans-by-balance.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Scope: a sweep after each pull, for mapped BANK accounts only (cards stay list-only). It uses the Conferência's own balance difference (bank − app), extracted into a shared helper, never a second formula. It removes an orphan only when the difference equals exactly what removing it fixes (+X for an expense, −X for an income), and only after the bank refreshed past date + 5 days. It keeps, as "confirmado pelo saldo", what the balance already counts (including an international purchase "em processamento"). It never removes a row with a receipt, a share, "Aconteceu", an amount I typed, or a converted transfer. Count the removals in the pull log; show the label on web and APK.

Non-negotiables: never push to main and never merge; never touch production data; no tolerance and no subset search, so when in doubt the row stays; a stale connection removes nothing; every rule gets a test.

When everything is green: update CLAUDE.md and the docs, push your branch, and open a pull request to main titled "Notifications + Pluggy — Phase 5". Do not merge it. Reply to me in Portuguese with the PR link and branch name, what changed, the tests added and what I must check.
```

### 12. Verify 5 and the final pass

```text
You are verifying Phase 5 and doing the final pass of the "Notifications + Pluggy" plan in this repository. Phase 5 is on branch <PHASE 5 BRANCH> (PR <link or number>), not merged yet; Phases 1–4 are on main.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job, including its "Final pass" section)
3. docs/prompts/notify-pluggy/05-orphans-by-balance.md
4. docs/notifications-pluggy-design.md

Fetch that branch and merge it into your session branch, then merge origin/main. Run the backend suite, npm test, and android-check on your pushed branch. Go through the "Phase 5" checklist, with a test that pins the sign of the balance difference. Then do the final pass:
- run the seeded scenario generator over the whole series (twins, own transfers, pending→posted with new ids, near amounts, international purchases still "em processamento", automatic review clears, orphans) and assert one row per real movement, every account balance equal to the generated truth, and assert_identity();
- write one end-to-end test with cases A–R and J–Q in one user's world;
- check EXPLAIN QUERY PLAN for every new query;
- read CLAUDE.md top to bottom for rules that contradict each other;
- update docs/notifications-pluggy-design.md with what was really built and every deviation.

Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features or change section 7 decisions.

When done: push your branch and open a pull request to main titled "Notifications + Pluggy — verify Phase 5 and final pass". Do not merge it. Reply to me in Portuguese with the PR link, each bug (severity, test, fix commit), what you checked and found fine, and the checks only I can do on the server and the phone (including the weekly scripts/check_identity.py).
```
