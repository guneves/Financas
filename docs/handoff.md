# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-18 · Card refunds (033) and "Disponível por dia" from the plan

Owner: "make it so i can add a reinbursement to my card", then mid-session: "Disponível por dia
should be the amount left in gastar in orçamento divided by the days of the month", then "commit
and push to main when done". No session-scout (follow-up on fresh context).

### Done
- **Estorno no cartão** (migration `033_cc_refunds.sql`: `cc_expenses.kind` PURCHASE/REFUND +
  `refund_of`). `POST /api/cc-expenses/refunds` (card, amount, date, description, optional
  category/`refund_of`/`client_id`). Invoice rules in `services/invoices.py`: `signed_amount()`,
  `invoice_open_lines()`, `refund_invoice()`; `settle_invoice()` debits the net, settles a zeroed
  invoice without a lançamento, skips one in credit (manual pay → 409), and an earlier invoice in
  credit is absorbed by the next payment. Budget and monthly plan subtract refunds; candidates,
  the attachments sibling query and inbox matching ignore them; sharing a refund is refused.
- Frontend: Cartões › purchase ⋯ "Registrar estorno" (prefilled with the purchase's total,
  category and card) and an "Estorno" header button → `CardRefundSheet.jsx`. Refund rows show
  green "+R$", an invoice in credit shows "Crédito" with no Pagar. All card sums (Início, flow,
  projections, autopay warning, overdue) go through `cardSignedAmount()`.
- **Disponível por dia** (Início): `progress.spend_remaining` of the month plan ÷ days left in
  the month, today included. I read "divided by the days of the month" as the days *remaining* —
  a per-day allowance over the whole month's days would undercount every day after the 1st; flip
  `daysRemainingInMonth` in `Dashboard.jsx` if the owner meant all days. Without a plan the tile
  keeps the old rule (balance − next invoice) and its old caption.
- Checks: 1142 pytest passed, 74 node tests, `vite build` clean. Committed and pushed.

### Not done, and why
- **Not clicked through in a browser or on the phone** — only built and tested. Walk-through:
  Cartões → ⋯ on a purchase → Registrar estorno; check the invoice total drops; Início's daily tile
  with and without a plan.
- Aprovar's "estorno" detections still draft an INCOME lançamento, not a card refund. Wiring a
  card-final estorno into `CardRefundSheet`'s endpoint is the natural next step once a real
  estorno notification is captured.
- An installment purchase's refund is one credit in one invoice (what most banks do); cancelling
  the remaining installments instead is not offered.

### Next
1. After the deploy: open A receber, Aprovar, Ajustes and Cartões once to confirm 029–033 ran.
2. Owner walk-throughs above, plus the sharing ones still open: Extrato → edit a despesa →
   "Dividida"; Cartões → ⋯ → "De quem é?"; A receber → mark paid.
3. Install the new APK ("Nova versão disponível"), then one Pix between own accounts, one to
   someone else, one card purchase → check Aprovar (next-steps, first item).
4. Keep capture on; the next export drives a parser pass (Samsung first).

### Carried from the sharing session (2026-10-18)
- Sharing is set only by editing; the "+ Novo" forms and Aprovar don't offer it.
- A receber's "paid" writes no money on purpose: the Pix the person sends is its own lançamento.

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
