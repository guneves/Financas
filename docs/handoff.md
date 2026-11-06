# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-06 · Docs cleanup

Branch: **`claude/clean-docs`**, from `main` at `8090745`. The owner: "clean all .mds in this project, delete
docs
otifications-pluggy-design.md and docs
o-vpn-access.md", then "merge when done".

**Done**
- Deleted `docs/notifications-pluggy-design.md`, `docs/no-vpn-access.md`, the whole `docs/prompts/` folder (the
  notify-pluggy session prompts: all five sessions are merged) and `mobile-docs/native/screens/02-aprovar.md`
  (the screen is gone on web and APK).
- Comments in backend, web and APK code no longer cite the design (`design §…`); CLAUDE.md likewise.
- `docs/next-steps.md` (925 → ~790 lines): the notifications + Pluggy section is now only the owner's open
  checks plus the verification's known limits (moved from the design's §8.3). Removed items settled by later
  decisions: Aprovar's ambiguous target, the 044/045 first-deploy steps (Gravar sozinho, "Ignorar avisos"),
  waiting one-sided transfers, "a different amount is a second movement" (near match exists), fixed income
  always HELD (Phase 3), the mapping screen, brokerage operations from notifications.
- `DEPLOY.md` › Open Finance and the native specs (`00-shell`, `11-ajustes`, `desktop.md`) describe Revisar and
  the "Avisos dos bancos" brake instead of Aprovar/Gravar sozinho; dangling links to `migration-order.md`,
  `native-app.md`, `steps-to-production.md`, `findings.md` and `docs/prompts/global-account-usd.md` removed.

**Not done, and why**
- Migrations 054–056 still name the design doc in their first comment: migrations are append-only.
- `docs/done-tasks.md` is history: old file names in it (`findings.md`, `06-verify-and-fix.md`, …) stay.
- The native screen specs still carry port-era notes about the WebView (removed 2026-10-25); they are
  history-heavy and were not rewritten line by line.
- The removed design held the rationale (probe A–R, deviations table, references); it is in git history
  (`git show 8090745:docs/notifications-pluggy-design.md`).

**Next**: the owner checks at the top of `docs/next-steps.md`.
