# Mobile app — steps to production

An Android APK of the existing app, with offline entry and purchases detected from bank
notifications. "Production" here means: installed on the owner's phone, used daily, syncing with the
backend on the owner's PC.

Written 2026-10-12 and verified against the code and the web the same day (see "Verification" at
the end). The status of each phase is in its heading.

## Decisions taken

| Topic | Decision |
|---|---|
| Shape | Capacitor wraps the existing React frontend into an APK. Same repo, same UI code. No native rewrite. |
| Connection | Tailscale between phone and PC. The backend stays on the PC; HTTPS comes from `tailscale serve`. |
| Offline scope | Creating a despesa, receita, transferência and card purchase works offline. Edits, deletes, investments, invoice payment and imports stay online-only. |
| Sync | One direction: an outbox on the phone replays creations to the server. The server is the only source of truth; the phone refetches after each run. |
| Idempotency | Each entry carries an id generated on the phone (`client_id`). The server stores it so a second delivery is a no-op. |
| Notifications | A native `NotificationListenerService` reads notifications from the listed bank apps only. Parsing happens on the phone. |
| Publishing | Always confirm. A detected purchase waits in an inbox until the owner taps Confirmar (from the notification or the list). Nothing is recorded on its own. |
| Statement import | The import preview flags rows that match an existing lançamento on account, date and amount as probable duplicates and leaves them unchecked. |
| Banks | Itaú, BTG Pactual, Banco do Brasil, plus Samsung Wallet as a fallback: most card purchases are paid through Samsung Pay and some cards send no push, so Samsung's notification counts only when the bank's does not arrive (owner, 2026-10-17). Itaú Cartões and Ourocard are not read: they repeat the bank apps. |
| Login lifetime | 180 days, one setting for PC and phone: `JWT_EXP_DAYS=180` in `backend/.env` (owner, 2026-10-12). The backend is reachable only through Tailscale, and an expired token stalls background sync and the notification's Confirmar button. |
| Distribution | Sideloaded APK signed with the owner's own keystore. No Play Store. |

Benefit cards (VA/VR) are out of the app: no account type for them, no notifications read from
them (owner, 2026-10-12).

## Where the outbox lives

The queue of entries waiting for the server has one home per platform, behind one interface
(`frontend/src/lib/outbox.js`: `enqueue`, `list`, `update`, `discard`, `flush`):

- **Browser** (the PC, and the phone's browser in Phase 1): IndexedDB, and the web layer sends.
- **APK**: a native SQLite table, and **native code sends**. The web layer reaches it through a
  Capacitor plugin; it never sends on Android.

The reason is that two things in this plan must work with the app closed: the Confirmar button on
a notification (Phase 7) and syncing after the connection returns. Native code cannot write to the
WebView's IndexedDB while the WebView is not running, and the Android WebView has no Background
Sync. So on the phone the queue has to be native, and the sender has to be a `WorkManager` job with
a network constraint that posts to the server itself. It needs the API address and the token: the
web layer hands both to the plugin on login and clears them on logout.

One queue and one sender per platform means there is never a question of which copy is right. The
server's `client_id` makes a double delivery harmless either way.

## Before starting

- The uncommitted work in the tree no longer touches `NewEntrySheet.jsx`, `newEntry.js` or
  `Extrato.jsx` (those were committed in 88411f3 and 6589e78). What remains uncommitted belongs to
  another session and is in other files; commit mobile work by explicit path.
- Collect real notification texts: at least five per bank app, copied exactly, covering credit,
  debit, Pix sent, Pix received, a refund (estorno) and a declined purchase. The parsers are written
  against these. Since 2026-10-17 the listener's capture mode (Phase 6, step 2) collects them on
  the phone, with each app's real package name and posted time; copying by hand is no longer
  needed. Example texts from any other source are never a test fixture.
- Install Android Studio (SDK and platform tools) and Tailscale on the PC and the phone. In the
  Tailscale admin console, enable MagicDNS and HTTPS certificates: `tailscale serve` needs both.
  Enabling HTTPS publishes the PC's machine name in the public certificate log.

## Phase 1 — One origin, reachable from the phone (PC half built 2026-10-13)

Built: steps 1, 2 and 4, and `backend/.env.example` for step 3. On 2026-10-16 `backend/.env` had a
real `JWT_SECRET`, and Claude set `JWT_EXP_DAYS=180` and added `https://localhost` to `CORS_ORIGINS`.
`tailscale serve` already proxies `https://financas.<tailnet>.ts.net` to `127.0.0.1:5000` (step 5).
Open: the phone's browser on mobile data. The APK reaches the address from the phone (2026-10-16).

1. Flask serves the built frontend (`frontend/dist`) at `/`, with a fallback to `index.html` for
   client routes. `/api/*` is unchanged, and an unknown `/api/...` path stays a JSON 404.
2. The frontend's default API base becomes same-origin in a production build; `vite dev` keeps
   `http://localhost:5000`, and `VITE_API_BASE_URL` stays as the override.
3. Set a real `JWT_SECRET` in `backend/.env` (the fallback in `config.py` is `dev-secret-change-me`),
   `JWT_EXP_DAYS=180`, and `CORS_ORIGINS` explicitly: `http://localhost:5173` (the Vite dev server)
   and, from Phase 5, `https://localhost` (the APK). The phone's browser is same-origin and needs
   no entry.
4. `start.ps1` gains a mode that builds the frontend and starts the backend alone.
5. Run `tailscale serve` in front of port 5000. Flask keeps listening on localhost only.

No service worker and no web manifest: the phone's browser is an online-only stopgap until the APK
exists, and the APK bundles the frontend itself.

Done when, on the PC: `http://localhost:5000/` opens the app, a client route such as
`/lancamentos` survives a reload, and a despesa is recorded. Then, on the phone: its browser opens
the Tailscale HTTPS address on mobile data, logs in and records a despesa.

## Phase 2 — Phone-width layout (built on the PC 2026-10-16; the "done when" needs the phone)

1. Walk every banking screen at 360–412 px: Início, Extrato, "+ Novo" (all four forms), Orçamento,
   Recorrentes, cards and invoices.
2. Fix what breaks: tables that overflow, sheets taller than the screen with the keyboard open,
   touch targets under 44 px, the nav.
3. Numeric fields open the numeric keyboard; the amount field is focused when "+ Novo" opens.

Done when: a despesa can be entered one-handed in under ten seconds. Investment screens only need
to be readable, not optimised.

What the walk found (Playwright, phone emulation at 360 and 412 px, scratch database with the
three-year mock): **no screen scrolled sideways**; the gaps were elsewhere.
- Section tabs overflowed at 360 px (Metas and Importar cut off). Below `sm` they now drop the icon
  and some padding, and three tabs fit.
- Cartões: next to the amount and "Pagar", an invoice label had ~40 px left and the "Fechada" /
  "Próxima" badges were drawn over the amount. On phones the amount now sits under the label.
- Touch targets: `Button` `sm`/`md`, `SegmentedControl` and `Tabs` were 36–40 px. They are 44 px
  below `lg` now (the `IconButton` rule), so the per-call `h-11 lg:h-9` overrides are no longer
  needed. Início's panel-title links get a 46 px hit area without moving.
- "+ Novo": the type picker took three rows. It is one row of four 56 px buttons (icon over a short
  label: Despesa, Receita, Transferir, Cartão). Every form starts with a large amount field, and the
  amount gets focus whichever type opens the sheet (before, only despesa/receita). Despesa/receita
  ask in typing order — valor, categoria, descrição — with data and conta (almost always the
  default) side by side at the end. The whole despesa form plus Salvar fits in 360×780.
- Keyboard: `interactive-widget=resizes-content` in `index.html` and a `92dvh` sheet height. With
  the viewport shrunk to 360×420 (what the keyboard leaves) the amount field and Salvar are both on
  screen. In the APK, Capacitor's default `adjustResize` does the same.
- `inputMode` on every numeric field of the banking screens and Ajustes (`decimal` for money,
  `numeric` for parcelas, days, interval, rows to skip). The initial balance in Ajustes › Contas is
  left alone: it can be negative and Android's decimal keyboard has no minus key.

Still open, and only the phone can answer it: the ten-second test itself, and whether the decimal
keyboard of the owner's phone types a comma that `type="number"` accepts (Chrome accepts the
locale's separator, but keyboards differ).

## Phase 3 — Backend: idempotent creation (built 2026-10-13)

The four "+ Novo" forms use three endpoints: `POST /api/transactions` (despesa and receita),
`POST /api/transfers` (transferência — `POST /api/transactions` refuses `TRANSFER`) and
`POST /api/cc-expenses/purchases` (card purchase).

1. Migration `024`: a nullable `client_id` column on `transactions` and on `cc_expenses`, each
   under a unique index that includes `user_id`. A transfer is one row, so one id per request is
   enough. A card purchase in installments is N rows from one request; they share the id, so the
   `cc_expenses` index is on `(user_id, client_id, installment_info)`.
2. The three endpoints accept an optional `client_id`. A repeated one returns the rows the first
   delivery created, with 200 instead of 201, and writes nothing. The lookup comes before
   validation: a replay must succeed even if the account was archived in between.
3. `source_type` is left alone. A lançamento that arrived with a `client_id` was still typed by
   the owner, so it stays editable and deletable from the Extrato and exports as "Manual", with no
   new rule anywhere that reads `source_type`.
4. Tests: double delivery of each of the four entry kinds creates one row (N for installments);
   the second response equals the first; the same `client_id` from another user does not collide;
   a malformed `client_id` is refused; an entry without one behaves as before.
5. Run `finance-guard` over the change.

Done when: the suite passes and posting the same payload twice by hand leaves one lançamento.

## Phase 4 — Offline: cache and outbox (browser) (built and checked in a desktop browser, 2026-10-13)

Built: steps 1 to 6. Step 7 is partial: the header says when the server is unreachable and an
online-only action fails with a clear message, but buttons are not disabled screen by screen.
The "done when" below was run in a scripted desktop browser on a scratch database and holds,
including the cases it does not name: "+ Novo" opened for the first time with the server down, a
pending item corrected before sending, and a request that reached the server while its answer was
lost (resent, it creates nothing). One limit of the browser, which the APK does not have: a screen
never visited cannot be loaded with the server down, because its code is fetched on first visit.

Built and checked in a desktop browser. The APK reuses everything here except the storage and the
sender, which Phase 5 swaps for the native ones.

1. Persist the TanStack Query cache to IndexedDB so accounts, categories, cards and the last
   Extrato are available with no connection. The cache is cleared on logout.
2. `frontend/src/lib/outbox.js`: the queue interface described above, with the IndexedDB storage.
   An item is `{client_id, kind, payload, status, last_error, created_at}`; statuses `pending` and
   `needs_attention`. The rules (what each response does to an item, what a pending item does to a
   balance) are pure functions with tests run by `node --test` — the frontend has no test runner
   and this needs none installed.
3. The four forms always send a `client_id`, online or not, so a request that timed out after
   reaching the server is also safe to repeat. A creation that fails for network reasons goes to
   the outbox; one that the server answered is never queued.
4. Replay: on app open, on returning to the foreground, on the `online` event and from a manual
   "Sincronizar agora". One item at a time, in order. Response handling:
   - created or already exists: remove the item;
   - network error, timeout or 5xx: keep `pending`;
   - 401: stop the run, keep everything, ask for login;
   - 400 / 409: mark `needs_attention` with the server's message; later items still go.
   An entry can be queued with an expired login; only sending needs the token.
5. Pending entries show in the Extrato with a "pendente" mark, and balances shown offline are
   adjusted by them and labelled as an estimate. A pending transfer moves two accounts and leaves
   the consolidated balance alone; a pending card purchase touches no account.
6. A "Pendentes" screen lists the outbox: retry, edit or discard an item.
7. Online-only actions are disabled offline with a message, not left to fail.

Done when, on the PC: with the backend stopped, three entries are recorded, the tab is closed and
reopened (the entries are still listed as pending), and after the backend returns all three appear
once in the Extrato. The phone repeats this test in Phase 5.

## Phase 5 — The APK (built and installed on the phone 2026-10-16; closed-app check open)

Built: steps 1 to 7. The owner installed Android Studio; its JDK is Java 25, which needs Gradle
9.1 (the wrapper was bumped; AGP stays 8.13). The key exists in `%USERPROFILE%\.financas-android`
and the APK is installed on the owner's Galaxy S25. On the phone: login through Tailscale, real
data, the bars in the theme, and an offline entry queued and then sent by the WorkManager job on
reconnect, once. Open: the "done when" with the app actually closed, and the smaller checks listed
in `docs/next-steps.md`.

Two things the phone taught:
- With the Tailscale VPN up and no network under it, a request does not fail, it hangs. So
  `apiFetch` has timeouts (`timeoutMs`): with no real network (`Outbox.hasNetwork()` ignores the VPN) a "+ Novo" creation is
  queued at once; otherwise it gives up after 6 s and goes to the
  queue (safe: `client_id`), a read after 45 s; edits and deletes wait, since a timed-out one may
  have gone through.
- The phone's text zoom makes `FitValue` land a fraction of a pixel over the box, which showed
  "R$ 1.000,…". It measures fractional widths and leaves 2% slack.

1. Capacitor 8.5 in `frontend/` (`capacitor.config.json`, app id `br.financas.app`, name
   "Finanças"); `frontend/android/` generated and committed. The APK bundles its own build of the
   frontend, so it opens with no connection.
2. The API base is set at build time: `build-apk.ps1` builds with `VITE_API_BASE_URL` into
   `frontend/dist-android/` (gitignored), so `frontend/dist`, which Flask serves on the PC and to
   the phone's browser, keeps calling its own origin. The default address is
   `https://financas.<tailnet>.ts.net`: the PC's MagicDNS name is `financas`, not its Windows
   hostname (which does not resolve in the tailnet). `-ApiBase` overrides it.
   `https://localhost` is in `CORS_ORIGINS` in `backend/.env`.
3. The native outbox, Java, in `android/app/src/main/java/br/financas/app/outbox/`:
   - `OutboxStore`: a SQLite table holding each item whole, in the Phase 4 shape;
   - `OutboxRules`: `outcomeOf`, `endpointFor` and `deliveredDiffers`, ported from
     `outboxRules.js`, with JVM tests in `app/src/test/` (`build-apk.ps1` runs them);
   - `OutboxSender`: one run at a time behind a lock, one item at a time, in order, with the
     Phase 4 rules. A run also takes items queued while it runs. Redirects are not followed, and
     a 2xx counts only when its body is the created row. The result is written only to the
     version that was sent, so an item corrected or discarded mid-request stays as the screen
     left it;
   - `OutboxWorker`: WorkManager, network constraint, exponential backoff from 30 s, unique work
     with `KEEP`. On 401, or with no session, it posts a "Sessão expirada" notification and does
     not retry; the next `setSession` schedules a new run;
   - `Session`: API address, user id and token. The token is encrypted with an AES-GCM key from
     the Android Keystore;
   - `OutboxPlugin` (`Outbox`): `all`, `put`, `remove`, `flush` (runs a round now and returns
     the same summary as the browser's `flush()`), `setSession`, `clearSession`, and a `changed`
     event when the background sender moved the queue.

   `lib/nativeApp.js` swaps it in with `setOutboxBackend()` before `startOutbox()`. It hands over
   the session on every `finance-auth-change` and, on `changed`, reloads the queue and invalidates
   the server data. Java instead of Kotlin: the generated project is Java, and plain Java does not
   depend on matching a Kotlin plugin version to a build nobody could run here. Phase 6's parsers
   can bring Kotlin in.
4. Android details:
   - the back button closes the open sheet, confirmation or menu (by the same Escape the keyboard
     uses), then goes back a screen, and on Início minimises the app;
   - the status and gesture bars take the app's theme (the `Shell` plugin, fed by
     `finance-theme-change` from `lib/theme.js`). This matters because the theme toggle can
     differ from the system's;
   - `SystemBars` `insetsHandling: native` pads the WebView, so nothing sits under the bars;
   - the same padding follows the keyboard;
   - `POST_NOTIFICATIONS` is asked for once, at first launch;
   - `allowBackup="false"`: nothing goes to Google's backup.
5. The icon is the favicon's chart as an adaptive vector icon (emerald background; a monochrome
   layer for themed icons). The launch screen is that icon on the app's background, light or dark.
   The name is "Finanças". The small notification icon is a white vector of the same chart.
6. `mobile/new-keystore.ps1` creates `%USERPROFILE%\.financas-android\financas-release.jks`
   (PKCS12, RSA 4096, 100 years) and `keystore.properties` with a generated password. It refuses
   to run if a key already exists. Gradle reads the properties file (or
   `FINANCAS_KEYSTORE_PROPERTIES`). The folder must be backed up — it was, off the PC, by the owner
   (confirmed 2026-10-16).
7. `mobile/build-apk.ps1` runs the web build, `cap sync`, the JVM tests and `assembleRelease`
   with the version (commit count; date + commit, plus `-dirty`), then `apksigner verify` and
   `adb install -r` on the single connected device. It never uninstalls: on a signature mismatch
   it stops and says to empty "Pendentes" first.

The version shows in Ajustes › Versão do app since 2026-10-17 (APK, native level, screen version).

Done when: with the phone in airplane mode, three entries are recorded, the app is closed, and
after reconnecting — without opening the app — all three appear once on the PC.

## The screens update themselves (built 2026-10-17; the phone check is open)

Before this, every change in `frontend/src` needed a new APK over USB. Now the server hands the
phone its screens, and a new APK is needed only for a native change. The three options considered:
the app downloads its own screen bundle (built), CI builds and offers the APK (built too, step 7),
and loading the screens from the server (rejected: the app could not open offline).
Hand-written rather than `@capgo/capacitor-updater`: Capacitor already serves the WebView from a
folder (`CapWebViewSettings` → `serverBasePath`, read by `Bridge` on load), the custom plugins are
Java already, and nothing reports to a third party.

1. **The bundle.** The image builds the frontend a second time, for the APK
   (`VITE_API_BASE_URL` = `APP_API_BASE`, the server's address), into `frontend/dist-android`, and
   `frontend/scripts/bundle-manifest.mjs` writes its `bundle.json`: `version` (16 hex of a SHA-256 of
   every file's path and bytes), `native_level` (`frontend/native-level.txt`) and `api_base`.
   `build-apk.ps1` stamps its own build the same way, so the APK knows the version of the screens
   it carries. Same code gives the same version on Windows and in the Linux image (checked: both
   `51714bc…`), so a fresh APK does not download its own screens again.
2. **The server.** `GET /api/app-bundle` returns the manifest plus the zip's `sha256`, `size` and
   `url`; `GET /api/app-bundle/<version>.zip` returns the zip, only for the current version.
   `services/app_bundle.py` builds the zip once per version with fixed dates, so the bytes (and
   the hash) are the same after a restart. Both are public, like `/`: it is the same frontend the
   server already gives anyone on the tailnet, and a logged-out app can still get a fix.
3. **The phone** (`android/.../bundle/`, plugin `AppBundle`). `check()` asks for the manifest and
   compares: the server's version is the target, whatever it is — no "newer than" (a revert on
   the server takes the phone back, to the APK's own screens if that is what the server serves).
   It refuses a bundle that needs a higher native level, or another API address, and one that failed here
   before. A download is checked against the size and SHA-256, unzipped with every entry kept
   inside the folder, and its `bundle.json` must name the same version and a level the APK has. It then waits
   (`staged`) in `files/bundles/<version>/`.
4. **Switching.** On the next cold start the plugin's `load()` — which runs before the WebView
   loads — promotes the waiting bundle and points Capacitor at it. It also switches when the app
   comes back after 30 min away with nothing open on top (no "+ Novo" half typed), and from
   Ajustes › Versão do app.
5. **Rollback.** A new bundle opens on trial and must call `ready()`, which the screen does in an
   effect after its first render (`main.jsx`). No `ready()` in 30 s → back to the APK's screens at
   once; killed twice before `ready()` → the same at the next start. A version that failed is
   never downloaded again. Ajustes › Versão do app also has "Voltar à versão do APK". A new APK
   wipes every downloaded bundle (its own screens are newer), as Capacitor itself does.
6. **When to bump `native-level.txt`.** Whenever the screens start needing something the
   installed APK does not have: a Java change the JS calls (a plugin, a method, an event), a
   Capacitor or plugin upgrade, a permission. Bump it in the same commit. The level in
   `bundle.json` is the *minimum*: an APK at or above it opens the bundle, an older one keeps its
   screens and is offered the new APK (below).
7. **The APK from CI (option 2, built 2026-10-17).** A push that changes the Android project, the
   native level or Capacitor's config also runs the `apk` job (DEPLOY.md, "Updating the phone"):
   signed with the phone's key from the `android-release` environment, `versionCode = 10000 + run
   number`, published with `version.json` to `/apk/` on the server (tailnet only, `tailscale
   serve`). Plugin `AppUpdate` (`android/.../update/`) reads it; when it is newer than the
   installed APK the app shows "Nova versão disponível", downloads it (size, SHA-256, package,
   versionCode checked) and opens Android's installer, asking once for "Instalar apps
   desconhecidos". Installed over the old one, so the data stays.

Checked on the PC: backend tests, JVM tests of `BundleRules` and `ApkUpdateRules`, node tests of
`appBundleRules`, a local image serving the manifest and a zip whose SHA-256 matches, and a local
release build signed with the key whose fingerprint CI checks.

## Phase 6 — Reading bank notifications (steps 1–4 and the debug half of step 7 built 2026-10-17)

Built: the listener, capture mode, the Ajustes screen, the debug build that accepts adb-posted
notifications, and **the parsers (step 4)**, written against the owner's first export (10
notifications): `notify/NotifyParsers.java`, run on every allowed notification; the parsed
fields go to the server's Aprovar (`DetectionQueue` → `DetectionWorker` →
`POST /api/inbox/detections`), which pairs bank × Samsung and the two legs of an own-account
transfer, and tells a transfer between the owner's accounts from a Pix to someone else by the
counterparty (`docs/done-tasks.md`, "Notification auto-identifier"). **Not built: the mapping
screen (step 5)** — Aprovar's remembered choices do that job — and **step 6**: unrecognised texts
stay on the phone. Open: more captures for the kinds not seen yet (Samsung Wallet's text above
all; see `docs/next-steps.md`).

Package names, each checked against its Google Play listing on 2026-10-12 (Samsung Wallet on
2026-10-17, through a web search of play.google.com: the store itself is unreachable from the
cloud session). Capture mode still has the last word on which app actually sends a card
notification.

| App | Package | Allow-list |
|---|---|---|
| Samsung Wallet (Samsung Pay) | `com.samsung.android.spay` | Yes again, later on 2026-10-17 (owner: used when the bank app does not notify a card purchase; the bank's notification wins when both arrive). |
| Itaú | `com.itau` | Yes. |
| Itaú Cartões | `com.itaucard.activity` | No, since 2026-10-17 (owner: duplicates `com.itau`). |
| Banco do Brasil | `br.com.bb.android` | Yes. |
| Ourocard | `br.com.bb.oewallet` | No, since 2026-10-17 (owner: duplicates `br.com.bb.android`). |
| BTG Pactual Banking | `com.btg.pactual.banking` | Yes. Card and account notifications come from here. |
| BTG Pactual Investimentos | `com.btg.pactual.digital.mobile` | Yes, since 2026-10-17 (owner: operations must be recorded from it too). Excluded at first; see "Brokerage notifications" below. |

The list lives in `NotifyRules.APPS` and in the manifest's `<queries>` (so the screen can tell
whether each app is installed); a JVM test fails when the two differ.

No reliable public source gives the wording of these apps' notifications; published examples
disagree with each other. Known variations the parsers must expect: the time as `14:30` or
`16h30`, a purchase in a foreign currency (`US 3,00`), and the card's product name before
"final 1234". Some Itaú cards send no push for purchases at all.

**Brokerage notifications** (owner, 2026-10-17): "I want the app to gather from BTG Pactual
Investimentos as well … when buying stocks and investments it should come out from the stock
exchange account." So the BTG investments app is on the allow-list, and a detection from it is an
*operation*, not a lançamento: a "Registrar operação" suggestion (ticker, buy/sell, quantity,
price, date) that comes out of the portfolio account (the Corretora account, built 2026-10-17)
— the existing cash link (`metadata.cash_account_id`), so the cost and the IR read the movement and the account
balance reads the linked lançamento, as when the form is typed by hand. Unknown until the captures: whether
the app notifies executions at all, and with which fields (fees, the nota de corretagem, are not
expected in a notification and stay editable). Money moving from BTG Banking to the brokerage is a
TRANSFER between two of the owner's accounts, never an expense or an aporte: a Pix/TED
notification whose destination is the brokerage account must become a transfer suggestion.

**One purchase, one entry.** Itaú Cartões and Ourocard were taken off the allow-list on
2026-10-17 (owner: "this apps will replicate expenses that exist in other apps"). Samsung Wallet
came back the same day as a fallback (owner: "samsung notification should be used when bank
notifications doesnt reach about card use"): a Samsung detection is held for a short window and
dropped if the bank's notification for the same purchase arrives, promoted otherwise. The rule is
built and JVM-tested, not yet wired to the listener (`notify/NotifyPairing.java`, 2026-10-18):
same purchase = Samsung on one side, a bank app on the other, same amount to the cent, a card
neither side contradicts (last 4, issuer), posted within the window (10 min, inclusive, to be
tuned from the captures); one-to-one, the closest in time. The bank wins: a held Samsung
detection is SUPERSEDED, a promoted one not yet confirmed gives its place to the bank's (same
`client_id`), a confirmed one makes the bank's MATCHED; only the bank's decline cancels a Samsung
detection. Every detection of a purchase carries the `groupClientId` of the first one, and that is
the entry's `client_id`. If the captures show a bank app itself notifying one purchase twice, that is still the parsers' problem.

How it was built (the steps below say what each one asked for):
- Java, in its own package `android/.../notify/` with its own plugin (`Notify`), not Kotlin in
  the outbox plugin: the project has no Kotlin set up, and the listener shares nothing with the
  outbox.
- `BankNotificationListener` drops any package off the list before reading anything. Today there
  is no parser, so **with capture off it stores nothing**; with capture on it writes each
  notification to `financas_notify.db` (`NotifyStore`): package, `android.title`, `android.text`,
  `android.bigText`, posted time, `Notification.when`, the key, channel, category, group-summary
  and ongoing flags, and **every textual extra** by its Android name (`android.subText`,
  `android.textLines`…), so a parser never needs a field the capture left out. The unique
  `dedup_key` (`NotifyRules.dedupKey`: SHA-256 of package, key and posted time, 64 hex characters,
  which fits the server's `client_id` format) makes the same posting read twice one row. That
  happens on purpose: when Android reconnects the listener (a new APK, the process killed) it
  reads the notifications still in the tray (`via = active`). On disconnect it asks for a rebind.
  The table keeps the newest 5,000 rows.
- Capture is off by default and switched in Ajustes › Notificações dos bancos. Texts leave the
  phone only through the export (JSON or text, Android's share sheet, from the app's cache); no
  upload, no third party, and `allowBackup="false"` keeps the table out of Google's backup.
- The screen shows whether access is granted, whether Android has the listener connected (the
  last connect/disconnect time), a button to Android's notification-access page (straight to the
  app's toggle on Android 11+), the "Permitir configurações restritas" steps (open by default
  when access is missing on Android 13+) with a button to the app's info page and who installed
  the APK, the count per app (and "não instalado"), the last 20 captured, export and delete.
- Debug half of step 7: the debug build is **another package**, `br.financas.app.debug` ("Finanças
  debug"), so it installs beside the real app and never over it. Only it accepts
  `com.android.shell` (`BuildConfig.DEBUG`; a JVM test pins that the release rule refuses it), and
  in a debug build the package name of every refused notification goes to logcat (tag
  `FinancasNotify`), to find the shell's real package if it is not `com.android.shell`. CI builds
  it next to the release APK, signed with the same key, and publishes it as
  `/apk/financas-debug.apk`, outside `version.json`; the debug app never offers the published APK.

1. *(Built, in Java — see above.)* A `NotificationListenerService`. It keeps only
   notifications whose package is on the allow-list and writes them to a native table, so nothing
   is lost while the app is closed. Stored per notification: package, `android.title`,
   `android.text`, `android.bigText` (preferred over `text` when present; it usually carries the
   full merchant name), posted time and the notification key.
2. *(Built.)* A capture mode, off by default: while on, every notification from an allowed app is kept
   verbatim in a list that can be exported from the phone. This is how the parser fixtures and the
   real package names are collected, and how a wording change is diagnosed later. The texts stay on
   the phone and the PC; they are never sent to a third-party service.
3. *(Built: Ajustes › Notificações dos bancos.)* A settings screen that sends the owner to Android's notification-access page and shows whether
   access is granted. Android 13+ blocks notification access for an app installed by opening the
   APK file on the phone, until "Permitir configurações restritas" is chosen in its app info (the
   option appears only after one refused attempt). An install over USB with `adb install` is not
   expected to trigger this, which is why Phase 5 installs that way; the screen explains the menu
   for the case where it does.
4. *(Next, after a week of capture.)* One parser per bank app, as pure
   functions with JVM unit tests built from the collected texts (they run on the PC, without a
   phone): amount, merchant, kind (credit, debit, Pix sent, Pix received, refund, declined), and
   card final digits when present. Declined purchases are ignored; refunds become an INCOME
   suggestion. Native, not JavaScript, because the parser runs when the notification arrives,
   with the app closed — Java like the listener unless Kotlin is set up first. Once parsers exist
   the listener hands them every allowed notification, capture on or off. Rules for every parser:
   - match fragments (`R$ <valor>`, `em <local> às`, `Local: <local>`), never a whole sentence,
     so a changed preposition does not break it;
   - classify the negative kinds first (declined, refund, cancelled), before any keyword such as
     "compra" or "aprovada" can mark the text as a purchase;
   - anchor the amount to the purchase phrase, not to the first `R$` in the text: a message may
     also carry a balance or an available limit;
   - a text with an amount but no recognised merchant is still a detection, with the merchant
     left empty for the owner to fill.
5. A mapping screen: bank app plus kind (and card digits) to a card or account, and a default
   category for each. Set once in the app and copied to native storage, so a detection can be
   completed with the app closed.
6. Unrecognised text from an allowed app still reaches the inbox with its raw text.
7. End-to-end tests without a real purchase: `adb shell cmd notification post -S bigtext -t
   "<title>" <tag> "<text>"` posts a notification through the normal path, so the listener
   receives it. It arrives under the shell's own package (`com.android.shell` on a stock build;
   a debug build logs the real value), so debug builds accept that package; release builds do
   not. *(Built: the debug half.)* Letting the test choose which bank parser to run (by the tag,
   say) comes with step 4.

Done when: a real purchase on each of the three banks appears in the native table with the right
amount and merchant.

## Phase 7 — Inbox and publishing (not started)

1. Backend: the three creation endpoints accept `auto_category: true` in place of a category, and
   resolve it with the import rules the statement preview already uses (the rule that matches the
   description, else the mapping's default category sent by the phone). One rule engine, on the
   server. Tests: a matching rule wins, the default is used otherwise, another user's rules are
   never read, and an explicit category is left alone.
2. "Compras detectadas": the list of detections, each pre-filled with card or account, date,
   amount and description. Online, the category shown is the server's suggestion.
3. Actions: confirm one, confirm all, edit before confirming, discard.
4. The app posts its own notification for each detection with Confirmar and Editar buttons.
   Confirmar is handled by a native `BroadcastReceiver`: it writes the entry to the native outbox
   with `auto_category` and schedules the sender. The app is not opened. Editar opens the form.
5. The `client_id` is derived from the notification (package, key and posted time —
   `NotifyRules.dedupKey`, already in the server's `client_id` format), so one notification can
   never become two lançamentos, whether it is confirmed from the notification or from the list.
   Open question for the captures: Android gives an *updated* notification a new posted time, so
   a bank that updates its notification would yield a second key. If the export shows that, the
   id has to come from the key and `Notification.when` (also captured) instead. With Samsung
   Wallet paired to the bank (Phase 6, "One purchase, one entry"), the id is the detection's
   `groupClientId` — the `dedupKey` of the first detection of the purchase — so confirming either
   notification writes once.
6. Discarded detections are remembered, so the same notification does not return.
7. A detection from the brokerage app (BTG Investimentos) becomes a "Registrar operação"
   suggestion, cash linked to the brokerage account; Confirmar writes it through
   `POST /api/investments` with a `client_id` (the endpoint does not take one yet — add it the
   same way as migration 024). See "Brokerage notifications" in Phase 6.

Done when: a purchase is recorded on the PC from the notification button alone, with the app
closed, in the category its rule gives.

## Phase 8 — Statement import dedup (not started)

1. `POST /api/import/preview` gains a third status next to `NEW` and `DUPLICATE`: a probable
   duplicate, for a row with no matching `source_id` but with an existing lançamento on the same
   account, date and amount. A tolerance of a few days covers a purchase that posts later.
2. The Importar screen shows those rows unchecked, next to the lançamento they match.
3. The same check for card statements against `cc_expenses`, where a purchase in installments
   matches on the installment amount.
4. Tests for each: exact match, date within tolerance, two same-amount purchases on one day (both
   must survive), and no match across accounts.

Done when: importing a month's statement after a month of notification entries adds only what
was missing.

## Phase 9 — Hardening and daily use (not started)

1. Exempt the app from battery optimisation and confirm the listener survives a reboot and a
   night idle (Ajustes › Notificações shows when Android last connected and disconnected it).
2. Confirm the sender's backoff when the server is unreachable, so the radio is not kept awake
   while the PC is off.
3. Confirm the PC side: the backend and `tailscale serve` start with Windows, and backups still run.
4. Bump the app version on every build and show it in Ajustes, so a stale APK is recognisable.
5. Two weeks of real use, logging every missed or mis-parsed notification, then a parser pass.
6. Write the routine into `docs/`: how to build and install, how to add a bank parser, what to do
   when a bank changes its wording.

Done when: two weeks pass with no lost purchase and no duplicate after a statement import.

## Not planned

- Offline edits and deletes, and offline investments.
- Receipt photos taken offline.
- Automatic publishing without confirmation.
- Benefit cards (VA/VR).
- iOS, and the Play Store.

## Verification (2026-10-12)

What the first draft claimed, and what checking found.

| Claim | Result |
|---|---|
| No manifest or service worker; `api.js` defaults to `http://localhost:5000` | Confirmed. |
| `config.py` defaults: `JWT_SECRET` dev value, `CORS_ORIGINS` `*`, `JWT_EXP_DAYS` 30; Flask on port 5000, localhost | Confirmed. |
| `transactions` has `source_type` / `source_id` under `idx_transactions_user_source`; `cc_expenses` has neither | Confirmed. |
| Next migration is 024 | Confirmed (highest is 023). |
| `POST /api/transactions` and `POST /api/cc-expenses/purchases` serve the four forms | Wrong. Transfers use `POST /api/transfers`. Phase 3 now covers three endpoints. |
| A unique index on `(user_id, client id)` for `cc_expenses`, shared by all installments | Contradictory: N rows cannot share a unique value. The index includes `installment_info`. |
| Mark offline rows with `source_type = 'OFFLINE_ENTRY'` | Replaced by a `client_id` column. `source_type` empty means "typed" to the export and the Extrato; a new value would have shown up as an origin. |
| `POST /api/import/preview` returns `NEW` and `DUPLICATE` | Confirmed (and `ERROR`). |
| The uncommitted work touches `NewEntrySheet.jsx`, `newEntry.js`, `Extrato.jsx` | No longer true. |
| Token lifetime blocks Phase 3 | It did not: it is a `.env` value. Now decided. |
| Package names of Itaú, BB and the two BTG apps | Confirmed on Google Play. |
| Itaú Cartões and Ourocard, unchecked | Both exist as separate apps: `com.itaucard.activity`, `br.com.bb.oewallet`. Added, then removed on 2026-10-17 (duplicates of the bank apps). |
| A sideloaded app on Android 13+ needs "Permitir configurações restritas" | True for an APK opened on the phone. Reported not to apply to `adb install`; not confirmed from a primary source, so the settings screen still covers it. |
| `adb shell cmd notification post` reaches a listener, from `com.android.shell` | The command and its flags are in AOSP and go through the normal enqueue call. The package is whatever Android maps the shell's uid to; `com.android.shell` is expected, to be read on the device. |
| The APK's origin, and calling `tailscale serve` | `https://localhost` (Capacitor docs). HTTPS to a public-CA certificate needs no extra configuration; MagicDNS and HTTPS must be enabled in the tailnet. |
| Confirmar "publishes without opening the app" through the WebView outbox | Could not work. See "Where the outbox lives"; Phases 4, 5, 6 and 7 were rewritten around a native queue and sender. |
| Category "suggested by the existing import rules" on the phone | The rules live on the server and the phone may be offline. Phase 7 moves the choice to the server (`auto_category`). |
| Explicit `CORS_ORIGINS` | Would have locked out the Vite dev server; `http://localhost:5173` added. |
| Phase 1 and Phase 4 "done when" | Both needed the phone. Each now has a check that runs on the PC first. |
