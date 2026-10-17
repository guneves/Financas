# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (late) · BTG Investimentos on the notification list; the portfolio account; proventos into it; Corretora balance only in Investimentos

The owner asked how to check the notification gatherer (answered: Ajustes › Notificações dos
bancos; the phone now has the new APK and capture works), how to make captures change balances
(answered: Phase 6 steps 4–5 and Phase 7, after the week of capture), and then asked for the BTG
investments app to be read too, with every operation later recorded automatically and paid from
the brokerage account.

### CI/CD broken by `38b9877`, rolled back
`38b9877` ("Repo publico") moved the server address into Actions secrets `DEPLOY_SERVER` /
`APP_API_BASE` that were never created: GitHub hands an empty string for a missing secret, the
Dockerfile's guard (`APP_API_BASE nao informado`) failed the image and the apk job, and nothing
reached the server or the phone from `38b9877` through `fc495a0`. The owner asked for a rollback:
`deploy.yml`, `Dockerfile`, `deploy.ps1` and `mobile/build-apk.ps1` are back to `38b9877^` (address
in the code again; it was in the public history anyway) and DEPLOY.md says so. The rest of that
commit (docs without the owner's data) stays.

### Done
- `com.btg.pactual.digital.mobile` ("BTG Investimentos") added to `NotifyRules.APPS` and the
  manifest `<queries>`; `NotifyRulesTest` no longer asserts it is refused. JVM tests green
  (`gradlew :app:testDebugUnitTest --tests "br.financas.app.notify.*"`). CI will publish a new APK
  because `frontend/android/` changed; the owner installs it by "Nova versão disponível".
- The plan for brokerage operations written down: `mobile-docs/steps-to-production.md`
  ("Brokerage notifications" in Phase 6, step 7 in Phase 7) and two items in `docs/next-steps.md`.

- **The portfolio account** (owner: "I need to link at least one account to my investment
  portfolio and every transaction I make there will come out of this account, except the ones I
  click the flag to not discount from anywhere"). A Corretora (`BROKERAGE`) account is the
  portfolio's; every new operation comes out of it (sale/redemption into it) unless "Não
  descontar de nenhuma conta" is ticked (`cash_account_id: null`). Backend default for a POST
  without the key (`portfolio_cash_account_id()` in `services/investments.py`); the screens
  always send the key and refuse a new operation until one exists (`lib/portfolioAccount.js`);
  Ajustes › Contas has "Vincular à carteira" (PATCH type) and a "Carteira" badge. CLAUDE.md's
  cash-link convention rewritten. Backend 1042 passed, node 53. Clicked through with Playwright
  at 390 px on a scratch database: refused without the account, linked from Ajustes, a buy took
  R$ 200 from the account, a flagged buy wrote nothing, no console errors.

- **Paid proventos into the portfolio account** (owner: "proventos paid should go to the account if
  there is any"). `services/proceeds_cash.py`, materialized on read like débito automático; only
  proventos paid from the day the account became Corretora (`metadata.portfolio_since`), because
  the balance typed in Ajustes already holds the older ones and StatusInvest brings years of
  history. Locked in the Extrato as "Provento". 8 tests; backend 1050 passed. No screen walk for
  this part (one label and the edit lock in the Extrato).

- **Corretora balance only in Investimentos** (owner: "the reais amount in the corretora type
  account should be shown only in investimentos area, make sure all past changes work on the phone
  app as well"). Rules in `lib/transactions.js` (see CLAUDE.md, the portfolio-account convention).
  Walked at 390 px on a scratch database: Início R$ 4.580 = 5.000 − 300 to the brokerage (shown as
  Aporte) − 120; Extrato header the same; Posição "Saldo na corretora" R$ 1.100; Ajustes "Em
  Investimentos"; no console errors. Phone: the APK's screen bundle builds at native level 2 (the
  phone's APK runs level-2 screens: its Notificações screen works), `test_app_bundle.py` green;
  nothing native changed except the BTG Investimentos allow-list, which reaches the phone only
  with the next CI APK. Nothing pushed yet: the owner has not said to push.
- Decision: rows inside a Corretora account still list in the Extrato's accounts view (only the
  balance is hidden); the owner may want them moved to Extrato › Investimentos.

### Not done, and why
- **No native-level bump**: no screen calls anything new; the screen's list of apps comes from
  `Notify.status()`, so an older APK just lists one app fewer.
- **No parser or operation suggestion**: nothing to write it against until the captures show
  whether, and how, the BTG investments app notifies an execution.
- **"Automatically"**: the standing decision is "Always confirm". Kept; flagged as the owner's call
  in next-steps.
- **Portfolio account, decisions taken without asking** (say so if wrong): the link is the account
  *type* Corretora, not a new column — no migration; with several Corretora accounts the default
  one, then the name, is the default and the form lets the owner pick another; the API without a
  Corretora account still writes nothing (strict refusal would break 80 test POSTs and the
  seeds — the screens are where the "need at least one" rule is enforced); proventos still do
  not touch the account (since built, below the line: paid ones do); operations recorded before
  today keep their own setting.
- **Open trap for the owner**: a *historical* operation typed now (a 2023 buy, to rebuild the
  portfolio) also comes out of the account unless "Não descontar de nenhuma conta" is ticked —
  unlike proventos, operations have no "since" date. Asked the owner whether the form should tick
  the box by itself for dates before the link.

### Learned
- Gradle on this PC needs `JAVA_HOME` = Android Studio's `jbr` and `ANDROID_HOME` =
  `%LOCALAPPDATA%\Android\Sdk`; neither is set in the shell.
- `POST /api/investments` does not take a `client_id`; a notification-confirmed operation needs one
  (024's shape) so a double tap cannot buy twice.

### Carried (Phase 6 on the phone, still open)
1. Done by the owner: the real app updated, access granted, capture working ("it is working").
   The next APK (BTG Investimentos on the list) must be installed the same way.
2. Test APK from the PC: `curl -fLO https://<server>.<tailnet>.ts.net/apk/financas-debug.apk`,
   `adb install -r financas-debug.apk`, grant access, capture on, run the adb command on its
   screen; the notification must show under "Teste (adb)" there and not in the real app. Then
   `adb uninstall br.financas.app.debug`.
3. Capture on in the real app for about a week (Samsung Pay on each card, debit, Pix both ways,
   estorno, a declined purchase), then "Exportar JSON". Decide first whether fixtures may go into
   the repo verbatim. Next coding session: Phase 6 step 4 against that export, . Samsung Wallet,
   Itaú Cartões and Ourocard are off the allow-list (2026-10-17), so no cross-app pairing.

### Carried from the investments check (2026-10-17 night) and earlier, still open
- After the deploy, open IR 2025 again on the server (next-steps, "Investments check"); the
  owner's decisions listed there (brapi 1 ticker/request, ETF code 07.09, units, isentos line 18).
- After 2026-10-19, check the first workflow run on Ubuntu 26 is green.
- Mobile Phase 5's last phone checks (app swiped away + offline), against the server.
- The remaining self-update cases (offline queue across a switch, the native-level bump of
  `e340d1c`, the 30 s fallback). The rclone backup, if the owner wants help.
- Walk-through of Extrato → Investimentos and Proventos → Atualizar, on the server.
- Nothing enforces the native-level bump: it is a rule in CLAUDE.md.

### Learned earlier (investments check)
- The seed (`seed_three_years_mock.py`) and the API store a sale with the **sale price** in the
  price column; the screen stores the position's average there. Any cost read from that column
  was wrong for one of them — hence the server-side average cost.
- A full-page screenshot scaled down can turn "0,00" into "0.00": read the cell text before
  calling it a formatting bug.
- From the cloud container: gov.br, planalto, Receita's normas site, Play Store and dl.google.com
  are blocked (WebFetch fails to resolve them too); WebSearch works for citations.
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
