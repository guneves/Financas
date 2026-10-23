# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 (late night) · native "+ Novo" (the rest of step 1)

Local session on the owner's PC, branch `claude/native-novo` (cut here from `origin/main` after PR
#31, upstream unset so nothing pushes to `main`). The owner's prompt called it "session 2"; in the
plan it is the rest of step 1 (Aprovar is step 2). Briefing by `session-scout`, found by
`subagent_type`, no fallback.

### Done
- **`native-screen-builder`** built `ui/newentry/` (NewEntryActivity: a translucent Compose bottom
  sheet with the four forms, amount first; Corrigir from Pendentes is native too), the save path of
  `createEntry()`, `buildItem`/`newClientId`/`editedItem` in `OutboxRules.java` (`editedItem` also
  added to `outboxRules.js`), `rules/EntryOptions.kt`, `rules/InboxNotice.kt` and the first
  `ui/components/`. `NativeScreens.routes()` lists `new-entry`, `open()` starts it, `dataChanged`
  carries the toast. Web: `lib/nativeScreens.js` + `nativeScreensRules.js`, Layout opens the native
  sheet only when listed. `native-level.txt` 2 → 3 in the same commit.
- **`native-parity-reviewer`**: one blocker (closing the sheet mid-save cancelled the POST, so a
  retype would duplicate), one major (app killed mid-POST, same result), minors. The builder fixed
  the blocker, the major and two minors in one round; the reviewer re-checked: all closed, nothing
  new. Details in `done-tasks.md`.
- CI: 39884267832 (`e641424`) and 39884996021 (`4144bf8`), both green first time. 51 new JVM tests;
  `npm test` 150 (was 144); backend untouched.

### Not done, and why
- **No phone check.** Nothing has run on a device; the PR carries the Acceptance list as the
  owner's checklist. Merge after it.
- **The web still duplicates after a killed tab** (`createEntry()` queues only after the failure).
  Native now keeps the item in the outbox during the POST; porting that to `lib/outbox.js` is a
  separate change with a node test (next-steps).
- Launcher shortcut not built; Corrigir after the worker already sent the item still says
  "pendente atualizada" (same on web). Both in next-steps.
- Accepted, not fixed: a 5xx is shown and the item removed (web parity), so a 5xx racing a worker
  delivery could lead the owner to retype; requires both at the same instant.
- Carried, still open: everything in the previous entry's "Not done" (pytest red 21:00–midnight
  local; the sharing form refusing "12,5"; `settlePayload`/`shareSummary` unported; APK not buildable
  in a cloud container; desktop redesign; `findings.md` triage; Plus Jakarta Sans; the phone checks
  of the APK-on-every-deploy and the card débito/Flash; brapi quota with hourly quotes; the fuzzing
  leftovers).

### Next session
After the owner's phone check and merge: step 2, Aprovar (`screens/02-aprovar.md`), which creates
`NativeActivity`/the NavHost. It can reuse `ui/components/`, `EntrySaver`'s pattern and the
`dataChanged` toast bridge.

### Learned
- **Native "+ Novo" deliberately differs from `createEntry()`**: the item is in `OutboxStore`
  before the POST (worker not scheduled) and removed on any server answer. A concurrent worker
  delivery is safe: the server answers a duplicate `client_id` with the first row (IntegrityError
  guard in transactions, transfers and purchases), and the worker writes back only through
  `removeIfUnchanged`/`replaceIfUnchanged`.
- A save must outlive its screen: it runs in `AppGraph.appScope`; results after the sheet closed go
  through `EntryDelivery` (WebView toast or an Android Toast).
- `OutboxPlugin.load()` already schedules the worker on every app start; no extra startup hook.
- The web's required-field check is the browser's popup; native has its own wording in the error
  box ("Preencha este campo: …"), recorded in the spec.

