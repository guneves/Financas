# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-31 · Spending, anticipated installments, Pluggy feeds everything

Owner asked: spending near R$ 1.500 a month, the advanced installments gone from future invoices, a fresh validation of
everything against Pluggy, Pluggy as the only source (Flash typed), no Aprovar, then commit, PR and merge when 100%.

**Deployed and applied on production** (PRs #56, #57 and the follow-up; backup `/data/backups/finance-before-owner-fix-20261031-020024.db`).
A one-off script applied the owner's answers; no balance moved. Then a fresh Pluggy read, in production: every balance equal, BTG
Investimentos 1.808,75 with difference 0, November 1.467,59 (BB 18,19), nothing open after it, 14 payments = 14 bank rows, 37 October
movements (32 Pluggy, 2 bitcoin, 3 provisional), 0 position mismatches. Seen on the web: Início, Ritmo, Evolução 2.823,75, Parcelamentos
abertos 0,00, Ajustes without "Diferença", `/lancamentos/aprovar` lands on the Extrato. APK 10109 published; not seen on the phone.

Done, in code and rehearsed on a copy with a fresh Pluggy read:
- **Spending**: March–September 1.282,94 / 2.343,77 / 2.212,07 / 1.291,27 / 1.537,41 / 1.523,50 / 1.674,24. What inflated it:
  the Inter line (R$ 25.058,72, exactly the month's net moved into Inter, owner: not spending), BB fund rows
  (`BANK_INVESTMENT`), 2025 Pix to himself (now BB → Inter transfers plus three month lines), Wise rows in the Ritmo.
- **Installments**: Rota 3–6 and Ig 2–6 were charged in the October bill (R$ 237,16, proved to the cent); Pluggy still
  lists 7 of them `PENDING`. November stays 1.467,59; nothing open after it.
- **The 02:41 UTC duplicates**: the 11 `CC_AUTOPAY` rows of 10-28 had other amounts, `invoice_payment_link()` needs the
  same amount, so `record_bank_payments()` wrote a second, loose row. Fixed by `_kept_payment()`, tested.
- **BTG Investimentos**: the old code's `resync_investment_cash_dates()` moved AUPO11 back to D+2 when Posição opened. On
  the right day, cash today is 1.808,75 = the bank; R$ 884,00 (BBDC3) is in transit to 03/11, legitimately.
- **Father**, from the owner: 1.800, 900 and the 5.400 advance stay income (R$ 22.500); 50 other Pix (R$ 23.922,22) are
  repasses. "Best interpretation", as the owner asked: the owner can re-mark any row.
- Rehearsal: every balance, day-by-day statement and invoice match except what `next-steps.md` lists; 14 payments = 14
  bank rows, no doubles; 0 position mismatches. Remaining day differences are transfers dated by one side, same month.

**Not done:** the phone was not checked (the APK has to be updated for the dropdown and the Investir tab; balances and invoices
come from the server); eslint has no config file, so it cannot run (imports checked by script);
the APK compiled and its rule tests passed, not run on a device; the open items in `next-steps.md`.

Lessons: Pluggy's card lines don't always sum to the bill (check `GET /bills`, `billId` beats `billForecastDate`). An old
deployed read can undo a rebuild: `resync` runs on GET. `first_sync_days` limits test dates: a date too old is silently
not pulled, and a test on it passes empty.

CI runs in UTC: anything "local" must use BRT, never the machine's zone (the deploy of #56 failed on that test).

Next: the 09:10 UTC pull and the first real invoice payment, then read the Conferência.

Also: an invoice paid before closing settles when it is the exact amount on a known card (`_pick_invoice()`); the APK's section tab, tapped from a page inside its own section (Investir on Proventos), restored that same page and looked dead; it now returns to the section's entry (`ShellNav.reopensRoot()`, not tried on a device).
