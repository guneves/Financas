# UX reorganization

> Frontend-only reorganization of the app: organization, flows and presentation, no backend change,
> no new feature, no change to any calculation. The full original spec (audit, decisions D1–D10,
> screen map, per-screen hierarchy, label glossary, tap counts, feature inventory) is in git at
> `9c186fe:docs/ux-reorganization.md`. What was built and tested has been written off below;
> only open items remain in this file.

---

## ✅ Done — 2026-09-21

All six steps shipped, one commit each, `vite build` green after each step. Every feature in the
original §8 inventory was exercised in headless Chrome at 1400px and 390px, against a scratch
backend with a throwaway database (never `backend/finance.db`): no console errors, no horizontal
page scroll.

| Step | Commit | What it delivered |
|---|---|---|
| 1 Shell | `d47e506` | 4 sections (Início · Lançamentos · Planejamento · Investimentos) + Ajustes; phone bottom bar with **[+]**; gear to Ajustes; Portuguese nested routes, old paths redirect (`lib/navigation.js`); section tabs from the URL; "Área atual" header removed. `ui.jsx`: `AlertMessage`, `Tabs`, `Collapsible`, `Sheet` (portal), 44px `IconButton` on touch. |
| 2 Ajustes | `c439a3e` | `/ajustes` with `#contas`, `#cartoes`, `#categorias`, Dados de exemplo (now behind `window.confirm`), Sessão. Forms behind Collapsible. Management UI removed from the statement and budget pages. |
| 3 Lançamentos | `7763447` | `pages/lancamentos/` (Extrato, Cartões, projection header). Extrato: search + Filtros with count, card list on phones. Cartões: Carteira's four figures, nearest invoice expanded, Pagar fatura primary. Global **+ Novo** sheet (Despesa, Receita, Transferência, Compra no cartão, Investimento) with today / default account / first card / 1x defaults; `DataVersionContext` refetch. `Carteira.jsx` and `Transactions.jsx` deleted. |
| 4 Planejamento | `e59193e` | Orçamento: month selector in header, "Adicionar categoria ao mês" collapsible, "Copiar mês anterior", "Gerenciar categorias". Recorrentes: "Lançar pendentes" primary, "Nova recorrência" collapsible. |
| 5 Investimentos | `8c24858` | `pages/investimentos/` (Posição, Operações) on the UI kit, no blue, cards on phones; `InvestmentLaunchModal` on `Sheet` (same props); Proventos with live filters and collapsible form. |
| 6 Início | `0ba9dde` | "Precisa de você" strip (overdue recurrences → Lançar; open invoice → Pagar); panel titles link to their screens; §5 label and accent pass across the app. |

Removed on purpose: Carteira's duplicate forms/lists and its 6-month chart (D1, D10), its all-time
"Entradas/Saídas totais" figures, the "Área atual" header.

Behaviour differences from before (deliberate, see `docs/handoff.md`):
- Card purchases go through `POST /api/cc-expenses/purchases` (backend invoice rule). Installments
  now sum to the exact total (100 in 3x = 33,34 + 33,33 + 33,33 instead of 3 × 33,33), so deleting
  a purchase matches its installments with a 1-cent tolerance.
- Cartões' balance figures skip `TRANSFER` rows (Carteira counted them as expenses).
- Demo data dates are computed when the button is pressed, not at module load.

---

## Open

- [ ] **Owner walk-through in the real app.** Everything above was tested on a scratch database;
  the owner has not used it yet. Things to judge: the two "+ Novo" buttons on Início and Extrato
  (page header + sidebar/bottom bar — keep one?), the Cartões header having Pagar fatura and
  + Novo side by side, the type selector wrapping onto two lines in the sheet.
- [ ] Cash-flow chart legend on Início still says "Entradas/Saídas" (allowed for plural aggregates
  by the glossary; change to Receitas/Despesas if preferred).
- [ ] Statement filters are not kept in the URL — a reload clears them.
- [ ] `index.html` declares no favicon, so every first load logs a 404.
- [ ] Bundle is 737 kB (> 500 kB warning) — route-level `lazy()` would split it.
