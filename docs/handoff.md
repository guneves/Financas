# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-23 · native migration session 7: Início and the bell

Cloud session, branch `claude/wizardly-faraday-cbx3mb` (from `main` at `c137844`, PR #36 merged),
PR #37 to `main`. Briefing by `session-scout`, found by `subagent_type`, no fallback. Confirmed
first that `main` had `GET /api/home`, `GET /api/attention` and `rules/OutboxPending.kt`.
The builder (`native-screen-builder`) was cut off once by a usage limit and resumed from its
transcript; nothing was lost.

### Done
- **Native Início and the bell** (step 3, native-level 4 → 5): `ui/home/`, `ui/charts/`, the
  rules ports, privacy mirrored both ways, the web Início tab opening native. Details in
  `docs/done-tasks.md` (session 7 note) and `mobile-docs/native/screens/03-inicio.md`.
- **CI**: `android-check.yml` run 39959748862 on `cfb68e2` **green** (JVM tests + debug APK),
  checked from here. `npm test` 175 (was 160), both vite builds (normal and android) pass.
  pytest not run: no backend change.
- **Parity review**: no blockers; two majors and four minors fixed in one round (`779d1e3`),
  then re-verified by a second reviewer pass.
- **Comparing native and web**: `mobile/inicio-snapshot.py` (stdlib, GETs only) prints Início's
  numbers from the server with the screen's labels; the steps are in `03-inicio.md`, "Comparing
  native and web". Tried against a local server on a scratch database.
- Docs: `03-inicio.md` (Status, Endpoints/Data/Client rules rewritten for the session-6
  endpoints), the native README's status table (steps 1–2 now say merged), next-steps, done-tasks.

### Not done, and why
- **The four history panels** (Despesas por categoria, Ritmo de gastos, the invoice projection,
  Parcelamentos abertos) are not native: they need `home-panels.md`'s endpoints. A row opens the
  web Início for them (`/inicio?web=1`).
- **Reviewer's minor 6**: toggling the eye natively and then following a link can show the web's
  values for a moment before the web reads the new mode on resume. Not a one-liner; next-steps.
- **Aprovar's writes** still use the read client's 45 s timeout (Início's moved to `writeApi`).
- **No phone check**: sessions cannot install an APK. The owner runs the spec's Acceptance.
- Carried, still open: B2; the owner's phone check of steps 1–2; native 401 handling in the shell
  (Início's "Entrar novamente" opens the web login); grouped Tesouro delete not atomic; the web
  `createEntry()` duplicate after a killed tab; the sharing form refusing "12,5"; pytest red
  21:00–midnight local; `done-tasks.md` has no row for the Aprovar session (PR #33).

### Decisions made here (worth checking)
- **Native scope = what the server serves.** The history panels stay on the web rather than being
  ported as client rules over the whole history, which the native conventions forbid without tests
  and which `home-panels.md` will replace anyway.
- **Dismissals are per store**: native and web keep separate lists of dismissed cards (same keys).
  The bell lists everything on both, so nothing can be hidden for good.
- **With values hidden, no red** on a negative account chip or the Evolução badge (the web shows
  the colour and so leaks the sign). Native-only, deliberate.
- **A stored route survives process death** for 2 minutes (`takePendingRoute()`), read once by the
  web at start.

### Questions for the owner
0. **B2**: should the plan's "spent" leave out a despesa typed in a Corretora account, as Início's
   "Saiu" does (one rule)? It overlaps question 1.
1. Corretora accounts in "+ Novo", the pay-invoice sheet and autopay?
2. Should the Extrato show a transfer to the Corretora as aporte/resgate, as Início does?
3. A débito purchase in Pendentes: Corrigir reopens it as Despesa. Should it?
4. Installments 48 (client) vs 72 (server); description required or optional?
5. "Despesas por categoria" on Início groups by name: should it group by id? (`home-panels.md`)
6. Privacy mode across the other screens?
7. A bank field on cards?
8. `/api/credit-cards` cached under two keys (partly gone since session 6).
9. New: should native and web share one dismissed-cards list?

### Next session
1. If the owner's phone check of PR #37 finds something, fix it on that branch before the merge.
2. Otherwise `home-panels.md` (so Início, web and native, stops downloading the history and the
   four panels can go native), or step 4 (Extrato/Cartões, with paging §5).

### Learned
- **`android-check.yml`'s path filter skips a push that touches only web files** (`charts.jsx`);
  dispatch it by hand (`workflow_dispatch`) when the last commit must be checked.
- **A native page restored after process death has no WebView behind it**: `emitNavigate` goes
  nowhere. Anything that leaves native must also work from a cold `MainActivity`.
- `pkill -f` on a pattern in the same command line kills the calling shell (exit 144) — again.
