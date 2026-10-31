import { useState } from 'react'
import { Landmark, Plus, RefreshCw } from 'lucide-react'
import { accountsApi, creditCardsApi, openFinanceApi } from '../../lib/dataApi'
import { AlertMessage, Badge, Button, Collapsible, EmptyState, Field, ListSkeleton, Menu, Panel, PanelHeader } from '../../components/ui'
import { confirmAction } from '../../lib/confirm'
import { formatCurrency, formatDateBR, getLocalDateString } from '../../lib/format'
import {
  IGNORE_CHOICE,
  accountLabel,
  balanceCheck,
  balanceExplanation,
  checkReasonLabel,
  checkSummary,
  connectedItemId,
  firstSyncDaysError,
  heldReasonLabel,
  historyLine,
  itemBankName,
  itemProblem,
  itemStatus,
  mappedId,
  mappingChoices,
  mappingPayload,
  portfolioSummary,
  syncHoursChoices,
  syncSummary,
} from '../../lib/openFinance'
import { usePrivateFormatter } from '../../lib/privacy'
import { queryClient, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'

const NO_ITEMS = []
const OVERVIEW_KEY = ['open-finance']
const SETTINGS_KEY = ['open-finance', 'settings']

function whenLabel(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${formatDateBR(getLocalDateString(date))} ${time}`
}

// O widget Pluggy Connect (pacote oficial, versao fixa), carregado so aqui:
// quem nunca conecta um banco nao baixa o widget. O pacote so tem a
// exportacao nomeada (o README ainda mostra um default que nao existe).
async function openPluggyConnect(connectToken, { onSuccess, onError, onClose }) {
  const { PluggyConnect } = await import('pluggy-connect-sdk')
  const widget = new PluggyConnect({
    connectToken,
    // Sandbox so em desenvolvimento: no servidor so os bancos de verdade.
    includeSandbox: import.meta.env.DEV,
    onSuccess,
    onError,
    onClose,
  })
  await widget.init()
  return widget
}

// Cada linha pode ter um botao: quem resolve a diferenca e o dono.
function CheckList({ title, rows, money, action }) {
  if (!rows?.length) return null
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-zinc-700">{title}</p>
      <ul className="space-y-1">
        {rows.map((row, index) => (
          <li key={`${row.date}-${index}`} className="flex items-start justify-between gap-3 text-xs text-zinc-600">
            <span className="min-w-0 break-words">
              {formatDateBR(row.date)} · {row.description || 'Sem descrição'}
              {checkReasonLabel(row.reason) ? <span className="text-zinc-500"> · {checkReasonLabel(row.reason)}</span> : null}
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <span className="num">{money(row.amount)}</span>
              {action && row.id ? (
                <Button size="sm" variant="secondary" loading={action.busy === `${action.key}:${row.id}`} disabled={Boolean(action.busy)} onClick={() => action.run(row)}>
                  {action.label}
                </Button>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Conferência: o banco contra o app, so apontando (nada e ajustado). Com
// diferenca de saldo, de onde ela vem; os gravados sozinhos que o banco mudou
// depois que o dono editou ficam listados para ele decidir.
function AccountCheck({ check, money, busy, onRecord, onConfirm }) {
  const summary = checkSummary(check)
  if (summary.state === 'none') return null
  const explained = balanceExplanation(check.explanation, money)
  const conflicts = (check.conflicts || []).map((row) => ({
    ...row,
    description: `${row.description || 'Sem descrição'}${row.reason === 'changed'
      ? ` · o banco agora diz ${money(row.bank_amount)}`
      : ' · o banco não tem mais'}`,
  }))
  const hasRows = check.bank_only?.length || check.app_only?.length || check.awaiting?.length || conflicts.length
    || check.awaiting_bank?.length || check.confirmed?.length || explained.length
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600">
        {summary.state === 'match' ? <Badge tone="success">Movimentos conferem</Badge> : null}
        {check.awaiting_count && summary.state === 'match' ? <span>{summary.text}</span> : null}
      </div>
      {hasRows ? (
        <Collapsible label="Ver a conferência" variant="secondary" size="sm">
          <div className="space-y-3">
            <CheckList
              title="Só no banco (recusado no Revisar ou lançado com outro valor/data)"
              rows={check.bank_only}
              money={money}
              action={{ key: 'record', label: 'Lançar', busy, run: onRecord }}
            />
            <CheckList
              title="Só no app (o banco não tem)"
              rows={check.app_only}
              money={money}
              action={{ key: 'confirm', label: 'Aconteceu', busy, run: (row) => onConfirm(row, false) }}
            />
            <CheckList
              title="Você disse que aconteceu"
              rows={check.confirmed}
              money={money}
              action={{ key: 'confirm', label: 'Desfazer', busy, run: (row) => onConfirm(row, true) }}
            />
            <CheckList title="Esperando no Revisar" rows={check.awaiting} money={money} />
            <CheckList title="Esperando a Pluggy atualizar" rows={check.awaiting_bank} money={money} />
            <CheckList title="Você editou e o banco mudou depois (o app não mexeu)" rows={conflicts} money={money} />
            {explained.length ? (
              <div className="space-y-1">
                <p className="text-xs font-semibold text-zinc-700">De onde vem a diferença de saldo</p>
                <ul className="space-y-1 text-xs text-zinc-600">
                  {explained.map((line) => <li key={line} className="num">{line}</li>)}
                </ul>
              </div>
            ) : null}
            <p className="text-xs text-zinc-500">
              Desde {formatDateBR(check.from)}; pares de mesmo valor até 3 dias de distância.
            </p>
          </div>
        </Collapsible>
      ) : null}
    </div>
  )
}

function AccountRow({ account, item, choices, money, busy, checkBusy, onMap, onRecord, onConfirm }) {
  const check = balanceCheck(account)
  const current = mappedId(account)
  const suggested = !current && account.suggested_id ? choices.find((choice) => choice.value === account.suggested_id) : null
  const kind = account.type === 'CREDIT' ? 'cartão' : 'conta'
  return (
    <li className="space-y-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-sm font-semibold text-zinc-900">{accountLabel(account)}</p>
        <Badge tone={account.type === 'CREDIT' ? 'info' : 'neutral'}>{account.type === 'CREDIT' ? 'Cartão' : 'Conta'}</Badge>
      </div>
      <Field label={`Vai para qual ${kind} do app?`}>
        <select
          value={current}
          disabled={busy}
          onChange={(event) => onMap(account, event.target.value)}
          className="app-input"
          aria-label={`Destino de ${accountLabel(account)} em ${itemBankName(item)}`}
        >
          <option value="">Nenhum (não traz nada)</option>
          <option value={IGNORE_CHOICE}>Não usar (esta conta não tem movimentos meus)</option>
          {choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </select>
      </Field>
      {account.brokerage ? (
        <p className="text-xs text-zinc-500">
          O caixa da carteira: só a transferência com o banco vira lançamento (aporte/resgate); compras, vendas e proventos vêm pelas operações.
        </p>
      ) : null}
      {suggested ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600">
          <span>Parece ser {suggested.label}.</span>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onMap(account, suggested.value)}>
            Confirmar
          </Button>
        </div>
      ) : null}
      {!current && !account.ignored && account.unmapped_count ? (
        <p className="text-xs text-zinc-500">
          {account.unmapped_count === 1 ? '1 movimento espera' : `${account.unmapped_count} movimentos esperam`} esta escolha.
        </p>
      ) : null}
      {check.state !== 'none' ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600">
          <span className="num">No banco {money(account.pluggy_balance)} · no app {money(account.app_balance)}</span>
          {check.state === 'match'
            ? <Badge tone="success">Confere</Badge>
            : <Badge tone="warning">Diferença {money(check.difference)}</Badge>}
        </div>
      ) : account.type === 'CREDIT' && account.pluggy_balance != null ? (
        <p className="num text-xs text-zinc-500">Fatura no banco: {money(Math.abs(account.pluggy_balance))}</p>
      ) : null}
      <AccountCheck check={account.check} money={money} busy={checkBusy} onRecord={onRecord} onConfirm={onConfirm} />
    </li>
  )
}

// A carteira da corretora contra a do app (044): quantidade por ativo, o
// caixa (com o que esta a liquidar) e as operacoes que esperam o dono.
function PortfolioCheck({ investments, money }) {
  const summary = portfolioSummary(investments)
  if (summary.state === 'none') return null
  const cash = investments.cash
  const mismatched = (investments.positions || []).filter((row) => row.matches === false)
  return (
    <section className="space-y-2 rounded-2xl border border-zinc-200 p-3" aria-label="Carteira da corretora">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-base font-semibold text-zinc-950">Carteira da corretora</p>
        <Badge tone={summary.state === 'match' ? 'success' : 'warning'}>{summary.text}</Badge>
      </div>
      {cash ? (
        <p className="num text-xs text-zinc-600">
          Caixa na corretora {money(cash.pluggy_balance)} · na Corretora do app {money(cash.app_balance)}
          {cash.unsettled ? ` · a liquidar ${money(cash.unsettled)}` : ''}
          {cash.unexplained ? ` · sem explicação ${money(cash.unexplained)}` : ''}
        </p>
      ) : null}
      {mismatched.length || investments.held?.length ? (
        <Collapsible label="Ver a carteira" variant="secondary" size="sm">
          <div className="space-y-3 text-xs text-zinc-600">
            {mismatched.length ? (
              <ul className="space-y-1">
                {mismatched.map((row) => (
                  <li key={row.code} className="num">
                    {row.code}: corretora {row.pluggy_quantity} (em {formatDateBR(row.position_date)}) · app {row.app_quantity}
                  </li>
                ))}
              </ul>
            ) : null}
            {investments.held?.length ? (
              <ul className="space-y-1">
                {investments.held.map((row, index) => (
                  <li key={`${row.code}-${row.trade_date}-${index}`}>
                    {formatDateBR(row.trade_date)} · {row.type} {row.code || row.name} · {heldReasonLabel(row.reason)}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </Collapsible>
      ) : null}
    </section>
  )
}

// O historico (044): o que a Pluggy tem dos ultimos dias, contado por conta,
// antes de gravar; aplicar so confirmado. Nada digitado e apagado.
function HistoryPanel({ enabled, busy, run }) {
  const [days, setDays] = useState('365')
  const [preview, setPreview] = useState(null)
  const error = firstSyncDaysError(days)
  const load = () => run('history', async () => {
    setPreview(await openFinanceApi.historyPreview(Number(days)))
  })
  const apply = async () => {
    if (!(await confirmAction({
      title: 'Trazer o histórico?',
      message: 'O que a prévia contou é gravado ou ligado ao que você já lançou. O que só existe no app fica como está.',
      confirmLabel: 'Trazer',
    }))) return
    await run('history-apply', async () => {
      const body = await openFinanceApi.historyApply(Number(days))
      if (body?.items) queryClient.setQueryData(OVERVIEW_KEY, body)
      const auto = body?.history?.auto_recorded || {}
      toast(`Histórico trazido: ${auto.recorded || 0} gravado(s), ${auto.linked || 0} ligado(s).`)
      setPreview(null)
    })
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Histórico (dias para trás)" hint={error || 'Compara tudo que já aconteceu nas contas com destino.'}>
          <input type="text" inputMode="numeric" value={days} onChange={(event) => setDays(event.target.value)} className="app-input w-28" />
        </Field>
        <Button size="sm" variant="secondary" loading={busy === 'history'} disabled={Boolean(error) || Boolean(busy)} onClick={load}>
          Ver prévia
        </Button>
      </div>
      {preview ? (
        <div className="space-y-2">
          <ul className="space-y-1 text-sm text-zinc-700">
            {preview.accounts.map((account) => (
              <li key={account.id}>
                <span className="font-semibold">{account.target_name || account.name}</span>
                <span className="text-zinc-600"> · {historyLine(account)}</span>
              </li>
            ))}
          </ul>
          {enabled ? (
            <Button size="sm" loading={busy === 'history-apply'} disabled={Boolean(busy)} onClick={apply}>
              Trazer o histórico
            </Button>
          ) : (
            <p className="text-xs text-zinc-500">Ligue "Gravar sozinho" para trazer o histórico.</p>
          )}
        </div>
      ) : null}
    </div>
  )
}

// Ajustes › Open Finance (043, 044): conectar um banco pela Pluggy (so aqui, na
// web), dizer para qual conta/cartao do app vai cada conta dele (ou "nao
// usar"), ver o estado e o saldo do banco ao lado do do app. Com "Gravar
// sozinho", o que chega vira lancamento; desligado, espera em Lancamentos ›
// Revisar.
export default function OpenFinanceSection() {
  const overviewQuery = useQuery({ queryKey: OVERVIEW_KEY, queryFn: () => openFinanceApi.overview() })
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const cardsQuery = useQuery({ queryKey: ['cartoes'], queryFn: () => creditCardsApi.list() })
  const settingsQuery = useQuery({ queryKey: SETTINGS_KEY, queryFn: () => openFinanceApi.settings() })
  const money = usePrivateFormatter(formatCurrency)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [days, setDays] = useState('')

  const data = overviewQuery.data
  const items = data?.items || NO_ITEMS
  const accounts = accountsQuery.data || NO_ITEMS
  const cards = cardsQuery.data || NO_ITEMS
  const settings = settingsQuery.data
  const daysValue = days === '' ? String(settings?.first_sync_days ?? data?.first_sync_days ?? '') : days
  const daysError = days === '' ? '' : firstSyncDaysError(days)

  const keep = (body) => {
    if (body?.items) queryClient.setQueryData(OVERVIEW_KEY, body)
    return body
  }

  const run = async (key, action) => {
    setBusy(key)
    setError('')
    try {
      return await action()
    } catch (actionError) {
      setError(actionError.message || 'Não foi possível falar com o Open Finance.')
      return null
    } finally {
      setBusy('')
    }
  }

  const connect = (item = null) => run(item ? `fix:${item.id}` : 'connect', async () => {
    const { access_token: token } = await openFinanceApi.connectToken(item?.id)
    await openPluggyConnect(token, {
      onSuccess: async (result) => {
        const pluggyItemId = connectedItemId(result)
        if (!pluggyItemId) return
        await run('register', async () => {
          keep(await openFinanceApi.register(pluggyItemId))
          toast(item ? 'Conexão atualizada.' : 'Banco conectado. Diga para onde vai cada conta.')
        })
      },
      onError: (widgetError) => {
        // A mensagem da Pluggy (ex.: o limite de CPF do plano) aparece como veio.
        setError(widgetError?.message || 'A Pluggy não conseguiu conectar este banco.')
      },
    })
  })

  const refresh = (item) => run(`sync:${item.id}`, async () => {
    const body = keep(await openFinanceApi.sync(item.id))
    toast(syncSummary(body?.result))
  })

  const disconnect = async (item) => {
    const name = itemBankName(item)
    if (!(await confirmAction({
      title: `Desconectar ${name}?`,
      message: 'A conexão é apagada na Pluggy e nada mais chega deste banco. Os lançamentos já gravados e o que espera no Revisar ficam.',
      confirmLabel: 'Desconectar',
    }))) return
    await run(`off:${item.id}`, async () => {
      keep(await openFinanceApi.disconnect(item.id, name))
      toast(`${name} desconectado.`)
    })
  }

  const map = (account, value) => run(`map:${account.id}`, async () => {
    const body = keep(await openFinanceApi.map(account.id, mappingPayload(account, value)))
    const recorded = body?.auto_recorded?.recorded || 0
    if (!value) toast('Esta conta não traz mais nada.')
    else if (value === IGNORE_CHOICE) toast('Esta conta fica de fora.')
    else if (recorded) toast(`Destino salvo. ${recorded} lançamento(s) gravado(s).`)
    else toast(body?.placed ? `Destino salvo. ${body.placed} movimento(s) foram para o Revisar.` : 'Destino salvo.')
  })

  const recordBankRow = (row) => run(`record:${row.id}`, async () => {
    keep(await openFinanceApi.recordBankRow(row.id))
    toast('Lançado. Confira em Revisar.')
  })

  const confirmAppRow = (row, undo) => run(`confirm:${row.id}`, async () => {
    keep(await openFinanceApi.confirmAppRow(row, undo))
    toast(undo ? 'Voltou para a conferência.' : 'Certo: fica como feito.')
  })

  const saveSettings = (key, payload, message) => run(key, async () => {
    const body = await openFinanceApi.updateSettings(payload)
    queryClient.setQueryData(SETTINGS_KEY, body)
    queryClient.setQueryData(OVERVIEW_KEY, (old) => (old ? { ...old, first_sync_days: body.first_sync_days } : old))
    toast(message)
    return body
  })

  const saveDays = async () => {
    if (daysError) return
    if (await saveSettings('days', { first_sync_days: Number(days) }, 'Janela da primeira busca salva.')) setDays('')
  }

  return (
    <Panel id="open-finance" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Open Finance"
        description={settings?.auto_record
          ? 'Os movimentos das suas contas e cartões chegam pela Pluggy e viram lançamentos sozinhos. O Revisar, no Extrato, fica para as categorias e o que só você decide.'
          : 'Os movimentos das suas contas e cartões chegam pela Pluggy e esperam no Revisar, no Extrato.'}
        actions={data?.configured ? (
          <Button size="sm" icon={Plus} loading={busy === 'connect' || busy === 'register'} onClick={() => connect()}>
            Conectar banco
          </Button>
        ) : null}
      />
      <div className="space-y-4 p-5">
        <AlertMessage message={error || queryErrorMessage(overviewQuery, 'Não foi possível ler o Open Finance.')} onDismiss={error ? () => setError('') : undefined} />
        {overviewQuery.isPending ? <ListSkeleton rows={2} className="p-0" /> : null}
        {data && !data.configured ? (
          <AlertMessage
            tone="info"
            message="Desligado: o servidor não tem as credenciais da Pluggy (PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no .env do servidor; veja DEPLOY.md)."
          />
        ) : null}
        {data?.configured && items.length === 0 ? (
          <EmptyState
            icon={Landmark}
            title="Nenhum banco conectado"
            message="Conecte um banco seu (um CPF, o seu). Os movimentos dos últimos dias viram lançamentos; depois o app busca sozinho de tempos em tempos."
          />
        ) : null}
        {items.map((item) => {
          const status = itemStatus(item)
          const problem = itemProblem(item)
          return (
            <section key={item.id} className="space-y-3 rounded-2xl border border-zinc-200 p-3" aria-label={itemBankName(item)}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-zinc-950">{itemBankName(item)}</p>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {item.last_sync_at ? `Última busca: ${whenLabel(item.last_sync_at)}` : 'Ainda sem busca.'}
                    {item.pluggy_updated_at ? ` · Banco lido pela Pluggy: ${whenLabel(item.pluggy_updated_at)}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="secondary" icon={RefreshCw} loading={busy === `sync:${item.id}`} disabled={Boolean(busy)} onClick={() => refresh(item)}>
                    Atualizar
                  </Button>
                  <Menu
                    label={`Mais ações de ${itemBankName(item)}`}
                    items={[
                      { label: 'Reconectar (senha, código)', onSelect: () => connect(item) },
                      { label: 'Desconectar', tone: 'danger', onSelect: () => disconnect(item) },
                    ]}
                  />
                </div>
              </div>
              {problem ? <AlertMessage tone="warning" message={problem} /> : null}
              <ul className="divide-y divide-zinc-100 rounded-xl border border-zinc-100">
                {item.accounts.map((account) => (
                  <AccountRow
                    key={account.id}
                    account={account}
                    item={item}
                    choices={mappingChoices(account, { accounts, cards, items })}
                    money={money}
                    busy={busy === `map:${account.id}`}
                    checkBusy={busy}
                    onMap={map}
                    onRecord={recordBankRow}
                    onConfirm={confirmAppRow}
                  />
                ))}
              </ul>
            </section>
          )
        })}
        <PortfolioCheck investments={data?.investments} money={money} />
        {data?.configured && settings ? (
          <div className="space-y-4 border-t border-zinc-100 pt-4">
            <Field
              label="Busca automática"
              hint={settings.auto_sync_available
                ? 'O app só lê o que a Pluggy já trouxe do banco (ela atualiza sozinha, de 6 a 24 h); nunca menos de 6 h. "Atualizar" lê na hora.'
                : 'O servidor está com a busca automática desligada (OPEN_FINANCE_SYNC_SECONDS=0); só "Atualizar".'}
            >
              <select
                value={settings.sync_hours}
                disabled={busy === 'hours'}
                onChange={(event) => {
                  const hours = Number(event.target.value)
                  saveSettings('hours', { sync_hours: hours }, hours ? `Busca automática a cada ${hours} h.` : 'Busca automática desligada.')
                }}
                className="app-input sm:w-56"
              >
                {syncHoursChoices(settings.sync_hours).map((choice) => (
                  <option key={choice.value} value={choice.value}>{choice.label}</option>
                ))}
              </select>
            </Field>
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={Boolean(settings.include_pending)}
                disabled={busy === 'pending'}
                onChange={(event) => saveSettings(
                  'pending',
                  { include_pending: event.target.checked },
                  event.target.checked ? 'Pendentes do banco vêm para o Revisar.' : 'Pendentes do banco ficam de fora.',
                )}
                className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
              />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-zinc-900">Trazer pendentes</span>
                <span className="block text-sm text-zinc-600">
                  Movimentos que o banco ainda não liquidou (compra na fatura aberta) também entram. Se o banco trocar o movimento ao liquidar, o item pendente sai sozinho.
                </span>
              </span>
            </label>
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Primeira busca de um banco novo (dias)" hint={daysError || 'Até 365 dias; a Pluggy guarda 12 meses.'}>
                <input
                  type="text"
                  inputMode="numeric"
                  value={daysValue}
                  onChange={(event) => setDays(event.target.value)}
                  className="app-input w-28"
                />
              </Field>
              {days !== '' ? (
                <Button size="sm" variant="secondary" loading={busy === 'days'} disabled={Boolean(daysError)} onClick={saveDays}>
                  Salvar
                </Button>
              ) : null}
            </div>
            {items.length ? <HistoryPanel enabled={Boolean(settings.auto_record)} busy={busy} run={run} /> : null}
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
