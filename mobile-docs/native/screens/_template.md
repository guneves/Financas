# <Screen name> — native spec

| | |
|---|---|
| Migration order | <n> (see `../migration-order.md`) |
| Status | Not started |
| React source | `frontend/src/...` (every file the screen uses, components included) |
| Route(s) | `/...` |
| Endpoints | `GET /api/...`, `POST /api/...` |
| Client rules | `lib/....js` (`functionName()`), ... |

## What it is for
Two or three sentences: what the owner does here day to day, and why it matters on the phone.

## What it shows
The phone layout from top to bottom, section by section. For each section: the values shown, where
each value comes from (endpoint + field, or a client rule), formatting (currency, sign, date),
privacy mode (masked or not), and colour meaning (gain/loss/warning/info only).

## Actions
One row per thing the owner can do:

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| ... | button/menu | `METHOD /api/...` + payload fields | toast / confirmAction text | queued / refused / n.a. |

Validation messages and the server's refusals (status + Portuguese message) the screen must show.

## Data
Each endpoint the screen reads: method, path, query parameters, and the response fields actually
used (not the whole payload). Note the TanStack Query key it uses today (`lib/queries.js`) and what
invalidates it.

## Client rules
Each rule the React screen computes itself (from `lib/`, or inline in the component): what it does,
where it lives (file + function), its tests (`*.test.js`), and the recommendation for native:
**port** (same test cases as JVM tests) or **endpoint** (move to the server; preferred when the
rule is about money). Mark any rule that exists only inline in a component (no test today).

## States
Loading (skeleton), empty, error, offline (cached data? estimate label?), privacy mode, light/dark.

## Conventions that apply
The CLAUDE.md conventions this screen must keep, quoted by their bold title (e.g. "Transfers are
one row, not two"), each with one line on what it means here.

## Native-only improvements
Optional: what native can do better here (instant open, haptics, swipe actions, widget, shortcut).
Never a change in a money rule.

## Acceptance
Checklist the owner verifies on the phone (debug APK first), written as observable behaviour.

## Desktop
What the desktop redesign should do with this screen (`../../desktop/`): keep, merge, widen into a
table, add analysis, or drop from the desktop.
