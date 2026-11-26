# The desktop interface

The desktop stays the React app (`frontend/src`), served by Flask at `/`. Once the phone is native,
the desktop no longer has to work at 390 px: it can be designed for the desk — a wide screen, a
mouse and keyboard, longer sessions of analysis and data entry in bulk. Owner, 2026-10-22: "quero
manter o desktop, inclusive gostaria que as interfaces fossem diferentes".

## Principles

1. **Analysis first.** The phone is for entering, approving and glancing; the desk is for
   understanding and fixing: full tables, filters always visible, comparisons side by side,
   exports, bulk edits, imports.
2. **Same server, same rules.** A desktop redesign changes presentation only. A new number on a
   desktop screen comes from an endpoint (or an existing tested `lib/` rule), never from a new
   inline computation.
3. **Same visual language.** The tokens, palettes and visual rules of CLAUDE.md still hold
   ("Theme and tokens", "Visual rules", "Frontend conventions", "Privacy mode"). Emerald is the only
   accent; colour only for meaning.
4. **Keyboard and density.** Tables instead of stacked cards; sticky headers; sortable columns;
   keyboard shortcuts for the frequent actions (new entry, search, next/previous month); hover for
   secondary details instead of taps.
5. **Don't break the phone while it still uses React.** Until a screen is native, the APK renders
   its React version at phone width. Desktop layouts go from the `xl` breakpoint (1280 px) up and
   leave the existing behaviour below `lg` alone. When the screen is native (README status table),
   its phone-only code can go.

## Layout

| Area | Today (shared) | Desktop |
|---|---|---|
| Navigation | Top bar + phone bottom bar, section tabs from `lib/navigation.js` | A fixed left sidebar with the sections and their tabs always visible; the header keeps the bell, the eye and the account |
| "+ Novo" | Bottom sheet | A dialog, plus an inline "new row" in the Extrato; `N` opens it |
| Page body | One column | Content in a grid: the main table/list and a side panel (filters, details of the selected row, summaries) |
| Row actions | "⋯" menu, 44 px targets | Visible icon buttons on hover, "⋯" for the rest, compact rows |
| Charts | Full width, one at a time | Side by side with their table; larger, with hover tooltips |

## Screen by screen

| Screen | Desktop plan |
|---|---|
| Início | A dashboard grid: balance and accounts, Resumo do mês, attention items, next invoices, the month's cash flow and categories on one screen without scrolling at 1440×900. |
| Extrato | The main desktop workspace: a full table (date, description, category, account, amount, balance), filters in a side panel, search, multi-select for bulk recategorize/delete, inline edit, the selected row's details and receipts in the side panel. |
| Cartões | Invoices as columns (open, next, paid) with the purchase table of the selected invoice; refunds and sharing in the side panel. |
| A receber | A table grouped by person with totals; mark several as paid at once. |
| Importar | Desktop-first: drag-and-drop file, the preview as a wide table with rules applied, duplicates flagged. |
| Orçamento | Plan and categories side by side; the category table with planned/spent/remaining columns; the month switcher always visible. |
| Recorrentes | A table with the next occurrences; run/pause inline. |
| Metas | Cards in a grid with the forecast chart beside each. |
| Investimentos › Posição | One full table of positions (all classes, groupable), with the allocation chart beside it; Tesouro lots expandable inline. |
| Investimentos › Operações | A full table with filters; "Registrar operação" as a dialog. |
| Investimentos › Rentabilidade | The comparison chart large, the year table beside it. |
| Investimentos › Proventos | Calendar/month table plus totals by asset. |
| Investimentos › Alocação, IR | Desktop-first: wide tables (targets vs current, the monthly apuração, Bens e Direitos), exports. |
| Calculadora | Form and the yearly table side by side. |
| Ajustes | Two-column settings: sections list on the left, the section on the right. |

"Per screen" below carries the details found while specifying each screen.
Before a screen's redesign starts, its plan goes into `docs/next-steps.md` and the owner sees the
1440 px screenshots (agent `desktop-screen-builder`).

## Order

Independent of the native steps; the suggested order follows what the owner does at the desk:
Extrato → Investimentos (Posição, Operações) → Importar → Orçamento → Início → the rest.

## Per screen

The "Desktop" sections of the old per-screen specs (the specs themselves were removed 2026-11-26, once
the native port was done: `git show a79c731:mobile-docs/native/screens/<file>`).

### App shell, login and session — native spec

Keep the single top strip (brand, section pills, review/pending pills, bell, eye, user menu,
"+ Novo") but move to the planned fixed sidebar ≥ 1280 px; drop the bottom navigation and the 44 px
targets; "+ Novo" becomes a dialog or inline row. The login page can lose the phone-specific
layout (it is "Finanças" since 2026-10-23).

### "+ Novo" — native spec

Keep the four forms but as a dialog or an inline row at the top of the Extrato (no bottom sheet,
no 44 px targets); allow keyboard-only entry (Enter saves, type shortcuts). The offline queue matters
less on the desktop but stays (same `lib/outbox.js`).

### Início — native spec

Keep and widen: hero + summary + next invoice in one row, then flow/categories and invoices/
installments side by side (as today at `xl`), plus room for analysis (12-month table under the flow,
category drill-down to the Extrato). Drop the horizontal account strip in favour of a grid.

### Extrato — native spec

Keep and widen: full table (Conta, Categoria, Descrição, Valor, Ações) with inline edit, filters always
visible in a side panel, multi-select for bulk delete/recategorize (with `POST /api/import-rules/apply`-style
confirmation), and the export dialog. The investments view becomes a sortable table.

### Cartões — native spec

Keep, widened: cards side by side (already two columns at `xl`), each invoice as a table (date, description,
category, installment, share, amount), and a timeline of future invoices per card. Add a per-card history view
(paid invoices, `?include_archived=1` for archived cards) — today only open items are listed.

### A receber — native spec

Keep, as a table per person (date, description, card, total, others' part, status) with multi-select settle,
and a filter by person. Low priority for redesign: the current layout already reads well at desk width.

### Importar — native spec

Primary home. Redesign as a full-width review table (sticky header, select-all per status, bulk category
change, inline rule creation with an editable pattern), the options and mapping in a side panel, and drag-and-
drop of several files in sequence.

### Orçamento — native spec

Keep, widen: plan panel and summary side by side, categories as a table (category, %, planned,
carry-over, spent, remaining, status) with lines expanding inline; add a month-over-month view of
spent per category (analysis). The sliders can stay; a numeric field beside them is fine on desktop
as long as it clamps with the same `percentRoom()`.

### Recorrentes — native spec

Keep, widen into a table (descrição, tipo, categoria, conta, frequência, próxima, valor, status) with
inline editing of every field (not just amount — including the account, which closes the `blocked`
gap), and the 90-day forecast as a side panel or a cumulative cash chart.

### Metas — native spec

Keep; widen into a two-column grid (already `xl:grid-cols-2`) and add a projection chart per goal
(value over time at the planned contribution vs the target line), computed by a new server endpoint,
not in the browser.

### Ajustes — native spec

Keep Contas, Cartões, Categorias, Regras and Integrações, widened into tables with inline edit (Regras
with the apply preview as a full-width table). Drop Notificações and Versão do app (phone only; already
hidden outside the APK). Fix stale copy: Integrações' "…e o extrato dos bancos" (there is no bank API)
and Notificações' "Por enquanto só guarda os textos".

### Investimentos › Posição — native spec

Keep and widen: the full table (Ativo, Qtd, Preço médio, Cotação, Valor, Rentab., Proventos,
Rentab. c/ proventos) with groups as `tbody` sections, the Tesouro table (Vencimento, Quantidade,
PU, Saldo líquido, Saldo bruto), donut and evolution side by side, summary always visible.

### Investimentos › Operações and "Registrar operação" — native spec

Widen into the table (Data, Ativo, Preço, Total, Resultado, IR estimado) with filters by asset,
type and period; the register form as a dialog; corporate events in a side panel.

### Investimentos › Rentabilidade (and the investments' charts) — native spec

Keep and widen: summary + toggles + chart in a wide row, the year × month table as a real table,
per-asset table sortable; add a selectable comparison range (desktop-only analysis).

### Investimentos › Proventos — native spec

Keep the table history (Pagamento, Ativo, Valor/cota, Qtd., Bruto, Imposto, Líquido, YOC) with the
filters always visible; calendar and chart side by side; per-asset table sortable.

