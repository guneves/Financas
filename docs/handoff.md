# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-22 (latest) · Motion pass

The owner asked for research across seven animation sources (tailwindcss-motion, motion.dev, Magic
UI, Aceternity, animate.css, Recharts, animations.dev/easings.net) and a plan under hard
constraints: extend the existing Tailwind vocabulary, emerald only, legibility over decoration,
≤2 deps under ~15 kB each, reduced motion everywhere, animation in `ui.jsx` primitives. The plan was
approved with one addition ("rework it" — the privacy-mode remount in `Layout.jsx`), then built.

### What was done

- **Zero new dependencies.** Motion's smallest bundle with exit animations (`LazyMotion` +
  `domAnimation`) is ~19.6 kB, over the budget; everything below is CSS keyframes plus small hooks.
- **`tailwind.config.js` (additive):** keyframes `fade-out`, `scale-out`, `slide-out-down`,
  `flash-emerald`, `check-draw`, `nudge` (animate.css `headShake` without `rotateY`); animations for
  each plus `skeleton` (fade-in after 150 ms + shimmer); `transitionTimingFunction.out-quint`. The
  app curve `cubic-bezier(0.22, 1, 0.36, 1)` is easings.net's `easeOutQuint` — kept as the only
  curve; exits use it at ~60% of the enter duration.
- **`ui.jsx` primitives:**
  - `prefersReducedMotion()`; `usePresence(open, exitMs)` keeps a node mounted through its exit.
  - `Sheet` animates out (desktop `scale-out`, phone `slide-out-down`, backdrop `fade-out`) and
    renders the **last open content** while leaving — callers null their state with `open`
    (`paying` → null) and it would otherwise flash "Pagar R$ 0,00".
  - `Expand` (new, exported): height via `grid-template-rows 0fr → 1fr`, unmounts after the exit
    like the old Collapsible did (form-reset behaviour unchanged); `overflow` turns visible once
    settled so focus rings are not clipped. `Collapsible` uses it; so do Cartões invoices.
  - `Tabs`: one white pill measured from `aria-current="page"` slides between tabs.
  - `useCountUp(target, { duration, cacheKey })`: 500 ms easeOutQuint, and a module-level cache of
    the last value per `pathname|title` — only the first visit of a session counts from 0; a real
    change animates old → new. Also fixed a one-frame flash of the final value before the count.
    `MetricCard` value is now `tabular`.
  - `useArrivals(items, version)`: ids that appear after a `DataVersion` bump; Extrato rows flash
    `flash-emerald` once. Disarms on the first list change so a later filter never flashes.
  - Success `AlertMessage` draws its check (`check-draw`).
- **`charts.jsx`:** `useChartAnimation()` replaces spreading the static `ANIMATION`. It honours
  reduced motion (recharts' `isAnimationActive` is JS — the CSS media query never reached it, and
  recharts' own `'auto'` only means "off in SSR") and draws a page's charts once per session (marks
  the path on unmount so charts mounting after the data load still draw). 600 ms, app curve; the
  hardcoded 1200 ms / 1000 ms overrides are gone. Used in Dashboard, PortfolioOverview, Proventos,
  Sparkline, DonutChart.
- **`Layout.jsx` (the rework):** the page wrapper is keyed by `pathname` only; the privacy toggle
  remounts through an inner `<Fragment key={valuesHidden}>`, so it no longer replays the page
  fade-up (and, with the caches above, numbers and charts do not re-animate). Moving between tabs of
  the same section uses `fade-in`; changing section keeps `fade-up`.
- **Pages:** Cartões and Início show a success notice after paying an invoice; `PayInvoiceSheet`
  nudges a refused-payment error; Orçamento bars transition `width` on the app curve.
- **`index.css`:** reduced-motion block adds `animation-iteration-count: 1` — the infinite shimmer
  at 0.01 ms was a busy repaint loop, not a static skeleton.

### What was not done and why

- **Not clicked through.** The Chrome extension was offline again; Playwright not installed. Only
  `vite build` (clean) and a check that every new keyframe is emitted. The walk-through list in
  `next-steps.md` has a "Motion pass" item.
- **Deviation from the plan, E (list rows):** no whole-table fade on filter change. Filtering is
  typing; animating the table on every keystroke violates the frequency-of-use rule. Only the
  new-row flash shipped.
- **`fade-in-late`** from the plan became the `skeleton` animation entry instead (one class carries
  both the delay and the shimmer).
- `SegmentedControl` does not get the sliding pill yet — it could reuse the `Tabs` logic.
- Rejected on purpose (see the plan): Magic UI BorderBeam/AnimatedBeam/NumberTicker, Aceternity
  Focus/Wobble/Glare/3D cards, Text Generate, Sticky Scroll, Multi Step Loader, animate.css
  attention seekers, tailwindcss-motion presets, Motion `layoutId`.
- Carried forward from the previous session: **`BRAPI_TOKEN` is still empty** in `backend/.env`,
  so quotes still come from yfinance (brapi integration inert, not broken).

### Next session

- Owner: the browser walk-through at the top of `next-steps.md`, including the motion item.
- Paste the brapi token into `backend/.env`, hit "Atualizar cotações" once, and confirm the quote
  metadata says `provider: brapi` and that a second refresh within 5 minutes spends no credit.
- Phase 5 (splitting `app.py`).

### Non-obvious things learned

- Tailwind emits utilities in config order, so `animate-slide-down` comes after `animate-nudge` in
  the CSS: two `animate-*` classes on one element → the later-defined one wins. `PayInvoiceSheet`
  puts the nudge on a wrapper div for that reason.
- Recharts 3.7 parses `cubic-bezier(...)` easing strings (`es6/animation/easing.js`).
- The invoice-payment path unmounted the sheet and dropped the paid invoice from the list with no
  confirmation at all — hence the success notices.
- The bash tool mangles `${...}` template literals inside a double-quoted `python -c`; use the
  Edit tool or a script file in the scratchpad for JSX with template strings.
