# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · Phone layout pass (sizing) and "45,90 or 45.90"

Owner: "My phone is connected, check the screens and improve button sizing and information
sizing, do a few tests to check if everything works, insert data to analyse graphs". Mid-session:
"make the saldo em conta bubble overall smaller", "centralize the bottom buttons, the + should be
at the exact middle", "',' and '.' should be accepted when typing R$45,90 in lançamento".
session-scout ran by `subagent_type` (worked).

### Done
- **Início's balance block on the phone** (`BalanceHero`, `Dashboard.jsx`): ~430 → ~260 px tall at
  360 px. Below `sm`: number 38 px (56 above), month flow as one wrapped line of "Receitas R$ …"
  text instead of a pill per figure, accounts in one horizontally scrolling strip. `sm`+ unchanged.
- **Bottom bar**: five equal grid columns, the "+" at the exact middle (180 of 360). The two long
  names didn't fit a 72 px column ("Investimentos" needed 72 px with no gap), so the bar shows
  `shortName` — "Planejar", "Investir" (`lib/navigation.js`); everywhere else keeps the full name.
- **Section tabs scroll the active tab into view** (`Tabs`, `ui.jsx`): opening Proventos, IR or
  Alocação left the active tab off-screen. Scrollbar hidden (the cut-off tab is the hint).
- `PageHeader` title `text-2xl` below `sm`; `SummaryPanel` `p-4`, lead 32 px.
- `.app-input` / `.app-select` `min-h-11` below `lg` (were 42 px); AportesChart's "Ocultar" 44 px.
- **Money fields in lançamentos accept comma and dot**: "+ Novo" (despesa, receita, transferência,
  cartão), the Extrato edit and Aprovar's amount are `type="text" inputMode="decimal"` parsed by
  `parseMoneyInput()` (`lib/monthlyPlan.js`) — "45,90", "45.90", "1.234,56", "R$ 45,90".
  `changesFromDraft()` (`lib/inboxRules.js`) uses it too, with tests.
- Checks: pytest 1172 passed; node tests 84 passed; `vite build` clean. On the phone (Galaxy S25,
  360×780 dp, Chrome): typed "45,90", "45.90" and "R$1.234,56" in "+ Novo" with the real keyboard
  → stored 45.90, 45.90, 1234.56.

### How the phone was driven (reusable)
- Throwaway DB in the session scratchpad: `DATABASE_PATH=<scratch>/demo.db`, signup
  `demo@local.test`, then `scripts/seed_three_years_mock.py demo@local.test` (3 years, ~15 s; it
  wrote its pre-wipe copy to `backend/backups/finance-pre-mock-20261018-121425.db` — a copy of the
  empty demo DB, gitignored, safe to delete). `vite build` + `python app.py` with that env.
- `adb reverse tcp:5000 tcp:5000` → the phone's Chrome opens `http://localhost:5000`.
  `adb forward tcp:9222 localabstract:chrome_devtools_remote` → DevTools protocol from Node 24
  (global `WebSocket`): set `localStorage['@financeMVP:auth']`, navigate, measure, screenshot
  (`Page.captureScreenshot`; a `clip` beyond the viewport comes out garbled on the phone — scroll
  and shoot the viewport instead).
- Git Bash rewrites a `/path` argument into `C:/Program Files/Git/path`: `MSYS_NO_PATHCONV=1`.
- The release APK can't be pointed at the PC (https-only API base, server bundle), so this checks
  the same screens in Chrome, not the APK shell.

### Not done, and why
- Not deployed: committed only, not pushed (a push to `main` deploys).
- Other money fields are still `type="number"` (Metas, Orçamento, Recorrentes, Ajustes › Contas'
  initial balance, ShareFields' others' part, Extrato's min/max filter, the investment forms).
  The owner asked about lançamentos; the same `parseMoneyInput()` swap applies to each.
- Seen but left: Início's attention cards are tall (icon block + title + link, ~170 px each);
  benchmark cards in Rentabilidade that are "indisponível" still take a full card each; charts
  are 286 px wide (page gutter + panel padding). Rentabilidade took ~19 s today because the BCB
  (CDI/IPCA) timed out — not a screen problem.

### Carried from the Orçamento lines session, still open
- Not clicked through in a browser — only built and tested.
- Lines are read-only; tapping one does not open it in the Extrato/Cartões (no deep link to a
  single lançamento exists yet).

### Carried from the 034 session (Aprovar × Recorrentes), still open
- Not clicked through. An occurrence `/run` already wrote is matched only at the exact amount; a
  recurrence's amount is not updated after a price change; a deleted approved lançamento does not
  reopen the occurrence.
- After the deploy: open A receber, Aprovar, Ajustes, Cartões and Recorrentes once to confirm
  029–034 ran. Owner walk-throughs: Aprovar × Recorrentes, card refund, Início's daily tile,
  sharing. Install the new APK, then one Pix between own accounts, one to someone else, one card
  purchase → check Aprovar.
- `services/recurring.py` holds the recurrences' calendar now (moved out of `routes/recurring.py`).

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
