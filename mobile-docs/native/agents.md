# Running the migration with agents

The migration is many similar, well-specified units of work (a spec per screen, a rule per module, a
screen per step). That shape suits Claude Code subagents: the main session plans, hands each unit
to an agent with its own context, and keeps only the results. Every agent is defined in
`.claude/agents/`.

## The agents

| Agent | Writes code? | Job | Typical input |
|---|---|---|---|
| `session-scout` | No | Start-of-session briefing (existing) | "Brief me for this session." |
| `screen-spec-writer` | Docs only | Writes or refreshes one spec from the React source and the backend | A screen name and spec file |
| `rule-porter` | Yes | Ports one `frontend/src/lib/` module to Kotlin with the same test cases | A module name and a branch |
| `native-screen-builder` | Yes | Builds one native screen (or a step's shared foundation) from its spec, pushes, waits for CI | A spec file, a branch, which shared files it owns |
| `android-ci-watcher` | No | Waits for a CI run on a branch and diagnoses a failure | A branch (and commit) |
| `native-parity-reviewer` | No | Reviews a native screen against its spec, the React screen and the conventions | A spec file, base and branch |
| `desktop-screen-builder` | Yes | Redesigns one React screen for the desktop, with screenshots | A screen and a branch |

If `Agent(subagent_type="<name>")` answers "Agent type not found", use the fallback CLAUDE.md
describes: `subagent_type="general-purpose"` with "Read .claude/agents/<name>.md in full and follow
it exactly as your instructions" in the prompt.

## The loop for one step

```
main session ── reads handoff/next-steps (or session-scout)
     │
     ├─► rule-porter × N          (parallel, one module each, separate branches or one branch in sequence)
     ├─► native-screen-builder     (the step's screen; owns the shared files for this step)
     │        └─ push ─► android-check.yml ─► (android-ci-watcher if it fails)
     ├─► native-parity-reviewer    (read-only, on the builder's branch)
     ├─► native-screen-builder     (fix round, with the reviewer's findings)
     └─► main session: updates docs, asks the owner to test the debug APK, opens the PR on request
```

## Rules for running agents in parallel

- **One writer per branch.** Two code-writing agents never share a branch. Use
  `isolation: "worktree"` (each gets its own checkout) and a branch per agent, then merge in order.
- **Shared files have one owner per round**: `variables.gradle`, `app/build.gradle`,
  `AndroidManifest.xml`, `res/values/strings.xml`, the `NavHost`, `NativeScreens`. The prompt says
  which agent owns them; the others report the change they need.
- **Read-only agents run freely** in parallel (spec writers on different files, reviewers, the CI
  watcher).
- **The foundation goes first and alone** (steps 1 and 2 build `ui/components/`, `data/`,
  `NativeActivity`, `NativeScreens`). Parallel screen builders start from step 3.
- **The main session owns the session documents** (`docs/handoff.md`, `docs/next-steps.md`,
  `docs/done-tasks.md`, this folder's `README.md` status). Agents update only their spec's `Status`.
- **Nothing is merged without a green `android-check.yml`** on the branch's last commit.
- Each agent's report is short by design. The main session relays what matters to the owner.

## Prompts

Paste these into a new Claude Code session on this repository. Each one names its branch: replace
`<branch>` with the branch the session was given.

### Start a session

```
Leia o CLAUDE.md e use o agent session-scout para o briefing. Depois me diga qual é o próximo passo
da migração nativa (mobile-docs/native/migration-order.md) e o que ele precisa antes.
```

### Step 1 — the foundation and "+ Novo"

```
Passo 1 da migração nativa ("+ Novo"), na branch <branch>.
1. Em paralelo, use o agent rule-porter para portar para Kotlin, cada um com os mesmos casos de
   teste do node: (a) o parser e o formatador de dinheiro e datas de lib/format.js para core/;
   (b) lib/cardFunctions.js para rules/. Use worktrees separadas e depois junte na <branch>.
2. Depois, use o agent native-screen-builder com mobile-docs/native/screens/01-novo.md. Esta
   branch é dona dos arquivos compartilhados (variables.gradle, app/build.gradle, manifest,
   strings.xml) e cria o data/ (ApiClient, ReadCache), o plugin NativeScreens e a NewEntryActivity.
   Pode adicionar OkHttp, kotlinx-serialization, coroutines e lifecycle-viewmodel-compose.
3. Se o CI falhar, use o android-ci-watcher para o diagnóstico e devolva ao builder.
4. Quando estiver verde, rode o native-parity-reviewer na branch e corrija os bloqueadores e os
   majors com o builder.
5. Atualize a documentação da sessão e me diga o que testar no celular com o APK de debug.
```

### Step 2 — Aprovar

```
Passo 2 da migração nativa (Aprovar), na branch <branch>. Use o native-screen-builder com
mobile-docs/native/screens/02-aprovar.md; esta branch é dona do NavHost/NativeActivity, que este
passo cria. Inclua abrir o Aprovar nativo pela notificação. Depois rode o native-parity-reviewer e
corrija o que ele achar. Atualize a documentação e me diga o que testar.
```

### Step 3 onward — screens in parallel

```
Passo <n> da migração nativa. Rode em paralelo, cada um numa worktree e numa branch própria
(<branch>-<tela>), o native-screen-builder para: <spec A>, <spec B>. Nenhum deles é dono dos
arquivos compartilhados: cada um lista o que precisa mudar neles. Quando os dois estiverem verdes,
junte na <branch> aplicando as mudanças compartilhadas você mesmo, rode o CI, depois o
native-parity-reviewer em cada tela. Me dê um resumo por tela.
```

### Decide the client rules of a screen before building it

```
Antes do passo <n>, leia mobile-docs/native/rules-port.md e a spec <spec>. Para cada regra marcada
"endpoint", proponha o endpoint (rota, resposta, testes pytest) e me pergunte antes de implementar.
Para as marcadas "port", rode o rule-porter em paralelo, uma por módulo.
```

### Refresh stale specs

```
O React mudou desde que as specs foram escritas. Compare o git log de frontend/src desde
<commit ou data> com mobile-docs/native/screens/ e rode o screen-spec-writer em paralelo só para as
specs afetadas. Me liste o que mudou em cada uma.
```

### Desktop redesign

```
Redesenho do desktop, na branch <branch>. Leia mobile-docs/native/desktop.md e rode o
desktop-screen-builder para <tela>. A versão de celular dessa tela ainda é usada pelo APK, então
ela não pode quebrar abaixo de lg. Me mostre os screenshots em 1440 px e 390 px, claro e escuro.
```

### Review a finished step before the merge

```
Revise a branch <branch> contra a main: rode o native-parity-reviewer para cada tela que mudou e o
android-ci-watcher no último commit. Me dê os achados por severidade e diga se está pronta para o
merge.
```

## Costs and limits

- Each agent starts cold and reads the docs; that is the point (it keeps the main context small),
  but it costs tokens. Prefer one well-scoped agent over several overlapping ones.
- A session container cannot build an APK (`build-and-test.md`), so every native agent waits on CI
  (~2–3 min per push). Batch fixes; don't push one line at a time.
- Agents never merge, never push to `main`, and never open a PR unless the owner asked.
