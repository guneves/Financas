# Handoff

> Only the most recent session, at most ~25 lines (shape in `CLAUDE.md` › Ending a session). Older entries
> are in git history.

## Session — 2026-11-26 · APK pull to refresh; CLAUDE.md made static, on `main`

**Done:**
- Início's pull to refresh: the spinner now belongs to the pull (a cancelled resume read used to end it at
  once), and the pull calls the new `POST /api/open-finance/refresh` (`sync_fresh_items()`, GET only), re-reading
  if something came in. Backend `TestPullToRefresh` (5), APK `HomeRepositoryTest` (5), 603 JVM tests green.
  Checked on the emulator against a scratch backend (before the server became the rule).
- Owner: "testing on the server is the norm" → CLAUDE.md › Testing on the server. Docs cut to what a session
  needs: CLAUDE.md static, 76 → 9 KB (rules verbatim in `docs/domain-rules.md`); next-steps 75 → 2 KB;
  backlog (one line per open item) 73 → 9 KB; done-tasks 178 → 15 KB; `docs/audit.md` and the 17 native
  screen specs (~300 KB) deleted (their "Desktop" sections are in `desktop.md`); memory 19 → 6 KB. Full
  texts: `git show a79c731:<path>`.
- Another session removed ROADMAP.md and docs/automation-prompt.md (1c366dd); code comments still say
  "automation-prompt N.N" as phase labels.

**Not done, and why:**
- Not pushed or deployed, so not checked on the server or the phone: pushing deploys production, waiting for the owner's OK.
- SSH to the server was refused by the auto-mode permission check this session; the server-first rule needs
  an allow rule for `ssh guilherme@guilhermeserver` in the owner's settings.
- Backend tests run: only `test_open_finance_tick.py`, `test_route_map.py`, `test_architecture.py`.

**Next:** with the owner's OK, push `main`; after the deploy, check `POST /api/open-finance/refresh` in the
server log and ask the owner to pull Início on the phone (next-steps' first item).
