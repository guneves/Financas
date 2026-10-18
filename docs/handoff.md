# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · "Precisa de atenção" dismissable, header bell, theme in Ajustes

Owner: make "Precisa de atenção" closable so it does not show again, keep those notifications
under a new bell where the sun (theme toggle) was, and move the light/dark choice into Ajustes;
open a PR. Branch `claude/confident-cannon-ig2hze`. No session-scout (small, self-contained UI
task).

### Done
- `lib/attentionRules.js` (pure): the rules Início used inline — overdue invoices, the closed
  invoice, autopay shortfalls, pending recurrences, categories over budget — plus
  `attentionItems()`, which gives each item a `key` naming the case. `Dashboard.jsx` now calls
  these instead of its own copies (behaviour unchanged).
- Início: an X next to "Precisa de atenção · N" dismisses the items on screen (localStorage,
  `lib/attention.js`); the same case never returns to Início, a new one does (next month's
  invoice, a new overdue recurrence, another category or month over budget).
- Header bell (`components/Attention.jsx`, `AttentionBell`) in place of the theme toggle, desktop
  and phone: a count badge and a dropdown with every current item, dismissed or not, each linking
  to its screen (Cartões, Recorrentes, Orçamento). It runs Início's queries with Início's keys.
- Ajustes › Aparência: Sistema / Claro / Escuro (`setThemePreference`); `toggleTheme` removed.
- Checks: 80 node tests (7 new in `attentionRules.test.js`), `vite build` clean; clicked through
  with Playwright on a throwaway DB (desktop + 390 px): dismiss survives reload, bell lists the
  items, the theme switches from Ajustes.

### Not done, and why
- The bell's items are links, not actions: paying an invoice needs Início's pay sheet, so the bell
  sends you to the screen instead of duplicating it.
- Dismissal is per device (localStorage), like the theme; nothing goes to the server.
- No backend change, so pytest was not re-run.

### Next
1. Owner: try it on the phone after merge (the bell on the narrow header; the APK gets it with the
   next screen bundle — no native change, no native-level bump).
2. Carry on with next-steps' first items (the phone checks, Aprovar walk-through).

### From the expense-sharing session (2026-10-18), still open
- Sharing not walked through in a browser or on the phone: Extrato → edit a despesa →
  "Dividida"; Cartões → ⋯ → "De quem é?"; A receber → mark paid; Início's flow "Outras pessoas".
- After the deploy: open A receber, Aprovar and Ajustes once to confirm 029–032 ran.
- Install the new APK, then one Pix between own accounts, one to someone else, one card
  purchase → check Aprovar; keep capture on, the next export drives a parser pass.

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
