# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (5) · The phone on the 045 paradigm (no Aprovar)

Local session on the owner's PC, from a pasted request (it was cut off mid step 4, "a badge…"; steps
5–6 were inferred from the docs: the review badges/pill, waiting items in Revisar, the Ajustes
switch). Branch `claude/apk-revisar`, opened as a PR at the owner's request — **not merged, not
deployed**.

### Done
- **Aprovar gone from the APK**: `ui/inbox/` deleted (Screen, ViewModel, EditSheet, Notifier, Logic +
  `InboxLogicTest`), `NativeRoutes.INBOX`, `LancamentosTab.APROVAR`, `ShellNav.backTarget()`, the
  focus-item intent extra, every `inboxCount`/"para aprovar" pill. `/lancamentos/aprovar`, `/aprovar`
  and `?review=1` open the Extrato in review mode (`NativeLinks.VIEW_REVIEW`). The old notification
  and its channel `financas_inbox` are removed on start. `DetectionSender` posts exactly as before;
  only the local notification after the response is gone.
- **Revisar** (`ui/extrato/ReviewSection.kt`): queue from `GET /api/review`, category picker, "É meu",
  "Confirmar todos (N)", first 5 + "Mostrar todos". **Não gravou sozinho**: the waiting inbox items
  with the other account / amount in reais → approve (`remember: false`), "não é entre minhas contas"
  → despesa/receita, Descartar. Uses the existing inbox endpoints — **no server change**.
- **Card purchases** in the Extrato timeline (`GET /api/cc-expenses/statement`, same filters, paged
  merge), tag, signs, no day total, tap → Cartões. "A revisar" mark, "Revisão" filter.
- **Shell**: `ReviewPill` in every header (count from `GET /api/review`, re-read on resume, data
  change and every 60 s); Extrato tab "Extrato · N".
- **Ajustes › Avisos do celular**: Gravar sozinho switch (`auto_record`) + "Sempre perguntar"
  (disabled while on). Phone texts that said "Aprovar" (Open Finance summaries, the "+ Novo" matched
  toast, notification help) now point to Revisar — a deliberate divergence from the web port, noted
  in `OpenFinanceRules.kt` / `InboxNotice.kt`.
- Rules/tests: `rules/ReviewRules.kt` (port of `lib/review.js` + waiting rules) with
  `ReviewRulesTest`; `ExtratoRules` card-row cases; `ReviewRepositoryTest`; nav tests updated.
  Local: `testDebugUnitTest` 526 green, `assembleDebug` ok; pytest 1942; npm test 200; vite build ok.
- Docs: specs 00, 02 (marked removed), 04, 11, architecture, CLAUDE.md.

### Not done, and why
- **Not run on a device**: no phone or emulator was attached to adb. The Acceptance walk is in
  next-steps.
- **Not pushed to main**: the owner asked for a PR. Merging deploys the server too (045 switches on)
  and builds the signed APK; check the apk job is green and `version.json`'s versionCode went up.
- With Gravar sozinho off, items needing a card or crédito/débito cannot be resolved on the phone
  (the row says so). Swipe actions in Revisar not built.
- `InboxRules.kt` and the DTOs stay (waiting rows use them); most of InboxRules is now unused on the
  phone — can be trimmed later.

### Next session
1. Owner: merge the PR, install the update, walk the next-steps item.
2. Then the 045/044 checks on real data.

### Lessons (non-obvious)
- Bash heredocs with Kotlin `$` strings and quotes broke here: write edit scripts with Write and run
  them with python (as the memory note says).
- `adb` is not on PATH: `$LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe`.
- pytest's summary only prints with `-o addopts=""` in this repo's config.
