# App shell, login and session — native spec

| | |
|---|---|
| Migration order | 0 (see `../migration-order.md`) — the shell is built gradually; login + the session handover matter for step 1 |
| Status | Not started |
| React source | `frontend/src/App.jsx`, `main.jsx`, `components/Layout.jsx`, `components/Attention.jsx` (`AttentionBell`), `components/PendingSheet.jsx`, `components/ApkUpdateBanner.jsx`, `components/InvestmentLaunchModal.jsx` (opened by "+ Novo" inside Investimentos), `pages/Auth.jsx`, `lib/navigation.js`, `lib/auth.js`, `lib/api.js`, `lib/nativeApp.js`, `lib/privacy.js`, `lib/theme.js`, `lib/connection.js`, `lib/inboxCount.js`, `lib/outbox.js`, `lib/layers.js`, `lib/appBundle.js` + `appBundleRules.js`, `lib/queryPersist.js`; Java `outbox/Session.java`, `outbox/OutboxPlugin.java`, `outbox/LoginNotifier.java`, `ShellPlugin.java`, `MainActivity.java`, `update/ApkUpdatePlugin.java`; Kotlin `ui/theme/Theme.kt` (`ShellPrefs`) |
| Route(s) | `/` (login when signed out), every route under `Layout`: `/inicio`, `/lancamentos/*`, `/planejamento/*`, `/investimentos/*`, `/ajustes` (+ `legacyRedirects`) |
| Endpoints | `POST /api/auth/login`, `POST /api/auth/signup`, `GET /api/inbox/count`; the bell reads Início's queries (`GET /api/transactions`, `GET /api/cc-expenses`, `GET /api/accounts?include_archived=1`, `GET /api/credit-cards`, `GET /api/recurring`, `GET /api/budgets?month=`, see `03-inicio.md`); `GET /api/investments/portfolio?refresh_prices=false` (assets for the investment modal); APK: `<baseUrl>/apk/version.json` via `ApkUpdatePlugin` |
| Client rules | `lib/navigation.js` (`sections`, `findSection()`), `lib/attentionRules.js` (`attentionItems()` …, via `lib/attention.js` `useAttentionItems()`), `lib/outboxRules.js` (`NEEDS_ATTENTION`, `KIND_LABELS`, `itemAmount()`, `itemDate()`), `lib/appBundleRules.js` (`apkPrompt()`, `installStatusMessage()`), `lib/privacy.js` (`usePrivateFormatter()`) |

## What it is for
The frame every screen lives in: the bottom navigation and header on the phone, the counters that
say "something waits for you" (Aprovar, pending outbox, the bell), the privacy eye, the theme, the
APK update banner and the "+ Novo" button. It also owns login and hands the session to the Java
side, which is what lets a native screen (and the outbox worker) call the API with the app closed.

## What it shows
Phone (below `lg`, 1024 px). Top to bottom:

1. **Header** (`Layout.jsx`, sticky, `h-16`): left the brand mark (green `bg-brand` square with "F"
   + "Finanças"); right, in this order, each 44 px:
   - **Aprovar pill** (`InboxPill compact`): shown only when `GET /api/inbox/count` → `pending_count`
     > 0. Amber (warning: something to decide), bell-ring icon + the number. Tap → `/lancamentos/aprovar`.
     Refetched every 60 s while visible and on window focus (`lib/inboxCount.js`, `retry: 0`; offline → 0, hidden).
   - **Pending pill** (`PendingPill compact`): shown when the outbox has items for the current
     user **or** the server is unreachable. Label `"<n> pendente(s)"`, or (no items, offline) a
     cloud-off icon with the sr-only text "Sem conexão". Amber when any item is `needs_attention`
     or the server is unreachable; neutral while the queue is just moving. Tap → "Pendentes" sheet.
   - **Bell** (`AttentionBell`): count badge (amber, "9+" above 9) of **all** current attention
     items (dismissed ones included). Tap → popover "Precisa de atenção" (see below).
   - **Eye** (`PrivacyToggle`): `Eye` / `EyeOff`; emerald-tinted when values are hidden.
     Labels "Ocultar valores" / "Mostrar valores".
   - **Ajustes** (gear) → `/ajustes`; emerald-tinted when active. (The desktop has a user menu with
     Ajustes + Sair instead; on the phone "Sair" lives in Ajustes › Perfil.)
2. **APK banner** (`ApkUpdateBanner`, only in the APK): "Nova versão disponível (<versionName>)."
   + button "Instalar"; info tone, warning when `apkPrompt().required` (adds "A tela nova precisa
   dela para atualizar."). Under it the install status text (`installStatusMessage()`): e.g.
   'Instalador aberto. Toque em "Atualizar"; os dados do app são mantidos.', 'Permita "Instalar apps
   desconhecidos" para o Finanças e volte: o download começa sozinho.'. A debug build never reports
   `newer` (`ApkUpdatePlugin`).
3. **Section tabs** (`Tabs`, from `sections[i].tabs`): Lançamentos = Extrato, Aprovar (badge =
   inbox count), Cartões, A receber, Importar; Planejamento = Orçamento, Recorrentes, Metas;
   Investimentos = Posição, Rentabilidade, Operações, Alocação, Proventos, IR, Calculadora. Início
   and Ajustes have no tabs.
4. **Page content** (fade-up when the section changes, fade-in between tabs of a section).
5. **Bottom navigation** (fixed, 5 equal columns, safe-area padding): Início, Lançamentos, **+**
   (centre, 52 px emerald `bg-emerald-500` rounded square, `text-on-accent`), Planejar,
   Investir (`shortName`). Active tab: dark label + emerald-100 pill behind the icon.

**Bell popover**: title "Precisa de atenção"; empty → "Nada pendente agora."; else one row per
item: tone icon (danger rose / warning amber / info sky), title, detail, link label. Texts
(`useAttentionText()` in `Attention.jsx`):
- `INVOICE_OVERDUE`: "Fatura vencida: R$ X" · "<card> · venceu em dd/mm/aaaa · n lançamento(s)" → "Ver faturas" (`/lancamentos/cartoes`)
- `INVOICE_PAYABLE`: "Fatura fechada: R$ X" · "O pagamento já está liberado." → "Ver faturas"
- `AUTOPAY_SHORTFALL`: "Débito automático sem saldo: faltam R$ X" · "<conta> tem R$ Y para R$ Z a debitar · o primeiro em dd/mm/aaaa" → "Ver faturas". **X and Y are masked in privacy mode** (they reveal the balance); Z is not.
- `RECURRING`: "n recorrência(s) vencida(s)" → "Ver recorrentes"
- `OVER_BUDGET`: "<Pai › Categoria> passou do orçamento" · "R$ gasto de R$ disponível" → "Ver orçamento"

**Pendentes sheet** (`PendingSheet.jsx`): title "Pendentes", description "Lançamentos guardados
neste aparelho, à espera do servidor."; offline info "Sem conexão com o servidor. Novos lançamentos
ficam guardados aqui; o resto do app volta com a conexão."; empty state "Nada pendente" / "Tudo o
que foi lançado neste aparelho já chegou ao servidor."; each row: description (or kind label),
badge "Pendente" (neutral) / "Recusado" (warning), "<Despesa|Receita|Transferência|Compra no cartão>
· dd/mm/aaaa[ · Nx]", `last_error` in amber, amount (not masked), menu "Corrigir" / "Descartar".
Footer "Fechar" + "Sincronizar agora".

**Login** (`pages/Auth.jsx`, "Finanças"): segmented "Entrar" / "Criar acesso", only when
`GET /api/auth/signup` answers `{open: true}` (no answer = closed, the segment is hidden); headings "Acesse sua conta" /
"Crie seu acesso"; fields E-mail, Senha ("Mínimo de 6 caracteres"), and on signup "Nome de usuário"
(2–40 chars, hint "É o nome exibido no app. O e-mail serve só para entrar."). Error box in rose.

## Actions

| Action | Where | Request | Confirmation | Offline |
|---|---|---|---|---|
| Sign in | Login | `POST /api/auth/login` `{email, password}` (no auth) → `{user:{id,email,username,created_at}, access_token}` | navigates to `/inicio` | refused (`ApiNetworkError`: "Sem conexão com o servidor. Esta ação só funciona conectado.") |
| Sign up | Login › Criar acesso | `POST /api/auth/signup` `{email, password, username}` → same shape, 201 | navigates to `/inicio` | refused |
| Sign out | Ajustes › Perfil "Sair" (desktop: user menu) | none: `clearStoredAuth()` → `finance-auth-change` → `Outbox.clearSession()`; caches cleared (`clearServerData`, `clearPersistedQueryCache`) | none | works; the outbox survives logout (per user) |
| Toggle privacy | Eye | none (`setValuesHidden`, localStorage `@financeMVP:hideValues`) | none | works |
| Open "+ Novo" | Bottom **+** | opens `NewEntrySheet` (`01-novo.md`); inside `/investimentos` opens `InvestmentLaunchModal` ("Registrar operação") after `GET /api/investments/portfolio?refresh_prices=false` | — | sheet works offline; the investment modal does not |
| Open Aprovar | Aprovar pill | navigation | — | pill hidden offline |
| Open bell / follow item | Bell | navigation to the item's screen | — | cached data |
| Sync now | Pendentes › "Sincronizar agora" | `flush({retryAttention: true})` → in the APK `Outbox.flush` → `OutboxSender.run` | toast "1 lançamento enviado." / "N lançamentos enviados."; warnings: "Entre novamente para enviar os lançamentos pendentes." (login), "O servidor não respondeu. Os lançamentos continuam guardados neste aparelho." (offline), "O servidor recusou um ou mais lançamentos. Veja o motivo em cada um." | tries; reports offline |
| Fix a pending item | Pendentes › "⋯" › Corrigir | reopens "+ Novo" pre-filled (`01-novo.md`, edit mode) | — | works |
| Discard a pending item | Pendentes › "⋯" › Descartar | `Outbox.remove({clientId})` | `confirmAction`: "Descartar o lançamento pendente?" / "<Kind> de R$ X ainda não foi enviada. Descartar apaga do aparelho; ela não chega ao servidor." / "Descartar" | works |
| Install new APK | Banner "Instalar" | `AppUpdate.install({baseUrl})` | status text under the banner | needs network |
| Android back | system | `closeTopLayer()` first, then history back, at the root `App.minimizeApp()` (never kills the app) | — | — |

Server refusals to show on login (body key `error`): 401 "Email ou senha invalidos."; signup 400
"Informe email valido e senha com pelo menos 6 caracteres." or the username messages of
`normalize_username()` ("Informe um nome de usuario com pelo menos 2 caracteres.", "O nome de
usuario pode ter no maximo 40 caracteres.", "O nome de usuario nao pode ser um e-mail."); 403 "O
cadastro esta fechado neste servidor. Entre com a conta existente." (signup is closed once a user
exists); 409 "Ja existe uma conta com este email.". Any later request answering 401 (body key
`message`: "Token ausente ou invalido.", "Sessao expirada.", "Token invalido.", "Usuario nao
encontrado.") signs the WebView out (`apiFetch` → `clearStoredAuth()`).

## Data
- **Session (web)**: localStorage `@financeMVP:auth` = the login response `{user, access_token}`
  (`lib/api.js` `getStoredAuth/setStoredAuth/clearStoredAuth`, event `finance-auth-change`). The
  token is a hand-rolled HS256 JWT, `exp` = now + `JWT_EXP_DAYS` (default 30, `config.py`); there is
  **no refresh endpoint** — expiry means logging in again.
- **Session (native)**: `Session.java`, SharedPreferences `financas_session`: `base_url`,
  `user_id` in clear, `token` AES-GCM sealed with Android Keystore key `financas_session_key`.
  Written by `OutboxPlugin.setSession({baseUrl, token, userId})` (refuses a non-`https://` base URL
  and an empty token/user), cleared by `clearSession()`. `lib/nativeApp.js` `syncSession()` calls one
  or the other at start and on every `finance-auth-change`. `Session.load(context)` returns null when
  there is no login or the key is gone (backup restored on another phone). **A native screen reads
  `Session.load()` for `baseUrl` + `Bearer <token>`**; the username is not stored there.
- `setSession` also cancels the "Sessão expirada" notification (`LoginNotifier`) and schedules
  `OutboxWorker` and `DetectionWorker`.
- `GET /api/inbox/count` → `{pending_count}`. Query key `['aprovar', 'contagem']`.
- The bell: `useAttentionItems()` (`lib/attention.js`) with Início's keys `['inicio','movimentos']`,
  `['inicio','cartoes']`, `['inicio','recorrencias']`, `['inicio','orcamento', <AAAA-MM>]` plus the
  outbox (pending items adjust account balances via `applyPendingToAccounts()`). Field details in
  `03-inicio.md`.
- Every successful write through `apiFetch` invalidates the whole TanStack cache
  (`setMutationListener` in `lib/queries.js`); `staleTime` 30 s; the cache is persisted to IndexedDB
  for 14 days per user and per build (`lib/queryPersist.js`).
- Reachability: `lib/api.js` `serverReachable` flips on each request (false on a network error or
  timeout, true on any response). Reads time out at 45 s.
- APK: `AppUpdate.latest({baseUrl})` → `{installedCode, nativeLevel, latest:{versionCode,
  versionName, nativeLevel, size}, newer, canInstall}`; checked after `AppBundle.ready()` and on
  resume (`shouldCheck()`).

## Client rules
- **Navigation map** — `lib/navigation.js` `sections`, `findSection()`, `legacyRedirects`. No test.
  **Port** as a Kotlin route table; the WebView keeps the same paths for unmigrated screens.
- **Attention items for the bell** — `lib/attentionRules.js`, tested (`attentionRules.test.js`).
  **Endpoint** recommended (see `03-inicio.md`): the bell and Início would read one
  `GET /api/attention` instead of downloading every transaction and card row.
- **Attention texts** — inline in `components/Attention.jsx` (`useAttentionText()`), no test. Port
  the strings with the item kinds.
- **APK prompt** — `appBundleRules.js` `apkPrompt()` / `installStatusMessage()`, tested
  (`appBundleRules.test.js`); the Java side has `ApkUpdateRules` (`ApkUpdateRulesTest`). Port the
  prompt (two branches) when the banner goes native.
- **Pending pill visibility / tone** — inline in `Layout.jsx` (`PendingPill`): shown when
  `count > 0 || !reachable`; amber when `attention > 0 || !reachable`. No test. Port.
- **Outbox item labels** — `outboxRules.js` `KIND_LABELS`, `itemAmount()`, `itemDate()` (tested).
  Port.
- **Privacy** — `lib/privacy.js`: one boolean, masked text `R$ ••••••` (`MASKED_CURRENCY`),
  chart axes blank. No test. Port as app-wide state; see "States".

## States
- **Boot**: "Carregando..." while the stored session is read; the persisted query cache is
  restored before the first render, so screens open with the last data even without a server.
- **Page chunk loading**: `PageLoading` skeleton (title bar + two blocks).
- **Signed out**: everything redirects to `/` (login). The outbox items of another user stay on
  the phone but are never shown or sent for the current one.
- **Offline**: the pending pill shows "Sem conexão"; reads show the cached copy; only "+ Novo"
  creations are queued — every other write fails with the network message.
- **401 in the background**: the native sender stops and, with items kept, posts the notification
  "Sessão expirada" / "N lançamentos aguardam envio. Entre novamente no app para enviá-los."
  (channel "Envio de lançamentos"). The sender does **not** clear `Session` on 401.
- **Privacy mode**: hides account balances, the consolidated balance, the portfolio and the two
  balance-revealing values of `AUTOPAY_SHORTFALL`; never remounts or refetches.
- **Theme**: `lib/theme.js`, preference `system|light|dark` in localStorage `@financeMVP:theme`
  (Ajustes › Aparência; no header toggle). Dark = class `dark` on `<html>`. In the APK
  `ShellPlugin.setTheme({dark, background})` colours the system bars (`#0B1210` dark, `#EFF2ED`
  light) and saves `ShellPrefs.saveDark()`; native screens read `ShellPrefs.dark(context)` through
  `FinancasTheme`.

## Conventions that apply
- **"The phone goes native, the desktop gets its own interface"**: the shell is the last thing to
  disappear; until then native screens open over the WebView.
- **"Signup is closed once a user exists"**: offer "Criar acesso" only when `GET /api/auth/signup`
  says it is open (as the web does since 2026-10-23); show the 403 text if used anyway.
- **"The APK's screens come from the server"**: bump `frontend/native-level.txt` with any new
  plugin method the web shell calls (e.g. `NativeScreens.open`).
- **"A new APK comes from CI, never from GitHub Releases"**: the banner reads `/apk/version.json`.
- **"The outbox holds creations only, and only when the request never reached the server"**: the
  pending pill and sheet show exactly that queue.
- **"Privacy mode"** (Known sharp edges): balances and portfolio only.
- **"Theme and tokens"**: colours from `ui/theme/Tokens.kt` (= `index.css`); emerald is the only
  accent; amber/rose/sky only for warning/loss/info.
- **"Visual rules"**: 44 px touch targets.

## Native-only improvements
- A native bottom bar and header that stay mounted while the WebView swaps routes (no flash).
- Login can stay in the WebView for step 1 (it already feeds `Session`). A native login later must
  also write `@financeMVP:auth` into the WebView (or the WebView must read the session from Java),
  otherwise the two disagree.
- On a 401 in a native screen: clear `Session` and send the user to the WebView login (today only
  the WebView clears its auth on 401). Unverified design — needs a plugin event.
- App shortcut "Novo lançamento" (long-press icon) straight into the native "+ Novo".

## Acceptance
- [ ] Logging in on the debug APK lands on Início; killing and reopening the app keeps the session.
- [ ] After login, a creation made in airplane mode is sent by the worker with the app closed.
- [ ] Logging out and in as the same user keeps pending items; a different user does not see them.
- [ ] The Aprovar pill appears within a minute of a new notification and opens Aprovar.
- [ ] The pending pill turns amber with "Sem conexão" in airplane mode and disappears when synced.
- [ ] The bell lists the same items as Início's "Precisa de atenção", including dismissed ones.
- [ ] The eye hides balances on every screen instantly and survives a restart.
- [ ] Ajustes › Aparência › Escuro turns the WebView, the system bars and native screens dark.
- [ ] Back closes an open sheet first; on Início it minimizes the app.
- [ ] With an older APK installed, the banner offers "Instalar" and the installer opens.

## Desktop
Keep the single top strip (brand, section pills, Aprovar/pending pills, bell, eye, user menu,
"+ Novo") but move to the planned fixed sidebar ≥ 1280 px; drop the bottom navigation and the 44 px
targets; "+ Novo" becomes a dialog or inline row. The login page can lose the phone-specific
layout (it is "Finanças" since 2026-10-23).
