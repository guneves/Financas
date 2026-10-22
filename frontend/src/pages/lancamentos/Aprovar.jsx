import { useMemo, useState } from 'react'
import { ArrowRight, BellRing, CheckCheck, Inbox, Pencil, Repeat, RotateCcw, Smartphone, Undo2, X } from 'lucide-react'
import { accountsApi, categoriesApi, creditCardsApi, inboxApi } from '../../lib/dataApi'
import { creditCards } from '../../lib/cardFunctions'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  ListSkeleton,
  Menu,
  PageHeader,
  Panel,
  SegmentedControl,
  Sheet,
} from '../../components/ui'
import { formatCurrency, formatDateBR, formatSignedCurrency, getLocalDateString } from '../../lib/format'
import { invalidateServerData, queryClient, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'
import { confirmAction } from '../../lib/confirm'
import {
  ambiguousText,
  amountSign,
  approveReadySummary,
  candidateKindLabel,
  changesFromDraft,
  CONFIRM_TEXTS,
  decisionText,
  draftFromItem,
  ENTRY_TYPE_LABELS,
  entryTypeLabel,
  hintText,
  needText,
  offersRemember,
  onlySamsung,
  quickChoice,
  readyIds,
  reasonText,
  recurringText,
  recurringToggle,
  sourceLabel,
  splittableSources,
  targetFields,
  targetText,
  whenText,
} from '../../lib/inboxRules'
import { buildCategoryOptions, filterCategoryOptions } from './helpers'

const NO_ITEMS = []
// O celular e o computador leem a mesma lista: a tela aberta rele sozinha, e
// voltar para ela (outra aba, o app de novo na frente) rele na hora.
const REFRESH_MS = 20_000
const CONFLICT_MESSAGE = 'Este item mudou em outro aparelho. A lista foi atualizada: confira antes de decidir.'

function useInbox(view) {
  return useQuery({
    queryKey: ['aprovar', view],
    queryFn: () => inboxApi.list(view),
    refetchInterval: view === 'pending' ? REFRESH_MS : false,
    refetchOnWindowFocus: true,
  })
}

function SourceLine({ source }) {
  return (
    <li className="flex min-w-0 items-start gap-2 text-xs text-zinc-500">
      <Smartphone className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span className="min-w-0">
        {sourceLabel(source)}
        {source.source === 'notification'
          ? ` · ${whenText(source.occurred_at)}`
          : ` · ${formatDateBR(source.date)}`}
        {source.role === 'PAIRED' ? ' · mesma compra' : ''}
      </span>
    </li>
  )
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

function Select({ label, value, options, onChange, placeholder = 'Escolha…', hint }) {
  return (
    <Field label={label} hint={hint} className="min-w-0">
      <select value={value || ''} onChange={(event) => onChange(event.target.value)} className="app-select">
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>{option.name}</option>
        ))}
      </select>
    </Field>
  )
}

// Os seletores que o item mostra aberto: o que falta, o palpite a confirmar e,
// depois de "Trocar", todos os do tipo.
function openPickers(item, changing) {
  const needs = item.needs || NO_ITEMS
  const confirm = item.confirm || NO_ITEMS
  return targetFields(item).filter((field) => changing || needs.includes(field) || confirm.includes(field))
}

// As escolhas que o item pede, ali mesmo no cartao: credito ou debito, qual
// cartao, qual conta. Um palpite vem preenchido com "confirme"; "Trocar" abre
// os mesmos seletores num item que ja sabia para onde ia.
function Decisions({ item, accounts, cards, onQuick, changing }) {
  const needs = item.needs || NO_ITEMS
  const confirm = item.confirm || NO_ITEMS
  const askMethod = needs.includes('method')
  const open = openPickers(item, changing)
  const showCard = open.includes('card')
  const showAccount = open.includes('account')
  const showDestination = open.includes('transfer_account')
  if (!(askMethod || showCard || showAccount || showDestination)) return null
  const warn = askMethod || open.some((field) => needs.includes(field) || confirm.includes(field))
  const ambiguous = ambiguousText(item)
  return (
    <div className={warn ? 'space-y-3 rounded-2xl border border-amber-200 bg-amber-50/60 p-3' : 'space-y-3 rounded-2xl border border-zinc-200 p-3'}>
      {askMethod ? (
        <div className="space-y-1.5">
          <p className="text-sm font-semibold text-zinc-800">{needText('method')}</p>
          <SegmentedControl
            items={[
              { value: 'CARD', label: 'Crédito (cartão)' },
              { value: 'DEBIT', label: 'Débito (conta)' },
            ]}
            value=""
            onChange={(method) => onQuick(item, quickChoice(item, { method }))}
          />
        </div>
      ) : null}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {showCard ? (
          <Select
            label={needText('card')}
            value={item.card_id}
            options={cards}
            hint={confirm.includes('card') ? CONFIRM_TEXTS.card : undefined}
            onChange={(cardId) => onQuick(item, quickChoice(item, { card_id: cardId }))}
          />
        ) : null}
        {showAccount ? (
          <Select
            label={item.entry_type === 'TRANSFER' ? 'De qual conta?' : needText('account')}
            value={item.account_id}
            options={accounts}
            hint={confirm.includes('account') ? CONFIRM_TEXTS.account : undefined}
            onChange={(accountId) => onQuick(item, quickChoice(item, { account_id: accountId }))}
          />
        ) : null}
        {showDestination ? (
          <Select
            label={needText('transfer_account')}
            value={item.transfer_account_id}
            options={accounts.filter((account) => account.id !== item.account_id)}
            hint={confirm.includes('transfer_account') ? CONFIRM_TEXTS.transfer_account : undefined}
            onChange={(accountId) => onQuick(item, quickChoice(item, { transfer_account_id: accountId }))}
          />
        ) : null}
      </div>
      {ambiguous ? <p className="text-xs text-zinc-600">{ambiguous}</p> : null}
    </div>
  )
}

// Para onde vai, sempre a vista — inclusive o lembrado —, com "Trocar" ali
// mesmo. Some o botao quando os seletores ja estao abertos.
function TargetLine({ item, changing, onToggle }) {
  const text = targetText(item)
  if (!text) return null
  const fields = targetFields(item)
  const alreadyOpen = !changing && fields.length > 0 && openPickers(item, false).length === fields.length
  return (
    <div className="flex min-w-0 items-center gap-2">
      <ArrowRight className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden="true" />
      <p className="min-w-0 flex-1 truncate text-sm font-medium text-zinc-800">{text}</p>
      {alreadyOpen ? null : (
        <Button variant="subtle" size="sm" onClick={onToggle} aria-expanded={changing}>
          {changing ? 'Fechar' : 'Trocar'}
        </Button>
      )}
    </div>
  )
}

function ItemCard({ item, accounts, cards, busyKey, onApprove, onDeny, onEdit, onQuick, onMatch, onSplit }) {
  const [remember, setRemember] = useState(true)
  const [changing, setChanging] = useState(false)
  // Trocado num seletor, o item volta a mostrar so a linha de destino.
  const choose = async (target, body) => {
    await onQuick(target, body)
    setChanging(false)
  }
  const sign = amountSign(item)
  const reason = reasonText(item)
  const splittable = splittableSources(item)
  const busy = (action) => busyKey === `${item.id}:${action}`
  const menu = [
    { label: 'Editar antes de aprovar', icon: Pencil, onSelect: () => onEdit(item) },
    ...splittable.map((source) => ({
      label: `Não é a mesma: separar ${sourceLabel(source)}`,
      icon: Undo2,
      onSelect: () => onSplit(item, source),
    })),
  ]

  return (
    <Panel as="li" className="space-y-3 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-semibold text-zinc-950">{item.description || entryTypeLabel(item.entry_type)}</p>
          <p className="text-sm text-zinc-600">{whenText(item.occurred_at)}</p>
        </div>
        <p className="num shrink-0 text-lg font-bold text-zinc-950">
          {sign ? formatSignedCurrency(item.amount, sign) : formatCurrency(item.amount)}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={item.entry_type ? 'neutral' : 'warning'}>{entryTypeLabel(item.entry_type)}</Badge>
        {item.category && item.entry_type !== 'TRANSFER' ? <Badge>{item.category}</Badge> : null}
        {onlySamsung(item) ? <Badge tone="info">via Samsung Wallet</Badge> : null}
        {item.edited?.length ? <Badge tone="info">corrigido</Badge> : null}
      </div>

      <ul className="space-y-1">
        {(item.sources || NO_ITEMS).map((source) => <SourceLine key={`${source.source}:${source.id}`} source={source} />)}
      </ul>

      {reason ? <p className="text-sm text-zinc-600">{reason}</p> : null}

      <TargetLine item={item} changing={changing} onToggle={() => setChanging(!changing)} />

      <Decisions item={item} accounts={accounts} cards={cards} onQuick={choose} changing={changing} />

      {item.recurring ? (
        <div className="flex flex-col gap-2 rounded-2xl border border-zinc-200 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <p className="flex min-w-0 items-start gap-2 text-sm text-zinc-700">
            <Repeat className="mt-0.5 h-4 w-4 shrink-0 text-zinc-500" aria-hidden="true" />
            <span className="min-w-0">{recurringText(item)}</span>
          </p>
          <Button
            variant="subtle"
            size="sm"
            loading={busy('quick')}
            onClick={() => onQuick(item, recurringToggle(item, item.recurring_off))}
          >
            {item.recurring_off ? 'Desfazer' : 'Não é esta'}
          </Button>
        </div>
      ) : null}

      {item.candidates?.length ? (
        <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200">
          {item.candidates.map((candidate) => (
            <CandidateRow
              key={`${candidate.table}:${candidate.id}`}
              candidate={candidate}
              busy={busy(`match:${candidate.id}`)}
              onPick={() => onMatch(item, candidate, remember)}
            />
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" icon={CheckCheck} loading={busy('approve')} onClick={() => onApprove(item, remember)}>
          {item.candidates?.length ? 'Aprovar como novo' : 'Aprovar'}
        </Button>
        <Button variant="secondary" size="sm" icon={Pencil} onClick={() => onEdit(item)}>Editar</Button>
        <Button variant="subtle" size="sm" icon={X} loading={busy('deny')} onClick={() => onDeny(item)}>Recusar</Button>
        <div className="flex-1" />
        {offersRemember(item) ? (
          <label className="flex items-center gap-2 text-sm text-zinc-600">
            <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} className="h-4 w-4 accent-emerald-600" />
            Lembrar a escolha
          </label>
        ) : null}
        {menu.length > 1 ? <Menu items={menu} /> : null}
      </div>
    </Panel>
  )
}

const TYPE_ITEMS = Object.entries(ENTRY_TYPE_LABELS).map(([value, label]) => ({
  value,
  label: value === 'CARD' ? 'Cartão' : label,
}))

// Corrigir antes de virar lancamento: tipo, valor, data e hora, descricao,
// categoria, conta/cartao, parcelas.
function EditSheet({ item, onClose, accounts, cards, categoryOptions, onSave, saving }) {
  const [draft, setDraft] = useState(() => draftFromItem(item))
  const set = (field) => (event) => setDraft({ ...draft, [field]: event.target.value })
  const type = draft.entry_type
  const categoryType = type === 'INCOME' ? 'INCOME' : 'EXPENSE'
  const categories = filterCategoryOptions(categoryOptions, categoryType)
  const itemCategory = draftFromItem(item).category_id
  const changes = changesFromDraft(item, draft)
  const footer = (
    <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
      <Button type="button" variant="secondary" size="lg" onClick={() => onSave(item, changes, false)} loading={saving === 'save'}>
        Salvar e decidir depois
      </Button>
      <Button type="button" size="lg" icon={CheckCheck} onClick={() => onSave(item, changes, true)} loading={saving === 'approve'}>
        Salvar e aprovar
      </Button>
    </div>
  )
  return (
    <Sheet
      open
      onClose={onClose}
      title="Corrigir antes de aprovar"
      description={`Hora original: ${whenText(item.source_occurred_at)}. Ela fica guardada mesmo se você mudar a data.`}
      footer={footer}
    >
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <SegmentedControl
            items={TYPE_ITEMS}
            value={type}
            onChange={(value) => setDraft({ ...draft, entry_type: value })}
          />
        </div>
        <Field label="Valor (R$)" className="col-span-2">
          <input type="text" inputMode="decimal" autoComplete="off" value={draft.amount} onChange={set('amount')} className="app-input text-2xl font-bold" />
        </Field>
        <Field label="Data" className="min-w-0">
          <input type="date" value={draft.date} onChange={set('date')} className="app-input" />
        </Field>
        <Field label="Hora" className="min-w-0" hint={draft.time ? undefined : 'A notificação não disse a hora.'}>
          <input type="time" value={draft.time} onChange={set('time')} className="app-input" />
        </Field>
        <Field label="Descrição" className="col-span-2">
          <input type="text" value={draft.description} onChange={set('description')} className="app-input" />
        </Field>
        {type !== 'TRANSFER' ? (
          <Field label="Categoria" className="col-span-2">
            <select value={draft.category_id} onChange={set('category_id')} className="app-select">
              <option value="">Sugerida pelas regras</option>
              {/* A categoria que o item ja tem, quando nao esta na lista (so o
                  nome, arquivada ou de outro tipo): fica como esta. */}
              {itemCategory && !categories.some((option) => option.id === itemCategory) ? (
                <option value={itemCategory}>{item.category}</option>
              ) : null}
              {categories.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </Field>
        ) : null}
        {type === 'CARD' ? (
          <>
            <Field label="Cartão" className="min-w-0">
              <select value={draft.card_id} onChange={set('card_id')} className="app-select">
                <option value="">Escolha…</option>
                {cards.map((card) => <option key={card.id} value={card.id}>{card.name}</option>)}
              </select>
            </Field>
            <Field label="Parcelas" className="min-w-0">
              <input type="number" inputMode="numeric" min="1" max="72" value={draft.installments} onChange={set('installments')} className="app-input" />
            </Field>
          </>
        ) : null}
        {type === 'EXPENSE' || type === 'INCOME' || type === 'TRANSFER' ? (
          <Field label={type === 'TRANSFER' ? 'De' : 'Conta'} className={type === 'TRANSFER' ? 'min-w-0' : 'col-span-2'}>
            <select value={draft.account_id} onChange={set('account_id')} className="app-select">
              <option value="">Escolha…</option>
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
            </select>
          </Field>
        ) : null}
        {type === 'TRANSFER' ? (
          <Field label="Para" className="min-w-0">
            <select value={draft.transfer_account_id} onChange={set('transfer_account_id')} className="app-select">
              <option value="">Escolha…</option>
              {accounts.filter((account) => account.id !== draft.account_id).map((account) => (
                <option key={account.id} value={account.id}>{account.name}</option>
              ))}
            </select>
          </Field>
        ) : null}
        {type === 'TRANSFER' ? (
          <p className="col-span-2 text-sm text-zinc-500">Entre suas contas: não conta como entrada nem saída.</p>
        ) : null}
      </div>
    </Sheet>
  )
}

function DecidedRow({ item, onRestore, busy }) {
  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-zinc-900">{item.description || entryTypeLabel(item.entry_type)}</p>
        <p className="text-xs text-zinc-500">
          {decisionText(item)} · {whenText(item.occurred_at)} · {formatCurrency(item.amount)}
          {item.target?.date && item.target.date !== item.occurred_at?.slice(0, 10) ? ` · lançado em ${formatDateBR(item.target.date)}` : ''}
        </p>
        {item.recurring ? <p className="text-xs text-zinc-500">{recurringText(item)}</p> : null}
      </div>
      {item.state === 'DENIED' ? (
        <Button variant="secondary" size="sm" icon={RotateCcw} loading={busy} onClick={() => onRestore(item)}>
          Voltar para aprovar
        </Button>
      ) : null}
    </li>
  )
}

// Lancamentos › Aprovar: o que o celular (notificacoes dos bancos) trouxe.
// Nada entra no extrato antes de o dono aprovar; a mesma
// compra contada por mais de uma fonte aparece uma vez so.
export default function Aprovar() {
  const [view, setView] = useState('pending')
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState('')

  const inboxQuery = useInbox(view)
  const hintsQuery = useQuery({ queryKey: ['aprovar', 'lembradas'], queryFn: () => inboxApi.hints() })
  const accountsQuery = useQuery({ queryKey: ['contas', 'ativas'], queryFn: () => accountsApi.list() })
  const cardsQuery = useQuery({ queryKey: ['cartoes'], queryFn: () => creditCardsApi.list() })
  const categoriesQuery = useQuery({ queryKey: ['categorias', 'ativas'], queryFn: () => categoriesApi.list() })

  const items = inboxQuery.data?.items || NO_ITEMS
  const pendingCount = inboxQuery.data?.pending_count ?? 0
  const accounts = useMemo(
    () => (accountsQuery.data || NO_ITEMS).filter((account) => !account.archived_at),
    [accountsQuery.data]
  )
  // So os de credito (041): a compra num cartao so debito vira despesa na conta dele.
  const cards = useMemo(() => creditCards(cardsQuery.data || NO_ITEMS), [cardsQuery.data])
  const categoryOptions = useMemo(() => buildCategoryOptions(categoriesQuery.data || NO_ITEMS), [categoriesQuery.data])
  const hints = hintsQuery.data || NO_ITEMS
  const ready = view === 'pending' ? readyIds(items) : NO_ITEMS

  const run = async (key, action, success) => {
    setBusyKey(key)
    setError('')
    try {
      const result = await action()
      if (success) toast(typeof success === 'function' ? success(result) : success)
      return result
    } catch (actionError) {
      if (actionError.status === 409) {
        setError(CONFLICT_MESSAGE)
        await invalidateServerData()
      } else {
        setError(actionError.message || 'Não foi possível concluir.')
      }
      return null
    } finally {
      setBusyKey('')
    }
  }

  const approve = (item, remember) => run(
    `${item.id}:approve`,
    () => inboxApi.approve(item.id, { version: item.version, remember }),
    'Aprovado: já está no extrato.'
  )
  const match = (item, candidate, remember) => run(
    `${item.id}:match:${candidate.id}`,
    () => inboxApi.approve(item.id, { version: item.version, remember, candidate: { table: candidate.table, id: candidate.id } }),
    'Conferido: ficou um lançamento só.'
  )
  const deny = (item) => run(`${item.id}:deny`, () => inboxApi.deny(item.id, item.version), 'Recusado. Não entra no extrato.')
  const restore = (item) => run(`${item.id}:restore`, () => inboxApi.restore(item.id, item.version), 'De volta para aprovar.')
  // Uma escolha no cartao do item ja troca o item na lista (com a versao nova):
  // "Aprovar" logo em seguida nao espera a releitura nem cai num 409.
  const quick = async (item, body) => {
    const updated = await run(`${item.id}:quick`, () => inboxApi.update(item.id, body))
    if (!updated) return
    queryClient.setQueryData(['aprovar', 'pending'], (data) => (data
      ? { ...data, items: data.items.map((entry) => (entry.id === updated.id ? updated : entry)) }
      : data))
  }
  const split = async (item, source) => {
    if (!(await confirmAction({
      title: 'Não é a mesma?',
      message: `"${sourceLabel(source)}" vira um item separado, para aprovar ou recusar sozinho.`,
      confirmLabel: 'Separar',
      tone: 'neutral',
    }))) return
    await run(
      `${item.id}:split`,
      () => inboxApi.split(item.id, { version: item.version, source: source.source, source_id: source.id }),
      'Separado em dois itens.'
    )
  }
  const approveReady = () => run(
    'ready',
    () => inboxApi.approveReady(ready),
    approveReadySummary
  )
  const forgetHint = async (hint) => {
    if (!(await confirmAction({
      title: 'Esquecer esta escolha?',
      message: `${hintText(hint)}\nO próximo aviso assim volta a perguntar. Nenhum lançamento muda.`,
      confirmLabel: 'Esquecer',
    }))) return
    await run(`hint:${hint.id}`, () => inboxApi.forgetHint(hint.id), 'Escolha esquecida.')
  }

  const saveEdit = async (item, changes, andApprove) => {
    setSaving(andApprove ? 'approve' : 'save')
    const result = await run(
      `${item.id}:edit`,
      () => (andApprove ? inboxApi.approve(item.id, changes) : inboxApi.update(item.id, changes)),
      andApprove ? 'Aprovado com a correção.' : 'Correção salva. O item continua esperando você.'
    )
    setSaving('')
    if (result) setEditing(null)
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <PageHeader
        title="Aprovar"
        description="O que o celular encontrou. Nada entra no extrato até você aprovar, e a mesma compra aparece uma vez só."
        actions={(
          <>
            {ready.length ? (
              <Button size="sm" icon={CheckCheck} loading={busyKey === 'ready'} onClick={approveReady}>
                Aprovar prontos ({ready.length})
              </Button>
            ) : null}
          </>
        )}
      />

      <SegmentedControl
        items={[
          { value: 'pending', label: pendingCount ? `Pendentes (${pendingCount})` : 'Pendentes' },
          { value: 'decided', label: 'Decididos' },
        ]}
        value={view}
        onChange={setView}
      />

      <AlertMessage message={error || queryErrorMessage(inboxQuery, 'Não foi possível ler o que espera aprovação.')} onDismiss={error ? () => setError('') : undefined} />

      {inboxQuery.isPending ? (
        <ListSkeleton rows={3} />
      ) : view === 'pending' ? (
        items.length ? (
          <ul className="space-y-3">
            {items.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                accounts={accounts}
                cards={cards}
                busyKey={busyKey}
                onApprove={approve}
                onDeny={deny}
                onEdit={setEditing}
                onQuick={quick}
                onMatch={match}
                onSplit={split}
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Inbox}
            title="Nada esperando"
            message="Compras e Pix avisados pelo celular aparecem aqui para você aprovar."
          />
        )
      ) : items.length ? (
        <Panel className="overflow-clip">
          <ul className="divide-y divide-zinc-100">
            {items.map((item) => (
              <DecidedRow key={item.id} item={item} onRestore={restore} busy={busyKey === `${item.id}:restore`} />
            ))}
          </ul>
        </Panel>
      ) : (
        <EmptyState icon={Inbox} title="Nada decidido ainda" />
      )}

      {hints.length ? (
        <Collapsible label={`Escolhas lembradas (${hints.length})`} icon={BellRing} variant="secondary" size="sm">
          <Panel className="overflow-clip">
            <ul className="divide-y divide-zinc-100">
              {hints.map((hint) => (
                <li key={hint.id} className="flex items-center justify-between gap-3 px-4 py-2.5">
                  <div className="min-w-0">
                    <p className="text-sm text-zinc-800">{hintText(hint)}</p>
                    <p className="text-xs text-zinc-500">
                      Usada {hint.uses} {hint.uses === 1 ? 'vez' : 'vezes'} · desde {formatDateBR(getLocalDateString(new Date(hint.created_at)))}
                    </p>
                  </div>
                  <IconButton label="Esquecer" icon={X} size="sm" variant="subtle" onClick={() => forgetHint(hint)} />
                </li>
              ))}
            </ul>
          </Panel>
        </Collapsible>
      ) : null}

      {editing ? (
        <EditSheet
          key={`${editing.id}:${editing.version}`}
          item={editing}
          onClose={() => setEditing(null)}
          accounts={accounts}
          cards={cards}
          categoryOptions={categoryOptions}
          onSave={saveEdit}
          saving={saving}
        />
      ) : null}
    </div>
  )
}
