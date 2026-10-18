# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · Expense sharing (032) finished, checked, pushed

Owner: "finish last sessions work, it got interrupted, run checks on the changes it made and if
everything is green commit and push it to main". The interrupted session had built expense
sharing ("de quem é o gasto") but never committed it nor wrote its handoff. No session-scout
(the task was the working tree itself).

### Done
- Reviewed the uncommitted work and found it complete end to end: migration
  `032_expense_share.sql` (+ `schema.sql`), `services/sharing.py`, `routes/receivables.py`
  (`GET /api/receivables`, `POST /api/receivables/settle`), `PATCH /api/cc-expenses/<id>/share`,
  share fields on `PATCH /api/transactions/<id>`, the owner's-part rule (`own_amount_sql()`) in
  the budget and the monthly plan; frontend `lib/sharing.js`, `lib/cashFlow.js` (Início's cash
  flow moved out of `Dashboard.jsx`, with "Outras pessoas" apart), `ShareFields` in the Extrato
  edit, `CardShareSheet` from a purchase's menu in Cartões, the Lançamentos › A receber page.
- Checks: **1126 pytest passed** (`test_expense_share.py` included), **73 node tests**, `vite
  build` clean. Committed and pushed to `main` — which deploys the server (032 runs there) and,
  because the earlier unpushed commits touch `frontend/android/`, builds the new APK too.
- Docs: done-tasks row, CLAUDE.md (tests, convention), this handoff.

### Not done, and why
- **Not tried in a browser or on the phone**: the request was checks + commit; the screens were
  only built, not clicked through. Owner walk-through: Extrato → edit a despesa → "Dividida";
  Cartões → ⋯ → "De quem é?"; A receber → mark paid; Início's flow shows "Outras pessoas".
- Sharing is set only by editing; the "+ Novo" forms and Aprovar don't offer it (the previous
  session's design, apparently — nothing half-built for it).
- A receber's "paid" writes no money on purpose: the Pix the person sends is its own lançamento.

### Next
1. After the deploy: open A receber, Aprovar and Ajustes once to confirm 029–032 ran.
2. Install the new APK ("Nova versão disponível"), then one Pix between own accounts, one to
   someone else, one card purchase → check Aprovar (next-steps, first item).
3. Keep capture on; the next export drives a parser pass (Samsung first).

### From the notification session (2026-10-17), still open
- Not tried end to end on the phone; Samsung Wallet's purchase text never captured (its parser is
  a guess), same for credit/debit "final", declined, estorno, boleto, BTG Investimentos.
- Mapping screen (Phase 6 step 5) and raw-text-to-inbox (step 6): not built, on purpose.
- `schema.sql` still lacks the 028 tables and 031's columns (032 is in it).
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
