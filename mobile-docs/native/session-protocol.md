# Native migration — the session protocol

Every prompt in `session-prompts.md` says "follow the protocol". This is the part that was repeated
in every prompt. A prompt adds only its screens, its order and its decisions.

**Token budget first.** Each subagent starts cold and re-reads CLAUDE.md, the specs and the code
the main session already has, so a session with a scout, porters, five builders, a CI watcher and
reviewers paid for the same reading many times over. This protocol does the work in the main
session and keeps subagents to one review per session.

## Start

1. Read `docs/handoff.md` and only the native section of `docs/next-steps.md` yourself — no
   `session-scout` (that is for a cold start with no prompt; the prompt is the briefing).
2. Read `mobile-docs/native/conventions.md` and the prompt's specs. Open `architecture.md` or the
   README only when a question needs them. Read code by search and line range, not whole files.
3. Check the prompt's **Needs** with `git log origin/main` / `git ls-tree`. A need still in an open
   PR whose last `android-check.yml` is green: **stack** — cut this branch from that PR's branch,
   open the PR against it, say so in the handoff. Neither: stop and tell the owner.
4. A **Decisions** line still reading `DECIDE:` is not decided: keep the web's current behaviour
   there and list it in the handoff's questions.

## Building

- **The main session builds every screen itself**, one after another, on its own branch. No
  `native-screen-builder`, no `rule-porter`, no worktrees: the shared files (`variables.gradle`,
  `app/build.gradle`, the manifest, `strings.xml`, the `NavHost`, `NativeScreens`' route list,
  `Tokens.kt`) then have one owner automatically, and nothing is merged.
- A rule a screen needs is ported inline, with the node test cases copied into a JVM test. A rule
  with no node test gets one first, in a `lib/` module.
- Commit and push after each screen. Check CI with
  `gh run watch $(gh run list -w android-check.yml -b <branch> -L 1 --json databaseId -q '.[0].databaseId') --exit-status`
  in the background (Bash `run_in_background`), not with `android-ci-watcher`. On a failure read
  only the failing step: `gh run view <id> --log-failed | tail -80`. A push that touches only web
  files skips the path filter: `gh workflow run android-check.yml --ref <branch>`.
- Never paste whole specs, logs or files into the conversation; read the lines you need.

## Review — one subagent, once

- After the last screen is green, **one** `native-parity-reviewer` run (with `model: "sonnet"`)
  over all of this session's screens, with the diff range (`origin/main..HEAD`) and the spec paths
  in the prompt so it does not rediscover them. Ask for blockers and majors only, at most ~15 lines.
- Fix them in the main session. No second review round; say in the handoff what was fixed.

## Rules every screen follows

- Money is never `Double`/`Float` (`BigDecimal` or cents), rounded as `rounded_money()` does.
- Writes go through `writeApi` (no timeout retry); only creations with a `client_id` are queued
  offline. Anything else is refused offline with a message, never retried after a timeout.
- Privacy mode masks every money value. User-facing text in Portuguese, as the web says it.
- No money rule changes. A rule is an endpoint or a port with the same tests (`rules-port.md`).
- Bump `frontend/native-level.txt` in the commit where the web first calls a new plugin method.
- CLAUDE.md's conventions hold (archive, never delete; `user_id` everywhere; append-only
  migrations). Never push to `main`, never merge a PR.

## Close

1. Each spec's `Status` row, the README status table, `next-steps.md` (remove what was done), a
   row per finished item in `done-tasks.md`, and a new `docs/handoff.md` entry replacing the old
   one: done, not done and why, decisions made, questions for the owner. Keep it short.
2. Commit, push, open the PR (to `main` or the stacked base) with one phone checklist per screen:
   the spec's Acceptance list, online and airplane mode, light and dark.
