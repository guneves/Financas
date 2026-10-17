# Deploy

The app runs on `guilhermeserver` (x86_64, reached over Tailscale) as one Docker container:
gunicorn serving the API and the built frontend on one origin. The server holds no source code and
no Git — `/srv/apps/financas/` contains only `compose.yaml` and `.env`. The image lives in GHCR.

**The server is the only backend** (since 2026-10-16). The first-time setup below is done, the PC's
data was imported, and the APK points at the server. The PC is a development machine now:
`.\start.ps1` refuses to start without `-Local`, the PC's `tailscale serve` was reset, and the old
`backend\finance.db` is a development copy, not the owner's data. The last PC copy of the real data
is in `Documents\Financas-backup-pc-20261016\` (with `finance-imported-to-server.db`, the exact
snapshot imported).

| | |
|---|---|
| Image | `ghcr.io/guneves/financas-app`, tags `latest` and the full commit SHA |
| Host port | **8101**, localhost only (`APP_PORT` in the server's `.env`). Ports on this server: 81xx, one per app. |
| Address | `https://guilhermeserver.tail5084ff.ts.net` (`tailscale serve`, HTTPS 443 → `127.0.0.1:8101`) |
| Volume | `financas_data`, mounted at `/data`: `finance.db`, `backups/`, `attachments/`, `logs/` |

Pulling a new image or recreating the container never touches the volume.

## Updating (the everyday flow)

Push to `main`. `.github/workflows/deploy.yml` then:

1. runs the backend and frontend tests;
2. builds the image for linux/amd64 and pushes it to GHCR as `latest` and `<sha>` (buildx cache);
3. joins the tailnet as `tag:ci`, copies `compose.yaml` to the server (never `.env`) and runs
   `sudo docker compose pull && sudo docker compose up -d` in `/srv/apps/financas`.

Migrations run when the new container boots. A failed test stops the deploy before anything is
pushed. It can also be started by hand from the Actions tab (`workflow_dispatch`).

By hand from the PC, for the server half only (the image must already be in GHCR):

```powershell
.\deploy.ps1                 # copy compose.yaml if changed, pull latest, up -d
.\deploy.ps1 -Rollback <sha> # see "Rolling back"
```

## Rolling back

Pull the image of an earlier commit from GHCR and retag it as `latest`:

```powershell
.\deploy.ps1 -Rollback <full 40-character sha>
```

which runs on the server:

```bash
sudo docker pull ghcr.io/guneves/financas-app:<sha>
sudo docker tag ghcr.io/guneves/financas-app:<sha> ghcr.io/guneves/financas-app:latest
cd /srv/apps/financas && sudo docker compose up -d
```

Every command is `sudo docker ...` with no environment variable, so the sudoers rule (no `SETENV`)
covers it. Don't run `docker compose pull` after a rollback: it brings `latest` back from GHCR. The
next push to `main` moves forward again. A rollback does not undo migrations, so an older image on a
database migrated by a newer one may fail.

## First-time setup

### 1. Tailnet policy (Tailscale admin console → Access controls)

The server gets `tag:server`, the CI runner `tag:ci`. Tagging a device removes it from
`autogroup:self`, which is all the default ssh rule covers, so the policy needs explicit rules for
your own devices first. Merge into the policy:

```jsonc
{
  "tagOwners": {
    "tag:server": ["autogroup:admin"],
    "tag:ci":     ["autogroup:admin"]
  },
  "grants": [
    // your devices (PC, phone) reach everything, the server included (443 for the app, 22 for ssh)
    { "src": ["autogroup:member"], "dst": ["*"],          "ip": ["*"] },
    // the CI runner reaches only the server's ssh
    { "src": ["tag:ci"],           "dst": ["tag:server"], "ip": ["22"] }
  ],
  "ssh": [
    // the default rule, kept
    { "action": "check",  "src": ["autogroup:member"], "dst": ["autogroup:self"], "users": ["autogroup:nonroot", "root"] },
    // you, from any of your devices, into the server as guilherme (no browser re-check)
    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:server"],     "users": ["guilherme"] },
    // the workflow; "check" would wait for a browser login it cannot do
    { "action": "accept", "src": ["tag:ci"],           "dst": ["tag:server"],     "users": ["guilherme"] }
  ]
}
```

If the policy still has the default allow-all (`"acls": [{"action": "accept", "src": ["*"], "dst":
["*:*"]}]`), replace it with the two grants above. Otherwise `tag:ci` reaches every device in the
tailnet.

**Order, so access is never lost:**

1. Save the policy above. Nothing is tagged yet, so nothing changes. Check that `ssh
   guilherme@guilhermeserver` still works from the PC.
2. Tag the server: Machines → guilhermeserver → Edit ACL tags → `tag:server`. Check ssh again from
   the PC right away. If it fails, remove the tag. Safety net: OpenSSH also listens on the LAN
   (`0.0.0.0:22`), so `ssh guilherme@<LAN IP>` from home does not depend on Tailscale at all.
3. Settings → OAuth clients → new client, scope **Auth Keys: write**, tag `tag:ci`.
4. GitHub → repo → Settings → Secrets and variables → Actions: `TS_OAUTH_CLIENT_ID`,
   `TS_OAUTH_SECRET`.

A tagged device's key no longer expires, and the tag does not affect `tailscale serve` or the HTTPS
name.

### 2. On the server

```bash
# Passwordless sudo for docker: the workflow cannot type a password.
echo 'guilherme ALL=(root) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/90-docker-deploy
sudo chmod 440 /etc/sudoers.d/90-docker-deploy
sudo visudo -c                         # must end with "parsed OK"

# GHCR is private: a classic token with read:packages only.
sudo docker login ghcr.io -u guneves

# HTTPS for the phone and the browser.
sudo tailscale serve --bg 8101
```

Anyone who logs in as `guilherme` can then run docker as root, which is effectively root on the
server. That is the trade accepted here. The rule deliberately has no `SETENV`.

`/srv/apps/financas/.env` (from `.env.example`, `chmod 600`): `APP_PORT=8101`, `JWT_SECRET`
(`openssl rand -hex 32`, changing it logs every device out), `BRAPI_TOKEN`. Edit it on the server
only. No script or workflow ever writes it.

### 3. First deploy, with the PC's data

Push to `main` once, or run the workflow by hand, so the image is in GHCR. Then:

```powershell
.\deploy.ps1 -CreateOnly
```

That copies `compose.yaml`, pulls, and creates the volume and the container **without starting
them**. If the workflow already started the container (it creates an empty database), stop it
first with `sudo docker compose stop`. The import below removes the old `-wal`/`-shm` files, so
the copied database is the only one left.

Stop the backend on the PC (Ctrl+C on `start.ps1`) so SQLite folds the `-wal` file into
`finance.db`. If a `-wal` is still there (a backend killed without a clean stop leaves one), copy
a single-file snapshot instead: `sqlite3.connect("file:finance.db?mode=ro", uri=True).backup(dst)`
reads the WAL and leaves the originals alone; that is how the 2026-10-16 import was done. Then:

```powershell
ssh guilherme@guilhermeserver "mkdir -p /tmp/financas-import"
scp backend\finance.db guilherme@guilhermeserver:/tmp/financas-import/
scp -r backend\attachments guilherme@guilhermeserver:/tmp/financas-import/
ssh guilherme@guilhermeserver "sudo docker run --rm --user 0 --entrypoint sh -v financas_data:/data -v /tmp/financas-import:/import ghcr.io/guneves/financas-app:latest -c 'rm -f /data/finance.db-wal /data/finance.db-shm && cp -a /import/. /data/ && chown -R 10001:10001 /data' && rm -rf /tmp/financas-import"
ssh guilherme@guilhermeserver "cd /srv/apps/financas && sudo docker compose up -d && sudo docker compose logs --tail 30"
```

The copy uses the app's own image (uid 10001 is the user the app runs as). On the server,
`curl http://localhost:8101/api/health` should answer `"status":"ok"`.

The APK has its API address baked in at build time. `mobile/build-apk.ps1` defaults to the server's
address, so rebuild and install it once.

The image also carries the APK's screens (`frontend/dist-android`, built with `APP_API_BASE`, the
same address), and the phone downloads them from `/api/app-bundle`: after a deploy the APK picks up
screen changes by itself on its next start. A new APK is needed only when `frontend/native-level.txt`
goes up (`mobile-docs/steps-to-production.md`).

## Building and running on the PC

```powershell
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

This needs a `.env` at the repo root (copy `.env.example`). It uses a volume on the PC, separate from
the server's data and from `backend\finance.db`.

## Useful commands on the server

```bash
cd /srv/apps/financas
sudo docker compose logs -f --tail 100
sudo docker compose restart
sudo docker image ls ghcr.io/guneves/financas-app      # remove old ones with docker image rm
# Copy the backups out of the volume (they share its disk with the database):
sudo docker run --rm --user 0 --entrypoint cp -v financas_data:/data -v "$HOME":/out ghcr.io/guneves/financas-app:latest -r /data/backups /out/
```

Never run `sudo docker compose down -v`. The `-v` flag deletes the volume, and the database with it.
