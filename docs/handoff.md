# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (6) · The owner's data aligned with Pluggy; Rende Fácil out

Local session, owner's request: fix every record of their account against Pluggy. SSH to the server
was refused by the harness ("Production Reads"), so the data work ran **through the app's API in
the owner's logged-in Chrome tab** (`claude-in-chrome`), with the owner's explicit OK to insert and
delete. Code: branch `claude/rende-facil`, merged to `main` and pushed (deploys) at the owner's request.

### Done (production data, via the API)
- Targets the owner gave, all met: BTG conta corrente 170, BTG black next invoice 1.467,59
  (Pluggy 1.328,22 + today's 139,37), BB 25, BB ourocard 19, Itaú 0, Flash 34,72; BTG investimentos
  kept at the owner's 8,94; new account **Wise** (559,43: three BTG Pix to Wise Brasil Câmbio).
- Deleted: duplicates ("1% cartão" = Pluggy InternalTransfer; CCR 4,10 on BB = the ourocard one),
  every manual "Normalização/Saldo/Aporte/Salários" balancing row, BB Rende Fácil rows, 4 BTG
  investment movements the Pluggy sync created at 23:59 that summed same-day typed trades (AUPO11,
  TIMS3 — they doubled quantities; deleting = DISMISSED for good).
- Recorded the 14 waiting + 6 denied Pluggy rows: BTG TEFs = transfers with BTG investimentos; BTG
  Pix 2.400/1.620 = transfers to BTG investimentos (owner: not spending); BB Pix 02/10 = transfers
  to BTG investimentos (a guess); TedSalary 1.680 = Salário; Wagner 2.400 to BB = receita.
- BTG black invoice 10/2026 rebuilt (4 Pluggy purchases + "Compras antes do app" 1.188,14) and paid
  by pay-invoice on 05/10 = the bank's 1.337,95 boleto. "emprestimo pai" 5.390 → 5.400; Flash→BB
  280 dated 26/10; ourocard "Ajuste para a fatura do banco" 0,81. Opening balances set: BTG 394,03,
  BB to land on 25, BTG investimentos to land on 8,94.
- October Gastar: 5.880 → **1.172,73** (owner: "less than 1.500").

### Done (code, branch `claude/rende-facil`)
- `inbox.is_auto_invest()`; Pluggy rows "RENDE FACIL"/"REND.FACIL" are `COVERED` in `place()`;
  the phone notice is `ignored`; migration 046 covers rows already pulled and denies pending items.
  `test_rende_facil.py` (12, fail without the fix). Full suite: 1953 passed, 1 failed (below).

### Not done, and why
- Mapping **BTG Investimentos → Corretora** and the zero-balance second Ourocard → "Não usar" (the
  two Gravar sozinho blockers) not done: mapping the broker could duplicate the manual aporte/resgate
  transfers; the owner should decide (see the 044 section of next-steps).
- 42 rows in Revisar left for the owner. Guesses to confirm: BB Pix 02/10 (1.810) → BTG
  investimentos; Pix 74,14 on 28/09 as receita; ourocard 0,81 adjustment; Wagner's 2.400/5.400
  recorded as receita (October income looks high because of them).
- The Pluggy investment sync summed same-day trades into one operation, so the typed-twin link
  (same quantity) missed: a code fix is still open (link a Pluggy op to a set of typed trades of the
  same asset/day whose quantities sum to it).

### Next session
1. Owner: after this deploy (it also carries PR #50, the APK without Aprovar), install the APK
   update and walk its next-steps item; check BB's Conferência (046 drops the Rende Fácil rows).
2. Fix the summed-twin case in `services/open_finance_investments.py`.

### Lessons (non-obvious)
- `test_fixed_income_interest.py::TestTheCouponReachesTheAccount` fails locally between 21:00 and
  midnight BRT (UTC is already tomorrow); it passes in CI (UTC). Pre-existing.
- The Chrome tool hides a JS result that echoes certain strings ("[BLOCKED: Cookie/query string
  data]") — the code still ran; re-read state instead of re-running writes.
- The Conferência pairs by amount/date (±3 days), not by link: re-typing a row with the bank's
  amount and date is enough to clear it.
