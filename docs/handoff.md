# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 (ninth) · Home server live, PC retired as backend

The owner did the setup steps from `DEPLOY.md` and asked to check it, finish the move and retire
the PC. **The home server is now the only backend**: `https://guilhermeserver.tail5084ff.ts.net`.

### What was done
- **Setup checked, read-only**: server tagged `tag:server`, `tailscale serve` HTTPS → 8101, sudoers
  rule, GHCR login (proved by a pull; `/root` is unreadable with the docker-only sudo), `.env` has
  every name in `.env.example`, docker and tailscaled enabled at boot, secrets present.
- **First workflow run** (11b1b63) green end to end: tests, GHCR push, Tailscale SSH deploy.
- **Data imported.** The server had an empty DB (0 users). The PC had a 4 MB leftover `-wal`, so
  a single-file snapshot was made with SQLite's backup API from a read-only connection
  (integrity ok), copied, and imported as in DEPLOY.md. All 26 table counts match the PC (3 users,
  563 operations, 279 proventos, 5 lançamentos). No receipts exist, so no attachment to check.
- **APK** rebuilt against the server (`2026.10.16-11b1b63`, code 208) and installed; the owner
  confirmed the server version works.
- **GHCR package is private**: an anonymous token gets 404 on the manifest.
- **Actions bumped** to Node 24 versions (checkout/setup-python/setup-node v7, setup-buildx v4,
  login v4, build-push v7, tailscale v4; all inputs checked against each `action.yml`). Run
  38995281549 green with no Node 20 warnings; counts unchanged after the redeploy.
- **PC retired**: `tailscale serve reset` (it served `financas.tail5084ff.ts.net` → :5000);
  `start.ps1` refuses to start without `-Local` (`-Tests` unaffected); CLAUDE.md, README and
  DEPLOY.md say so. Old `finance.db` + `-wal`/`-shm` copied (hash-checked) to
  `C:\Users\User\Documents\Financas-backup-pc-20261016\`, plus `finance-imported-to-server.db`.
  Originals not deleted. Nothing autostarts the PC backend (no task, startup entry or Run key).
- **Git over SSH**: `~/.ssh/id_ed25519` (passphrase-protected) is already the key on
  github.com/guneves; the Windows `ssh-agent` service was *Disabled*, so no shell could use it.
  Set `git config --global core.sshCommand C:/Windows/System32/OpenSSH/ssh.exe` so every shell's
  git uses the Windows agent. Enabling the service and `ssh-add` need the owner (admin + passphrase).

### What was not done and why
- See the SSH status in the session's final report; if the agent was not set up, pushes still
  fail over SSH. Workaround used this session: `git -c credential.helper= -c
  'credential.helper=!gh auth git-credential' push https://github.com/guneves/Financas.git main`.
- Old PC DB not deleted (owner asked to keep it); `backend\backups\` on the PC left as is.
- Backups still live only on the server's volume disk.
- `finance-guard` not run: no backend code changed (workflow, a PowerShell script, docs).

### Next session
1. Off-server backup copy on a schedule (`next-steps.md`, Home server).
2. Mobile Phase 5's last phone checks (app swiped away + offline), now against the server.
3. After 2026-10-19, check the first run on Ubuntu 26.

### Carried from earlier sessions (still open)
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, now on the server.
- Back up `%USERPROFILE%\.financas-android` (the APK signing key) off this PC.

### Learned
- `adb` showed "unauthorized" with no prompt on the phone; `adb kill-server` + start brought the
  dialog back.
- Git Bash's `/usr/bin/ssh` does not talk to the Windows ssh-agent; `core.sshCommand` pointing at
  `C:/Windows/System32/OpenSSH/ssh.exe` makes git in every shell use it. Plain `ssh` typed in Git
  Bash still uses its own.
- The `gh` token has `workflow` scope, so an HTTPS push via `gh auth git-credential` can change
  workflow files; it lacks `read:packages`, so package visibility is checked anonymously instead.
- With `sudo` limited to `/usr/bin/docker`, read root-only files or the volume through a throwaway
  container (`docker run --rm -v financas_data:/data:ro ...`).
