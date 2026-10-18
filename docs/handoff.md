# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-17 (late) · Notification auto-identifier, v1 (session financas-78)

Owner: "check its notification history and the notifications recorded on the app to create the
first version of the transactions auto identificator, that will identify and insert under approve
every notification that refers to a transaction, make sure to recognize when a transaction is
made between my accounts and with external accounts"; then "every transaction identified through
a notification should end up in aprovar"; and "samsung wallet only handles card payments, it must
serve as a fallback … in case of a duplication, use the own banks notification". session-scout
ran directly (no fallback needed).

### Done
- **Phone** (`frontend/android/.../notify/`): `NotifyParsers.java` (pure, 17 JVM tests built from
  the owner's export with names/CPF swapped), `DetectionQueue` (`financas_detections.db`),
  `DetectionSender` + `DetectionWorker` (WorkManager, app closed; also scheduled at login from
  `OutboxPlugin.setSession`). `BankNotificationListener` parses every allowed notification,
  capture on or off. Only parsed fields leave the phone. No native-level bump (no screen calls
  the new Java). `gradlew testDebugUnitTest compileReleaseJavaWithJavac` green, 91 JVM tests.
- **Server**: migration `031_notify_counterparty.sql`; `services/inbox.py` learns "it's me"
  (`self:doc:` / `self:name:` hints) from paired legs and approved transfers, drafts a single leg
  to the owner as a TRANSFER (other side from the cited institution), a Pix to someone else as
  despesa/receita "Pix para/de <nome>" (`external_transfer`), never pairs legs with different
  counterparties, drops a bank's repeated posting (`repeated`), and no longer matches a detection
  to an existing lançamento without an Aprovar item. `test_inbox_counterparty.py` (15);
  one `test_inbox.py` case rewritten for the new "always Aprovar" rule. 1099 pytest green.
- **Second export** (`Downloads\notificacoes-20261017-232518.json`, owner: "the transferencia was
  from the btg banking account to the btg investimentos app"): BTG Banking's "Sua transferência
  de R$ 5,08 foi confirmada." was dropped by v1 (no direction word) — "confirmada" now means
  outgoing; BTG Investimentos' "Recebemos sua transferência…" is TRANSFER_IN. Server: a transfer
  seen by the brokerage app is always the owner's own (`BROKERAGE_APP`), other side BTG Banking.
  2 more parser tests (19), 2 more server tests.
- **Frontend**: `lib/inboxRules.js` — the `external_transfer` reason text and the counterparty in
  a source's line (66 node tests green).
- Docs: CLAUDE.md, next-steps (Phase 6 rewritten; the "automatic vs confirm" decision closed —
  the owner's "insert under approve"), done-tasks, mobile-docs Phase 6.

### Follow-up, same day (session financas-5e): Pluggy out of the migrations
Owner: "take down all pluggy mentions in the database", done after deploy `39088581530` applied
029. `027_reserved.sql` / `029_reserved.sql` are comment-only and **keep their numbers** (a
database that applied them skips any new file with that number); `028_inbox.sql` lost its Pluggy
lines; `030_reserved_names.sql` renames the 027/029 rows in `schema_migrations`. Checked with
`db.init_db()` from the old migrations and from scratch. One comment word stays inside the stored
`CREATE TABLE inbox_items` on old databases (a rebuild isn't worth it). Committed together with
this session's work, as the owner asked.

### How the phone was read
- `adb` is not on PATH: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`. The phone
  (SM-S931B) is connected; the installed app is the **release** build, so `run-as` cannot read
  `financas_notify.db`. `dumpsys notification` keeps no text in its archive, and Android's
  notification history is not readable without root. The share sheet has no local-save target.
  The owner exported the JSON by hand to `Downloads\notificacoes-20261017-225528.json` — that is
  the source. It is not in the repo.

### Learned from the capture
- **BTG puts the message in `android.infoText`**; title/text/bigText are empty. Anything reading
  BTG must read extras.
- **BTG posts each purchase twice**, 24 ms apart, same `Notification.when`, different posted time
  → two dedupKeys. The server's `_repeated_posting()` handles it.
- BB's Pix notification is a **group summary** with the full text; summaries cannot be skipped.
- Pix texts carry the counterparty's masked CPF (`***.378.195-**`, `XXX.378.195-XX`) on Itaú and
  BTG, and the destination institution on BB — that is the own-vs-external signal.
- The phone's time zone is `America/Bahia` (UTC−3, no DST).

### Not done, and why
- **Not pushed.** A push to `main` deploys the server and builds a new APK (the `apk` job runs on
  `frontend/android/` changes); left for the owner to say so.
- **Not tried end to end on the phone**: needs the new APK. The parsers ran only on the JVM.
- Samsung Wallet's purchase text was never captured (only its "Instalando…"): its parser is a
  guess (amount + "compra/aprovada", merchant from the title). Same for credit/debit with "final",
  declined, estorno, boleto, BTG Investimentos.
- Mapping screen (Phase 6 step 5) and raw-text-to-inbox (step 6): not built, on purpose (see
  next-steps).
- `schema.sql` still lacks the 028 tables and now 031's columns — drift that predates this.
- The server's `.env` may still hold `PLUGGY_*` lines (harmless).

### Next
1. Owner: push (or say so), install the APK by "Nova versão disponível", then one Pix between two
   own accounts, one to someone else, one card purchase → check Aprovar (next-steps, first item).
2. Keep capture on; the next export drives a parser pass (Samsung first) and the Samsung × bank
   window.

### Carried, still open
- After the deploy, open Lançamentos › Aprovar and Ajustes once to confirm 029–031 ran.
- Test APK from the PC (`/apk/financas-debug.apk`, `adb install -r`, capture, the adb command),
  then `adb uninstall br.financas.app.debug`. With the parsers in, an adb-posted text like
  `Você enviou R$ 1,00 para FULANO` now also produces a detection (app `com.android.shell`).
- IR 2025 on the server (next-steps, "Investments check"); the first Ubuntu 26 workflow run after
  2026-10-19; Mobile Phase 5's last phone checks; the remaining self-update cases; Extrato →
  Investimentos and Proventos → Atualizar walk-through. Nothing enforces the native-level bump.

### Learned earlier, still true
- `pytest -q` here prints no summary line; `-o addopts=""` brings back "N passed".
- In PowerShell 5.1 a javac "deprecated API" note on stderr shows as an error; check the exit code
  from bash.
- Several Claude sessions share this tree: claim migration numbers by message before creating
  the file (030 collided this session), stage explicit paths, one committer.
