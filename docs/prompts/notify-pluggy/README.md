# Notifications + Pluggy: session prompts

Design: `docs/notifications-pluggy-design.md`. Each session reads `00-common.md` and then its own
prompt.

| Order | File | What | Needs merged first |
|-------|------|------|--------------------|
| 1 | `01a-claims-succession.md` | per-channel claims, Pluggy pending → posted under a new id, guessed transfer side (defects A, B, R) | — |
| 2 | `01b-absorb-near-match.md` | own transfers absorb across channels, nothing waits, near match, PTAX (defect I) | 1a |
| 3 | `06-verify-and-fix.md` for "Phase 1" | bug hunt over 1a + 1b | 1a, 1b |
| 4 | `02-open-the-gate.md` | bank notifications on (server + APK) | 1a, 1b |
| 5 | `06-verify-and-fix.md` for "Phase 2" | bug hunt | 2 |
| 6 | `03-investments-pluggy-only.md` | investments only from Pluggy | 2 (to keep migrations in order) |
| 7 | `04-quiet-review-twins.md` | review only guesses; "2× igual" | 1 (2 recommended) |
| 8 | `05-orphans-by-balance.md` | notified rows Pluggy never lists | 1, 2, 4 |
| 9 | `06-verify-and-fix.md` for "final" | full pass | all |

Run `06-verify-and-fix.md` after 3, 4 and 5 too, if you want each checked separately.

**Between sessions**: merge each session's branch into `main` (it deploys) before starting a
session that needs it. If you want to start before merging, tell the new session the previous
branch's name; `00-common.md` explains how to merge it.

## Starting a session (paste into a new session)

Until one phase is merged into `main`, these files only exist on branch
`claude/zealous-edison-2ca8jd`. The first line of each starter makes the session fetch them.

```text
Faça `git fetch origin claude/zealous-edison-2ca8jd` e, se docs/prompts/notify-pluggy/ não existir no seu checkout, `git merge --no-edit origin/claude/zealous-edison-2ca8jd`. Depois leia e siga docs/prompts/notify-pluggy/00-common.md e docs/prompts/notify-pluggy/01a-claims-succession.md.
```

Replace `01a-claims-succession.md` with the phase's file. For verification:

```text
Faça `git fetch origin claude/zealous-edison-2ca8jd` e, se docs/prompts/notify-pluggy/ não existir no seu checkout, `git merge --no-edit origin/claude/zealous-edison-2ca8jd`. Depois leia e siga docs/prompts/notify-pluggy/00-common.md e docs/prompts/notify-pluggy/06-verify-and-fix.md para a Fase 1 (1a + 1b), que está em <main ou nome da branch>.
```
