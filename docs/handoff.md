# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-25 · native Aprovar goes back to Extrato

Cloud session, branch `ccr-d9a20479-tevyk2` from `main` at `3281070` (session E merged).

### Done
- The owner asked that Aprovar go back to Extrato. In the APK, Aprovar's back arrow and the
  system back now open Extrato (`openTab`, so Início stays below), whether Aprovar came from the
  Lançamentos tab, Início's attention card or the notification. Rule: `ShellNav.backTarget()`
  (`ShellNavTest.aprovarGoesBackToExtrato`); the handler sits inside the INBOX destination so
  Aprovar's own sheets still close first. `mobile-docs/native/architecture.md` updated.

### Not done, and why
- Not built here (no Android SDK in the container): `android-check.yml` on the push is the first
  compile. No phone check yet (the owner's).
- Everything in session E's "Not done" still stands (phone check of the shell, the "+" inside
  Investimentos, web Início on `/api/home/panels`, `CORS_ORIGINS=https://localhost`).

### Next session
1. If `android-check.yml` is red on this branch, fix it first.
2. Otherwise session E's next: the owner's phone check, then the web Início onto
   `/api/home/panels` or the desktop redesign plan.

---
