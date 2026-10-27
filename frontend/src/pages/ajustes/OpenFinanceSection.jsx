import { useState } from 'react'
import { Landmark, Plus, RefreshCw } from 'lucide-react'
import { accountsApi, creditCardsApi, openFinanceApi } from '../../lib/dataApi'
import { AlertMessage, Badge, Button, Collapsible, EmptyState, Field, ListSkeleton, Menu, Panel, PanelHeader } from '../../components/ui'
import { confirmAction } from '../../lib/confirm'
import { formatCurrency, formatDateBR, getLocalDateString } from '../../lib/format'
import {
  accountLabel,
  balanceCheck,
  checkSummary,
  connectedItemId,
  firstSyncDaysError,
  itemProblem,
  itemStatus,
  mappedId,
  mappingChoices,
  mappingPayload,
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

function CheckList({ title, rows, money }) {
  if (!rows?.length) return null
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-zinc-700">{title}</p>
      <ul className="space-y-1">
        {rows.map((row, index) => (
          <li key={`${row.date}-${index}`} className="flex items-start justify-between gap-3 text-xs text-zinc-600">
            <span className="min-w-0 break-words">{formatDateBR(row.date)} · {row.description || 'Sem descrição'}</span>
            <span className="num shrink-0">{money(row.amount)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Conferência: o banco contra o app, so apontando (nada e ajustado).
function AccountCheck({ check, money }) {
  const summary = checkSummary(check)
  if (summary.state === 'none') return null
  const hasRows = check.bank_only?.length || check.app_only?.length || check.awaiting?.length
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600">
        <Badge tone={summary.state === 'match' ? 'success' : 'warning'}>
          {summary.state === 'match' ? 'Movimentos conferem' : 'Movimentos com diferença'}
        </Badge>
        {summary.state === 'drift' || check.awaiting_count ? <span>{summary.text}</span> : null}
      </div>
      {hasRows ? (
        <Collapsible label="Ver a conferência" variant="secondary" size="sm">
          <div className="space-y-3">
            <CheckList title="Só no banco (recusado no Aprovar ou lançado com outro valor/data)" rows={check.bank_only} money={money} />
            <CheckList title="Só no app (o banco não tem)" rows={check.app_only} money={money} />
            <CheckList title="Esperando no Aprovar" rows={check.awaiting} money={money} />
            <p className="text-xs text-zinc-500">
              Desde {formatDateBR(check.from)}; pares de mesmo valor até 3 dias de distância.
            </p>
          </div>
        </Collapsible>
      ) : null}
    </div>
  )
}

function AccountRow({ account, item, choices, money, busy, onMap }) {
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
          aria-label={`Destino de ${accountLabel(account)} em ${item.connector_name || 'Open Finance'}`}
        >
          <option value="">Nenhum (não traz nada)</option>
          {choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </select>
      </Field>
      {suggested ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600">
          <span>Parece ser {suggested.label}.</span>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onMap(account, suggested.value)}>
            Confirmar
          </Button>
        </div>
      ) : null}
      {!current && account.unmapped_count ? (
        <p className="text-xs text-zinc-500">
          {account.unmapped_count === 1 ? '1 movimento espera' : `${account.unmapped_count} movimentos esperam`} esta escolha para ir ao Aprovar.
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
      <AccountCheck check={account.check} money={money} />
    </li>
  )
}

// Ajustes › Open Finance (043): conectar um banco pela Pluggy (so aqui, na
// web), dizer para qual conta/cartao do app vai cada conta dele, ver o estado
// e o saldo do banco ao lado do do app. O que chega espera em Lancamentos ›
// Aprovar: nada e lancado sem o dono aprovar.
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
    const name = item.connector_name || 'Open Finance'
    if (!(await confirmAction({
      title: `Desconectar ${name}?`,
      message: 'A conexão é apagada na Pluggy e nada mais chega deste banco. Os lançamentos já aprovados e o que espera no Aprovar ficam.',
      confirmLabel: 'Desconectar',
    }))) return
    await run(`off:${item.id}`, async () => {
      keep(await openFinanceApi.disconnect(item.id, name))
      toast(`${name} desconectado.`)
    })
  }

  const map = (account, value) => run(`map:${account.id}`, async () => {
    const body = keep(await openFinanceApi.map(account.id, mappingPayload(account, value)))
    if (!value) toast('Esta conta não traz mais nada.')
    else toast(body?.placed ? `Destino salvo. ${body.placed} movimento(s) foram para o Aprovar.` : 'Destino salvo.')
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
        description="Os movimentos das suas contas e cartões chegam pela Pluggy e esperam em Lançamentos › Aprovar. Nada é lançado sem você aprovar."
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
            message="Conecte um banco seu (um CPF, o seu). Os movimentos dos últimos dias vêm para o Aprovar; depois o app busca sozinho de tempos em tempos."
          />
        ) : null}
        {items.map((item) => {
          const status = itemStatus(item)
          const problem = itemProblem(item)
          return (
            <section key={item.id} className="space-y-3 rounded-2xl border border-zinc-200 p-3" aria-label={item.connector_name || 'Conexão'}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-semibold text-zinc-950">{item.connector_name || 'Banco'}</p>
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
                    label={`Mais ações de ${item.connector_name || 'conexão'}`}
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
                    onMap={map}
                  />
                ))}
              </ul>
            </section>
          )
        })}
        {data?.configured && settings ? (
          <div className="space-y-4 border-t border-zinc-100 pt-4">
            <Field
              label="Busca automática"
              hint={settings.auto_sync_available
                ? 'Cada busca gasta o limite mensal do banco na Pluggy; menos de 1 h não é possível. "Atualizar" funciona sempre.'
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
                  event.target.checked ? 'Pendentes do banco vêm para o Aprovar.' : 'Pendentes do banco ficam de fora.',
                )}
                className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-600"
              />
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-zinc-900">Trazer pendentes</span>
                <span className="block text-sm text-zinc-600">
                  Movimentos que o banco ainda não liquidou (compra na fatura aberta) também vão para o Aprovar. Se o banco trocar o movimento ao liquidar, o item pendente sai sozinho.
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
          </div>
        ) : null}
      </div>
    </Panel>
  )
}
