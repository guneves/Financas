# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-27 (evening) · every B3 ticker can be found

The owner reported that the app did not find LEVE3, then FESA4, and asked that all assets be
available. Cause: the ticker search and the buy guard (`resolve_catalog_ticker`) read only the
static ~250-ticker list in `market_catalog.py`. Five of the owner's real holdings (LEVE3, FESA4,
RANI3, SAPR4, SOJA3) were missing from it. No `session-scout` (targeted bug). `finance-guard` ran; see below.

### What was done
- `brapi_client.get_listing()`: the whole `/quote/list` (2 pages, ~2300 tickers), sharing the one-day
  cache with `get_sectors`. `SectorInfo` gained `name` as its **last** field (tests build it positionally).
- `services/market_listing.py`: converts the listing into catalog entries and caches them for a day.
  After a brapi failure it waits 10 minutes before retrying, so the autocomplete never waits on a
  timeout per keystroke. With no token or no network it returns `{}`, which leaves the static list.
  `lookup()` only goes to the network when the static list does not know the ticker.
- `market_catalog.search/lookup` take `extra`, and the static entry wins (better names). The mapping is
  `LISTING_KIND`: stock/unit → Ação, bdr → BDR, fund/etf → ETF, fund/fii and **Fiagro → FII (REIT)**.
  **FI-Infra, FIP, FIDC and untyped funds are excluded** (their tax does not match any class). The
  fractional ticker (`LEVE3F`) is dropped when its base exists.
- `routes/market.py` and `resolve_catalog_ticker` go through the service.
- `conftest.py` now blanks `BRAPI_TOKEN`: the real token from `.env` was reaching the test run.
- 8 new tests (`TestFullB3Listing`), **856 pass**. Live check against brapi: 2284 of 2332 accepted,
  and all five of the owner's missing tickers resolve.

### What was not done and why
- Not tried in the browser. The **backend must be restarted** to pick this up. The first search after
  boot takes a second or two (two brapi pages).
- Fiagro counted as FII is a judgement call (similar tax). FI-Infra remains unbuyable as a quoted
  asset. Ask the owner if they hold any.
- Not opened in a browser — logged as an owner check in `next-steps.md`.
- The fixed-income redemption form in Posição does not send the flag (backend honours it); no bulk
  "mark everything before date X". Both logged in `next-steps.md`; wait for the owner to ask.
- Carried from before, still open: two findings needing the owner (budgets on income categories;
  positions whose running applied value goes ≤ 0), owner checks of benchmarks/sectors/IRPF text, the
  brapi 1-ticker limit, two IRPF codes, **restart the backend** (`:5000` predates migrations
  015–023), the owner walk-through, decisions 3 and 4. `docs/negociacao-2026-09-26-23-43-43.pdf` is
  not ours — leave it out of commits.

### Next session
Ask the owner to restart the backend and search LEVE3/FESA4. Otherwise every open item needs the owner.

### Learned
- A Python heredoc through Git Bash mangles non-ASCII (ç, ã) in the script text, so an `assert old in s`
  on Portuguese text fails. Anchor on ASCII or insert by line number.
- `sed -i` on a CRLF file silently turns it LF; patch CRLF files with `newline=''`.
