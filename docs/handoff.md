# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-10-27 (2) · Open Finance settings, Conferência, merge to main

Local session on the owner's PC. `claude/pluggy-open-finance` (`c5f4e7e`) fast-forwarded into
`main` with the owner's OK, then this work on `main`.

### Done
- **Scope changed mid-session, by the owner.** The prompt asked for a "Só Open Finance" switch
  (`aprovar_sources`). The owner then said Open Finance helps most in Investimentos, and that on the
  bank side it should check for inconsistencies. Asked and decided: Pluggy **stays a source** of
  Aprovar next to notifications, **no switch**, plus a Conferência. Investments go through approval
  (operations, never overwritten positions) and are only planned for now. The half-built switch was
  removed before commit.
- `GET/PATCH /api/open-finance/settings`: `first_sync_days`, `sync_hours` (0 or 1–24, per user,
  default the server's 6 h), `include_pending`. Everything validated before anything is written;
  unknown keys refused. There is no `auto_approve`; a comment in `services/open_finance.py` says why.
- `services/open_finance_refresh.py`: ticks every 15 min, `due_user_ids()` pulls a user whose oldest
  item `last_sync_at` (or last attempt) is older than their interval. `OPEN_FINANCE_SYNC_SECONDS=0`
  still turns the thread off for everyone.
- `include_pending`: `normalize_transaction(..., include_pending=)`. When a known id comes back with
  the same amount but other details (posted), the row updates in place; an id change goes through
  the existing vanish → `REMOVED`.
- **Conferência** (`services/open_finance_check.py`, `check` on each account in `list_view`):
  bank-only, app-only, awaiting (pending in Aprovar); one to one, same signed cents ≤ 3 days, closest
  first. On cards: one entry per purchase (`client_id`), n-cents tolerance for installments, invoice
  payments out.
- Web (Ajustes › Open Finance): the Conferência per account (badge + "Ver a conferência"), "Busca
  automática" select, "Trazer pendentes" checkbox, first-sync field. APK: the same Conferência,
  select and checkbox (first-sync stays on the web).
- Tests: `test_open_finance_settings.py` (37), `test_open_finance_check.py` (20), full pytest green;
  `npm test` 182; `vite build` ok; `gradlew testDebugUnitTest assembleDebug` 509 JVM tests, APK built.
- Docs: next-steps (new "Open Finance in Investimentos" section, MeuPluggy checks, Conferência
  limits), done-tasks, CLAUDE.md (Aprovar › Open Finance), DEPLOY.md, `.env.example`.

### Not done, and why
- **Investments via Open Finance**: probed, planned, not built (next-steps, first section).
- The Aprovar header line naming the source: dropped with the switch.
- **Phone test (Part 2)**: stopped at step 4. The owner changed direction (results below).

### Phone test results
- **Step 1 (deploy): passed.** Run green (test, build, deploy, apk); `/api/health` ok; Pluggy
  "Configurada"; the settings endpoint answers its defaults. Integrations show "degraded" only from
  Tesouro prices (stale to 15/10), unrelated.
- **Step 2 (APK)**: the workflow publishes it at the server's `/apk/`; `android-check.yml` runs only
  on PRs. Not yet installed by the owner.
- **Step 3 (connect): passed, differently.** The owner had made three MeuPluggy connections on
  Pluggy's side (BB, BTG, Itaú; Flash stays notifications-only). They were registered by item id
  through `POST /api/open-finance/items` (no widget): all `UPDATED`, first 30-day pull ok, 7
  accounts, ~210 rows waiting for mapping. Every `connector_name` is "MeuPluggy", so **no mapping
  suggestion** came (it compares the connector name).
- **Step 4 (map)**: handed to the owner, result not reported. BTG Investimentos cannot be mapped
  (the Corretora is refused); it goes to Investimentos.
- Steps 5–15: not done.
- **Investments probe** (read-only, from the PC with `backend/.env`): BTG through MeuPluggy sends
  36 positions and 71 operations with trade dates. Details are in `next-steps.md`.

### Next session
1. **`docs/prompts/open-finance-only.md`**, the owner's decisions from the end of this session:
   Pluggy becomes the only source for connected banks, recorded automatically (Aprovar only for
   Flash). BTG Investimentos goes into Investimentos automatically. The whole history is compared,
   then linked or recorded (preview → apply). The pull runs hourly (check the quota first).
2. Before building: ask the owner what was mapped in step 4 and what the second Ourocard is.

### Lessons (non-obvious)
- The owner uses the **MeuPluggy** connector on the free plan (one CPF): the connector name is
  probably not the bank's. Check what Aprovar and the suggestions show.
- Tests share one SQLite across users: a "who is due" test must assert membership, not equality.
- `bank_tx` dates in the fake must sit inside the 7-day overlap after the first pull, or nothing is pulled.
