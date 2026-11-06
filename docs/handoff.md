# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-06 · Remote access: a login in front of the app on Tailscale Funnel

Branch: **`feat/funnel-auth`**, from `main` at `9b6a1ff`. The owner's plan (design + implementation prompt,
from a design session the same day): browsers through Google (oauth2-proxy), the APK through a device key,
both behind Caddy on :8443, published by Funnel; 443 stays tailnet-only.

**Done** (five commits, in the plan's order)
1. *Dev on one origin*: flask-cors, `CORS_ORIGINS` and the `Access-Control-Expose-Headers` lines removed;
   Vite proxies `/api` to `127.0.0.1:5000`; the dev API base is `''`; `start.ps1` waits on
   `127.0.0.1:5173`; `test_no_cors.py`.
2. *SPA*: `lib/proxySession.js` (`isProxyAuthResponse`, `shouldReload`) with a node test; `apiFetch`/`apiBlob`
   fetch with `redirect: 'manual'`, throw `ApiProxyAuthError` (its own class, `proxyAuth: true`), reload after
   1 s at most once per 30 s (sessionStorage), never clear the JWT; `queuesCreation()` and `outcomeOf`
   `proxyAuth → retry` in `outboxRules.js`.
3. *Compose*: `oauth2-proxy` and `proxy` (Caddy) as in the prompt; `PROXY_PORT`/`OAUTH2_ALLOWED_EMAILS` in
   `.env.example`; `oauth2.env`/`proxy.env` ignored. Checked on the PC (Docker 29.6): every expected status
   matched (401 + `X-Proxy-Auth`, 302, 200 with the key for `/api/health` and `/apk/version.json`, 401 for
   wrong/empty/missing key, 502 without `oauth2.env` while 8101 answers); the `expression` matcher with
   `{env.PROXY_DEVICE_KEY}` works as written.
4. *APK*: base `…ts.net:8443` (build.gradle, deploy.yml, build-apk.ps1); `ServerAddress.migrate()` rewrites a
   stored 443 base on start (`Session.migrateBaseUrl`, from `AppGraph` init); the key is in `Session`,
   Keystore-encrypted, and `Session.clear()` keeps it; `DeviceKey` (header, `isProxyAuthRequired`, `apply`)
   used by `OutboxSender`, `DetectionSender`, `ApkUpdater` (manifest and download) and an OkHttp
   `DeviceKeyInterceptor` (ApiClient, AuthRepository). A proxy 401 is `ApiException.ProxyAuth`, **a subclass
   of `Network`** (reads show the cache, "+ Novo" queues, no `when` had to change), calls `onProxyAuth` →
   `AppGraph.deviceKeyNeeded` → the shell's `DeviceKeyDialog`; "Agora não" silences it until a new key is
   saved. The outbox stops with `"key"` and the worker retries (`OutboxWorker.retries()`); the detection
   sender returns `"key"` and retries. Login screen field "Chave de acesso remoto" (prefilled, saved before
   the login; `LoginResult.KeyNeeded`); Ajustes › Perfil › "Trocar chave de acesso". Saving a key flushes
   the queue and the detections.
5. *Docs*: README "Remote access", DEPLOY.md (rollout section, address table, `/apk`, no-webhooks wording),
   CLAUDE.md (deploy paragraph, outbox line), `frontend/.env.example` (empty `VITE_API_BASE_URL`).

**Checks**: pytest in 4 chunks, all green (see the PR); `npm test` 243 pass; APK `testDebugUnitTest` 596
pass + `assembleDebug`; `uvx ruff check backend`: 406 findings, all pre-existing (the touched files have
the same 3 I001 as on `main`), reported, not fixed.

**Not done, and why**
- **The rollout** (DEPLOY.md "Remote access", steps 1–10): it needs the owner's Google OAuth client and an
  approval at every `sudo`/Tailscale step; the order matters — `tailscale serve --https=8443` **before** the
  merge, and the phone installs the new APK **over the VPN from 443** (the old APK knows only 443).
- No real-device check of the APK's key UI, and the web reload only unit-tested.

**Next**: the rollout in `docs/next-steps.md` (top item).

**Lessons**
- Bash heredocs collapse `\\` (a `"\\s+"` became `"\s+"` in Java); write edit scripts with the Write tool.
- `frontend/.env.local` on the PC holds only old Supabase keys; it doesn't set `VITE_API_BASE_URL`, so dev
  really is same-origin now.
- Without `oauth2.env`, oauth2-proxy restart-loops; `/api` then answers 502 (not 401) through Caddy. The key
  path still works.
