# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 (tenth) · Final setup check, HTTPS remote, reboot test

The owner asked for a read-only check of the whole setup, then for a few follow-ups.
**Production is the home server**: `https://guilhermeserver.tail5084ff.ts.net`.

### What was done
- **Setup check, read-only, all green**: container healthy with `restart: unless-stopped`;
  `/api/health` 200 over HTTPS; data counts match the import (3 users, 563 operations,
  279 proventos, 5 lançamentos; integrity ok); docker, containerd and tailscaled enabled; serve
  config 443 → `127.0.0.1:8101`; lid switch `ignore`, sleep/suspend/hibernate/hybrid-sleep
  masked; disk 1% used; no errors in the logs; latest run (38995965415) green with no Node 20
  warnings; running image's `org.opencontainers.image.revision` = main's SHA; GHCR private
  (anonymous 404); nothing on the PC runs or autostarts the old backend; PC serve reset; PC DB
  backup present.
- **`origin` is HTTPS now** (`https://github.com/guneves/Financas.git`) with `gh auth setup-git`
  as the credential helper, so a plain `git fetch` / `git push` works. No SSH, no ssh-agent.
- **Reboot test passed**: the owner ran `sudo reboot`; about 40 s after boot the container was up
  with restart count 0, `tailscale serve` was back, and `/api/health` answered 200 once the
  healthcheck passed (a 502 for the first few seconds while gunicorn boots is normal).
- **Docs**: stale "restart `:5000`" / "rebuild the APK" items removed from `next-steps.md` (the
  server runs the latest code); the daily encrypted rclone backup and the Ubuntu 26 run check
  written as open items; the APK signing key marked as backed up off the PC
  (`mobile-docs/steps-to-production.md`, owner confirmed).

### What was not done and why
- **Off-server backup**: the owner will set up rclone (gdrive + crypt, systemd timer, 30 days,
  tested restore) themselves; the plan is in `next-steps.md`.
- Old PC `finance.db*` not deleted (owner keeps it for now).
- `finance-guard` not run: docs and git config only, no backend code.
- `.claude/agents/app-bug-hunter.md` was untracked in the tree when this session started and is not
  this session's; left uncommitted.

### Next session
1. After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
2. Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
3. The rclone backup, if the owner wants help with it.

### Carried from earlier sessions (still open)
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, now on the server.

### Learned
- `sudo` on the server covers only `/usr/bin/docker` passwordless, so a reboot (or anything else)
  needs the owner's password in an interactive `ssh -t`.
- With `sudo` limited to docker, read root-only files or the volume through a throwaway container
  (`docker run --rm -v financas_data:/data:ro ...`).
- The `gh` token has `workflow` scope (pushes may touch workflow files) but no `read:packages`, so
  GHCR visibility is checked anonymously.
