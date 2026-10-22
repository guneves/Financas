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
| Aprovar | A list + detail layout: pending items on the left, the selected item's draft on the right; keyboard to approve and move to the next. |
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

Each screen's spec (`screens/*.md`, section "Desktop") carries the details found while specifying it.
Before a screen's redesign starts, its plan goes into `docs/next-steps.md` and the owner sees the
1440 px screenshots (agent `desktop-screen-builder`).

## Order

Independent of the native steps; the suggested order follows what the owner does at the desk:
Extrato → Investimentos (Posição, Operações) → Importar → Orçamento → Início → the rest.
