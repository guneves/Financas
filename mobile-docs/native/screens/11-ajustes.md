# Ajustes — native spec

| | |
|---|---|
| Migration order | 6 (see `../migration-order.md`) |
| Status | Built 2026-10-24 on `claude/practical-hamilton-e6nxfi` (native-level 7): `ui/ajustes/` — a section list opening each section: Contas (create with signed initial balance, edit, default, link/unlink portfolio, archive, reactivate; balances masked), Cartões (functions via `CardFunctions.cardFormPayload`, closing-day auto-fill, the row's Débito automático select, edit keeping an archived debit account, delete), Categorias, Aprovar (`always_ask`), Aparência, Perfil (username, masked e-mail, Sair), Notificações dos bancos (`NotifyPlugin`'s static helpers, `rules/NotifyTexts.kt` = `notifyRules.js`), Versão do app (APK only: `ApkUpdatePlugin.latestState/installNow`, `rules/ApkUpdateTexts.kt`). Session E (2026-10-25): no WebView — the theme applies by recreating the activity ("Sistema" follows the phone), Sair goes to the native login, `NotifyAccess`/`ApkUpdater` replace the plugins, and **Regras de importação and Integrações are desktop-only** (a note under the list). Every list re-read after a write refreshes the copies "+ Novo" and Aprovar use. Waiting for the owner's phone check. Not built: biometric gate, the listener-lost notification, "Sempre perguntar" inside native Aprovar |
| React source | `frontend/src/pages/Ajustes.jsx`; `pages/ajustes/ContasSection.jsx`, `CartoesSection.jsx`, `CategoriasSection.jsx`, `RegrasSection.jsx`, `AprovarSection.jsx`, `IntegracoesSection.jsx`, `AparenciaSection.jsx`, `PerfilSection.jsx`, `NotificacoesSection.jsx`, `AppVersionSection.jsx`; `components/ApkUpdateBanner.jsx` (`ApkUpdatePrompt`) |
| Route(s) | `/ajustes` with anchors `#contas`, `#cartoes`, `#categorias`, `#regras-de-importacao`, `#aprovar`, `#integracoes`, `#aparencia`, `#perfil`, `#notificacoes`, `#versao` (last two only in the APK) |
| Endpoints | `GET/POST /api/accounts`, `PATCH/DELETE /api/accounts/<id>`; `GET/POST /api/credit-cards`, `PATCH/DELETE /api/credit-cards/<id>`; `GET/POST /api/categories`, `PATCH/DELETE /api/categories/<id>`; `GET/POST /api/import-rules`, `PATCH/DELETE /api/import-rules/<id>`, `POST /api/import-rules/apply/preview`, `POST /api/import-rules/apply`; `GET/PATCH /api/inbox/settings`; `GET /api/health/integrations?refresh=1`; `PATCH /api/auth/me` |
| Client rules | `lib/cardFunctions.js` (`cardFormPayload()`, `cardFunctionOf()`, `cardFunctionLabel()`, `hasCredit()`, `hasDebit()`), `lib/portfolioAccount.js` (`pickPortfolioAccountId()`, `isBrlAccount()`, `PORTFOLIO_ACCOUNT_TYPE`), `lib/transactions.js` (`accountBalanceBrl()`), `lib/monthlyPlan.js` (`parseMoneyInput()`, `moneyInputValue()`), `lib/notifyRules.js`, `lib/notifyCapture.js`, `lib/appBundle.js`, `lib/appBundleRules.js`, `lib/theme.js`, `lib/auth.js`, `lib/format.js` (`maskEmail()`) |

## What it is for
One long page of things configured once and rarely changed: accounts, cards (and their crédito/débito
functions), categories, import rules, Aprovar's "always ask", integration health, theme, profile,
and — in the APK only — the bank-notification listener and the app version. On the phone the
frequent visits are Notificações (permission trouble), Versão (updates) and occasionally a new
account or card. Each section below can migrate on its own; the shell is a list of section rows
opening a sub-screen (instead of the web's single scroll with anchor chips).

## What it shows
Header "Ajustes" / "Contas, cartões e categorias — o que se configura uma vez e raramente muda.",
chips per section (scroll to anchor). Sections in page order:

### Contas — native **early** (with step 1's account cache)
- Panel "Contas" (badge "N conta(s)", active only). Row: `name`, badges "Padrão" (`is_default`) and
  "Carteira" (`id === pickPortfolioAccountId(active)` — first active BRL `BROKERAGE`); line 2 type
  label (`CHECKING` "Conta corrente", `SAVINGS` "Poupança", `BROKERAGE` "Corretora", `CASH`
  "Dinheiro", `OTHER` "Outra") + " · institution". Right: Corretora → link "Em Investimentos"
  (never its balance); else `accountBalanceBrl(account)` (`balance_brl` ?? `balance`), **masked in
  privacy mode**, rose when < 0, "sem câmbio hoje" when null. "⋯" menu.
- Collapsible "Arquivadas (N)": name + type, ↺ "Reativar a conta …".
- Collapsible "Nova conta": "Nome" (placeholder "Ex: Nubank"), "Tipo" (hint for Corretora "Conta da
  carteira: as operações de investimento saem dela."), "Instituição" (optional), "Saldo inicial"
  (text; leading "-" allowed, rest via `parseMoneyInput()`; NaN → "Informe um saldo inicial
  válido."). No currency field (reais only).
- Edit sheet `Editar "<nome>"` ("Mudar o saldo inicial recalcula o saldo da conta; nenhum lançamento
  muda."): Nome, Instituição, Saldo inicial.

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Create | "Nova conta" | `POST /api/accounts` `{name, type, institution, initial_balance}` | toast `Conta "<nome>" criada.` | refused |
| Edit | ⋯ "Editar conta" | `PATCH /api/accounts/<id>` `{name, institution, initial_balance}` | toast `Conta "<nome>" atualizada.` | refused |
| Make default | ⋯ "Tornar padrão" (not default, not Corretora) | `PATCH` `{is_default: true}` | toast `"<nome>" é a conta padrão.` | refused |
| Link to portfolio | ⋯ "Vincular à carteira" (not Corretora, not default, BRL) | `PATCH` `{type: "BROKERAGE"}` | confirm `Vincular "<nome>" à carteira?` / "A conta passa a ser do tipo Corretora, e as próximas operações de investimento saem dela. As operações já registradas não mudam." → toast `"<nome>" vinculada à carteira.` | refused |
| Unlink | ⋯ "Desvincular da carteira" (Corretora) | `PATCH` `{type: "CHECKING"}` | confirm `Desvincular "<nome>" da carteira?` (…"o saldo dela volta a aparecer no Início"…) → toast | refused |
| Archive | ⋯ "Arquivar conta" | `DELETE /api/accounts/<id>` → `{archived, transactions}` | confirm `Arquivar a conta "<nome>"?` / "Os lançamentos dela continuam no extrato." → toast | refused |
| Reactivate | ↺ | `PATCH` `{archived_at: null}` | toast `Conta "<nome>" reativada.` | refused |

Refusals: 409 "Ja existe uma conta com este nome.", 409 "Esta e a unica conta ativa. Crie outra antes
de arquivar esta.", 400 "Uma conta arquivada nao pode ser a padrao.", "A conta da carteira
(Corretora) nao pode ser a padrao.", 404 "Conta nao encontrada.". Data: `GET
/api/accounts?include_archived=1`, key `['contas', 'todas']` (`id, name, type, institution,
initial_balance, balance, balance_brl, currency, is_default, archived_at`). This GET **writes**
(default mark, due autopay, paid proventos) before answering. "Instituição" is the *bank field*
Aprovar reads (`bank_of_row()`), so it matters beyond display.

### Cartões — native **early** (card functions feed "+ Novo")
- Panel "Cartões" (badge "N cartão(ões)", active cards only). Row: `name`, badge
  `cardFunctionLabel()` ("Crédito" / "Débito" / "Crédito e débito"), badge "Débito automático" when
  `autopay_account_id`; line 2 "Vence dia D • Fecha dia F" (credit) and "Débito em <conta>" (debit;
  "conta arquivada" when not in the active list). Credit cards show an inline select "Débito
  automático" (Desligado / active accounts — Corretora included, unverified whether intended). "⋯":
  "Editar cartão", "Excluir cartão". Link "Ver faturas →" to `/lancamentos/cartoes`.
- "Novo cartão": "Nome do cartão", "Funções" segmented Crédito | Débito | Os dois (hint "Débito: a
  compra sai direto de uma conta, sem fatura."); credit → "Vencimento", "Fechamento" (auto-filled
  due − 7, wrapping +30; hint "Preenchido 7 dias antes; ajuste se precisar."), "Débito automático";
  debit → "Conta do débito" (active, non-Corretora; required).
- Edit sheet (description warns that turning credit off disables autopay and is refused with an
  open invoice): name, functions, due/closing (blank for a debit-only card, whose stored 1s are
  never read), debit account (keeps an archived current one as an option). Autopay is not in the
  sheet — only the row select.

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Create | "Novo cartão" | `POST /api/credit-cards` `cardFormPayload()` → `{name, credit_enabled, debit_account_id, due_day?, closing_day?, autopay_account_id?}` | toast `Cartão "<nome>" criado.` | refused |
| Edit | ⋯ → sheet | `PATCH /api/credit-cards/<id>` same minus autopay | toast `Cartão "<nome>" atualizado.` | refused |
| Autopay | row select | `PATCH` `{autopay_account_id: id \| null}` | toast "Débito automático do "<cartão>" ligado: a fatura será paga no vencimento, dia D, com saldo de <conta>." / "…desligado." | refused |
| Delete | ⋯ "Excluir cartão" | `DELETE /api/credit-cards/<id>` → `{deleted, archived?}` | confirm `Excluir o cartão "<nome>"?` (paid history stays; open invoice blocks) → toast `Cartão "<nome>" excluído.` | refused |

Client validation (`cardFormPayload()`): "Informe o nome do cartão.", "Escolha a conta de onde sai a
compra no débito.", "Informe o vencimento e o fechamento do cartão (dia de 1 a 31).". Server: "Escolha
ao menos uma funcao do cartao: credito ou debito.", "Um cartao so de debito nao tem fatura nem debito
automatico.", 409 "O cartao ainda tem fatura em aberto: pague ou exclua essas compras antes de tirar a
funcao credito.", "A conta da corretora fica em Investimentos: escolha uma conta do banco para o
debito.", "Informe o vencimento e o fechamento para ligar a funcao credito.", 409 "Ja existe um cartao
com este nome." / "Um cartao excluido ainda usa este nome no historico. Escolha outro nome.", 409 "O
cartao <nome> ainda tem N item(ns) em aberto nas faturas (R$ x,xx). …", 404 "Cartao nao encontrado.".
Data: `GET /api/credit-cards` (key `['cartoes']`; also writes due autopay) — `id, name, due_day,
closing_day, credit_enabled, debit_account_id, autopay_account_id, autopay_start_date`; `GET
/api/accounts` (`['contas', 'ativas']`). Archived cards (`?include_archived=1`) are never listed here.

### Categorias — native **mid**
- Panel "Categorias" (badge "N ativa(s)"; description: renaming carries the name everywhere,
  archiving keeps history). All categories incl. archived, server order (parent, then children):
  "Pai › Filho" (root bold, archived grey + badge "Arquivada"), kind label (Receita / Despesa /
  Ambos). Active → "⋯" "Renomear ou mudar tipo" (inline name + kind, ✓/✕), "Arquivar categoria";
  archived → "Reativar".
- "Nova categoria": Nome ("Ex: Delivery"), Tipo (Despesa default / Receita / Ambos), "Categoria pai"
  ("Nenhuma (categoria raiz)" + active roots; hint "…só existe um nível.").

| Action | Request | Confirmation |
|---|---|---|
| Create | `POST /api/categories` `{name, kind, parent_id?}` | none |
| Rename / kind | `PATCH /api/categories/<id>` `{name, kind}` | none |
| Archive | `DELETE /api/categories/<id>` | confirm `Arquivar "<nome>"?` / "Os lançamentos continuam, e dá para reativar depois." |
| Reactivate | `PATCH` `{archived_at: null}` | none |

All refused offline. Refusals: 409 "Ja existe uma categoria com este nome.", 409 "Arquive as
subcategorias antes de arquivar esta categoria.", "Categoria pai nao encontrada.", "A categoria pai
esta arquivada.", "So existe um nivel de subcategoria.". Data: `GET /api/categories?include_archived=1`,
key `['categorias', 'todas']` (`id, name, kind, parent_id, parent_name, archived_at`); the GET seeds
default categories on first use.

### Regras de importação — **late / desktop-first** (keep in the WebView until step 8)
- List (server order `priority DESC, created_at`): `contém|começa com|é igual a "<pattern>" →
  <category>` (inactive struck through), applies label (Entradas e saídas / Só entradas / Só saídas),
  amount condition ("de R$ a a R$ b", "a partir de …", "até …"), "só em <conta>", "prioridade N",
  badge "N lançamento(s)" (`hits`). Buttons "Aplicar" per rule and header "Aplicar ao extrato" (when
  any rule is active). "⋯": "Editar regra", "Desativar"/"Ativar", "Apagar regra".
- Form "Nova regra"/"Editar regra": Texto (≥ 2 normalized chars), Comparação, Categoria (by id),
  Aplica-se a, Valor mínimo/máximo (own `parseAmountInput()`, inline, untested — a different parser
  from `parseMoneyInput()`), Conta ("Qualquer conta"), Prioridade (−999…999).
- Apply sheet: preview list with checkboxes (all preselected; "Todos"; "N de M marcados · primeiros
  M de T" when truncated at 2 000), each "description · signed amount · date · conta · old → new".
  "Recategorizar N". Empty: "Nada a mudar" (transfers, investments, invoice payments excluded).
- Requests: `GET /api/import-rules` (key `['regras']`, with categories and accounts), `POST`,
  `PATCH /api/import-rules/<id>` (`{active}` for toggle), `DELETE` (confirm `Apagar a regra
  "<pattern>"?`), `POST /api/import-rules/apply/preview` `{rule_id?}` → `{items, total, truncated}`,
  `POST /api/import-rules/apply` `{transaction_ids, rule_id?}` → `{updated, skipped}` (toast "N
  lançamento(s) recategorizado(s). M mudou(aram) desde a prévia…"). Refusals: "Ja existe uma regra
  igual a essa." / `Ja existe uma regra para "<p>".`, "O valor minimo nao pode passar do maximo.",
  "Escolha ao menos um lancamento em 'transaction_ids'.", 404 "Regra nao encontrada.".

### Aprovar — native **early** (one toggle; also offer it inside native Aprovar)
- Checkbox "Sempre perguntar a conta/cartão" + explanation ("…"Aprovar prontos" não leva nenhum…").
- `GET /api/inbox/settings` → `{always_ask}` (key `['aprovar', 'ajustes']`); `PATCH` `{always_ask:
  bool}` (400 "Envie always_ask como true ou false."); toast "Aprovar vai pedir a conta/cartão de todo
  item." / "Aprovar volta a usar as escolhas lembradas.". Read error "Não foi possível ler os ajustes
  de Aprovar.".

### Integrações — **late / desktop** (diagnostic)
- Overall alert from `status`: ok "Cotações e índices chegando normalmente.", degraded "Uma integração
  falhou; o resto segue funcionando.", down "Nenhum provedor de cotação respondeu: a carteira fica com
  os últimos preços salvos.". Items (`yfinance`, `brapi`, `bcb`, `tesouro`): `label`, `purpose`,
  `detail`, "Última falha numa busca real: <when> — <last_error>", badge by status (Funcionando /
  Com falha / Atrasado / Não configurado / Indisponível), `latency_ms`. Footer "Verificado em … (guardado)".
- `GET /api/health/integrations` (key `['integracoes']`, staleTime 5 min; server caches 600 s);
  "Verificar agora" → `?refresh=1`, written into the cache without invalidating others.

### Aparência — native **early** (trivial, but must stay in sync with the WebView)
- Segmented "Sistema | Claro | Escuro" (`lib/theme.js`, localStorage `@financeMVP:theme`); in the APK
  `lib/nativeApp.js` forwards it to `ShellPlugin.setTheme` → `ShellPrefs`, which native screens read.
  A native Aparência writes `ShellPrefs` directly and must push the choice back to the WebView while
  web screens remain.

### Perfil — native **early**
- Info alert when no username ("Sua conta ainda não tem nome de usuário. Escolha um abaixo.");
  "Nome de usuário" (2–40, not an e-mail; Salvar disabled when unchanged or < 2) → `PATCH
  /api/auth/me` `{username}` → `{user}` (toast-like success "Nome de usuário atualizado."; errors
  "Informe um nome de usuario com pelo menos 2 caracteres.", "O nome de usuario pode ter no maximo 40
  caracteres.", "O nome de usuario nao pode ser um e-mail."). "E-mail de acesso" = `maskEmail(email)`.
  "Sair" (danger, no confirmation) → `signOut()` clears the stored auth; `nativeApp.js` then calls
  `Outbox.clearSession()`. A native "Sair" must clear `Session`, the WebView auth and the cached data.

### Notificações dos bancos — native **early**, phone only (it is already Java)
- Only when `Capacitor.isNativePlatform()`. Reads `Notify.status()` → `{granted, captureOn,
  captureSince, connectedAt, disconnectedAt, acceptsShell, sdk, installer, apps[{package, label,
  installed, count, lastPostedAt}], total}` and `Notify.latest({limit: 20})`; reloads on the plugin's
  `changed` event and on app resume. Shows `accessMessage()`, `listenerMessage()`, button "Abrir acesso
  às notificações" (`openAccessSettings`), collapsible "O Android diz “Configuração restrita”?" (open
  when `showsRestrictedHelp()`, steps + `installerLabel()` + "Abrir informações do app"), "Modo
  captura" Desligada/Ligada (`setCapture`, toast "Captura ligada." / "Captura desligada. O que já foi
  guardado continua aqui."), `captureMessage()`, the debug-only adb hint (`ADB_TEST_COMMAND`, when
  `acceptsShell`), `appRows()`, "Últimas capturadas (N)" (title/text verbatim, badges "resumo", "lida
  ao religar"), "Exportar JSON" / "Exportar texto" (share sheet; toast "N notificações no arquivo.
  Escolha onde guardar."), "Apagar capturas" (confirm "Apagar as notificações capturadas?").
- Native should call `NotifyStore` / `NotifySettings` directly (same process), not the plugin. Texts
  never go to the server. The panel description is stale: parsers exist and detections go to Aprovar;
  Flash Benefícios is heard too.

### Versão do app — native **mid**, phone only; the bundle half disappears at step 8
- `AppBundle.info()` → `{apkVersion, nativeLevel, running, onBuiltin, inTrial, staged}`;
  `ApkUpdatePrompt` ("Nova versão disponível (x). [A tela nova precisa dela para atualizar.]" +
  "Instalar", `installStatusMessage()`); `checkStatusMessage(lastCheck)`; rows "APK — <version> · nível
  nativo N" ("É o mais novo publicado.") and "Tela — <shortVersion> · a que veio no APK | baixada do
  servidor" (badge "Em teste"). Buttons "Verificar atualizações" (`checkForUpdate()`: `AppBundle.check`
  + `AppUpdate.latest`), "Reiniciar agora" / "Voltar à tela do APK agora" (`staged`), "Voltar à versão
  do APK" (confirm "Voltar à versão do APK?").
- Native keeps only the APK part (`ApkUpdatePlugin` / `ApkUpdateRules`) once the WebView is gone.

## Actions
Every action is per section above. Common to all: no write is queued — offline every write fails with
"Sem conexão com o servidor. Esta ação só funciona conectado."; success is a toast, errors go to the
section's own alert (server message verbatim, unaccented Portuguese from the API); destructive steps
use `confirmAction` (archive/delete/unlink/clear). Notificações and Versão act on the device, never
on the server.

## Data
| Query key | Endpoint | Section |
|---|---|---|
| `['contas', 'todas']` | `GET /api/accounts?include_archived=1` | Contas |
| `['contas', 'ativas']` | `GET /api/accounts` | Cartões (also "+ Novo", Aprovar) |
| `['cartoes']` | `GET /api/credit-cards` | Cartões (also "+ Novo", Aprovar) |
| `['categorias', 'todas']` | `GET /api/categories?include_archived=1` | Categorias (also Orçamento) |
| `['regras']` | `GET /api/import-rules` + categories + accounts | Regras |
| `['aprovar', 'ajustes']` | `GET /api/inbox/settings` | Aprovar |
| `['integracoes']` | `GET /api/health/integrations` | Integrações |

Every successful write invalidates every query; sections await `invalidateServerData()` before
toasting. The account and card lists are the same data "+ Novo" keeps on the phone (step 1): a
native Contas/Cartões must refresh that local copy after each write.

## Client rules
- `cardFormPayload()`, `cardFunctionOf()`, `cardFunctionLabel()`, `hasCredit()`, `hasDebit()`,
  `creditCards()` — `lib/cardFunctions.test.js`. **Port** (shared with "+ Novo").
- `pickPortfolioAccountId()` — `lib/portfolioAccount.test.js`; `isBrlAccount()` has no direct test. **Port** with tests.
- `accountBalanceBrl()` — `lib/transactions.js`, no direct test. Port with a test (display only).
- `parseMoneyInput()` / `moneyInputValue()` — tested; `parseBalanceInput()` (leading minus) is
  inline in `ContasSection.jsx`, untested — port with tests.
- Closing-day auto-fill (due − 7, wrap +30) — inline, untested; port (UI convenience only).
- `parseAmountInput()`, `amountConditionLabel()` in `RegrasSection.jsx` — inline, untested.
- `notifyRules.js` (all texts) — `lib/notifyRules.test.js`; a JVM `NotifyRulesTest` already exists for
  the Java side's allow-list. **Port** the texts.
- `appBundleRules.js` (`checkStatusMessage`, `shortVersion`, `apkPrompt`, `installStatusMessage`) —
  tested; port only the APK half.
- `maskEmail()` — `lib/format.test.js` ("maskEmail mostra so algumas letras do e-mail"); port.

## States
- Loading: Contas/Cartões/Categorias/Regras print "Carregando..." (no skeleton); Integrações and
  Notificações use `ListSkeleton`. Native: skeletons everywhere.
- Empty: "Nenhuma conta" / "Cadastre a primeira conta para começar.", "Nenhum cartão" / "Cadastre um
  cartão para lançar compras no crédito ou no débito.", "Nenhuma categoria", "Nenhuma regra" / "Crie
  uma regra aqui, ou direto na prévia da importação com o botão “Criar regra”.".
- Error: per-section alerts ("Não foi possível carregar as contas." etc.).
- Offline: cached lists visible; every write refused; Notificações and Versão work offline
  (device-only), except the update check.
- Privacy: only account balances are masked.
- Light/dark: Aparência itself; badges neutral except success/warning meanings.

## Conventions that apply
- "Accounts and categories are archived, never deleted" — and cards (037): delete archives a card with
  history, refuses one with open items.
- "There is always one default account, active and not the Corretora" — server moves the mark.
- "Investments and banking are separate areas…" — Corretora balance only in Investimentos; "Vincular à
  carteira" = PATCH type.
- "A card has functions: crédito, débito or both" — debit account never a Corretora; debit-only has no
  autopay and its days are never read.
- "Débito automático" — enabling stamps `autopay_start_date` = today; earlier invoices stay manual.
- "`transactions.category` still holds the category *name*, but the id decides" — rename rewrites five
  tables; selects send ids.
- "Rules touch the past only on confirmation" — apply rewrites only the confirmed ids.
- "Aprovar never remembers an ambiguous target" — `always_ask`; the account "Instituição" is the bank field.
- "Bank notifications are read on the phone and stay there" — capture/export never reach the server.
- "A new APK comes from CI…" / "The APK's screens come from the server" — Versão do app.
- "Signup is closed once a user exists" — Perfil has no account creation.
- "The app is reais-only on screen" — no currency fields.

## Native-only improvements
- Settings list with sub-screens; deep links (e.g. a hypothetical `financas://ajustes/notificacoes`) from the listener's
  "access lost" state.
- Notificações: live permission state via `NotificationManagerCompat`, a system notification when the
  listener disconnects.
- Biometric gate on "Sair" and on "Apagar capturas".

## Acceptance
- [ ] Creating an account with "-150,50" shows a negative (rose) balance, masked by the eye.
- [ ] A Corretora shows "Em Investimentos", never a value; "Tornar padrão" is absent on it.
- [ ] Archiving the last active account shows the 409 message.
- [ ] A debit-only card shows "Débito", no due/closing, no autopay select; "+ Novo" offers only Débito.
- [ ] Turning credit off with an open invoice shows the 409 message.
- [ ] Renaming a category updates the name in Extrato rows of that category.
- [ ] "Sempre perguntar a conta/cartão" persists across phone and desktop.
- [ ] Theme change applies to native and remaining WebView screens at once.
- [ ] Notificações shows access state, toggles capture, exports via the share sheet.
- [ ] "Sair" returns to login and the outbox stops sending.

## Desktop
Keep Contas, Cartões, Categorias, Regras and Integrações, widened into tables with inline edit (Regras
with the apply preview as a full-width table). Drop Notificações and Versão do app (phone only; already
hidden outside the APK). Fix stale copy: Integrações' "…e o extrato dos bancos" (there is no bank API)
and Notificações' "Por enquanto só guarda os textos".
