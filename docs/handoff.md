# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · Aprovar × Recorrentes (034)

Owner: "Aprovar should work along with recorrentes: if a notification of a purchase of a monthly
subscription or of my salary comes up, flag that it will update my recorrentes as done if I approve
the lançamento", then "make a PR when done". No session-scout (context read directly).

### Done
- **Migration `034_recurring_settlements.sql`**: `recurring_settlements` (recurrence, occurrence
  date, the lançamento that made it, the inbox item) and `inbox_items.recurring_off`.
- **`services/recurring.py`** (new): the recurrences' calendar, `/run`'s materialization, pending
  count and forecast moved out of `routes/recurring.py` unchanged, because `services/inbox.py`
  needs them and a service cannot import a blueprint. Plus the new rule: `suggest_for_item()`,
  `settle_occurrence()`, `advance_past_settled()`. `/run` skips a settled date, pending count and
  forecast leave it out.
- **Matching**: same type (outflow/card → EXPENSE, inflow → INCOME, transfer never), an open
  occurrence within 7 days, and exact amount, or ±20% when a description word or the category
  matches; an INCOME ±20% even without the name (the salary Pix carries the employer's name, not
  "Salário"). Name match beats exact amount, then the closest date.
- **Approve** writes the notification's lançamento (real amount, card/account) and settles the
  occurrence; with the import default category it takes the recurrence's. "É este" on an existing
  manual lançamento settles too. "Não é esta" on the item (PATCH `recurring: false`) holds for
  "Aprovar todos"; an explicit `{recurring_id, date}` is validated before anything is written.
- **Screen**: Aprovar's card shows "Recorrente: ao aprovar, "Netflix" de 05/10 fica como feita em
  Recorrentes" with "Não é esta" / "Desfazer"; Decididos shows "Marcou … como feita".
- Checks: 1164 pytest passed (22 new in `test_inbox_recurring.py`), 76 node tests, `vite build`
  clean.

### Not done, and why
- Not clicked through in a browser or on the phone. Walk-through in next-steps ("Aprovar ×
  Recorrentes, what is left").
- An occurrence `/run` already wrote is matched only at the exact amount (existing candidates); a
  new price gives a second lançamento. Deciding whether Aprovar should replace the `/run` row is
  the owner's call.
- The recurrence's amount is not updated after a price change; a deleted approved lançamento does
  not reopen the occurrence (same as a `/run` row today).
- The previous session's open items (card refund walk-through, estorno from Aprovar) still stand.

### Next
1. After the deploy: open A receber, Aprovar, Ajustes, Cartões and Recorrentes once to confirm
   029–034 ran.
2. Owner walk-throughs: this one, the card refund (Cartões → ⋯ → Registrar estorno), Início's
   daily tile, and the sharing ones.
3. Install the new APK, then one Pix between own accounts, one to someone else, one card purchase
   → check Aprovar.

### Learned
- `routes/recurring.py` had the whole calendar; anything outside that blueprint wanting it now
  imports `services.recurring`. `recurring_pending_count()` takes `(conn, user_id, row, today)`.
- In this cloud container there is no `.venv`; the suite ran from a venv in the scratch area.


### From the notification session (2026-10-17), still open
- Not tried end to end on the phone; Samsung Wallet's purchase text never captured (its parser is
  a guess), same for credit/debit "final", declined, estorno, boleto, BTG Investimentos.
- Mapping screen (Phase 6 step 5) and raw-text-to-inbox (step 6): not built, on purpose.
- `schema.sql` still lacks the 028 tables and 031's columns (032 and 033 are in it).
- TWR: Tesouro mark-to-market, the 12-month window definition (owner to decide), AMER3 not added.
- `adb` is at `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`; the installed app is the
  release build, so `run-as` can't read `financas_notify.db` — captures come from the owner's
  export.

### Learned from the capture
- **BTG puts the message in `android.infoText`**; title/text/bigText are empty. Anything reading
  BTG must read extras.
- **BTG posts each purchase twice**, 24 ms apart, same `Notification.when`, different posted time
  → two dedupKeys. The server's `_repeated_posting()` handles it.
- BB's Pix notification is a **group summary** with the full text; summaries cannot be skipped.
- Pix texts carry the counterparty's masked CPF (`***.378.195-**`, `XXX.378.195-XX`) on Itaú and
  BTG, and the destination institution on BB — that is the own-vs-external signal.
- The phone's time zone is `America/Bahia` (UTC−3, no DST).

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
