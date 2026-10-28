# Conta global — native spec

| | |
|---|---|
| Status | Built 2026-10-27 on `claude/conta-global`: `ui/globalaccount/` (`NativeRoutes.CONTA_GLOBAL`, link `/inicio/conta-global`), `rules/GlobalAccount.kt` (port of `lib/globalAccount.js`, JVM tests with the node cases), `formatForeignCurrency()` in `core/Format.kt`; the Início entry under the account strip, the "Conta global" link and the "Conta global (US$)" type in Ajustes › Contas, "+ Novo" without the dollar account. Debug APK built locally, 531 JVM tests green; waiting for the owner's phone check. 2026-10-28: "Pix para cá" (sheet, `GlobalAccount.pixMissing()`/`pixBody()`, POST /api/transfers with `client_id`, online only) and "Carregar mais" (next pages) |
| React source | `frontend/src/pages/ContaGlobal.jsx` |
| Route(s) | `/inicio/conta-global` (`?conta=<id>` when there is more than one) |
| Endpoints | `GET /api/accounts`, `GET /api/transactions?account_id=<id>` (paged, "Carregar mais"), `POST /api/review`, `POST /api/transfers` |
| Client rules | `lib/globalAccount.js` (`globalStatement()`, `globalTotals()`, `brlHint()`, `impliedRate()`), `formatForeignCurrency()` in `lib/format.js` |

## What it is for
The owner's Wise account is in dollars. This is the **only** screen of the app in another currency
(owner, 2026-10-27): its balance and statement in US$, and a small "≈ R$ …" from today's PTAX.
Everywhere else the account shows in reais and counts converted in Início's balance.

## What it shows
1. **Top bar** "Conta global", back, privacy eye. Description "<name> · em USD. Fora daqui o app é em
   reais: no Início ela entra convertida no saldo em contas." A segmented choice when there are several.
2. **Summary**: lead "Saldo em conta" = `balance` in US$ (`US$ ••••••` in privacy mode), hint
   "≈ R$ … pelo câmbio de hoje (PTAX)" from `balance_brl`, or "sem câmbio hoje"; figures "Entradas" and
   "Saídas" of the loaded statement (US$), "N a conferir" when a transfer has no dollar amount yet.
3. **Extrato** (US$): one row per movement of the account. A Pix from a reais account is a transfer
   (`transfer_amount` is what arrived: "+US$ 46,10", detail "de BTG conta corrente · saiu R$ 253,53 ·
   R$ 5,50 por USD"); without `transfer_amount` the row says "valor em USD a conferir". Rows with
   `needs_review` carry "A revisar" and "É meu"; "Confirmar todos" with two or more.

## Acceptance (owner, on the phone)
- [ ] Início shows "Conta global ›" under the accounts; it opens this screen.
- [ ] The balance equals Pluggy's (Wise) in US$; "≈ R$" matches the Wise tile on Início.
- [ ] The three Pix of October show the dollars Wise credited.
- [ ] Privacy mode masks the balance and the "≈ R$".
- [ ] Ajustes › Contas: Wise says "Conta global (USD)" and opens this screen.
- [ ] "Pix para cá": De BTG, Saiu R$ 10,00, Entrou US$ 1,80 → one row "+US$ 1,80 · saiu R$ 10,00";
  BTG's balance drops R$ 10,00 and nothing shows in Resumo do mês. Without connection: an error, nothing queued.
