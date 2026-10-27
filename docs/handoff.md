# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 · Prompt for bringing Pluggy (Open Finance) back

Cloud session, branch `claude/confident-keller-439tz2` from `main` at `de353ed`. Docs only.

### Done
- `docs/prompts/pluggy-open-finance.md`: a cold-start prompt to implement Pluggy again as a source
  for Aprovar (connect on the web, map Pluggy accounts to accounts/cards, pull sync since the
  server is tailnet-only, dedup by Pluggy transaction id, installments/refunds/transfers rules,
  read-only balance check, phases and tests). Listed under "Open decisions" in `next-steps.md`.

### Not done, and why
- No code: the owner asked for the prompt only. Access is settled: the owner has Pluggy, free for
  one CPF (theirs), which fits a single-user app; the prompt says so.
- The previous session's open items (below) still stand: the phone check of the 2026-10-25 work,
  the "+" inside Investimentos, web Início on `/api/home/panels`, `CORS_ORIGINS=https://localhost`.

### Next session
1. If `android-check.yml` is red on `main`, fix it first; then the owner's phone check.
2. Otherwise: the web Início onto `/api/home/panels`, the desktop redesign plan, or implement
   Pluggy from the prompt.

---

