# UX reorganization — plan

> The working spec for reorganizing the frontend. Written 2026-09-21 from an audit of every screen.
> **Scope: organization, flows and presentation only.** No backend change, no new feature, no change
> to any calculation. Every existing feature must still be reachable when this is done — §8 is the
> checklist that proves it.
>
> Progress is tracked in §9 and mirrored as one line in `docs/next-steps.md`.

Guiding question for every call: *using only what already exists, how can this be placed and
presented so the owner understands and completes the task with the least effort?*

---

## 1. Audit — what is wrong today

**A. Two screens do the same job.** `Carteira.jsx` ("Controle diário") is an older copy of
`Transactions.jsx` ("Movimentações"): both have a bank-entry form, card registration, a credit
purchase form and the open-invoices list. The Carteira copy is the weaker one — hard-coded category
list (`CATEGORY_OPTIONS`), no account selector, no editing, no filters, no transfers. Its name is
also wrong: in Brazilian finance *carteira* means an investment portfolio, and the investments
screen itself says "sua carteira".

**B. The most frequent action is the hardest to reach.** On Movimentações the entry form is the
*third* block, below account creation (done once) and the transfer form (occasional). Its date field
starts empty, so every entry costs an extra tap.

**C. Seven flat nav items, related things scattered.**

| Feature | Lives in | Problem |
|---|---|---|
| Categories | a tab inside Orçamento | used by statement, budget and recurrences; hidden in one of them |
| Proventos | its own top-level item | same assets and context as Investimentos |
| Recorrentes | its own top-level item | it is planning, like the budget |
| Accounts, cards (create/archive) | top of the daily entry screen | set up once, then in the way |
| "Criar dados demo" | dark primary button on Carteira | writes fake rows into the real database, one click away |

**D. The overview is a dead end.** Only "Pagar fatura" is actionable. Overdue recurrences are never
surfaced there, although `Recorrentes` knows about them.

**E. Inconsistency.**
- `Investments.jsx` ignores the UI kit: hand-rolled buttons, blue accent, `max-w-5xl`, its own tabs,
  tables and modal markup.
- One concept, several words: expense is "Saída bancária" / "Despesa" / "Saída"; save is
  "Lançar" / "Salvar" / "Registrar compra"; refresh is "Sincronizar Cotações" / "Atualizar";
  "Movimentações" names both the bank statement and the investment history.
- Proventos filters need a "Filtrar" submit; the statement filters live.
- Missing accents: Liquido, Calendario, Amortizacao, Operacoes, prejuizo, pos-IR, Observacoes,
  Declaracao, elegivel, Inicio; English "stale" in user-facing text.
- Desktop header: "Área atual" repeats the page title just below it; the email shows twice.

**F. Accessibility.** Icon buttons are 36px (below the 44px touch minimum), and on a phone the
delete/edit icons sit inside tables that scroll sideways. Labels are mostly `text-xs` zinc-500.
On a phone every screen change takes two taps (open menu, pick item) at the top of the screen.

---

## 2. Decisions

These were open in the proposal; the owner delegated them. Change them here, not in chat.

| # | Decision | Reason |
|---|---|---|
| D1 | **Carteira is merged away.** Its route redirects to `/lancamentos`. | Every feature in it exists, better, in Movimentações. Its four unique figures move to Lançamentos › Cartões (§4). |
| D2 | **Demo data moves to Ajustes and gains a `window.confirm`.** | It writes to the real DB. Every other data-changing button in the app already confirms; this one was the exception. |
| D3 | **Build the responsive layout** (bottom tab bar, card lists on phones). | The brief asks for one-handed use and it is cheap on top of the restructure. This does **not** settle `next-steps.md` open decision 4 — hosting/HTTPS stays open. |
| D4 | **Routes become Portuguese and nested**, one path per tab, so any panel can deep-link to a tab. Old paths redirect. | Paths were already mixed (`/orcamento` vs `/transactions`); nested paths let Início link straight to "Cartões". |
| D5 | **One "+ Novo" sheet** owns all entry forms: Despesa, Receita, Transferência, Compra no cartão, Investimento. | Five forms on three screens become one place and one pattern, reachable from anywhere. |
| D6 | **Entry forms default the date to today** and the account to the default account; the card form preselects the first card and 1 installment. | Removes a tap from every entry. A default value, not a behaviour change — the user can still change it. |
| D7 | **Forms that are not the daily action collapse behind a button** (new budget, new recurrence, new provento, new account, new card, new category). | One primary action per screen; the list is what the screen is for. |
| D8 | **No backend change.** If a step seems to need one, stop and record it here. | Keeps `finance-guard` out of the loop and the risk in the frontend. |
| D9 | **Six steps, one commit each, `npm run build` green between steps** (§9). The app must be usable after every step. | Same rule as the backend refactor: small, reversible steps. |
| D10 | **Carteira's 6-month flow chart is dropped.** | Início already has the 12-month cash-flow chart over the same data. The only thing that disappears in this plan. |

---

## 3. Screen map

```
Início            /inicio                        (was /dashboard)
Lançamentos       /lancamentos/extrato           (was /transactions, tab CONTA; also /carteira)
                  /lancamentos/cartoes           (was /transactions, tab CARTOES)
Planejamento      /planejamento/orcamento        (was /orcamento, tab BUDGET)
                  /planejamento/recorrentes      (was /recorrentes)
Investimentos     /investimentos/posicao         (was /investments, tabs VARIAVEL + FIXA)
                  /investimentos/operacoes       (was /investments, tab MOVIMENTACOES)
                  /investimentos/proventos       (was /proventos)
─────────
Ajustes           /ajustes                       sections: Contas · Cartões · Categorias ·
                                                 Dados de exemplo · Sessão (Sair)

+ Novo (everywhere) → Despesa · Receita · Transferência · Compra no cartão · Investimento
```

- **Desktop (≥ lg):** sidebar with the four sections; Ajustes pinned at the bottom next to the user
  block; `+ Novo` as the primary button in the top bar. Remove the "Área atual" header.
- **Phone:** bottom tab bar — Início · Lançamentos · **[+]** · Planejamento · Investimentos. Ajustes
  is a gear icon in the top bar. Tabs within a section are a `SegmentedControl` under the title.
- **Redirects:** `/dashboard`, `/transactions`, `/carteira`, `/orcamento`, `/recorrentes`,
  `/investments`, `/proventos` → their new path. Section roots (`/lancamentos`) → their first tab.
  The post-login redirect in `App.jsx` goes to `/inicio`.

---

## 4. Screens

Each screen: purpose, hierarchy (top to bottom), primary action.

### Início — *"How am I doing, and does anything need me?"*
1. **"Precisa de você"** strip, shown only when non-empty:
   - overdue recurrences → "N recorrência(s) vencida(s)" + **Lançar** (calls the existing
     `POST /api/recurring/run`, same as the Recorrentes button);
   - current invoice open → amount + **Pagar** (the existing `handlePayCurrentMonthInvoice`).
2. The four metric cards, unchanged.
3. Charts and lists, unchanged. Each panel title becomes a link: *Próximas faturas* and
   *Parcelamentos abertos* → `/lancamentos/cartoes`; *Saldo por conta* → `/ajustes#contas`;
   *Despesas por categoria* → `/planejamento/orcamento`; *Fluxo de caixa* → `/lancamentos/extrato`.

Primary action: **+ Novo**.

### Lançamentos › Extrato — *"What went in and out?"*
1. Header metrics (shared by both tabs): Saldo atual · Projeção próximo mês · Projeção global.
2. Search box, full width. The other filters (dates, type, account, category, min/max) fold behind a
   **Filtros** button that shows the active-filter count; "Limpar filtros" stays.
3. The statement. ≥ md: the current table with inline editing. < md: a card list (date, description,
   category, amount; edit/delete as 44px buttons; editing opens the same fields stacked).

Primary action: **+ Novo**.

### Lançamentos › Cartões — *"What do I owe on my cards?"*
1. Summary strip — the figures that only Carteira showed: **Total aberto**, **Fatura do mês**,
   **Saldo após a fatura atual**, **Saldo projetado** (conta − cartões abertos). Port the
   `walletSummary` computation from `Carteira.jsx` as is.
2. One panel per card; **the invoice with the nearest due date is expanded by default**, the rest
   collapsed. Pay and delete-purchase as today.

Primary action: **Pagar fatura** (on the nearest invoice).

### Planejamento › Orçamento — *"Am I within the plan this month?"*
Month selector in the header → four figures → the month's category list. The "Novo orçamento" form
becomes **Adicionar categoria ao mês** (expands inline); "Copiar mês anterior" is a secondary button
beside it. The Categorias tab leaves (→ Ajustes); a "Gerenciar categorias" link replaces it.

Primary action: **Adicionar categoria ao mês**.

### Planejamento › Recorrentes — *"What is coming, and is anything overdue?"*
Forecast figures (30d, 90d, pendentes) → the recurrence list → the 90-day list. The creation form
becomes **Nova recorrência** (expands inline).

Primary action: **Lançar pendentes** (label shows the count, as today).

### Investimentos › Posição — *"What do I hold and how is it doing?"*
Allocation + performance charts → a *Variável / Renda fixa* switch → the positions table (per-asset
refresh, manual price edit, sell, delete-by-asset with its `asset_class` guard — all unchanged).
**Atualizar cotações** is a secondary button; its result panel stays.

Primary action: **Registrar operação** (opens `InvestmentLaunchModal`).

### Investimentos › Operações
Realized figures (operações, resultado, IR estimado, resultado após IR) → history with edit/delete.
Same content, rebuilt on the kit.

### Investimentos › Proventos
Four figures → calendar + monthly chart → history. The form becomes **Registrar provento**
(expands; editing an item opens it filled). Filters apply on change, like the statement — the
"Filtrar" button goes.

Primary action: **Registrar provento**.

### Ajustes — *set up once, rarely touched*
Anchored sections, each a list with its existing form collapsed behind a button:
- **Contas** (`#contas`) — list with balances, archive, **Nova conta**. From `Transactions.jsx`.
- **Cartões** (`#cartoes`) — list, delete (keeps its "ATENÇÃO" confirm), **Novo cartão**.
- **Categorias** (`#categorias`) — the whole current Categorias tab of `Orcamento.jsx`: create,
  rename, archive, restore, subcategories.
- **Dados de exemplo** — "Criar dados de exemplo", now behind a confirm (D2).
- **Sessão** — email + **Sair**.

### + Novo sheet
A modal (desktop) / bottom sheet (phone) with a `SegmentedControl` for the type, then that type's
existing fields, then **Salvar**. Defaults per D6. On success it closes and every mounted page
refetches (§6). "Investimento" opens the existing `InvestmentLaunchModal` rather than duplicating it.
Opening from a tab preselects the obvious type (Cartões → Compra no cartão).

---

## 5. Labels

| Before | After |
|---|---|
| Saída bancária · Saída · Despesa | **Despesa** |
| Entrada bancária · Entrada · Recebimento | **Receita** |
| Lançar · Salvar · Registrar compra · Salvar cartão · Criar conta | **Salvar** (forms) |
| Sincronizar Cotações | **Atualizar cotações** |
| Adicionar Lançamento (investments) | **Registrar operação** |
| Movimentações (investments tab) · Histórico de Movimentações | **Operações** |
| Movimentações (bank screen) | **Lançamentos** |
| Visão geral | **Início** |
| Variável & Outros · Renda Fixa (CDI) | **Variável** · **Renda fixa** |
| Meus Investimentos | **Investimentos** |
| Criar dados demo | **Criar dados de exemplo** |
| Liquido, Calendario, Amortizacao, Operacoes, prejuizo, pos-IR, Observacoes, Declaracao, elegivel, Inicio | accents restored |
| stale / sem cotação | **desatualizada / sem cotação** |

Filters in the statement keep "Entradas / Saídas / Transferências" as plural list filters, but the
single-item badge and the form use Receita / Despesa.

---

## 6. Visual system and implementation notes

- **Components:** everything uses `components/ui.jsx`. New shared pieces go there too:
  `Tabs` (route-backed `SegmentedControl`), `Collapsible` (button that expands a form), `Sheet`
  (modal ↔ bottom sheet). No page defines its own button, alert or modal markup.
- **Colour:** emerald is the only accent. Rose = negative/destructive, amber = warning, sky = info.
  Remove the blue from Investimentos.
- **Size:** icon buttons 44×44 on touch (`h-11 w-11`, may stay `h-9` at ≥ lg); body text ≥ 14px;
  secondary text zinc-600, not zinc-500.
- **One alert component.** Four pages each define an `AlertMessage`; move one into `ui.jsx`. (This is
  also the "one consistent error banner" item of `next-steps.md` frontend debt.)
- **Refetch after + Novo.** The sheet lives in `Layout`, outside the pages. Add a small
  `DataVersionContext` in `Layout` — a counter bumped after any successful save — and have each
  page include it in its fetch effect's dependencies. No TanStack Query yet; that is separate debt.
- **Tab state lives in the URL** (D4), not `useState`. Pages read the tab from the route.
- **Moving code, not rewriting it.** Handlers and computations move with their panel. When a form
  moves into the sheet, its submit handler moves with it verbatim; do not re-derive payloads.
- **Traps:**
  - `Transactions.jsx` and `Carteira.jsx` default dates through a local `getNow()` clock hook, not
    `new Date()` (see `CLAUDE.md` › Known sharp edges). Keep that when prefilling today.
  - `Transactions.jsx` has its own `formatDateBR` returning `''`; the shared one returns `'-'`.
  - The statement's filtered fetch and the unfiltered balance fetch are separate on purpose — the
    balance must never come from the filtered list.
  - `Carteira.jsx` caches in its own localStorage keys (`@financeMVP:wallet*`). After the merge
    they are unused; leave them, they are harmless.
  - Card-purchase categories must come from the categories table (Transactions' version), not
    Carteira's hard-coded list.

---

## 7. Common tasks — phone taps, before → after

| Task | Before | After |
|---|---|---|
| Log a debit expense | ~10 + scroll | **5** (+ → value, category, description → Salvar) |
| Log a card purchase | ~11 + scroll | **6** (+ → Cartão → value, category, description → Salvar) |
| Pay the next invoice | 5 + confirm | **3** + confirm; **1** + confirm from Início |
| Post overdue recurrences | 3 | **1** from Início |
| Find a past entry | 2 + scroll past 3 panels | **2** |
| Transfer between accounts | 2 + scroll + fields | **2** + fields |
| Buy an asset | 3 | **2** |
| Record a dividend | 2 + fields | 3 + fields (one tap more — the price of 3 fewer top-level items) |
| Add a category | 3, hard to find | **2** |
| Check this month's budget | 2 | **1** |

---

## 8. Feature inventory — nothing lost

Tick each row when the step that moves it is done and the feature has been exercised in the app.

| Feature | From | To | ✓ |
|---|---|---|---|
| Net worth, balance, investments, available-per-day cards | Dashboard | Início | [ ] |
| 12-month cash flow, balance evolution, spending pace, category donut | Dashboard | Início | [ ] |
| Balance per account chart | Dashboard | Início | [ ] |
| Next invoices chart, pay current invoice | Dashboard | Início | [ ] |
| Open installments list | Dashboard | Início | [ ] |
| Bank entry (income/expense, account, category) | Transactions, Carteira | + Novo | [ ] |
| Transfer between accounts | Transactions | + Novo | [ ] |
| Credit card purchase with installments | Transactions, Carteira | + Novo | [ ] |
| Balance, next-month and global projections | Transactions | Lançamentos header | [ ] |
| Statement: search, date/type/account/category/amount filters, totals | Transactions | Lançamentos › Extrato | [ ] |
| Statement: inline edit, delete | Transactions, Carteira | Lançamentos › Extrato | [ ] |
| Open invoices per card, pay invoice, delete purchase | Transactions, Carteira | Lançamentos › Cartões | [ ] |
| Open credit total, month invoice, balance after invoice, projected balance | Carteira | Lançamentos › Cartões | [ ] |
| Month expenses, income received this month | Carteira | Início already shows both | [ ] |
| Accounts: list, balances, create, archive | Transactions | Ajustes › Contas | [ ] |
| Cards: list, create, delete | Transactions, Carteira | Ajustes › Cartões | [ ] |
| Categories: create, subcategory, rename, archive, restore | Orçamento | Ajustes › Categorias | [ ] |
| Demo data | Carteira | Ajustes › Dados de exemplo | [ ] |
| Log out | Layout | Ajustes › Sessão + desktop sidebar | [ ] |
| Budget: month nav, figures, add, edit, delete, rollover, copy previous month | Orçamento | Planejamento › Orçamento | [ ] |
| Recurrences: forecast, create, pause/resume, delete, run pending, 90-day list | Recorrentes | Planejamento › Recorrentes | [ ] |
| Positions: variable and fixed income tables | Investments | Investimentos › Posição | [ ] |
| Refresh all quotes, refresh one, manual price, quote result panel | Investments | Investimentos › Posição | [ ] |
| Allocation and performance charts | Investments | Investimentos › Posição | [ ] |
| Buy/sell (InvestmentLaunchModal, ticker autocomplete) | Investments | Posição + "+ Novo" | [ ] |
| Delete by asset (asset_class guard) | Investments | Investimentos › Posição | [ ] |
| Investment history, edit movement, delete movement, realized/tax figures | Investments | Investimentos › Operações | [ ] |
| Proventos: register, edit, delete, figures, calendar, monthly chart, filters, history | Proventos | Investimentos › Proventos | [ ] |
| Login / signup | Auth | unchanged | [ ] |

Removed on purpose: Carteira's duplicate forms and lists (D1), its 6-month chart (D10), the
"Área atual" header.

---

## 9. Steps

One commit per step. `npm run build` green and the app usable after each. Tick in §8 as you go.

1. [ ] **Shell.** `ui.jsx` additions (`Tabs`, `Collapsible`, `Sheet`, `AlertMessage`, 44px sizes);
   new `Layout` (4-section sidebar, bottom bar, top bar with `+ Novo` placeholder and gear); new
   routes with redirects; pages mounted at their new paths with tabs driven by the URL. Carteira
   route redirects but the file is not deleted yet.
2. [ ] **Ajustes.** Before anything leaves its page, give it somewhere to go: Contas and Cartões
   out of `Transactions.jsx`, Categorias out of `Orcamento.jsx`, demo data out of `Carteira.jsx`
   (with its confirm), Sessão. The source pages lose those panels in the same commit.
3. [ ] **Lançamentos.** Split `Transactions.jsx` into `pages/lancamentos/` (Extrato, Cartões,
   shared header); port Carteira's summary figures into Cartões; build the `+ Novo` sheet with the
   bank, transfer and card forms plus `DataVersionContext`; mobile card list for the statement.
   Delete `Carteira.jsx` once its §8 rows are ticked.
4. [ ] **Planejamento.** Orçamento and Recorrentes under one section; collapse their forms;
   "Gerenciar categorias" link.
5. [ ] **Investimentos.** Split `Investments.jsx` into Posição and Operações on the UI kit; mount
   Proventos as the third tab; live filters in Proventos; accents; "Investimento" in `+ Novo`.
6. [ ] **Início.** "Precisa de você" strip and panel links. Final pass over labels (§5) and the
   inventory (§8).
