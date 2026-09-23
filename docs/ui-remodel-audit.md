# UI remodel — Stage 1: audit and direction

> Stage 1 of `docs/ui-remodel-prompt.md`, done 2026-09-23. **Decided the same day: "Go with C, include
> a dark mode."** That settles the direction and E. F (top pills), H (Plus Jakarta Sans,
> self-hosted) and J (fix the balance with the remodel) were taken as C's defaults, not answered
> separately; G (command palette) and I (exact attention items) are still open. What was built:
> `docs/next-steps.md`. The canvas has a fourth
> row with C in dark mode.
>
> Mocks: Claude Design canvas "Finanças — UI rework"
> (https://claude.ai/artifact/DPSbd7JxFULWe4r9z36tto, private to the owner). Three directions,
> each drawn as Início (1280 px), Extrato (1280 px) and Início on the phone (390 px), filled with the
> figures the three-year mock seed produces — not invented numbers.
>
> Before screenshots were taken with Playwright against a scratch database
> (`seed_three_years_mock.py`), all ten screens at 1280 and 390 px. They are not committed (they
> show mock data only and would bloat the repo); rerun the recipe in `docs/handoff.md` to regenerate.

## Audit, screen by screen

What the screen is for → the one number or action the owner comes for → what gets in the way.

**Início** — "how am I doing this month?" → net worth, the month's result, anything overdue.
- Four equal MetricCards open the page; net worth, cash, investments and "disponível por dia" get
  the same weight, and **the month's result is not on the page at all** (you infer it from the
  cash-flow chart).
- The things that need action — an over-budget category, the invoice about to close — sit at the
  bottom of a ~3,000 px page (Orçamento do mês, Próximas faturas). On the phone they are five
  screens down.
- Fluxo de caixa's four stat chips truncate their values ("R$ 173.205,…") at 1280 px — the floor
  the visual pass set (no truncated money) is broken here.
- Seven panels, each with a title *and* a sentence of description. The descriptions read once are
  useful; read daily they are noise.

**Lançamentos → Extrato** — "what went out, and is this one right?" → the latest rows, search.
- Three MetricCards (Saldo atual, Projeção próximo mês, Projeção global) take the first ~200 px;
  on the phone the first lançamento starts **below the fold** (~820 px of header, cards and filter).
- 100 flat rows with no day grouping or day totals; the Conta column says "Conta Principal" on
  nearly every row; descriptions truncate at 1280 px ("Com…", "Res…", "Pagamento Fatur…").
- Pencil + trash on every row: 200 buttons of visual noise for an action taken a few times a week.

**Lançamentos → Cartões** — "how much is the next invoice and can I pay it?"
- Seven metric cards before the first invoice — the first three repeat Extrato's word for word.
- Future invoices (11/2026 … 06/2027, all the same instalment) each carry a disabled "Pagar"
  button: nine greyed-out buttons that say "not yet" nine times.
- A red trash button on every purchase.

**Investimentos → Posição** — "how much is it worth and what's moving?"
- An editable quote input + refresh button on every row dominates the table; it is the rarest
  action on the screen. FII tickers truncate ("HGLG…", "MXRF…").
- "Vender" + trash on every row, same noise as Extrato.
- Evolução do Patrimônio stayed a grey skeleton in the sandbox (yfinance has no network there — not
  necessarily a bug at home, but the empty/error state is indistinguishable from loading).

**Everywhere**
- Every page opens with the same stack: tabs, H1, a descriptive sentence, then cards. Nothing on
  the page says which of those numbers matters today.
- Phone: the header, tabs and page title together use ~200 px before any content.

### Found along the way

**"Saldo em conta" does not equal the sum of "Saldo por conta".** On the seeded data Início and
Extrato show R$ 1.061.007,88; the three accounts in Saldo por conta add up to R$ 1.308.507,88. The
difference, R$ 247.500,00, is exactly the sum of the accounts' `initial_balance`
(185.000 + 60.000 + 2.500). So the consolidated balance ignores opening balances while the per-account
balance includes them, and net worth is understated by the same amount. **Fixed with the remodel:**
it turned out to be a frontend bug — Início and Extrato summed `transactions` on the client instead
of using the per-account balances the server already computes (see `consolidatedBalance()` in
`frontend/src/lib/transactions.js`).

## Three directions

All three keep the hard constraints of the remodel prompt: emerald as the single accent,
green/red/amber/sky only for gain/loss/warning/info, tabular figures, real minus sign, pt-BR, 44 px
touch targets, privacy via the existing hooks. All three share the same **information changes** —
those are the real remodel; the directions differ in look and density:

1. **Início leads with the answer:** net worth hero + the month's result (entradas − saídas) +
   "disponível por dia"; then a **"Precisa de atenção"** strip (over-budget categories, invoices
   about to close, overdue recurrences, autopay shortfall) — above the fold on both widths.
2. **Extrato grouped by day** with the day's total, one summary line instead of three cards, a
   filter bar with chips (Conta, Categoria, Tipo, mês), row actions in one "⋯" menu, and the Conta
   shown only when it is not the usual one.
3. **One header layer per page:** title, month switcher, the eye — no descriptive paragraph.

### A · Sereno (calm, spacious, light)
Warm off-white ground, hairline borders instead of shadows, **Instrument Serif** for the big money
values over **Geist** for everything else. Generous spacing; list rows (not a table) in Extrato.
Sidebar kept. Best for: a daily glance that feels unhurried. Risk: lowest density of the three —
more scrolling in Extrato.

### B · Painel (dark, dense, keyboard-first)
Dark theme (this *is* decision E made visible), **IBM Plex Sans + Plex Mono** figures, an icon rail
instead of the sidebar, a `Ctrl K` command bar (go to, search, "novo gasto"), a five-figure KPI
strip, a 36 px-row table with day separators, keyboard shortcuts (J/K, E, C, /). Best for: the
owner at a desktop reconciling statements. Risk: the most work (command palette, shortcuts, a real
dark theme) and the least friendly on the phone.

### C · Cartões (warm, rounded, phone-first)
Deep-green hero block with net worth and account chips, big rounded tiles, top pill navigation
instead of the sidebar, attention items as swipeable cards on the phone, **Plus Jakarta Sans**.
Extrato becomes a card list with a side column (month in/out, accounts, Importar). Best for: daily
use from the phone. Risk: the hero block is a heavy colour field; on desktop it spends width that A
and B use for data.

My recommendation: **A's look with B's keyboard layer** (the `Ctrl K` palette and Extrato shortcuts
are independent of the theme), and design the tokens so B's dark palette is a token swap — which
the prompt asks for anyway.

## Decisions for the owner

- **Direction:** A, B, C, or a mix (say which parts).
- **E — dark mode:** build it now (as a token swap, following the system setting with a manual
  toggle next to the eye), or tokens-only for now?
- **F — navigation:** keep the sidebar (A), icon rail (B), or top pills (C)?
- **G — command palette (`Ctrl K`) and Extrato shortcuts:** in scope?
- **H — typefaces:** the app ships Inter today. Each direction adds a webfont (1–3 families, ~40–90
  KB woff2). Self-host in `frontend/public/fonts` (works offline, which the local app needs) or keep
  system/Inter?
- **I — "Precisa de atenção":** which items count? Proposed: category over budget, invoice closing
  within 10 days, invoice closed and unpaid, overdue recurrence, autopay account short of the
  invoice. All derivable from existing endpoints — no backend change.
- **J — the balance mismatch above:** fix in the backend before the remodel, or alongside it?
