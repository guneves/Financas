# UI remodel — session prompt

> A ready-to-paste prompt for a Claude Code session (or a series of them) that remodels the whole
> frontend: visual language, motion, screen layout, and how each screen presents and handles its
> data. Paste everything under "Prompt" into a fresh session. It is written to be run in stages —
> each stage stops for the owner's approval before the next one builds.
>
> Written 2026-09-22. At that date the "Visual design pass" in `docs/next-steps.md` had items 1–2
> committed (tokens, MetricCard) and item 3 (tables) in progress in the working tree. This remodel
> **absorbs** that pass: finish or fold its open items rather than running both plans in parallel.

---

## Prompt

You are remodelling the UI of a personal finance manager that its owner uses every day
(React 18 + Vite + Tailwind 3 + Recharts + lucide-react, Flask backend, pt-BR interface). The goal
is an app that feels calm, fast and trustworthy with money — clearer screens, better motion, a
coherent visual language — **without breaking any behaviour, financial rule or privacy guarantee.**
Daily usefulness beats novelty: every change must make reading or entering money easier, not just
prettier.

### 0. Before you touch anything

1. Follow the session process in `CLAUDE.md`: run the `session-scout` subagent (or read
   `docs/handoff.md` and `docs/next-steps.md` yourself), and read `ROADMAP.md` for background.
2. Read `docs/next-steps.md` → "Visual design pass": its audit findings (truncated values, money
   alignment, colour without meaning, row density, overflow, chart axes, contrast) are the floor this
   remodel must clear, and decisions A–E there are still the owner's to make — carry them forward.
3. Check `git status`. If the tables work (pass item 3) is still uncommitted, finish and commit it
   first, or ask the owner what to do with it. Do not mix it into a remodel commit.
4. Read the whole UI kit before designing: `frontend/src/components/ui.jsx`, `charts.jsx`,
   `Layout.jsx`, `NewEntrySheet.jsx`, `frontend/src/index.css`, `frontend/tailwind.config.js`,
   `frontend/src/lib/format.js`, `lib/privacy.js`, `lib/navigation.js`, `lib/newEntry.js`.
5. Take **before** screenshots of every screen at 1280 px and 390 px, including privacy mode, the
   "+ Novo" sheet, an empty account, loading and error states. Use the Playwright + scratch-app
   recipe in the handoff / memory (backend on :5001 with a throwaway DB and
   `CORS_ORIGINS=http://localhost:5174`, frontend on :5174, seeded with
   `scripts/seed_three_years_mock.py`). **Never run against `backend/finance.db`.**

### 1. Hard constraints (do not break these)

- **Privacy mode** (the eye) hides balances, net worth and the portfolio only, and never remounts
  the page or refetches. Every sensitive number goes through `usePrivateFormatter()` /
  `usePrivateAxisFormatter()` / `MetricCard sensitive`. Any new component that shows a balance or a
  position must opt in. Re-verify: 0 API calls on toggle, no remount, same masked set as before.
- **Data freshness.** A page that shows data saved by "+ Novo" keeps `useDataVersion()` in its fetch
  effect's dependencies. Don't break the `DataVersionContext` refetch.
- **Routes and navigation** come from `lib/navigation.js`; section tabs come from the URL; the
  `legacyRedirects` keep working. Filters that live in the URL stay in the URL.
- **Money display**: tabular numerals, real minus sign and non-breaking space
  (`formatSignedCurrency`), pt-BR percentages, right-aligned numeric columns, values never truncated.
  Keep `formatCurrency` / date helpers in `lib/format.js`; the `lancamentos/helpers.js` copy stays
  (see `CLAUDE.md`).
- **No new client-side financial logic.** The invoice-month rule, invoice payment, autopay, imports
  and FIFO all live in the backend; the UI only calls the existing endpoints. Destructive actions
  keep their confirmation step.
- **Language**: user-facing strings stay Portuguese (pt-BR); code comments match the surrounding
  file.
- **Accessibility**: WCAG AA contrast for all text (zinc-500 is the lightest text on white), visible
  focus rings, 44 px touch targets on phone, keyboard-operable sheets/tabs/menus with focus trap and
  restore, `aria-*` on toggles. `prefers-reduced-motion` disables every non-essential animation.
- **Dependencies**: prefer none. If you want one (e.g. `framer-motion` / `motion`, a headless UI
  lib), propose it with the reason and bundle cost and wait for approval.
- The backend and `database/` are out of scope. If a screen genuinely needs a new endpoint, list it
  as a follow-up instead of building it.

### 2. What to deliver — stage by stage

**Stage 1 — Audit & direction (report, then stop).** From the before-screenshots, write a short
audit per screen: what the screen is for, the one number or action the owner comes for, what gets
in the way. Then propose a design direction with 2–3 concrete options (mood, type scale, density,
surface/elevation, accent usage), each with one mock of Início and one of Extrato — as an HTML
artifact or screenshots of a throwaway branch. Include decisions A–E from `next-steps.md` and any
new ones. **Wait for the owner to pick.**

**Stage 2 — Plan (then stop).** A numbered, commit-sized plan in `docs/next-steps.md` (replace the
"Visual design pass" section, don't append beside it), kit first, screens after. Wait for approval.

**Stage 3 — Build**, one commit per item, suite and build green, before/after screenshots at both
widths checked by eye after each commit.

### 3. Scope of the remodel

**a. Design system (in `ui.jsx`, `index.css`, `tailwind.config.js` — the kit first).**
- Semantic tokens as CSS variables mapped into Tailwind (`surface`, `surface-raised`, `border`,
  `text`, `text-muted`, `accent`, `gain`, `loss`, `warning`, `info`) instead of raw `zinc-*` /
  `emerald-*` in pages. Emerald stays the single accent; green/red/amber/sky carry meaning only
  (gain / loss / warning / info).
- A type scale with a clear hierarchy for money: hero value, card value, row value, caption.
- Spacing, radius and elevation scales; one card style, one table style, one list-row style.
- **Dark mode** (decision E): design the tokens so it is a token swap, not a second stylesheet.
  Follow the system setting with a manual override next to the eye. Build it only if the owner
  approves; either way the tokens must make it possible.
- Consolidate the kit: every page uses only `ui.jsx` pieces. Add what is missing — e.g. `DataTable`
  / `ListRow` (desktop table ⇄ phone card list from one definition), `Toolbar` / filter bar,
  `Stat`, `Menu` (row actions), `Toast` for success/undo, `ConfirmDialog`, `Tooltip`,
  `Skeleton` variants that match each layout. Remove hand-built one-offs.

**b. Motion.** One motion vocabulary, defined once in `tailwind.config.js` / `ui.jsx`:
- Durations ~120 ms (hover/press), ~200 ms (small enter/exit), ~300 ms (sheets, page); one easing
  (`out-quint`) plus a spring-like variant for sheets; exits ~60% of enters (already the rule).
- Route transitions between sections and between tabs (a subtle cross-fade / slide that follows the
  tab direction), without remounting data-heavy pages unnecessarily.
- Shared, meaningful motion: the tab pill slides, the new row flashes (`flash-emerald`), deleted
  rows collapse, a saved entry animates from the sheet into its list, numbers count only on first
  view (already cached per session — keep that), charts animate once per session.
- Skeletons that match final layout (no layout shift), and optimistic updates where the endpoint
  makes it safe.
- Nothing loops, nothing bounces on every render, and `prefers-reduced-motion` gets instant states.

**c. Shell and navigation (`Layout.jsx`).**
- Desktop: sidebar (decision C width), section tabs, one global "+ Novo", the eye, the user menu.
  Consider a collapsible sidebar and a command palette (`Ctrl+K`: go to screen, new expense, search
  lançamentos).
- Phone: bottom bar, a header that condenses on scroll, sheets that open from the bottom with a
  drag handle and swipe-to-close.
- One header layer per page: title, the page's one primary action, context (month picker, account
  filter). No duplicated "+ Novo".

**d. Screens — rethink how each presents and handles its data.**
For every screen: lead with the answer the owner opens it for, then the detail; make the primary
action obvious; define empty, loading, error and privacy states; define the phone layout explicitly
rather than letting the desktop one wrap.
- **Início (`Dashboard.jsx`, ~1,300 lines — split it into components as you go).** A hero with net
  worth / balance and the month's result; "needs attention" strip (overdue recurrences, open or
  closed invoices, autopay shortfall, budget overruns); cash flow, category spend, saldo por conta,
  evolução. Decide what is above the fold on phone.
- **Lançamentos → Extrato.** Grouped by day with day totals, sticky filter bar, search, inline
  category edit, row actions in a menu, ~100 rows + "Mostrar mais" or virtualization (decision D),
  compact phone rows. **Cartões**: invoice as the unit (period, closing/due dates, status, total),
  purchases as rows, clear "Pagar fatura" state tied to the closed-only rule. **Importar**: a
  stepper (arquivo → prévia → confirmar) with the rules visible per row.
- **Planejamento → Orçamento**: progress bars per category with planned vs. spent vs. rollover,
  over-budget emphasis; month navigation. **Recorrentes**: next occurrence, overdue badge, the "run"
  action with its idempotent result shown.
- **Investimentos → Posição**: allocation and evolução on top, positions grouped by class with
  inline quote, gain/loss colouring, no horizontal overflow on phone. **Operações** and
  **Proventos**: filterable ledgers with monthly totals and a small chart.
- **Ajustes**: sub-navigation in the `Tabs` look; Contas, Cartões, Categorias, Regras, Perfil,
  Dados de demonstração as consistent forms with inline validation.
- **Auth**: a clean sign-in / sign-up with the brand mark.
- **"+ Novo" sheet and `InvestmentLaunchModal`**: fast keyboard entry (autofocus amount, Enter to
  save, `Esc` to close), sensible defaults, remembered last account/category, clear success
  feedback, and the type selector fitting on one line on phone (open decision 8).

**e. Charts (`charts.jsx`).** One palette, one tooltip, one-line axes with AA ticks, one month-label
format, privacy-aware axes, responsive heights, no Recharts resize jank on full-page screenshots.

### 4. Definition of done (per commit and at the end)

- `cd frontend; npm run build` passes; `.\start.ps1 -Tests` still green (the backend must not have
  changed — if it did, run `finance-guard`).
- Before/after screenshots at 1280 and 390 px for every screen touched, looked at by eye; no
  horizontal overflow, no truncated money, no console errors.
- Privacy toggle re-verified on Início, Extrato, Cartões, Posição, Operações, Ajustes (0 API calls,
  no remount, masked set unchanged).
- Reduced-motion and keyboard-only passes on the sheets and tabs.
- `CLAUDE.md` "Frontend conventions" updated with the new tokens, kit pieces and motion rules;
  `docs/next-steps.md` ticked and rewritten; `docs/handoff.md` replaced with the session entry,
  explicit about anything partial; one commit per theme, messages in the repo's pt-BR style.
