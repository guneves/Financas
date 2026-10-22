# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-22 · Hourly quotes, card débito, Flash and the second parser pass

Cloud session, owner request: "auto update renda variável prices every one hour, create the
function débito when creating a card, support Flash Benefícios notifications, use the JSON
(capture of 2026-10-22) to improve the other banks". Briefing from `session-scout` (worked by
`subagent_type`). PR opened at the owner's request.

### Done
- **Hourly quotes.** `services/quote_refresh.py`: a daemon thread started in `app.py` calls
  `refresh_market_prices(user, force=True)` for every user each `QUOTE_AUTO_REFRESH_SECONDS`
  (3600, first run 60 s after boot; 0 = off, set in `conftest.py`). Quoted assets only (ações,
  FIIs, ETFs, BDRs, BTC); Tesouro keeps its own thread. `test_quote_auto_refresh.py`.
- **Card débito (041).** `credit_cards.debit_account_id` + `credit_enabled`. Ajustes › Cartões has
  "Funções: Crédito / Débito / Os dois" (create and edit); "+ Novo › Cartão" offers Crédito/Débito
  on a combo card and only débito on a debit-only card; a débito purchase is an EXPENSE in the
  card's account (outbox kind EXPENSE, so offline works as before). Debit-only cards are out of
  Cartões/Aprovar's card lists and refused by every credit path (`require_active_card()`). Rules in
  `lib/cardFunctions.js` (tested). `test_card_debit.py` (21).
- **Flash.** `br.com.flashapp` in `NotifyRules.APPS`, the manifest `<queries>`,
  `NotifyPairing.issuerOf()` and the server (`FLASH_APP`, issuer `flash`, alias "meal and
  voucher"). Aprovar: a purchase on a debit card (`debit_card_for()`) goes to its account; the
  Flash's purchase arrives as a despesa in the Flash account, confirmed once, then remembered.
- **Second parser pass** (60 notifications, `RunCapture` harness in the session scratchpad, not
  committed): Samsung's new format was **never** read before (title = card name, text "<LUGAR>
  R$ <valor>", U+00A0 after R$) — now PURCHASE with merchant and `card_name`; the server derives
  Samsung's issuer from the card name so it pairs only with the same bank. BB "Pix Recebido" now
  names the sender ("Que ótimo! <Nome>, CPF/CNPJ …"). Everything else in the export already parsed
  right; marketing, BTG portal access and the bitcoin receipt stay ignored. 12 JVM cases added.
- Checks: pytest 1493 green; `npm test` 144 green; `vite build` ok; JVM notify tests 73 green
  (compiled with javac + JUnit jars outside Gradle — the container has no Android SDK); Chromium
  screenshots of Ajustes › Cartões and "+ Novo › Cartão" (a débito save landed in the account).

### Not done, and why
- **No Flash app capture**, so no Flash-specific parser and no detection of the benefit credit
  (monthly deposit). The generic parser covers "compra … R$ … em …" texts. `next-steps.md`.
- **Flash package unconfirmed** (`br.com.flashapp`, from two third-party listings; Play Store not
  reachable from here). Ajustes › Notificações shows whether it is installed.
- A débito purchase does not record which card it was (plain EXPENSE). Not asked; noted.
- No B3-hours window for the hourly refresh (the owner asked for every hour); brapi quota risk
  noted in `next-steps.md`.
- `native-level.txt` not bumped: the screens call no new Java. The CI `apk` job runs anyway
  (`frontend/android/` changed), so a new APK is offered by "Nova versão disponível".
- Last sessions' open items (server/phone timing of saves, static files uncompressed,
  Rentabilidade's daily loop, the Planejar owner check) are still in `next-steps.md`.

### Learned
- The test DB is one per session: a test that loops over all users sees the users of earlier
  tests — assert on your own user's rows, not on totals.
- Java's `\s` does not match U+00A0; Samsung puts one after "R$". Normalize in `textOf()`.
- BTG posts "Compra autorizada" twice (~25 ms, different keys); the server's `repeated` rule
  already folds it.
- The refund route takes `purchase_date`, not `date` (a 400 for the wrong field looks like the
  rule you meant to test — assert the message).
- Never name a backend module after a stdlib one (carried from earlier handoffs).
