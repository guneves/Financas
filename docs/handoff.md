# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-22 · No Revisar: confirmation is automatic, branch `ccr-de45a0e2-oil9rl`

Owner's ask: "Remova o repasse na hora da receita e remova a opção de confirmar as receitas e despesas. Quero que
seja automatico."

**Done** (UI only, web and APK; the server is unchanged):
- Web: `ReviewPanel.jsx` deleted; Extrato without the Revisar panel, the "A revisar" badge and the "Revisão" filter
  (`?review=1` is ignored); `Layout.jsx` without the "para revisar" pill and the Extrato tab count; Conta global
  without "É meu"/"Confirmar todos"/badge; Ajustes › Avisos do celular without "Revisar sai sozinho depois de";
  "Decidido sozinho" hides `auto_confirm` (`shownDecisions()` in `lib/autoDecisions.js`); `lib/review.js` keeps only
  the card-statement merge and `waitingNoticeText()`. `npm test` 247/247, `vite build` OK.
- APK: same cuts (`ReviewSection.kt` keeps only `WaitingPanel`; `ReviewPill`, `ShellChrome.reviewCount`,
  `ShellViewModel.refreshReview()` and the 60 s poll gone; `ReviewAutoBlock` gone; GlobalAccount `confirm()` gone;
  `AutoDecisions.shownDecisions()`; 29 orphaned strings removed). JVM tests updated (`ReviewRulesTest`,
  `ExtratoRulesTest`, `AutoDecisionsTest`).
- Docs: CLAUDE.md (repasse, Review, Review confirms itself, Twins), mobile-docs shell/extrato/architecture.

**Not done and why:**
- **The APK was not compiled or tested here**: the container has no Android SDK. Run `gradlew testDebugUnitTest
  assembleDebug` on the PC before installing; the edits were checked by grep for dangling references only.
- Backend untouched on purpose: `needs_review` still lets Pluggy fill/confirm the category of a notified row, and
  `review_auto.py` still clears it after `review_auto_days` (default 3). If the owner had set that to 0 ("Nunca"),
  rows keep `needs_review` forever — invisible now, harmless, but `PATCH /api/inbox/settings {review_auto_days: 3}`
  restores the old behaviour. `POST /api/review` (with `repasse`), `review_count`, `InboxRepository.setReviewAutoDays`
  and `ReviewRepository.confirm` stay for old APKs; remove once no old APK is installed.
- The undo of `transfer_guess`/`fx_fallback` still "puts the row back in review", which is now invisible (toast
  "Desfeito."). Left as is.

**Next:** build/test the APK on the PC, then the previous session's "Next" (B-series merge/deploy watch list).

**Lessons:**
- `GET /api/review` is still the web/APK source for `waiting` (WaitingItems / WaitingPanel): don't delete the read.
