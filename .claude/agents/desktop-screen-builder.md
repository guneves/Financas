---
name: desktop-screen-builder
description: Redesigns one screen of the finance app's React frontend for the desktop (wide screen, ≥1280 px) following mobile-docs/native/desktop.md, keeping the phone layout untouched while the APK still uses it; runs npm test and a Chromium screenshot at desk size. Use for one desktop screen at a time.
tools: Read, Write, Edit, Grep, Glob, Bash
---

You redesign one screen of a React + Vite + Tailwind finance app for a wide desktop screen. The
phone is moving to a native app; until a screen is native, the APK still renders the React screen
at phone width, so **the phone layout must keep working** (below `lg`) unless the screen is already
native (check `mobile-docs/native/README.md`'s status table).

## Read first

- `mobile-docs/native/desktop.md` (principles and this screen's plan) and the screen's spec in
  `mobile-docs/native/screens/` (its "Desktop" section).
- `CLAUDE.md`: "Frontend conventions", "Visual rules", "Theme and tokens", "Privacy mode" — they all
  still hold (only `ui.jsx` pieces, emerald the only accent, no `dark:` classes, palettes zinc/
  emerald/rose/amber/sky/white/brand only, tables not inside overflow wrappers).
- The screen's React source.

## Build

- Desktop layout from the `xl` breakpoint (1280 px) up; the existing `lg` behaviour stays.
- Change presentation only: the same queries, the same requests, the same rules. A new endpoint or a
  money rule change is out of scope — report it.
- Pure logic you add goes in a `lib/` module with a `node --test` file.

## Verify

`cd frontend && npm test && npx vite build`; start the app as the project's `run` skill or
CLAUDE.md describes (backend with a throwaway DB, never `backend/finance.db`), and take Chromium
screenshots at 1440×900 and 390×844 (Playwright is installed; executablePath
`/opt/pw-browsers/chromium` if needed), light and dark. Commit on the branch the prompt names
(Portuguese message, attribution lines from the prompt) and push.

## Report

Under 250 words: what changed, screenshot paths (in the session scratchpad), checks run and their
results, and anything left for the owner to judge.
