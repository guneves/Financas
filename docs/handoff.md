# Handoff

> Handoff between working sessions. It holds **only the most recent session** — each session
> replaces the entry below; older ones are in git history.
> The active work plan is `docs/next-steps.md`; this file records what actually happened and
> what the next session should pick up. See `CLAUDE.md` for the process.

---

## Session — 2026-09-27 (night) · fixed-income form: exemption by type, IPCA+; Gado removed

The owner asked, for the "Registrar operação" renda fixa form: classify "Isento de IR"
automatically from the title's specification, remove Gado from the asset picker, and offer IPCA+
under "Rentabilidade". No `session-scout` (targeted request). `finance-guard` ran twice (fixed income, then the Gado removal): no findings.

### What was done
- Backend: `fixed_income_is_tax_free()` in `services/fixed_income.py` is now the single exemption
  rule (LCI, LCA, LIG, CRI, CRA, `DEBENTURE_INCENTIVADA`; a stored `is_tax_free` still counts, for
  old rows). `fixed_income_net_value`, `realized_tax_rate`, the portfolio's `is_tax_free` and
  `tax_report.bens_code` read it. `LIG` and `DEBENTURE_INCENTIVADA` are accepted title types.
  Consequence: an existing LCI/LCA/CRI/CRA saved *without* the flag now nets no IR — correct by law.
- Frontend (`lib/fixedIncome.js`, `FixedIncomeFields.jsx`): the checkbox is gone; a read-only
  "Imposto de renda" field shows Isento / Tributado from the type, and `is_tax_free` is written from
  it. "Rentabilidade" = Pós-fixado (CDI) / IPCA+ / Pré-fixado (IPCA+ still stored as POS + IPCA);
  the Indexador select (% do CDI / CDI+) shows only for Pós. An old `DEBENTURE` flagged exempt opens
  for editing as "Debênture incentivada".
- Then the owner asked to remove Gado everywhere: `CATTLE` is gone from `ALLOWED_ASSET_CLASSES`
  (the API answers 400), the labels, its 15% default rate, the mortality rule in the portfolio value,
  the GCAP filter (now `OTHER` only) and every frontend class list. Checked read-only first: the
  real `finance.db` has 0 CATTLE movements and 0 allocation targets. The migrations' `CHECK`
  constraints still list it (append-only; a table rebuild for this is not worth it). CLAUDE.md updated.
- Tests: type-based exemption, legacy flag, net value, new types accepted, Bens code. Suite green.

### What was not done and why
- Not tried in a browser; `vite build` passes. Owner check: open Registrar operação → Renda Fixa.
- A CDB saved with a manual "Isento" tick loses it the next time it is edited and saved (the type
  rules). Deliberate; mention if the owner had such a row.
- Carried from before, still open: restart the backend and search LEVE3/FESA4; two findings needing
  the owner (budgets on income categories; positions whose running applied value goes ≤ 0); owner
  checks of benchmarks/sectors/IRPF text; the brapi 1-ticker limit; two IRPF codes; the owner
  walk-through, decisions 3 and 4; the skip_cash flag on the Posição redemption form.
  `docs/negociacao-2026-09-26-23-43-43.pdf` is not ours — leave it out of commits.

### Next session
Owner checks of this form and of the B3 listing. Otherwise every open item needs the owner.

### Learned
- `sed -i` on a CRLF file turns it LF (again) — re-add `` with `sed -i 's/$//'` or patch in
  Python with bytes.
- Python heredoc through Git Bash: write non-ASCII as `ç` escapes and it survives.
