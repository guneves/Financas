# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-23 · `findings.md`: possible bugs and stale texts

Cloud session, branch `claude/mobile-docs-bugs-stale-text-u8ylzb` (from `main` at `0016f5b`, after
PR #33). The owner called it "session 4". Web and backend only, no native code. Briefing by
`session-scout`, found by `subagent_type`, no fallback.

### Done
Each possible bug in `mobile-docs/native/findings.md` got a test first. Every test failed, so every
bug was real and is fixed in its own commit, with the test kept:

| Bug | Fix | Test |
|---|---|---|
| Metas refused any edit once the target month arrived | only a changed `target_date` must be future (`services/goals.py`) | `test_goals.py::test_an_edit_keeps_a_target_date_that_has_since_arrived` |
| Recorrentes: "escolha outra conta" with no account in the edit | "Editar valor e conta", account select | `lib/recurring.test.js` |
| Extrato could not change a transfer's destination | De/Para selects; form + PATCH in `lib/transactionEdit.js` | `lib/transactionEdit.test.js` |
| Investment statement: same day, proventos before operações (comment said the opposite) | sort fixed to match the comment | `investmentStatement.test.js` |
| Refund prefill = installment × count (R$ 100 in 3x from 2/3 → 99,99) | sum of the purchase's installments in cents | `lib/cardPurchase.test.js` |
| A receber "pago em" in UTC (next day after 21:00) | `localDateOfTimestamp()` in `lib/format.js` | `format.test.js` (TZ `America/Sao_Paulo`) |

Stale texts, all fixed: login "FinanceMVP" → "Finanças", and "Criar acesso" (was "Cadastrar")
appears only when a new public `GET /api/auth/signup` answers `{open: true}` (`test_signup_and_secret.py`,
`test_route_map.py` now has `GET,POST`); Metas' Patrimônio hint; Integrações; Notificações;
`CASH_WITHOUT_AMOUNT_MESSAGE`; the `Orcamento.jsx` comment. Specs updated (`00-shell`, `04-extrato`,
`05-cartoes`, `06-a-receber`, `09-recorrentes`, `10-metas`). pytest 1536 passed, `npm test` 164
passed, `vite build` clean.

### Not done, and why
- **The 401 finding is native** (the sender never clears `Session`), out of this session's scope.
  Its "180 days on the server" is the owner's `.env` (`JWT_EXP_DAYS=180` in `.env.example`); the
  code default is 30. Left open in `findings.md`.
- **Grouped Tesouro delete is not atomic** (next-steps listed it among the bugs; findings.md files it
  under Investimentos): it needs a new grouped endpoint, not a one-line fix. Open in next-steps.
- **No Inconsistency was changed**: none was a one-liner without a behaviour question.
- No screenshot or browser check of the changed screens (Recorrentes edit row, Extrato transfer
  edit, login). They build and their rules are tested; look at them once on the desktop and phone.
- **Drift found**: the Aprovar session (PR #33) left no handoff or plan update. I only rewrote
  next-steps' step 1 into "steps 1–2 merged, phone check not recorded" and renumbered "Steps 3–8";
  `done-tasks.md` still has no Aprovar row — whoever knows that session's details should add it.
- Carried, still open: the web `createEntry()` duplicating after a killed tab; the sharing form
  refusing "12,5" (web and native); pytest red 21:00–midnight local
  (`test_fixed_income_interest.py`, UTC vs local "today" — likely the same class of bug as A
  receber's, worth checking next); APK not buildable in a cloud container; desktop redesign;
  Plus Jakarta Sans natively; the owner's phone checks.

### Questions for the owner (the Inconsistencies in `findings.md`)
1. **Corretora in banking forms**: should "+ Novo", the pay-invoice sheet and autopay stop
   offering Corretora accounts? A despesa recorded there vanishes from Início today.
2. **Extrato vs Início for a transfer to the Corretora**: should the Extrato show it as
   aporte/resgate (`bankingTransactions()`), as Início does, and keep it out of its day totals?
3. **Débito purchase in Pendentes**: Corrigir reopens it as a Despesa. Acceptable, or should it
   reopen as Cartão › Débito?
4. **Installments**: the client stops at 48, the server at 72 — which limit? And should the
   description be required (client) or optional (server) for despesa/receita?
5. **"Despesas por categoria" on Início** groups by name, merging root "Outros" with "Lazer ›
   Outros". Group by id, showing "Lazer › Outros"?
6. **Privacy mode**: the cash-flow chart shows what Entrou/Saiu mask; Operações, Proventos'
   summary and history, Aprovar, Cartões' totals and A receber are unmasked. Mask which of these?
7. **Cards without a bank field**: Aprovar's ambiguous-target rule never runs for cards. Add a bank
   to cards?
8. Minor, no behaviour change, left for whoever touches Início: `/api/credit-cards` is cached under
   `['cartoes']` and `['inicio','cartoes']`.

### Next session
Answer-driven: take the owner's answers above as tasks. Otherwise the pytest 21:00–midnight
failure (a test that reproduces only at night: patch the clock to 22:00 local), then the plan's
native step 3 after the owner's phone check of steps 1–2.

### Learned
- `node --test` runs each file in its own process, so a test can set `process.env.TZ` (restore it
  after) to pin a timezone; V8 parses the server's six-digit fractional `...Z` timestamps.
- Two Flask rules on the same path with different methods show up as two rows in
  `test_route_map.py`; one view with `methods=["GET", "POST"]` keeps the map's `GET,POST` row.
- `GET /api/cc-expenses/candidates?id=` already returns a purchase's installments by `client_id`;
  any "whole purchase" amount on the client should sum those in cents, never installment × count.
- This Linux container has no `.venv`; `pip install -r backend/requirements-dev.txt` and
  `python3 -m pytest` work (the full suite takes ~2.5 min).
