# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (evening) · APK on every deploy, and the phone goes native

Cloud session. The owner asked how to make the APK "native", then: (1) "preciso apenas poder
baixar o app a cada deploy automaticamente"; (2) "uso praticamente apenas o celular, mas quero
manter o desktop, e gostaria que as interfaces fossem diferentes". Chosen (AskUserQuestion): the
phone native in Kotlin + Compose, screen by screen; the desktop redesigned for a wide screen. No
briefing subagent: the docs were read directly.

### Done
- **`apk` job on every deploy** (`deploy.yml`): the change-detection step, the `native` output,
  `fetch-depth: 0` and the `apk` input of `workflow_dispatch` are gone. DEPLOY.md, CLAUDE.md and
  `steps-to-production.md` updated.
- **Native plan**: `mobile-docs/native-app.md` (decisions, step 0, step 1 "+ Novo" in detail, the
  order, the desktop redesign, verification). It supersedes the "No native rewrite" row of
  `steps-to-production.md`. CLAUDE.md has the convention; `next-steps.md` the open steps.
- **Step 0**: Kotlin 2.3.20 + Compose compiler plugin in `android/build.gradle`, Compose BOM
  (`composeBomVersion` in `variables.gradle`), Material 3, `activity-compose`, `compose = true`,
  Kotlin JVM target 21 in `app/build.gradle`. `ui/theme/Tokens.kt`, `Theme.kt` (`FinancasTheme`,
  `Palette`, `LocalPalette`, `ShellPrefs`), `TokensTest.kt` (reads `index.css`). `ShellPlugin`
  stores the theme in `ShellPrefs`. Tokens cross-checked against the CSS with a Python script here.
- **The migration's documentation** (owner: "faça toda a documentação para o novo projeto, sugira
  prompts com agents"): `mobile-docs/native/` (README, architecture, conventions, build-and-test,
  migration-order, rules-port, findings, desktop, agents with prompts) and 16 specs in `screens/`
  from `_template.md`. The specs were written by four parallel `general-purpose` agents (shell +
  "+ Novo" + Início; Lançamentos; Planejar + Ajustes; Investimentos), each reading the React code
  and the backend; their cross-cutting findings are in `findings.md`. Six agent definitions in
  `.claude/agents/` (listed in CLAUDE.md, "The native migration's agents"); they were discovered by
  the harness in this same session.
- **`android-check.yml`**: debug APK + `testDebugUnitTest` on branch pushes that touch Android.
  First run green on 22338aa (run 39824479133: `testDebugUnitTest assembleDebug`, BUILD SUCCESSFUL in
  1m 55s, TokensTest included).

### Not done, and why
- **No native screen yet.** Step 1 ("+ Novo") is next, detailed in `native-app.md`. No
  `native-level.txt` bump: nothing the web screens call changed.
- **This container cannot build an APK**: `dl.google.com` (Android SDK and Google's Maven;
  `maven.google.com` redirects there) is blocked by the environment's network policy. Told the
  owner how to allow it. Until then, compile on the branch through `android-check.yml` and read
  the run with the GitHub MCP tools (`actions_list`, `get_job_logs`).
- Desktop redesign not started (plan in `mobile-docs/native/desktop.md`; a per-screen plan goes in
  next-steps first).
- **Nothing in `findings.md` was fixed**: possible bugs (Metas edit after the target month,
  Recorrentes' account, transfer destination in the Extrato, refund cents, UTC "pago em", grouped
  Tesouro delete), inconsistencies and stale texts are listed for triage in `next-steps.md`.
- The specs were checked for structure (every one has the template's ten sections) and "+ Novo"
  was read in full; the others were not re-verified line by line — a builder agent reads the React
  code anyway and fixes the spec where it disagrees (`native-screen-builder.md`).
- Plus Jakarta Sans is not in the native theme (needs a `.ttf` in `res/font`).
- The phone check of "APK on every deploy" waits for the merge to main (next-steps).
- Carried, still open in `next-steps.md`: the card débito/Flash walk-through, no Flash capture,
  Flash package unconfirmed, brapi quota with hourly quotes, the older items.

### From the parallel session merged before this one (bug hunt by fuzzing, PR #29)
Merged into this branch from `main`; its own entry is in git history (`git log -p docs/handoff.md`).
It fixed every 500 a fuzz of the API found (`parse_money()`, dates 1900–2199, investment metadata
and caps; `test_input_edges.py`, pytest 1534). Still open from it:
- Rows already stored with such values are not cleaned (none expected in production; the fixes
  only refuse new ones). `next-steps.md`, "Bug hunt by fuzzing".
- Not fuzzed: the frontend (no test runner), the Java parsers/listener, CSV/OFX contents, uploads.
- Proceeds' amounts and corporate-action ratios still have no upper bound (nothing broke).

Learned there (still true):
- With `TESTING = True` Flask re-raises; to see 500s as responses in a scratch test set
  `PROPAGATE_EXCEPTIONS = False` and `TESTING = False` (monkeypatch `app.config`) and hook
  `flask.got_request_exception` for the traceback.
- `/api/health/integrations`, returns and evolution take ~1.5 s each with no network (gov_http's
  retry): a fuzz over them is slow, not hung.
- `pkill -f <pattern>` matches the shell running it when the pattern is in its own command line.
- Linux `strftime("%Y")` does not zero-pad years < 1000, and Decimal's default context (28 digits)
  cannot quantize ≥ 1e26 to cents — both are now guarded, but remember them for new code.

### Next session
Step 1 of `mobile-docs/native/migration-order.md` ("+ Novo"), with the prompt in
`mobile-docs/native/agents.md`, "Step 1". Before step 3, the rule decisions (`rules-port.md`).

### Learned
- `components/charts.jsx`'s `SERIES` is a list of hex literals, not CSS variables as CLAUDE.md's
  "Theme and tokens" says; step 7 must move them into `index.css` before `Tokens.kt`.
- Maven Central rate-limits this container quickly (429 after a few directory listings): don't
  probe versions by listing directories; `kotlin-gradle-plugin` 2.3.20 is dated 2026-03-16.
- Kotlin's JVM target must equal Java's (21, set by Capacitor's generated
  `capacitor.build.gradle`, which must not be edited) or the build fails.
- From earlier sessions, still true: the test DB is one per session (assert on your own user's
  rows); Java's `\s` does not match U+00A0; never name a backend module after a stdlib one.
