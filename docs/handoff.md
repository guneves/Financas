# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-11-04 · Notifications + Pluggy, session 2 of 5: Phase 2 (open the gate)

Branch: **`claude/notify-pluggy-phase2`**, from `claude/notify-pluggy-phase1` at `e951311` (Phase 1a +
1b), merged with `origin/main` (already up to date). Pushed, not merged, no PR. Session 3 starts from it
(`docs/prompts/notify-pluggy/03-*.md`).

**Done**
- **Server policy** (`services/inbox.py`): `BANK_APPS`, `NOTIFICATION_POLICY` (the three banks: every
  kind in `KIND_SHAPES` + `DECLINED`; `BROKERAGE_APP`: only `MOVEMENT_KINDS`), `INVESTMENT_TEXT` +
  `is_investment_text()`. `notification_wanted(detection)` keeps its signature and stays pure: Flash
  rules unchanged, then the table, then investment words on a Pix/TED (merchant and counterparty) and on
  everything from the brokerage app, never on a card purchase's merchant. The word list allows plurals
  (`dividendos`, `proventos`, `resgates`, `aplicações`), a small step beyond the prompt's list, because
  the banks write plurals.
- **The brake**: `config.BANK_NOTIFICATIONS_DEFAULT` (env, on); `inbox.bank_notifications()` /
  `set_bank_notifications()` (`user_settings` key `bank_notifications`); in `ingest_detection()` right
  after `notification_wanted()`, a non-Flash detection with it off answers `ignored` and writes nothing.
  `GET/PATCH /api/inbox/settings` returns and accepts it (booleans only, 400 otherwise).
- **APK**: `NotifyRules.APPS` + manifest `<queries>` get `com.itau` "Itaú", `br.com.bb.android` "Banco
  do Brasil", `com.btg.pactual.banking` "BTG Pactual", `com.btg.pactual.digital.mobile` "BTG
  Investimentos" (`BROKERAGE_PACKAGE`). `accepts()` unchanged (Samsung stays Flash-only).
  `NotifyParsers.parse()`: invoice payment → null before `kindOf()`; the brokerage package → null for
  anything but `PIX_*`/`TRANSFER_*` and for investment words; `Parsed.international` (internacional,
  exterior, US$, USD, EUR, €, £) and `"international": true` in `toDetection()` only when true.
- **Ajustes**: APK, a checkbox "Avisos dos bancos" at the top of Notificações do celular (renamed from
  "Notificações do Flash"; description rewritten), via `InboxRepository.setBankNotifications()` and
  `InboxSettingsDto.bankNotifications` (default true). Web: new `pages/ajustes/AvisosSection.jsx`
  ("Avisos do celular", chip in the header), rule in `lib/bankNotifications.js` (missing field = on).
- **CLAUDE.md**: "Open Finance is the only banking source" is now "Notifications are fast, Pluggy is
  the record", with the policy table and the brake; "Phone notices of banks are ignored" and the
  Flash-only sentences are gone. "Only the Flash is typed" and Rende Fácil's `ignored` are kept.

**Tests**
- `test_notification_policy.py` (renamed from `test_flash_only.py`; 150 cases): every Flash case kept,
  plus `TestThePolicyTable` (each bank app's kinds, an Itaú debit recorded at once, the brokerage app's
  non-transfer kinds and "ordem de compra" ignored, its transfers accepted, its investment transfers
  ignored, a brokerage `TRANSFER_IN` recorded as a transfer into the Corretora, Samsung with BTG/Itaú/
  Ourocard ignored, unknown apps ignored), `TestInvestmentWords` (Pix to TESOURO DIRETO etc. ignored and
  no trace, card purchases at FUNDO DE QUINTAL BAR / TESOURO DO MAR RESTAURANTE / RESGATE PET SHOP / CDB
  MOTOS accepted, word boundaries, Rende Fácil still ignored), `TestTheSwitch` (default on, booleans
  only, per user, off leaves no trace for every bank app including an old APK's `PURCHASE`, the Flash
  passes when off, switching on records nothing old, env default off and on). No
  `any_bank_notifications` in that file.
- JVM: `NotifyRulesTest` `banksAreHeard`, `banksHaveTheServersNames`,
  `samsungWalletWithABankCardIsStillRejected`; `NotifyParsersTest` `aBrokerageOrderIsNotAMovement`,
  `aBrokerageTransferIsAMovement`, `theBrokerageNeverSendsInvestmentWords`,
  `anInvoicePaymentIsNeverAMovement`, `anInternationalPurchaseIsFlagged`,
  `foreignCurrencyIsInternational`, `aDomesticPurchaseSendsNoInternationalFlag`,
  `aBankPurchaseAtFundoDeQuintalIsParsed`, `samsungWithABtgCardIsStillRejected`.
- Node: `lib/bankNotifications.test.js`.
- Results: backend full suite green in 4 sequential chunks of files (one process for all ~1700 tests
  runs out of memory on this PC); `npm test` 227 green; `gradlew testDebugUnitTest assembleDebug` green
  locally (561 JVM tests); android-check on the pushed branch: see the commit/push note below.

**Not done, and why**
- `ignore_notifications: true` is still sent by `GET /api/open-finance/settings` (an old APK reads it;
  the current APK ignores it). Left as it is: removing it is not part of this phase.
- `NotifyPairing.issuerOf()` (phone-side Samsung pairing) doesn't know the brokerage package. Not needed:
  Samsung is Flash-only and the brokerage app sends no card kind.
- No real captured text yet for the brokerage app or for an invoice payment notice; the parser cases use
  the prompt's texts. If a real one slips through, capture it (modo captura) and adjust the parser.

**Next**: session 3, Phase 3 (investments Pluggy-only), starting from `claude/notify-pluggy-phase2`.

### For the final verification
- **Riskiest**: the gate is open by default once this ships. Every bank notice now reaches the Phase 1
  engine on real data; succession, absorb and the near match carry the weight. Run
  `scripts/check_identity.py` after a week.
- The investment-word filter applies to every Pix/TED of the three banks too (the design's server
  rule). A Pix to a person whose name contains a listed word as a whole word ("Resgate", "Provento") is
  ignored; Pluggy still brings it. Plurals are included on purpose.
- The APK's invoice-payment filter ("fatura" plus pagamento/pago/paga/quitada) could drop a purchase
  notice that mentions both (none seen). Pluggy still records it.
- **Tests changed**: `test_flash_only.py` → `test_notification_policy.py`. `TestOnlyFlashPasses`
  (banks ignored) is replaced because the rule changed (design §4, decisions 2 and 5):
  `test_a_bank_app_claiming_to_be_flash_is_ignored` became
  `test_a_bank_app_claiming_to_be_flash_follows_the_bank_rules`;
  `test_it_does_not_depend_on_the_old_setting_or_on_a_mapping` and `test_a_resend_is_still_ignored` are
  gone (they asserted banks are ignored). JVM `banksAreDroppedOnThePhone` → `banksAreHeard`, same reason.
  `test_auto_record.py`, `test_inbox*.py` and `test_card_debit.py` are unchanged.
- **Not tested**: real notices on the phone (needs the merged APK); the web section was built
  (`vite build`) but not opened in a browser; the APK switch was compiled, not run on a device.

Lessons:
- On this PC the full backend suite in one pytest process gets killed for low memory; run it in
  chunks of files (the session's scratch `chunks.sh` split `tests/test_*.py` in 4).
- A Bash heredoc turned `\b` in a Python string into a backspace character in `inbox.py`; write edit
  scripts with the Write tool, and grep for `$'\b'` after a scripted edit.
- Session 1's branch was not pushed when this session started, though its handoff said so. Check
  `git log origin/<branch>` before merging it.
