# Access without the VPN (Tailscale Funnel)

Plan, 2026-11-02. Status: not started.

## Goal and decision

The app becomes reachable from any network without the Tailscale VPN on the phone or PC, through
**Tailscale Funnel**, at no cost. Funnel is turned on **only after the login is hardened**: once it
is public, the app's own login is the only lock.

- **Free**: part of the Tailscale personal plan already in use; no domain, no paid service.
- **Reliable**: runs on Tailscale's relays; no router port, no dependency on the home IP.
- **Same address**: `https://<server>.<tailnet>.ts.net` resolves publicly, so the APK and
  bookmarks don't change.
- **Private**: TLS ends on the home server; Tailscale relays encrypted bytes it can't read.

Rejected:
- Cloudflare Tunnel + Access: needs a domain (paid, or a free eu.org one that takes weeks), and
  Cloudflare terminates TLS, so it reads the traffic.
- Router port forwarding + reverse proxy: opens the home network and depends on the home IP.

## Current state and risks

Today the tailnet is the wall; the login sits behind it. Exposed as is:

| Area | Today | Risk once public |
|---|---|---|
| `POST /api/auth/login` (`routes/auth.py`) | No rate limit, no lockout | Unlimited password guessing |
| Second factor | None | A leaked or guessed password is full access |
| Tokens (`auth.py`) | HS256 JWT, 30 days (`JWT_EXP_DAYS`), no revocation | A stolen token works for a month and can't be cut off |
| Security headers | None (no HSTS, CSP, frame blocking) | Clickjacking, weaker browser protections |
| Client IP | Flask sees `127.0.0.1` behind `tailscale serve` | Any per-IP limit counts everyone as one client |
| `/api/auth/signup` | Closed once a user exists (`ALLOW_SIGNUP`) | Fine; keep `ALLOW_SIGNUP` unset in production |
| `/apk` (served by tailscaled) | Tailnet only | Becomes public: anyone can download the APK |

## Hardening before going public

Each item is a backend change with tests (pytest), plus the web and APK screens where noted.

### 1. Brute-force protection on login
- Count failed logins per username and per client IP in SQLite (new migration, `user_id`/username
  keyed), not in memory, so a restart doesn't reset it.
- After 5 failures in 15 min: refuse with 429 and a `Retry-After`; growing delay after that.
- A successful login clears the username's counter.
- Same response text for "wrong user" and "wrong password".
- Log every failure and lockout through `applog` (never `print()`).
- Tests: lockout, unlock after the window, per-IP limit across usernames, success resets.

### 2. Two-factor login (TOTP)
- New migration: `totp_secret` (encrypted or at least never returned by the API), `totp_enabled_at`,
  and a few one-time recovery codes (hashed).
- Login becomes two steps when TOTP is on: password → short-lived "pending" token → 6-digit code →
  real token. The code step has the same rate limit as the password step.
- Standard RFC 6238 (30 s step, ±1 step tolerance), hand-rolled with `hmac`/`hashlib` like the
  JWT, no new dependency. Works with Google Authenticator, Aegis, etc.
- Ajustes (web) and the APK: turn on (QR code / secret to type, confirm with a code), show recovery
  codes once, turn off (needs a code).
- Tests: valid/invalid/replayed codes, clock skew, recovery code used once, login without the code refused.

### 3. Security headers and real client IP
- `after_request` headers: `Strict-Transport-Security`, `Content-Security-Policy` (self only; the
  font is already local), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`.
- `werkzeug.middleware.proxy_fix.ProxyFix` with `x_for=1`, so the rate limit sees the real IP that
  `tailscale serve`/Funnel forwards.
- Tests: headers on API and frontend responses; `remote_addr` from `X-Forwarded-For`.

### 4. Session control
- Shorter tokens (e.g. 7 days) with silent renewal while the app is in use.
- A per-user `token_version` (migration) inside the JWT: "Sair de todos os dispositivos" in Ajustes
  bumps it and every older token is refused.
- Changing the password bumps it too.
- Tests: old token refused after the bump, renewal keeps the user logged in.

### 5. `/apk` path
Decide one: keep it public (an APK holds no secret: the server still needs the login), or serve
it only on the tailnet and download updates over the VPN. Default: keep it public.

## Turning Funnel on

Only after items 1–4 are deployed to production and checked.

1. Tailscale admin console → Access controls: add the `funnel` node attribute for the server:
   ```json
   "nodeAttrs": [{ "target": ["tag:<server tag>"], "attr": ["funnel"] }]
   ```
2. On the server:
   ```bash
   sudo tailscale funnel --bg 8101
   tailscale funnel status
   ```
   Funnel publishes the existing `serve` config on 443, `/apk` included (item 5).
3. Turning it off at any time: `sudo tailscale funnel --https=443 off` (tailnet access via
   `tailscale serve` keeps working).

Funnel only publishes HTTPS on 443, 8443 or 10000; the app is already on 443.

## What stays the same

- **SSH and deploys**: the server and GitHub Actions keep using Tailscale SSH;
  `.github/workflows/deploy.yml` doesn't change.
- **Container**: still bound to `127.0.0.1:8101`; no router port.
- **APK and web address**: unchanged.
- **Pluggy**: still GET-only pulls from the server; nothing needs to reach the server from Pluggy.
- **Admin access** to the server (SSH from the PC) still needs Tailscale on the PC; daily use doesn't.

## Order of work and checklist

- [ ] 1. Login rate limit + lockout (backend, tests)
- [ ] 3. Security headers + `ProxyFix` (backend, tests); done early because item 1 needs the real IP
- [ ] 2. TOTP: backend + tests, then Ajustes (web), then the APK
- [ ] 4. Shorter tokens, renewal, "Sair de todos os dispositivos"
- [ ] Deploy; turn TOTP on for the owner's account; save the recovery codes offline
- [ ] 5. Decide the `/apk` path
- [ ] Add the `funnel` attribute and run `tailscale funnel --bg 8101`
- [ ] Verify from mobile data with Tailscale off: app loads, login asks for the code, 6 wrong
      passwords give 429, headers present (`curl -I https://<server>.<tailnet>.ts.net`)
- [ ] Update `DEPLOY.md` (Funnel on, how to turn it off) and the "server is tailnet-only" notes in
      `CLAUDE.md`
