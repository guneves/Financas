# Importar — native spec

| | |
|---|---|
| Migration order | 9 — desktop-first; recommended **not** to build natively (see "What it is for") |
| Status | Not started |
| React source | `frontend/src/pages/lancamentos/Importar.jsx` (Stepper, `readFileText()`, `suggestPattern()` inline), `pages/lancamentos/helpers.js` (`categoryLabel()`) |
| Route(s) | `/lancamentos/importar` |
| Endpoints | `POST /api/import/preview`, `POST /api/import/commit`, `POST /api/import-rules`, `GET /api/accounts`, `GET /api/categories` |
| Client rules | inline only: `readFileText()` (UTF-8, fallback windows-1252), `suggestPattern()`, row selection/override state; parsing, dedupe and rule matching are server-side (`backend/statement_import.py`, `backend/routes/imports.py`, `backend/services/import_rules.py`) |

## What it is for
Importing a bank statement file (CSV or OFX) into one account: preview every row with its status and
category, adjust, then commit. It is a desk task — the file comes from the bank's internet banking, the review
is a long table, and the column mapping/options need room.

**Recommendation: keep it desktop-only (order 9) and drop it from the phone's navigation when the WebView goes
away (step 8).** Reasons from the code and the plan: (1) since Phase 6 the phone's daily capture path is
Aprovar (bank notifications), which covers what import used to fill; (2) the screen needs a file picker,
encoding detection and a 2,000-row review table with per-row category selects and a column-mapping grid —
the phone gains nothing from native here; (3) import is already idempotent and server-driven, so the desktop
can do it any time without data loss. If the owner later wants it on the phone, the cheapest native form is an
Android **share target** ("Abrir com Finanças" on a `.ofx`/`.csv`) that sends the file to
`POST /api/import/preview` and shows a short "N novos, M já importados → Importar" confirmation, with all rows
at their rule/default category — no per-row editing.

## What it shows
1. **Header** "Importar extrato" / "CSV ou OFX do banco. Nada é gravado antes de você conferir a prévia."
2. **Stepper** "Arquivo" (Conta e extrato) → "Conferir" (Prévia e categorias) → "Importado" (Lançamentos
   gravados).
3. **Banners**: error; success "N lançamento(s) importado(s). M já existia(m) e foi(ram) ignorado(s)." (from
   the commit's `created` / `skipped`).
4. **Panel "1. Arquivo"** ("O banco exporta o extrato em CSV ou OFX; os dois servem."): "Conta de destino"
   (active accounts, default preselected; hint "Todos os lançamentos do arquivo entram nesta conta."),
   "Arquivo" drop zone ("Escolher arquivo ou arrastar para cá", accepts `.csv,.txt,.ofx,.ofc`). Action
   "Trocar arquivo" / "Importar outro arquivo".
   - **"Opções de leitura"** (after a preview): "Separador decimal" (Detectar / Vírgula (1.234,56) / Ponto
     (1,234.56)), "Separador de colunas" (Detectar / ; / , / tab / |, hint "Detectado: \"x\"" from
     `preview.delimiter`), "Linhas a pular", "Sinal: Inverter"; for CSV a mapping grid Data / Descrição / Valor
     / Débito / Crédito / Tipo over `preview.columns`. Every change re-runs the preview.
5. **Panel "2. Conferir"**: "N linha(s): a nova(s), b já importada(s), c com erro." and "Importar N"
   (disabled with no selection or a selected row without category). Warnings "Escolha uma categoria para cada
   linha selecionada." and, when `truncated`, "O arquivo tem mais linhas do que cabe em uma importação; as
   primeiras foram lidas."
   - **Row**: checkbox (NEW rows preselected; DUPLICATE unselected; ERROR disabled, rose background);
     description or "(sem descrição)"; "Linha N", date dd/mm/aaaa, status badge "Novo" (success) / "Já
     importado" (neutral) / "Erro" (danger) + error text, "regra: <pattern>" (green) when categorized by a rule;
     category select (the row's category kept when archived or name-only); "Criar regra"; amount
     `formatSignedCurrency` (INCOME green "+", EXPENSE "−").
6. Empty states: "Escolha um arquivo" / "Exporte o extrato do banco em CSV ou OFX e selecione o arquivo acima.
   A prévia mostra o que entraria antes de gravar."; "Nenhuma linha" / "O arquivo não tem lançamentos
   legíveis.". Footer note "Reimportar o mesmo extrato não duplica nada: cada linha carrega uma assinatura
   própria. As regras de categorização ficam em Ajustes → Regras de importação."

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Preview | pick file / change option, mapping or account | `POST /api/import/preview` `{content, filename, account_id, mapping?, delimiter?, decimal_separator, invert_sign, skip_rows}` (also accepts `format`, `has_header`) | none (never writes) | refused |
| Import | "Importar N" | `POST /api/import/commit` `{account_id, rows:[{date, amount, type, description, category_id?, category, source_id, rule_id?}]}` | success banner; preview reloads (rows become "Já importado") | refused |
| Create rule | row "Criar regra" | `POST /api/import-rules` `{pattern: suggestPattern(description), category_id?, category}` then re-preview | none | refused |
| Change a row's category | row select | local override only (sent with the commit) | — | n.a. |

Server refusals (400, verbatim): "Envie o conteudo do arquivo em 'content'.", "Arquivo grande demais para
importar de uma vez." (> 4,000,000 chars), parser errors (`statement_import.ImportError_`), "Envie as linhas a
importar em 'rows'.", "Linhas demais em uma unica importacao." (> 2,000), "Linha N: <validation>", "Ja existe
uma regra igual a essa." (rule).

## Data
- `POST /api/import/preview` → `{format: 'CSV'|'OFX', delimiter, has_header, columns[], mapping{role:
  index}, truncated, account_id, rows[], summary{total, new, duplicates, errors, categorized}}`. Row:
  `{line, date, amount, type: 'INCOME'|'EXPENSE', description, fitid, error, status: 'NEW'|'DUPLICATE'|'ERROR',
  source_id, category, category_id, rule_id, rule_pattern, category_source: 'RULE'|'DEFAULT'|null}`.
  Default category is "Outros" (root) for EXPENSE and "Receita" for INCOME (`DEFAULT_IMPORT_CATEGORIES`).
- `POST /api/import/commit` → `{created, skipped}` (201). Rows are `INSERT OR IGNORE` with
  `source_type = 'STATEMENT_IMPORT'`; rule hits counted only for rows actually created.
- Accounts and categories: keys `['contas','ativas']`, `['categorias','ativas']`. Preview/commit results are
  component state, not cached queries.

## Client rules
- `readFileText()` (inline, untested) — decode as UTF-8; on U+FFFD, decode as windows-1252. A share-target
  version must do the same (Brazilian banks still emit ISO-8859-1). **Port** if ever built.
- `suggestPattern()` (inline, untested) — first two words, numbers and "*" dropped, ≤ 40 chars. **Port** or
  move server-side (`POST /api/import-rules` could accept a description).
- Selection defaults (NEW selected) and "missing category" gate (inline). **Port** if built.
- Everything about money and identity is server-side: amount parsing ("the last separator is the decimal…"),
  the row hash / OFX FITID `source_id` with occurrence suffix, duplicate detection, rule matching.

## States
- Loading accounts: skeleton in the account field; parsing: one skeleton block in a panel.
- Errors in the top banner; per-row errors inline.
- Offline: not usable (every step needs the server).
- Privacy mode: amounts not masked (they are file rows, not balances).

## Conventions that apply
- "An import is idempotent by construction" — `source_id` from the preview goes back in the commit; a
  re-import is a no-op; identical rows in one file get an occurrence suffix.
- "Rules touch the past only on confirmation" — the preview never writes; rule application to old lançamentos
  lives in Ajustes, not here.
- "Transactions.category still holds the category name, but the id decides" — rows carry `category_id`; the
  commit accepts a rule's archived category (`allow_archived`).
- "Dates and months are stored zero-padded" — the server normalizes.
- "Investimento is not a category" — 039 switched off the rules that chose it; nothing to do here.

## Native-only improvements
Only if the owner asks: the share-target flow described above (receive a file from the bank app or Files,
preview counts, one-tap import). No native table.

## Acceptance
Desktop (where it stays):
- [ ] An OFX imported twice creates rows the first time and "0 importados, N ignorados" the second.
- [ ] A CSV in ISO-8859-1 shows accented descriptions correctly.
- [ ] "Criar regra" on a row re-categorizes the matching rows in the preview and shows "regra: <pattern>".
- [ ] Rows with errors cannot be selected; "Importar" stays disabled while a selected row has no category.
Phone (after step 8): the Importar tab is gone from Lançamentos, or opens a "use o computador" note.

## Desktop
Primary home. Redesign as a full-width review table (sticky header, select-all per status, bulk category
change, inline rule creation with an editable pattern), the options and mapping in a side panel, and drag-and-
drop of several files in sequence.
