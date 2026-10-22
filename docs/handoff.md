# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (evening) · A new APK on every deploy

Cloud session. The owner first asked how to make the APK "native"; after the options (targeted
native pieces, React Native, Kotlin + Compose) the real need came out: "preciso apenas poder baixar
o app a cada deploy automaticamente". No briefing subagent: a short, workflow-only task, docs read
directly.

### Done
- **`apk` job on every deploy.** `.github/workflows/deploy.yml`: the "Did the native app change?"
  step, the `test` job's `native` output, its `fetch-depth: 0` and the `apk` input of
  `workflow_dispatch` are gone; `apk` keeps `needs: test` with no `if:`. Every push to `main` (and
  every manual run) builds, signs, checks and publishes `financas-<10000 + run>.apk` and
  `version.json`, so the app offers "Nova versão disponível" after each deploy.
- Docs: DEPLOY.md (everyday flow step 4, "A new APK from CI, on every deploy"), CLAUDE.md's
  convention, `mobile-docs/steps-to-production.md` step 7. YAML parses.

### Not done, and why
- **Not run in CI from here**: the job only runs on `main`, and this branch is not merged. The
  phone check after the first deploy is in `next-steps.md`.
- **No rewrite of the screens in Kotlin/Compose.** Discussed and dropped: the owner only needed the
  download. The WebView, the bundle self-update and `native-level.txt` stay as they were — the
  bundle still updates the screens without installing, the APK is now an extra every time.
- Carried from the previous session, still open in `next-steps.md`: the card débito/Flash owner
  walk-through, no Flash capture (no Flash-specific parser, no benefit-credit detection), the
  Flash package unconfirmed, brapi quota with hourly quotes, and the older items (server/phone
  timing of saves, static files uncompressed, Rentabilidade's daily loop, the Planejar check).

### Learned
- The container has Java 21 and Gradle but no Android SDK: an APK can only be built by CI or on
  the owner's PC.
- Each deploy now costs the `apk` job's runner time (Gradle + two builds) and adds an APK on the
  server; the publish step keeps only the last three.
- From the previous session, still true: the test DB is one per session (assert on your own
  user's rows); Java's `\s` does not match U+00A0; never name a backend module after a stdlib one.
