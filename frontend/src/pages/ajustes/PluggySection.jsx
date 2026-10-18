import { useState } from 'react'
import { Landmark, Link2, Plus, RefreshCw, Trash2, Unlink } from 'lucide-react'
import { accountsApi, creditCardsApi, pluggyApi } from '../../lib/dataApi'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  ListSkeleton,
  Panel,
  PanelHeader,
} from '../../components/ui'
import { formatCurrency, formatDateBR, formatSignedCurrency, getLocalDateString } from '../../lib/format'
import { invalidateServerData, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'
import { confirmAction } from '../../lib/confirm'
import { syncPluggy } from '../../lib/pluggySync'
import {
  candidateKindLabel,
  differenceText,
  itemStatusLabel,
  lastSyncAt,
  linkPayload,
  linkTargets,
  pluggyAccountLabel,
  reviewReasonText,
  setupProblems,
  syncSummary,
} from '../../lib/pluggyRules'

const NO_ITEMS = []

function whenLabel(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${formatDateBR(getLocalDateString(date))} ${time}`
}

// Saida do banco com sinal de menos, entrada com mais (o livro guarda o valor positivo).
function bankAmount(item) {
  return formatSignedCurrency(item.amount, item.direction === 'DEBIT' ? -1 : 1)
}

function CandidateRow({ candidate, onPick, busy }) {
  const where = candidate.card_name || candidate.account_name
  const transferTo = candidate.transfer_account_name ? ` → ${candidate.transfer_account_name}` : ''
  return (
    <li className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-900">
          {candidate.description || candidate.category || candidateKindLabel(candidate.kind)}
        </p>
        <p className="text-xs text-zinc-500">
          {candidateKindLabel(candidate.kind)} · {formatDateBR(candidate.date)} · {formatCurrency(candidate.amount)}
          {candidate.installment_info ? ` · parcela ${candidate.installment_info}` : ''}
          {where ? ` · ${where}${transferTo}` : ''}
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onPick} loading={busy}>É este</Button>
    </li>
  )
}

// Uma transacao do banco que pode ser duplicata: o dono escolhe o lancamento
// que ela confirma, lanca separado, ou ignora.
function ReviewItem({ item, onDecide, busyKey }) {
  return (
    <li className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-zinc-900">{item.description || 'Sem descrição'}</p>
          <p className="text-xs text-zinc-500">
            No banco · {formatDateBR(item.date)}{item.account_name ? ` · ${item.account_name}` : ''}
            {item.total_installments ? ` · parcela ${item.installment_number}/${item.total_installments}` : ''}
          </p>
        </div>
        <p className="num shrink-0 font-semibold text-zinc-900">{bankAmount(item)}</p>
      </div>
      <p className="text-sm text-zinc-600">{reviewReasonText(item)}</p>
      {item.candidates.length ? (
        <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
          {item.candidates.map((candidate) => (
            <CandidateRow
              key={`${candidate.table}:${candidate.id}`}
              candidate={candidate}
              busy={busyKey === `${item.id}:attach:${candidate.id}`}
              onPick={() => onDecide(item, 'attach', candidate.id)}
            />
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" onClick={() => onDecide(item, 'insert')} loading={busyKey === `${item.id}:insert`}>
          Lançar separado
        </Button>
        <Button variant="subtle" size="sm" onClick={() => onDecide(item, 'dismiss')} loading={busyKey === `${item.id}:dismiss`}>
          Ignorar
        </Button>
      </div>
    </li>
  )
}

// Uma conta da Pluggy e a conta (ou o cartao) do app que ela alimenta.
function AccountLink({ itemRowId, account, accounts, cards, onError }) {
  const linked = account.link
  const [targetId, setTargetId] = useState(linked?.account_id || linked?.card_id || '')
  const [since, setSince] = useState(linked?.since || getLocalDateString())
  const [saving, setSaving] = useState(false)
  const targets = linkTargets(account, { accounts, cards })
  const changed = !linked || targetId !== (linked.account_id || linked.card_id) || since !== linked.since

  const save = async () => {
    if (!targetId) {
      onError(account.type === 'CREDIT' ? 'Escolha o cartão.' : 'Escolha a conta.')
      return
    }
    setSaving(true)
    try {
      await pluggyApi.link(account.id, linkPayload(account, { itemRowId, targetId, since }))
      const target = targets.find((item) => item.id === targetId)
      toast(`${pluggyAccountLabel(account)} ligada a ${target?.name || 'esta conta'}, desde ${formatDateBR(since)}.`)
    } catch (error) {
      onError(error.message || 'Não foi possível ligar a conta.')
    } finally {
      setSaving(false)
    }
  }

  const unlink = async () => {
    if (!(await confirmAction({
      title: 'Desligar esta conta da Pluggy?',
      message: 'O que já entrou fica no extrato. A conta para de ser lida até ser ligada de novo.',
      confirmLabel: 'Desligar',
    }))) return
    setSaving(true)
    try {
      await pluggyApi.unlink(account.id)
      setTargetId('')
      toast(`${pluggyAccountLabel(account)} desligada.`)
    } catch (error) {
      onError(error.message || 'Não foi possível desligar a conta.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 truncate font-medium text-zinc-900">{pluggyAccountLabel(account)}</p>
        {linked ? <Badge>Ligada</Badge> : null}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_11rem_auto] sm:items-end">
        <Field label={account.type === 'CREDIT' ? 'Cartão no app' : 'Conta no app'}>
          <select value={targetId} onChange={(event) => setTargetId(event.target.value)} className="app-input">
            <option value="">Não ligada</option>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>{target.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Desde">
          <input type="date" value={since} onChange={(event) => setSince(event.target.value)} className="app-input" />
        </Field>
        <div className="flex gap-2">
          <Button size="sm" icon={Link2} onClick={save} loading={saving} disabled={!changed}>
            {linked ? 'Salvar' : 'Ligar'}
          </Button>
          {linked ? <IconButton label="Desligar" icon={Unlink} variant="danger" onClick={unlink} disabled={saving} /> : null}
        </div>
      </div>
    </li>
  )
}

function ItemAccounts({ item, accounts, cards, onError }) {
  const accountsQuery = useQuery({
    queryKey: ['pluggy', 'contas', item.id],
    queryFn: () => pluggyApi.accounts(item.id),
    staleTime: 5 * 60_000,
  })
  if (accountsQuery.isPending) return <ListSkeleton rows={2} className="p-0" />
  const error = queryErrorMessage(accountsQuery, 'Não foi possível ler as contas desta conexão na Pluggy.')
  if (error) return <AlertMessage message={error} />
  const list = accountsQuery.data || NO_ITEMS
  if (!list.length) return <p className="text-sm text-zinc-500">A Pluggy não devolveu nenhuma conta para esta conexão.</p>
  return (
    <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
      {list.map((account) => (
        <AccountLink
          key={`${account.id}:${account.link?.since || ''}:${account.link?.account_id || account.link?.card_id || ''}`}
          itemRowId={item.id}
          account={account}
          accounts={accounts}
          cards={cards}
          onError={onError}
        />
      ))}
    </ul>
  )
}

function ItemRow({ item, accounts, cards, onRemove, onError }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-zinc-900">{item.connector_name || 'Conexão'}</p>
          <p className="text-xs text-zinc-500">
            {itemStatusLabel(item.status)}
            {item.last_sync_at ? ` · lida em ${whenLabel(item.last_sync_at)}` : ''}
          </p>
          {item.last_error ? <p className="mt-1 text-xs text-zinc-600">Última falha: {item.last_error}</p> : null}
        </div>
        <IconButton label="Remover conexão" icon={Trash2} variant="danger" size="sm" onClick={() => onRemove(item)} />
      </div>
      <Collapsible label="Contas desta conexão" variant="secondary" size="sm" open={open} onOpenChange={setOpen}>
        {open ? <ItemAccounts item={item} accounts={accounts} cards={cards} onError={onError} /> : null}
      </Collapsible>
    </li>
  )
}

// Ajustes › Banco (Pluggy): o extrato dos bancos pelo Open Finance
// (backend/services/pluggy_sync.py). O que o banco registra confirma o que o
// dono e o celular ja lancaram; o que faltava entra; o que pode ser duplicata
// espera aqui, em "Possivel duplicata".
export default function PluggySection() {
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [busyKey, setBusyKey] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [itemId, setItemId] = useState('')
  const [adding, setAdding] = useState(false)

  const statusQuery = useQuery({ queryKey: ['pluggy'], queryFn: () => pluggyApi.status() })
  const status = statusQuery.data
  const reviewQuery = useQuery({
    queryKey: ['pluggy', 'revisao'],
    queryFn: () => pluggyApi.review(),
    enabled: Boolean(status?.configured),
  })
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const cardsQuery = useQuery({ queryKey: ['cartoes'], queryFn: () => creditCardsApi.list() })
  const accounts = accountsQuery.data || NO_ITEMS
  const cards = cardsQuery.data || NO_ITEMS
  const items = status?.items || NO_ITEMS
  const review = reviewQuery.data?.review || NO_ITEMS
  const differences = reviewQuery.data?.differences || NO_ITEMS
  const configured = Boolean(status?.configured)
  const lastSync = lastSyncAt(items)

  const handleSync = async () => {
    setSyncing(true)
    setError('')
    try {
      const result = await syncPluggy({ force: true })
      await invalidateServerData()
      const message = syncSummary(result)
      if (result?.status === 'error') setError(message)
      else toast(message, { tone: result?.status === 'partial' ? 'info' : undefined })
    } catch (syncError) {
      setError(syncError.message || 'Não foi possível sincronizar com a Pluggy.')
    } finally {
      setSyncing(false)
    }
  }

  const handleDecide = async (item, action, targetId) => {
    setBusyKey(action === 'attach' ? `${item.id}:attach:${targetId}` : `${item.id}:${action}`)
    setError('')
    try {
      await pluggyApi.decide(item.id, action, targetId)
      toast(
        action === 'attach' ? 'Conferido: ficou um lançamento só.'
          : action === 'insert' ? 'Lançado separado.'
            : 'Transação do banco ignorada.'
      )
    } catch (decideError) {
      setError(decideError.message || 'Não foi possível decidir esta transação.')
    } finally {
      setBusyKey('')
    }
  }

  const handleAdd = async (event) => {
    event.preventDefault()
    if (!itemId.trim()) {
      setError('Cole o id da conexão (item) da Pluggy.')
      return
    }
    setAdding(true)
    setError('')
    try {
      const item = await pluggyApi.addItem(itemId.trim())
      toast(`${item.connector_name ? `Conexão ${item.connector_name}` : 'Conexão'} cadastrada. Agora ligue as contas dela.`)
      setItemId('')
      setFormOpen(false)
    } catch (addError) {
      setError(addError.message || 'Não foi possível cadastrar a conexão.')
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (item) => {
    if (!(await confirmAction({
      title: item.connector_name ? `Remover a conexão ${item.connector_name}?` : 'Remover esta conexão?',
      message: 'As contas dela deixam de ser lidas. Nenhum lançamento é apagado.',
      confirmLabel: 'Remover conexão',
    }))) return
    setError('')
    try {
      await pluggyApi.removeItem(item.id)
      toast('Conexão removida.')
    } catch (removeError) {
      setError(removeError.message || 'Não foi possível remover a conexão.')
    }
  }

  return (
    <Panel id="pluggy" className="scroll-mt-20 lg:scroll-mt-8">
      <PanelHeader
        title="Banco (Pluggy)"
        description="O extrato dos bancos pelo Open Finance. O que o banco registra confere o que você e o celular já lançaram; o que faltava entra sozinho."
        actions={configured && status?.links?.length ? (
          <Button variant="secondary" size="sm" icon={RefreshCw} loading={syncing} onClick={handleSync}>
            Sincronizar
          </Button>
        ) : null}
      />
      <div className="space-y-5 p-5">
        <AlertMessage message={error || queryErrorMessage(statusQuery, 'Não foi possível ler a configuração da Pluggy.')} onDismiss={error ? () => setError('') : undefined} />

        {statusQuery.isPending ? (
          <ListSkeleton rows={2} className="p-0" />
        ) : !configured ? (
          <AlertMessage tone="info">
            <p>A Pluggy não está configurada no servidor; até lá, nada é lido dos bancos.</p>
            {setupProblems(status?.setup).map((problem) => <p key={problem} className="mt-1">{problem}</p>)}
            <p className="mt-1">
              No servidor, <code>PLUGGY_CLIENT_ID</code> e <code>PLUGGY_CLIENT_SECRET</code> vão em{' '}
              <code>/srv/apps/financas/.env</code>; depois rode{' '}
              <code>sudo docker compose up -d --force-recreate</code>. Um <code>docker compose restart</code> não lê o <code>.env</code> de novo.
            </p>
          </AlertMessage>
        ) : (
          <>
            {review.length ? (
              <section aria-labelledby="pluggy-revisao" className="space-y-2">
                <h3 id="pluggy-revisao" className="flex items-center gap-2 text-sm font-semibold text-zinc-800">
                  Possível duplicata <Badge tone="warning">{review.length}</Badge>
                </h3>
                <p className="text-sm text-zinc-500">Nada disto entrou no extrato: decida cada uma.</p>
                <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
                  {review.map((item) => (
                    <ReviewItem key={item.id} item={item} onDecide={handleDecide} busyKey={busyKey} />
                  ))}
                </ul>
              </section>
            ) : null}

            {differences.length ? (
              <Collapsible label={`Conferidos com diferença (${differences.length})`} variant="secondary" size="sm">
                <p className="mb-2 text-sm text-zinc-500">
                  O lançamento ficou como você deixou; o banco diz outra data ou valor.
                </p>
                <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
                  {differences.map((item) => (
                    <li key={item.id} className="px-4 py-2.5">
                      <p className="truncate text-sm font-medium text-zinc-900">{item.description || 'Sem descrição'}</p>
                      <p className="text-xs text-zinc-500">
                        {item.account_name ? `${item.account_name} · ` : ''}
                        {differenceText(item.difference, formatCurrency, formatDateBR)}
                      </p>
                    </li>
                  ))}
                </ul>
              </Collapsible>
            ) : null}

            {items.length ? (
              <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
                {items.map((item) => (
                  <ItemRow key={item.id} item={item} accounts={accounts} cards={cards} onRemove={handleRemove} onError={setError} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={Landmark}
                title="Nenhuma conexão"
                message="Conecte o banco na Pluggy (MeuPluggy ou o painel da Pluggy) e cole aqui o id da conexão (item)."
                className="min-h-40"
              />
            )}

            <Collapsible label="Nova conexão" icon={Plus} open={formOpen} onOpenChange={setFormOpen}>
              <form onSubmit={handleAdd} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-[1fr_auto]">
                <Field label="Id da conexão (item) na Pluggy" hint="Um código como 1a2b3c4d-…; a Pluggy mostra ao conectar o banco.">
                  <input
                    type="text"
                    value={itemId}
                    onChange={(event) => setItemId(event.target.value)}
                    autoComplete="off"
                    spellCheck="false"
                    className="app-input"
                    required
                  />
                </Field>
                <div className="flex items-end">
                  <Button type="submit" loading={adding} className="w-full">Cadastrar</Button>
                </div>
              </form>
            </Collapsible>

            <p className="text-xs text-zinc-500">
              {lastSync ? `Última leitura: ${whenLabel(lastSync)}.` : 'Ainda não sincronizado.'}{' '}
              O extrato é lido ao abrir Lançamentos (no máximo a cada 10 minutos). Compras no cartão chegam quando a fatura fecha.
            </p>
          </>
        )}
      </div>
    </Panel>
  )
}
