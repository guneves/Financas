# Deploy

The app runs on a home server (x86_64, reached over Tailscale) as one Docker container:
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
| Address | `https://<server>.<tailnet>.ts.net` (`tailscale serve`, HTTPS 443 → `127.0.0.1:8101`) |
| Volume | `financas_data`, mounted at `/data`: `finance.db`, `backups/`, `attachments/`, `logs/` |

Pulling a new image or recreating the container never touches the volume.

## Updating (the everyday flow)

Push to `main`. `.github/workflows/deploy.yml` then:

1. runs the backend and frontend tests;
2. builds the image for linux/amd64 and pushes it to GHCR as `latest` and `<sha>` (buildx cache);
3. joins the tailnet as `tag:ci`, copies `compose.yaml` to the server (never `.env`) and runs
   `sudo docker compose pull && sudo docker compose up -d` in `/srv/apps/financas`.
4. only when the native app changed: builds the signed APK and publishes it for the phone
   ("Updating the phone", below).

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
    // you, from any of your devices, into the server as <user> (no browser re-check)
    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:server"],     "users": ["<user>"] },
    // the workflow; "check" would wait for a browser login it cannot do
    { "action": "accept", "src": ["tag:ci"],           "dst": ["tag:server"],     "users": ["<user>"] }
  ]
}
```

If the policy still has the default allow-all (`"acls": [{"action": "accept", "src": ["*"], "dst":
["*:*"]}]`), replace it with the two grants above. Otherwise `tag:ci` reaches every device in the
tailnet.

**Order, so access is never lost:**

1. Save the policy above. Nothing is tagged yet, so nothing changes. Check that `ssh
   <user>@<server>` still works from the PC.
2. Tag the server: Machines → <server> → Edit ACL tags → `tag:server`. Check ssh again from
   the PC right away. If it fails, remove the tag. Safety net: OpenSSH also listens on the LAN
   (`0.0.0.0:22`), so `ssh <user>@<LAN IP>` from home does not depend on Tailscale at all.
3. Settings → OAuth clients → new client, scope **Auth Keys: write**, tag `tag:ci`.
4. GitHub → repo → Settings → Secrets and variables → Actions: `TS_OAUTH_CLIENT_ID`,
   `TS_OAUTH_SECRET`.

**Server address.** `deploy.yml` (`SERVER`, `API_BASE`), the Dockerfile's `APP_API_BASE` default,
`deploy.ps1 -Server` and `mobile\build-apk.ps1 -ApiBase` carry the server's Tailscale name in the
code. Moving it into Actions secrets (2026-10-17) broke every deploy while the secrets did not
exist, so it was rolled back; the name is in the git history anyway.

A tagged device's key no longer expires, and the tag does not affect `tailscale serve` or the HTTPS
name.

### 2. On the server

```bash
# Passwordless sudo for docker: the workflow cannot type a password.
echo '<user> ALL=(root) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/90-docker-deploy
sudo chmod 440 /etc/sudoers.d/90-docker-deploy
sudo visudo -c                         # must end with "parsed OK"

# GHCR is private: a classic token with read:packages only.
sudo docker login ghcr.io -u guneves

# HTTPS for the phone and the browser.
sudo tailscale serve --bg 8101
```

Anyone who logs in as `<user>` can then run docker as root, which is effectively root on the
server. That is the trade accepted here. The rule deliberately has no `SETENV`.

`/srv/apps/financas/.env` (from `.env.example`, `chmod 600`): `APP_PORT=8101`, `JWT_SECRET`
(`openssl rand -hex 32`, changing it logs every device out), `BRAPI_TOKEN`, and — for the bank
statement through Open Finance — `PLUGGY_CLIENT_ID` / `PLUGGY_CLIENT_SECRET` (blank: nothing is
read from Pluggy; the other `PLUGGY_*` settings are in `backend/.env.example`). Edit it on the
server only. No script or workflow ever writes it.

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
ssh <user>@<server> "mkdir -p /tmp/financas-import"
scp backend\finance.db <user>@<server>:/tmp/financas-import/
scp -r backend\attachments <user>@<server>:/tmp/financas-import/
ssh <user>@<server> "sudo docker run --rm --user 0 --entrypoint sh -v financas_data:/data -v /tmp/financas-import:/import ghcr.io/guneves/financas-app:latest -c 'rm -f /data/finance.db-wal /data/finance.db-shm && cp -a /import/. /data/ && chown -R 10001:10001 /data' && rm -rf /tmp/financas-import"
ssh <user>@<server> "cd /srv/apps/financas && sudo docker compose up -d && sudo docker compose logs --tail 30"
```

The copy uses the app's own image (uid 10001 is the user the app runs as). On the server,
`curl http://localhost:8101/api/health` should answer `"status":"ok"`.

The APK has its API address baked in at build time. `mobile/build-apk.ps1` defaults to the server's
address, so rebuild and install it once.

Screen and APK updates after that: "Updating the phone", below.

## Updating the phone

The phone updates itself in two ways. Both come from pushing to `main`, and neither reinstalls by
USB or loses data.

### Screens (the everyday case): the bundle

The image carries the APK's screens (`frontend/dist-android`, built with `APP_API_BASE`) and
serves them at `GET /api/app-bundle`. Its `bundle.json` holds the version (a content hash) and
`native_level`, the **minimum** native level those screens need (`frontend/native-level.txt`).
After every deploy the app:

1. asks `/api/app-bundle` when it starts, and again on resume at most every 30 min (Ajustes ›
   Versão do app › **Verificar atualizações** asks right away);
2. downloads the zip only if its level is at or below the APK's, and checks size and SHA-256;
3. opens it on the next start, or right away with **Reiniciar agora**, on trial: if the screen
   does not call `ready()` within 30 s, or the app is killed twice before that, the app goes back
   to the APK's built-in screens and never downloads that version again.

The offline queue is native (SQLite plus WorkManager), so changing screens never touches a pending
lançamento.

**Rolling back screens:** roll back the image (`.\deploy.ps1 -Rollback <sha>`, above). The phone
sees a different version and goes back to it at its next check, or to the built-in screens if that
is what the old image serves. On the phone itself, Ajustes › Versão do app › "Voltar à versão do
APK" drops the downloaded screen at once.

### Native code: a new APK from CI

When a push changes `frontend/android/`, `frontend/native-level.txt` or
`frontend/capacitor.config.json` (or the workflow is run by hand with **apk** ticked), the `apk`
job runs alongside build and deploy, after the tests, in the `android-release` environment (main only):

1. builds the screens for the APK (the same content hash as the image's bundle) and `cap sync`;
2. decodes `ANDROID_KEYSTORE_BASE64` into `$RUNNER_TEMP`, builds `assembleRelease` with
   `versionCode = 10000 + run number`, and deletes the key in an `always()` step. The passwords
   reach gradle only as masked environment variables (`FINANCAS_KEYSTORE_*`, read by
   `app/build.gradle`);
3. refuses the APK unless its certificate SHA-256 equals `mobile/release-cert-sha256.txt`, the
   key the phone's app was signed with. Another key would not install over it;
4. copies `financas-<code>.apk`, then `version.json`, to `/srv/apps/financas/apk/` on the server
   (Tailscale SSH, like the deploy), keeping the last three APKs.

`tailscale serve` publishes that folder at `https://<server>.<tailnet>.ts.net/apk/`, on
the tailnet only. Nothing goes to GitHub Releases or workflow artifacts.

The app reads `/apk/version.json` with the bundle check. When the published `version_code` is
higher than the installed one, it shows **Nova versão disponível** at the top of every screen and
in Ajustes. The banner says the update is needed when the server's screens need a higher native
level than the APK has. Tapping **Instalar** downloads the APK, checks its size, SHA-256, package
and versionCode, and opens Android's installer. The first time, Android asks for "Instalar apps
desconhecidos" for Finanças: the app opens that screen, and the download starts by itself when the
owner comes back. The installer replaces the app in place, so the queue, the login and the cache
stay. The new APK drops downloaded screens and starts on its own.

When to bump `native-level.txt`: in the same commit as any Java/plugin/Capacitor change the screens
call (CLAUDE.md). A native change the screens do not depend on (a Java bug fix) still produces a new
APK, with no bump.

**Rolling back the APK:** Android never installs a lower versionCode over a higher one without
uninstalling, which deletes the offline queue. So an APK rollback goes forward: `git revert` the
native commit and push. CI builds the old code with a new, higher versionCode, and the phone offers
it like any update. While it builds, the previous `financas-<code>.apk` files are still in the
folder, but they cannot be installed over a newer one.

**Local builds:** `.\mobile\build-apk.ps1` still builds and installs over USB with the same key. Its
default versionCode (the commit count) is below CI's, so over a CI-installed app pass
`-VersionCode` higher than the installed one. The next CI APK must then be higher again.

### One-time server setup for `/apk`

```bash
ssh -t <user>@<server> "mkdir -p /srv/apps/financas/apk && sudo tailscale serve --bg --set-path /apk /srv/apps/financas/apk && tailscale serve status"
```

`/` keeps proxying to the container on 8101. `/apk` is served by tailscaled straight from the
folder, independent of the image.

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
