# Native migration — the remaining sessions

Five prompts replace the eight drafted for sessions 8–15. Each follows `session-protocol.md` (the
main session builds; one reviewer run per session). Paste one into a new session.

| Session | Screens | Needs | Can run alongside |
|---|---|---|---|
| A | Extrato (both views), Cartões | Steps 1–3 (PR #38) | B |
| B | Investments groundwork: endpoints, `client_id`, chart colours and shapes, ports | — | A |
| C | Orçamento, Recorrentes, Metas, A receber, Ajustes | A (stacked if A's PR is open) | D |
| D | Posição, Operações, Proventos, Rentabilidade, Alocação/IR/Calculadora | B merged | C |
| E | Native shell, remove the WebView | A–D merged, the owner's phone checks done | — |

A and B, then C and D, can run at the same time: B touches the backend, `rules/`, `ui/charts/` and
`Tokens.kt`; A touches the screens, routes and strings. If both edit `Tokens.kt` or `strings.xml`,
the second PR to merge resolves the conflict.

**Fill the `DECIDE:` lines before pasting.** An undecided line keeps the web's behaviour and comes
back as a question.

---

## A — Extrato and Cartões

```
Native migration, session A: Extrato (both views) and Cartões.
Follow mobile-docs/native/session-protocol.md exactly.

Needs: native Início (PR #38) and GET /api/cc-invoices on main.
Specs: screens/04-extrato.md, screens/05-cartoes.md.

Do, in order, on this branch:
1. Paging on GET /api/transactions (next-steps, "What the home/attention/invoices proposal left
   open" §5), with pytest, and the web's "Carregar mais" in the same commit.
2. Port lib/investmentStatement.js for the Extrato's Investimentos view (same cases). If the
   same-day ordering still contradicts its comment, port today's behaviour and say so.
3. Shared pieces: both routes, strings, the camera/file picker for receipts and the share sheet
   for export.
4. Extrato: both views; edit and delete online-only; receipts; export through the share sheet.
5. Cartões: invoices from /api/cc-invoices, pay-invoice, "Desfazer pagamento", refunds, sharing
   (port settlePayload and shareSummary from lib/sharing.js), deleting a purchase.
6. Also: move Aprovar's writes from the read client to writeApi (next-steps, step 3's leftovers).

Decisions:
- DECIDE: Corretora accounts offered in the banking forms, the pay-invoice sheet and autopay? (today: yes)
- DECIDE: the Extrato shows a transfer to the Corretora as aporte/resgate, like Início? (today: no)
- DECIDE: privacy mode masks every money value on these screens? (protocol default: yes)
```

## B — Investments groundwork

```
Native migration, session B: everything the Investimentos screens need before they are built.
Follow mobile-docs/native/session-protocol.md exactly. No native screen in this session.

Read: mobile-docs/native/rules-port.md, the Investimentos part of findings.md, screens 12–16
(only the "Endpoints" and "Client rules" sections).

Do, in order:
1. Backend, with pytest for each, and the React Investimentos screens switched with no visible
   change (one Chromium screenshot per touched screen, before and after):
   a) client_id on POST /api/investments, /api/investment-proceeds, /api/corporate-actions —
      only if decided yes below (a migration shaped like 024);
   b) endpoints for money the client computes today: the Tesouro redemption split
      (allocateTreasuryRedemption, PEPS — keep treasury.test.js's cases exactly), Operações'
      summary from the realized result, Proventos' yearly totals, the IR tab's tributação
      exclusiva net, and an atomic grouped Tesouro delete.
   Weighted average cost, the monthly tax rule and Tesouro marked to market stay as they are.
2. SERIES and FLOW in frontend/src/components/charts.jsx become CSS variables in index.css (light
   and dark, same colours), then join ui/theme/Tokens.kt so TokensTest covers them.
3. ui/charts/ already exists (session 7: Charts.kt, ChartScale.kt). Add only what Investimentos
   lacks — a donut, bars above and below zero, lines that break on gaps — with JVM tests for the
   geometry.
4. Port lib/portfolioAccount.js, lib/assetSearch.js (node tests first; it has none),
   lib/fixedIncome.js, the label part of lib/treasury.js, lib/proceedsRules.js and
   lib/compoundInterest.js.
5. Record each endpoint in rules-port.md and close the matching findings.md lines.

Decisions:
- DECIDE: client_id on the three investment creations, so native queues them offline? (or keep
  them online-only and refused offline)
- DECIDE: all five endpoints in 1b, or only the ones a native screen needs?
```

## C — Planning screens, A receber and Ajustes

```
Native migration, session C: Orçamento, Recorrentes, Metas, A receber, then Ajustes.
Follow mobile-docs/native/session-protocol.md exactly.

Needs: session A (main, or stack on its branch).
Specs: screens/08-orcamento.md, 09-recorrentes.md, 10-metas.md, 06-a-receber.md, 11-ajustes.md.

Do, in order:
1. Ports: the input side of lib/monthlyPlan.js (percentRoom, clampPercent, stepPercent,
   PERCENT_STEP, the percentOf preview, categoryAmountPreview, livePlanTotals, the flag texts,
   planFlagKey, visibleFlags) and lib/planFlags.js. frequencyLabel and the goal forecast texts
   have no tests: move them into lib/ with node tests from the React behaviour, then port.
2. Shared: the native PercentSlider in ui/components (− and +, the R$ beside it) and the routes.
3. Orçamento, Recorrentes, Metas, A receber — online-only, as on the web.
4. Ajustes, the sections the spec marks early or mid: Contas, Cartões (crédito/débito functions),
   Aprovar settings, Aparência, Perfil, Notificações dos bancos (port lib/notifyRules.js if
   needed), Categorias, Versão do app (APK update only). While WebView screens exist, a native
   theme change, privacy change and "Sair" also update the web side; bump native-level.txt for
   any new plugin method. Regras and Integrações stay in the WebView/desktop: record it in the
   spec's Status.
If context runs short after step 3, close the session there (PR with the four planning screens)
and leave Ajustes as the handoff's next step.

Decisions:
- DECIDE: 48 or 72 installments, and is the description required? (today: client 48, server 72)
```

## D — Investimentos

```
Native migration, session D: Posição, Operações (with "Registrar operação" and corporate
actions), Proventos, Rentabilidade, and from screens/16 Alocação (read-only plus the
contribution split), the IR exemption meter and DARF months, and the Calculadora.
Follow mobile-docs/native/session-protocol.md exactly.

Needs: session B merged in main (endpoints, chart colours and shapes, ports).
Specs: screens/12 to 16.

Do, in order:
1. Shared: the Investimentos tab structure in the NavHost and the routes.
2. Posição, Operações, Proventos, then Rentabilidade (with ui/charts), then the parts of 16 its
   spec keeps native. Editing targets, sectors and the full IR report stay on the desktop/WebView.
3. Operações and Proventos are queued offline only if session B added client_id; otherwise they
   are refused offline with a message.
If context runs short after Proventos, close there and leave 14 and 16 for the handoff.
```

## E — Native shell, then remove the WebView

```
Native migration, session E: the native shell, then the WebView leaves the APK.
Follow mobile-docs/native/session-protocol.md exactly.

Needs: sessions A–D merged in main, and the owner's phone checks of them done.
Specs: screens/00-shell.md, screens/07-importar.md.

First list every phone route and check each is native or decided desktop-only (Importar, Regras,
Integrações, the full IR report, editing allocation targets and sectors). If any is neither,
stop and tell me.

Do, in order:
1. Shell: native login (signup closed, no "FinanceMVP"); bottom navigation with the four sections
   and Ajustes; 401 clears the session and returns to login; NativeActivity becomes the launcher;
   desktop-only pages are left out, with a short note where a link pointed to one.
2. Remove the WebView: Capacitor and its plugins, MainActivity's BridgeActivity, bundle/, the
   NativeScreens bridge, services/app_bundle.py and GET /api/app-bundle* (with their tests),
   dist-android, frontend/scripts/bundle-manifest.mjs, frontend/native-level.txt, and their steps
   in deploy.yml, android-check.yml and the Dockerfile. Keep outbox/, notify/ and update/ working,
   keep the notification allow-list test, and keep installing over the current app without
   losing the offline queue (same package, same key, higher versionCode).
3. pytest, npm test and android-check.yml green. The review covers the shell and the removal only
   (the screens were reviewed in their sessions).

Close also: CLAUDE.md (drop the bundle and native-level conventions, describe the native shell),
DEPLOY.md, the README status (all native). The PR's phone checklist: fresh login, every section,
offline entry, bank notifications reaching Aprovar, the APK update banner.
```
