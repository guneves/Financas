# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-16 (eighth) · Docker deploy to the home server

The owner asked to move the app to their home server (`guilhermeserver`, Ubuntu x86_64, over
Tailscale) as Docker images only: no source or Git on the server, redeploys driven by GitHub
Actions. The plan changed twice in the session (git pull + build on server → images copied from
the PC → GHCR); only the GHCR shape is committed.

### What was done
- **`Dockerfile`** (two stages: Node 24 builds `frontend/dist`, Python 3.14-slim runs gunicorn,
  **1 worker × 8 threads** because boot work runs at import and the caches are in memory).
  `TZ=America/Sao_Paulo` (+ tzdata), because `local_today()` is `datetime.now()`. Data paths are
  set to `/data` by `ENV`; the app runs as uid/gid 10001. `.dockerignore` keeps data, `.env`,
  tests and the Android project out.
- **`compose.yaml`**: `ghcr.io/guneves/financas-app:latest`, port `127.0.0.1:${APP_PORT}:5000`
  (only `tailscale serve` reaches it), volume `financas_data` at `/data`, healthcheck on
  `/api/health`. `compose.build.yaml` adds `build:` for local runs.
- **`.github/workflows/deploy.yml`**: on push to `main`, tests (pytest + node) → buildx push to GHCR
  (`latest` + full SHA, gha cache) → `tailscale/github-action` as `tag:ci` → copies `compose.yaml`
  and runs `sudo docker compose pull && up -d` over Tailscale SSH. Passes actionlint.
- **`deploy.ps1`**: the server half by hand (compose.yaml sync, pull, up), `-Rollback <sha>`
  (pull the SHA, retag `latest`), `-CreateOnly` for the first deploy before importing data.
- **`DEPLOY.md`**: tailnet policy and the order to apply it, server setup, first deploy with the
  data import, rollback.
- **`mobile/build-apk.ps1`** now defaults to `https://guilhermeserver.tail5084ff.ts.net`.
- **Server**: `/srv/apps/financas/.env` exists (`APP_PORT=8101`, a JWT secret generated there, the
  brapi token copied from `backend/.env`, mode 600). The server's ssh host key was added to this
  PC's `known_hosts`; key login as `guilherme` works.
- **Verified locally**: image builds; `docker save`/`load` round trip; `compose.yaml` run like the
  server reports healthy; login, writes, yfinance quotes, SPA fallback and the `https://localhost`
  CORS preflight work; the documented data import works end to end. Backend and frontend tests
  pass in Linux containers (python:3.14-slim, node:24-slim).

### What was not done and why
- **Nothing is deployed and nothing is pushed.** Pushing to `main` runs the workflow, which needs
  the owner's steps first (DEPLOY.md, "First-time setup"): the tailnet policy, tagging the server
  `tag:server`, the OAuth client and `TS_OAUTH_*` secrets, the sudoers rule, `docker login ghcr.io`
  on the server and `tailscale serve --bg 8101`. All need the owner's accounts or sudo password.
- **The PC's data is not on the server yet.** Import order is in DEPLOY.md: `.\deploy.ps1
  -CreateOnly`, stop the PC backend, copy `finance.db` + `attachments`, start.
- **APK not rebuilt** against the server address. That waits for the server to answer on HTTPS.
- **The workflow has never run.** It is linted, not exercised; the first push is its test.
- `finance-guard` was not run: no backend code changed.

### Next session
1. Owner's setup steps above. Then push, watch the workflow, do the first deploy with the data
   import, `tailscale serve`, rebuild and install the APK, and check the phone end to end.
2. After that, the PC stops being the server: `start.ps1 -Built` is no longer daily use.

### Carried from earlier sessions (still open)
- Restart/walk-through of the Extrato → Investimentos view and Proventos → Atualizar (now on the
  server once deployed).
- Back up `%USERPROFILE%\.financas-android` off this PC.
- Repeat the offline "+ Novo" test with the APK swiped away.

### Learned
- `python:3.14-slim` + `yfinance` installs from wheels with no compiler; the image is ~100 MB
  compressed.
- Docker Desktop's containerd store adds a provenance attestation to every build. Build with
  `--provenance=false` so `docker save`/a registry carries just the image.
- `useradd --system` picks its own gid; give the group an explicit `--gid` when files are chowned
  by number.
- Tailscale SSH: tagging a device removes it from `autogroup:self`, the only target of the default
  ssh rule. Add an explicit `autogroup:member → tag:server` rule *before* tagging.
- The server's OpenSSH also listens on the LAN (`0.0.0.0:22`), a fallback if the tailnet policy
  locks ssh out.
