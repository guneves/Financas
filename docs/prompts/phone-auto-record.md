# Prompt — The phone app on the auto-record paradigm: no Aprovar, review in the Extrato

> Paste everything below the line into a new session. It is written for a cold start. Decisions
> marked **(owner)** are already taken by the owner; don't reopen them.

---

Bring the **native Android app** (`frontend/android/`, Kotlin + Compose, no WebView) up to the
paradigm the server and the web got in migration 045, and **remove the Aprovar screen from the
phone entirely**. The phone is the most important part of the app: it is what the owner opens every
day, and it should be fully automated — a notification becomes a lançamento by itself, and the
owner's only job on the phone is to confirm "é meu" and the category.

Read `CLAUDE.md` (section "Auto-record → reconcile → review", then "The inbox engine"),
`docs/handoff.md` (session 2026-10-27 (4)), `docs/next-steps.md` (section 045) first, as usual. For
the phone, read `mobile-docs/native/architecture.md`, `conventions.md` and the screen specs
`mobile-docs/native/screens/00-shell.md`, `02-aprovar.md`, `04-extrato.md`, `11-ajustes.md` before
touching code.

## Where things stand (2026-10-27, commit `41ed90d`)

- **Server (done, tested, 1942 pytest):** every detection posted to `POST /api/inbox/detections` is
  recorded at once (`services/auto_record.py`); the response now carries `auto_recorded:
  {recorded, linked, held}` next to `results`. Missing targets are guessed and the row is born
  `needs_review = 1`. Pluggy reconciles what a notification recorded (links, or redoes an untouched
  row the bank's way). Both switches default **on** (`AUTO_RECORD_DEFAULT`):
  `auto_record` in `GET/PATCH /api/inbox/settings` (notifications) and in
  `/api/open-finance/settings` (Pluggy).
- **New endpoints the phone must use:**
  - `GET /api/review` → `{items, count, waiting}`; each item: `table` (`transactions` |
    `cc_expenses`), `id`, `date`, `amount`, `type` (EXPENSE/INCOME/TRANSFER/CARD/REFUND),
    `description`, `category`, `category_id`, `account_name` / `transfer_account_name` or
    `card_name` + `installments`.
  - `POST /api/review` with `{items: [{table, id, category_id?}]}` → `{reviewed, count}`; all or
    nothing (404 on an unknown id); `category_id` only when the owner changed it; a transfer keeps
    its category.
  - `GET /api/cc-expenses/statement` (same filters as `GET /api/transactions`) → one row per card
    purchase: `id`, `client_id`, `date`, `type` CARD/REFUND, `amount` (total), `installments`,
    `card_name`, `category`, `description`, `needs_review`.
  - `GET /api/transactions?review=1`; every transaction and card row has `needs_review`;
    `GET /api/home` has `review_count`.
- **Web (done):** Extrato has a Revisar panel (category select + "É meu", "Confirmar todos"), card
  purchases interleaved in the timeline with a "Cartão · Nx" tag (never in day totals), an "A
  revisar" badge, a "Revisão" filter; the header pill/Extrato tab count reviews; Aprovar left the
  tabs. Reference implementation: `frontend/src/lib/review.js` (+ `review.test.js`),
  `frontend/src/pages/lancamentos/ReviewPanel.jsx`, `Extrato.jsx`.
- **Phone (not done — this task):** still has `ui/inbox/` (InboxScreen, InboxViewModel,
  InboxEditSheet, InboxLogic, InboxNotifier), the `NativeRoutes.INBOX` route and the Aprovar tab
  (`LancamentosTab.APROVAR`, `ShellNav`, `NativeLinks` maps `/lancamentos/aprovar`), the local
  "Novo para aprovar" notification fired by `notify/DetectionSender` from `results` statuses
  new/merged, and an Extrato (`ui/extrato/`) without card rows or review.

## What to build

1. **Remove Aprovar from the phone (owner).** No Aprovar tab, route, screen, deep link target or
   "para aprovar" badge/pill/notice. Delete `ui/inbox/InboxScreen.kt`, `InboxViewModel.kt`,
   `InboxEditSheet.kt` and whatever only they use (keep `InboxRepository`/DTOs only if the waiting
   rows below need them); update `NativeActivity`, `ShellNav`, `ShellChrome`, `NativeLinks`
   (`/lancamentos/aprovar` and `/aprovar` now open the Extrato in review mode) and their tests.
   **Keep the notification capture untouched**: `notify/` (listener, parsers, pairing, queue,
   sender, worker) is the source of everything and must keep posting detections exactly as today.
2. **Revisar in the native Extrato.** At the top of the Extrato (Contas view), a Revisar section
   built from `GET /api/review`: one row per item with description, date · place, signed amount,
   a category picker (pre-filled with the suggestion; expense categories for out/CARD, income for
   in/REFUND; none for a transfer) and a big "É meu" button (one tap = `POST /api/review` with that
   item); "Confirmar todos (N)" sends all with the categories on screen. Show the first 5, "Mostrar
   todos" for the rest. The row disappears on success (re-read the queue and the Extrato). Follow
   the web's rules in `lib/review.js` — port them to a pure Kotlin `rules/ReviewRules.kt` with JVM
   tests (`reviewPayload`, sign, place text, category type, notice texts).
3. **Card purchases in the native Extrato.** Merge `GET /api/cc-expenses/statement` into the
   timeline by date (newest first; same day: later `created_at` first), one row per purchase with a
   card tag ("Cartão" / "Estorno", "· 4x" when parcelada), amount signed (purchase −, refund +), and
   **outside the day totals** (a day with only card rows shows no total). With the Extrato's
   filters, pass the same filters to the statement endpoint; with paging, only purchases down to
   the oldest loaded date (`mergeStatement(..., until)` in the web). Tapping a card row opens
   Cartões. Port the merge to `rules/ExtratoRules.kt` (or `ReviewRules.kt`) with JVM tests.
4. **"A revisar" everywhere it matters:** a badge on rows with `needs_review`, a "Só a revisar"
   filter in the Extrato filters (`review=1` on both endpoints), the review count on the Extrato
   tab and in the shell header where the Aprovar count used to be (tap → Extrato in review mode),
   and on Início if it showed the Aprovar count.
5. **The local notification becomes "gravado".** Replace "Novo para aprovar" (`InboxNotifier`)
   with one quiet, grouped notification after an upload that recorded something
   (`auto_recorded.recorded + linked > 0`, or statuses new/merged): "R$ 45,90 em PADARIA gravado ·
   toque para revisar" (several: "3 lançamentos gravados · toque para revisar"); the tap opens the
   Extrato in review mode; no notification while the Extrato's Revisar is on screen. Never show
   bank text beyond what the app already parsed. Keep the pure part tested.
6. **What the server could not record (`waiting` in `GET /api/review`)** — an own transfer seen
   from one side only, another currency, or everything when the owner turned the switch off. With
   no Aprovar screen, these must be resolvable **inside Revisar**: list them under the review rows
   as "Falta a outra conta" with a quick choice of the destination/origin account (or "É de outra
   pessoa", which records it as despesa/receita), using the existing inbox API (`GET /api/inbox`,
   `PATCH /api/inbox/<id>`, `POST /api/inbox/<id>/approve` with `remember: false`, `version`
   from the item; 409 = re-read). Do the same on the web so the web's Aprovar page can go too:
   replace the Extrato's "N movimentos não puderam ser gravados sozinhos · Ver" link with these
   rows, then delete `frontend/src/pages/lancamentos/Aprovar.jsx`, its route, `lib/inboxRules.js`
   if unused, and redirect `/lancamentos/aprovar` to `/lancamentos/extrato?review=1`. Keep the
   inbox API on the server (the engine and these rows use it).
7. **Ajustes on the phone:** the "Gravar sozinho" switch for notifications
   (`/api/inbox/settings` `auto_record`) next to the Open Finance ones; drop "Sempre perguntar a
   conta/cartão" from the phone (it only applied to Aprovar). Off = the brake: items then show up
   as the waiting rows of step 6, never as a separate screen.
8. **Offline stays safe:** the outbox and detection queue behave as today; Revisar and card rows are
   reads (cached like the Extrato); a failed "É meu" shows the error and leaves the row.

## Rules to keep

- Native Compose only, the app's theme tokens and existing components (see `conventions.md`); 44 dp
  touch targets; user-facing text in Portuguese; reais only; privacy mode hides amounts as the
  Extrato already does.
- Every rule you touch gets a JVM test; the server's behaviour is not changed by this task except
  where step 6 needs a small endpoint addition (then add pytest cases and the route to
  `test_route_map.py`).
- Update `mobile-docs/native/screens/02-aprovar.md` (mark it removed, point to Extrato),
  `04-extrato.md`, `00-shell.md`, `11-ajustes.md`, and CLAUDE.md ("Aprovar left the tabs" →
  "Aprovar is gone from web and phone; waiting items resolve in Revisar").

## Verify, then ship to the phone

1. `cd frontend/android; .\gradlew --offline testDebugUnitTest assembleDebug` with Android Studio's
   JDK (see the memory note on the local Android build) — all green; `cd backend; pytest`;
   `cd frontend; npm test; npx vite build`.
2. If an emulator or the owner's phone is reachable over adb, install the debug APK
   (`br.financas.app.debug`, installs beside the real app) against a scratch backend and walk:
   a notification posted with `adb shell cmd notification post` (package `com.android.shell` is
   the parser's test app) appears in Revisar within seconds; "É meu" clears it; a card purchase
   shows in the timeline with its tag; no Aprovar anywhere. Otherwise say plainly that it was not
   run on a device.
3. **Getting it onto the phone** = a push to `main`: `deploy.yml`'s `apk` job builds the signed
   APK, publishes `apk/version.json`, and the installed app offers the update (`update/ApkUpdater`).
   Ask the owner before pushing (the push also deploys the server with the 045 switches on). After
   it lands, check the job is green and that `version.json`'s `versionCode` went up.

End the session as CLAUDE.md says: next-steps, done-tasks, handoff (including what was not run on a
device), commit.
