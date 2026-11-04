# Notifications + Pluggy: session prompts

Design: `docs/notifications-pluggy-design.md`. Every session reads `00-common.md`, then its own
prompt files, then the design.

## The flow: five sessions, one PR, one merge

Sessions 1–4 build. Each starts from the previous session's branch and pushes its own; none opens
a PR. Session 5 verifies **everything**, fixes what it finds and opens the **only** pull request.
You merge that one. Nothing reaches `main` (and so the server) before it is verified.

| # | Session | Prompt files | Starts from |
|---|---------|--------------|-------------|
| 1 | Engine: per-channel claims, Pluggy succession, guessed transfer side, absorb, nothing waits, near match, PTAX | `01a-claims-succession.md`, `01b-absorb-near-match.md` | `main` |
| 2 | Open the gate: bank notifications on (server + APK) | `02-open-the-gate.md` | session 1's branch |
| 3 | Investments only from Pluggy | `03-investments-pluggy-only.md` | session 2's branch |
| 4 | Review only guesses, "2× igual", orphans decided by the balance | `04-quiet-review-twins.md`, `05-orphans-by-balance.md` | session 3's branch |
| 5 | Final verification and fixes, all phases; opens the PR | `06-verify-and-fix.md` | session 4's branch |

Each session ends by telling you its branch name. Paste it into the next session's prompt where
it says `<BRANCH FROM SESSION N>`.

**After you merge session 5's PR:**
1. install the new APK;
2. an Itaú purchase shows up in seconds and is still one row after the next pull;
3. a Pix to BTG Investimentos gives one transfer;
4. run `scripts/position_fields.py` once;
5. run `scripts/check_identity.py` weekly; it must print nothing.

## What to send to each session

### Session 1: engine

```text
You are session 1 of 5 of the "Notifications + Pluggy" plan in this repository. You build Phase 1 (parts 1a and 1b), starting from main.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (the chain, setup, hard rules, how to finish)
2. docs/prompts/notify-pluggy/01a-claims-succession.md
3. docs/prompts/notify-pluggy/01b-absorb-near-match.md
4. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Order: build 01a completely (claims scoped per channel; Pluggy succession, so a PENDING row that posts under a new id keeps the same lançamento; the guessed side of a recorded transfer corrected by Pluggy; the identity invariant helper and scripts/check_identity.py), run the full suite and commit. Then build 01b (one absorb helper for own transfers from either channel; a one-sided own transfer never waits, except the Corretora and the Conta global; the near match for the same purchase with a different amount, including an international purchase "em processamento" like my Claude R$ 110 charge, which is test S; a foreign-currency notification recorded at PTAX), run the full suite and commit. Server only.

Non-negotiables: never push to main, never merge, no pull request; never read or write production data; migrations numbered only after merging origin/main, then the full suite again; "untouched" is decided by the snapshot, never by needs_review; keep the signature notification_wanted(detection); every rule gets a test.

When everything is green: update CLAUDE.md and the docs as the session process says (including the handoff section "For the final verification"), and push your branch. Reply to me in Portuguese with your branch name, what changed and the tests added.
```

### Session 2: open the gate

```text
You are session 2 of 5 of the "Notifications + Pluggy" plan in this repository. You build Phase 2 (open the gate for Itaú, BB, BTG Banking and BTG Investimentos notifications) on top of session 1's branch: <BRANCH FROM SESSION 1>.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (start with "The chain": merge session 1's branch, then origin/main, then run the full suite)
2. docs/prompts/notify-pluggy/02-open-the-gate.md (this phase; run its prerequisite checks first)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Scope:
- the server policy table: the BTG Investimentos app delivers only Pix/TED transfers; Samsung Wallet stays Flash-only; investment words never block a card purchase's merchant;
- the bank_notifications switch, on by default, leaving no trace when off;
- the APK allow-list plus the manifest <queries>, the parser filters (invoice payments and brokerage orders are never movements) and the international flag, with JVM tests;
- the Ajustes switch on web and APK;
- the CLAUDE.md rewrite of "Open Finance is the only banking source".

Non-negotiables: never push to main, never merge, no pull request; never touch production data; notification_wanted(detection) keeps its signature and stays pure; the container has no Android SDK, so push and read the android-check workflow result with the GitHub MCP actions tools, and a red android-check means not done; every rule gets a test.

When the backend suite, npm test and android-check are green: update the docs (including "For the final verification" in the handoff) and push your branch. Reply to me in Portuguese with your branch name, what changed and the tests added.
```

### Session 3: investments

```text
You are session 3 of 5 of the "Notifications + Pluggy" plan in this repository. You build Phase 3 (investments come only from Pluggy) on top of session 2's branch: <BRANCH FROM SESSION 2>.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (start with "The chain": merge session 2's branch, then origin/main, then run the full suite)
2. docs/prompts/notify-pluggy/03-investments-pluggy-only.md (this phase)
3. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Scope:
- store the whole Pluggy position (raw JSON) and add scripts/position_fields.py (read-only, key names only, never imports app);
- record held fixed income, Tesouro and INTEREST only from exact data; hold anything that cannot be mapped exactly, and never guess a rate;
- refuse typed operations, redemptions and proventos whose cash account is the Pluggy-fed Corretora, except when completing a HELD operation of this user by its op_key;
- guard only the HTTP routes, never proceeds_sync, apply_paid_proceeds() or open_finance_investments;
- the "Lançar" from a HELD line and the cash default, on web and APK.

Non-negotiables: never push to main, never merge, no pull request; never touch production data; migrations numbered after merging session 2's branch and origin/main, then the full suite again; MANUAL_ONLY_OFF_PLUGGY is off in conftest, so turn it on per test with monkeypatch at services.manual_entries; every rule gets a test.

When everything is green: update CLAUDE.md and the docs (including "For the final verification" in the handoff) and push your branch. Reply to me in Portuguese with your branch name, what changed and the tests added.
```

### Session 4: review, twins and orphans

```text
You are session 4 of 5 of the "Notifications + Pluggy" plan in this repository. You build Phase 4 and then Phase 5 on top of session 3's branch: <BRANCH FROM SESSION 3>.

Read these files completely before writing any code, and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (start with "The chain": merge session 3's branch, then origin/main, then run the full suite)
2. docs/prompts/notify-pluggy/04-quiet-review-twins.md
3. docs/prompts/notify-pluggy/05-orphans-by-balance.md
4. docs/notifications-pluggy-design.md (section 7 holds my decisions, which are final)

Phase 4 first, and inside it do "The trap to avoid first" before anything else:
- redefine "untouched" as snapshot equality everywhere, and refresh the snapshots in the same transaction whenever the server changes a recorded row;
- prove with tests that the bank's later changes (amount, vanish, the other side of a transfer, the near match) still apply after review was cleared automatically;
- only then clear review for Pluggy-confirmed rows with a confident category (rule, merchant, CNAE) and for two-sided transfers;
- add the twin flag on the server and the neutral "2× igual" badge on web and APK, with no attention card.

Commit.

Then Phase 5, a sweep after each pull for mapped BANK accounts only (cards stay list-only):
- use the Conferência's own balance difference (bank − app), extracted into a shared helper, never a second formula;
- remove an orphan only when the difference equals exactly what removing it fixes (+X for an expense, −X for an income), and only after the bank refreshed past date + 5 days;
- keep as "confirmado pelo saldo" what the balance already counts, including an international purchase "em processamento";
- never remove a row with a receipt, a share, "Aconteceu", an amount I typed, or a converted transfer.

Non-negotiables: never push to main, never merge, no pull request; never touch production data; the Flash and the Conta global keep their review; no tolerance and no subset search, so when in doubt the row stays; every rule gets a test.

When the backend suite, npm test and android-check are green: update CLAUDE.md and the docs (including "For the final verification" in the handoff) and push your branch. Reply to me in Portuguese with your branch name, what changed and the tests added.
```

### Session 5: final verification of everything

```text
You are session 5 of 5 of the "Notifications + Pluggy" plan in this repository: the final verification of all phases (1a, 1b, 2, 3, 4 and 5). Sessions 1–4 built them in a chain of branches; nothing is merged into main yet. The whole chain is on session 4's branch: <BRANCH FROM SESSION 4>.

Read these files completely and follow them exactly:
1. docs/prompts/notify-pluggy/00-common.md (start with "The chain": merge session 4's branch, then origin/main, then run the full suite)
2. docs/prompts/notify-pluggy/06-verify-and-fix.md (your job, including its "Final pass")
3. every phase prompt in docs/prompts/notify-pluggy/ (01a, 01b, 02, 03, 04, 05): what each phase was supposed to build
4. docs/notifications-pluggy-design.md

Do this:
- read each session's "For the final verification" section in the handoff history and start with the risky parts;
- go through every checklist in 06-verify-and-fix.md section 3, line by line;
- build the seeded scenario generator of section 4 over the whole series: twins, own transfers notified in separate uploads, pending→posted with new ids, near amounts, international purchases still "em processamento" like my Claude R$ 110 charge, detections through the real notification policy, automatic review clears, orphans. Assert one row per real movement, every account balance equal to the generated truth, and assert_identity();
- add the interleaving test and the EXPLAIN QUERY PLAN checks of section 5;
- write one end-to-end test with cases A–S;
- read CLAUDE.md top to bottom for contradicting rules;
- update docs/notifications-pluggy-design.md with what was really built.

Every bug gets a failing test first, then the smallest fix, one commit per bug. Do not add features and do not change any decision in section 7 of the design; if a fix needs a design change, stop and tell me.

Non-negotiables: never push to main and never merge; never touch production data; the backend suite, npm test and android-check must all be green at the end.

When done: push your branch and open the single pull request of the chain to main, titled "Notifications + Pluggy — Phases 1–5 (verified)", with the body 06-verify-and-fix.md describes. Do not merge it. Reply to me in Portuguese with the PR link, every bug found (severity, test, fix commit), what you checked and found fine, and the checks only I can do after the merge (the new APK on the phone, position_fields.py, the weekly check_identity.py).
```
