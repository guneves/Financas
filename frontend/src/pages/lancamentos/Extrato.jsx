import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Check, Download, Landmark, Paperclip, Pencil, Plus, Receipt, Search, SlidersHorizontal, Trash2, TrendingUp, Undo2, X } from 'lucide-react'
import { ccExpensesApi, transactionsApi } from '../../lib/dataApi'
import { useDataVersion, useNewEntry } from '../../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  ListSkeleton,
  Field,
  IconButton,
  Menu,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  cx,
  useArrivals,
} from '../../components/ui'
import { formatSignedCurrency } from '../../lib/format'
import { parseMoneyInput } from '../../lib/monthlyPlan'
import { INVESTMENT_CATEGORY, isInvestmentInflow, isInvestmentOutflow } from '../../lib/transactions'
import { shareFormError, shareFormFrom, sharePayload, shareSummary } from '../../lib/sharing'
import ShareFields from '../../components/ShareFields'
import { categoryLabel, getNow } from './helpers'
import AttachmentsSheet from '../../components/AttachmentsSheet'
import ProjectionHeader from './ProjectionHeader'
import useLancamentos from './useLancamentos'
import { confirmAction } from '../../lib/confirm'
import { toast } from '../../lib/toast'
import ExportSheet from '../../components/ExportSheet'
import { keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import useDebouncedValue from '../../lib/useDebouncedValue'
import ExtratoInvestimentos from './ExtratoInvestimentos'
import { useInboxCount } from '../../lib/inboxCount'
import { pendingNoticeText } from '../../lib/inboxRules'
import { APROVAR_PATH } from '../../lib/navigation'

const EMPTY_FILTERS = { q: '', from: '', to: '', type: '', account_id: '', category_id: '', min_amount: '', max_amount: '' }

// Os filtros moram na URL (?q=...&from=...): recarregar a pagina ou voltar
// para ela mantem a busca. So as chaves de EMPTY_FILTERS sao lidas.
function filtersFromParams(params) {
  return Object.fromEntries(Object.keys(EMPTY_FILTERS).map((key) => [key, params.get(key) || '']))
}

function paramsFromFilters(filters, previous) {
  const next = new URLSearchParams(previous)
  Object.keys(EMPTY_FILTERS).forEach((key) => {
    const value = String(filters[key] ?? '')
    if (value.trim() !== '') next.set(key, value)
    else next.delete(key)
  })
  return next
}

function hasActiveFilters(filters) {
  return Object.values(filters).some((value) => String(value).trim() !== '')
}

// Filtros escondidos atras do botao "Filtros" (tudo menos a busca).
function countHiddenFilters(filters) {
  return Object.entries(filters).filter(([key, value]) => key !== 'q' && String(value).trim() !== '').length
}

// So o que nao e receita nem despesa comum ganha etiqueta: o sinal e a cor
// do valor ja dizem entrada ou saida, e um "Despesa" vermelho em quase toda
// linha era alarme sem motivo.
function TypeBadge({ transaction }) {
  if (transaction.type === 'TRANSFER') return <Badge>Transferência</Badge>
  // Aporte sai da conta, mas nao e despesa; o resgate volta, mas nao e receita.
  if (isInvestmentOutflow(transaction)) return <Badge>Investimento</Badge>
  if (isInvestmentInflow(transaction)) return <Badge>Resgate</Badge>
  return null
}

function amountClass(transaction) {
  if (transaction.type === 'TRANSFER') return 'text-zinc-500'
  return transaction.type === 'INCOME' ? 'text-emerald-700' : 'text-zinc-950'
}

function amountText(transaction) {
  const sign = transaction.type === 'TRANSFER' ? 0 : transaction.type === 'INCOME' ? 1 : -1
  return formatSignedCurrency(transaction.amount, sign)
}

// Extrato agrupado por dia (a lista ja vem do mais novo para o mais antigo).
// O total do dia e o que entrou menos o que saiu na lista mostrada;
// transferencia nao entra, como no consolidado.
function groupByDay(transactions) {
  const groups = []
  transactions.forEach((transaction) => {
    const date = transaction.date || ''
    let group = groups[groups.length - 1]
    if (!group || group.date !== date) {
      group = { date, items: [], total: 0 }
      groups.push(group)
    }
    group.items.push(transaction)
    if (transaction.type === 'INCOME') group.total += Number(transaction.amount || 0)
    else if (transaction.type === 'EXPENSE') group.total -= Number(transaction.amount || 0)
  })
  return groups
}

// "Hoje", "Ontem" ou "ter., 22 de set." — o ano so quando nao e o atual.
function dayLabel(date) {
  if (!date) return 'Sem data'
  const [year, month, day] = date.split('-').map(Number)
  const value = new Date(year, month - 1, day)
  const today = getNow()
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const diff = Math.round((startOfToday - value) / 86400000)
  if (diff === 0) return 'Hoje'
  if (diff === 1) return 'Ontem'
  return value.toLocaleDateString('pt-BR', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...(year !== today.getFullYear() ? { year: 'numeric' } : {}),
  })
}

// Lancamentos criados por outra tela (carteira, fatura) so se editam la.
// Um pendente (lib/outbox.js) ainda nao existe no servidor: corrige-se ou
// descarta-se em "Pendentes", nao aqui.
function isEditableHere(transaction) {
  if (transaction.pending) return false
  return !['INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED', 'CC_INVOICE_PAYMENT', 'CC_AUTOPAY'].includes(transaction.source_type)
}

// O pagamento de uma fatura nao se edita aqui, mas se desfaz (037).
const isInvoicePayment = (transaction) => !transaction.pending
  && ['CC_INVOICE_PAYMENT', 'CC_AUTOPAY'].includes(transaction.source_type)

// "De quem é?" (lib/sharing.js) so vale para despesa e receita comuns:
// transferencia e investimento nao se dividem com outra pessoa.
const canShare = (transaction, form) => transaction.type !== 'TRANSFER'
  && form.category !== INVESTMENT_CATEGORY
  && !['INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED'].includes(transaction.source_type)

// "Dividida com Ana · sua parte R$ 40,00", embaixo da descricao.
function ShareMark({ transaction }) {
  const text = shareSummary(transaction)
  if (!text) return null
  return <span className="block truncate text-xs font-medium text-zinc-500" title={text}>{text}</span>
}

// Clipe ao lado da descricao quando ha comprovante; so informa, nao e botao.
function AttachmentMark({ transaction }) {
  const count = Number(transaction.attachment_count || 0)
  if (!count) return null
  const label = count === 1 ? '1 comprovante' : `${count} comprovantes`
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5 text-xs text-zinc-500" title={label}>
      <Paperclip className="h-3.5 w-3.5" aria-hidden="true" />
      {count > 1 ? count : null}
      <span className="sr-only">{label}</span>
    </span>
  )
}

function originLabel(transaction) {
  if (transaction.pending) return transaction.pending_status === 'needs_attention' ? 'Recusado pelo servidor' : 'Pendente de envio'
  if (transaction.source_type === 'INVESTMENT_TRANSACTION') return 'Pela carteira'
  if (transaction.source_type === 'INVESTMENT_PROCEED') return 'Provento'
  if (transaction.source_type === 'CC_AUTOPAY') return 'Débito automático'
  return 'Pela fatura'
}

// Linhas por vez: 800+ lancamentos de uma vez davam uma pagina de 54 mil px.
const PAGE_SIZE = 100

// A coluna Conta so existe a partir de xl. Um <col> com `hidden` nao sai da
// tabela (table-fixed), e o colSpan do dia criava uma coluna fantasma entre
// md e xl: cabecalho curto e total do dia fora da coluna Valor.
const XL_QUERY = '(min-width: 1280px)'

function subscribeXl(onChange) {
  const media = window.matchMedia(XL_QUERY)
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

function useIsXl() {
  return useSyncExternalStore(subscribeXl, () => window.matchMedia(XL_QUERY).matches, () => true)
}

// Qual extrato mostrar: o das contas (lancamentos bancarios) ou o dos
// investimentos (operacoes e proventos). Mora na URL (?ver=investimentos) e a
// ultima escolha fica no aparelho, para abrir onde o dono parou.
const VIEW_KEY = 'financas.extrato.view'
const VIEW_ITEMS = [
  { value: 'contas', label: 'Contas', icon: Landmark },
  { value: 'investimentos', label: 'Investimentos', icon: TrendingUp },
]

function readStoredView() {
  try {
    return window.localStorage.getItem(VIEW_KEY) === 'investimentos' ? 'investimentos' : 'contas'
  } catch {
    return 'contas'
  }
}

export default function Extrato() {
  const [searchParams, setSearchParams] = useSearchParams()
  const fromUrl = searchParams.get('ver')
  const view = fromUrl === 'investimentos' || fromUrl === 'contas' ? fromUrl : readStoredView()

  const chooseView = (next) => {
    try {
      window.localStorage.setItem(VIEW_KEY, next)
    } catch {
      // sem armazenamento: vale so a URL
    }
    // Trocar de extrato limpa os filtros do outro.
    setSearchParams(next === 'contas' ? {} : { ver: next }, { replace: true })
  }

  const viewSwitch = <SegmentedControl items={VIEW_ITEMS} value={view} onChange={chooseView} />
  return view === 'investimentos'
    ? <ExtratoInvestimentos viewSwitch={viewSwitch} />
    : <ExtratoContas viewSwitch={viewSwitch} />
}

function ExtratoContas({ viewSwitch }) {
  const showAccount = useIsXl()
  const { openNewEntry } = useNewEntry()
  const {
    loading,
    dataError,
    setDataError,
    fetchData,
    transactions,
    balance,
    balanceEstimated,
    projectedBalanceGlobal,
    projectedBalanceNextMonth,
    accounts,
    categories,
    categoryOptionsFor,
    accountName,
  } = useLancamentos()

  // O que o celular traz espera o dono em Lancamentos › Aprovar.
  const pendingApproval = useInboxCount()

  const [saving, setSaving] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [attachmentsFor, setAttachmentsFor] = useState(null)
  const [editForm, setEditForm] = useState({ amount: '', date: '', category_id: '', description: '', type: 'EXPENSE', account_id: '', share: shareFormFrom(null) })

  // Filtros do extrato: aplicados no backend (GET /api/transactions?...).
  // Sem filtro, o extrato usa a lista completa ja carregada por useLancamentos.
  // replace: digitar na busca nao empilha uma entrada de historico por letra.
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = useMemo(() => filtersFromParams(searchParams), [searchParams])
  const setFilters = useCallback((next) => {
    setSearchParams((previous) => {
      const value = typeof next === 'function' ? next(filtersFromParams(previous)) : next
      return paramsFromFilters(value, previous)
    }, { replace: true })
  }, [setSearchParams])
  const filtersActive = hasActiveFilters(filters)
  const hiddenFilterCount = countHiddenFilters(filters)
  // Chegando com filtros da URL, o painel ja abre mostrando-os.
  const [showFilters, setShowFilters] = useState(() => hiddenFilterCount > 0)

  const updateFilter = (key, value) => setFilters((prev) => ({ ...prev, [key]: value }))

  // Extrato filtrado: uma query por combinacao de filtros, 250 ms depois da
  // ultima tecla. A chave comeca com 'lancamentos', entao gravar algo tambem a
  // invalida (lib/queries.js).
  const debouncedFilters = useDebouncedValue(filters, 250)
  const filteredQuery = useQuery({
    queryKey: ['lancamentos', 'filtrado', debouncedFilters],
    queryFn: () => transactionsApi.list(debouncedFilters),
    enabled: filtersActive && hasActiveFilters(debouncedFilters),
    placeholderData: keepPreviousData,
  })
  const filtering = filtersActive && (filteredQuery.isFetching || debouncedFilters !== filters)
  const filterError = filtersActive ? queryErrorMessage(filteredQuery, 'Não foi possível aplicar os filtros.') : ''
  const filteredTransactions = filtersActive && filteredQuery.data ? filteredQuery.data : null

  const statementTransactions = filteredTransactions ?? transactions
  // Sem cascata nas linhas: um extrato se le de cima para baixo, e filtrar e
  // digitar. So o que acabou de ser gravado pisca, para ser achado.
  const arrived = useArrivals(statementTransactions, useDataVersion())

  // "Mostrar mais": volta a 100 linhas a cada filtro novo.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  useEffect(() => setVisibleCount(PAGE_SIZE), [filters])
  const visibleTransactions = statementTransactions.slice(0, visibleCount)
  const visibleDays = useMemo(() => groupByDay(visibleTransactions), [visibleTransactions])
  const hiddenCount = statementTransactions.length - visibleTransactions.length

  // Exporta exatamente o que a tela mostra: o backend refaz a mesma consulta
  // com os filtros da URL. Sem filtro, sai o extrato inteiro.
  const handleExport = (options) => transactionsApi.exportFile({ ...filters, ...options })

  // Investimento e liquido: aportes menos resgates. O resgate nao soma na
  // receita, como o aporte nao soma na despesa.
  const statementTotals = useMemo(() => {
    return statementTransactions.reduce((acc, item) => {
      const amount = Number(item.amount || 0)
      if (isInvestmentInflow(item)) acc.investment -= amount
      else if (item.type === 'INCOME') acc.income += amount
      else if (isInvestmentOutflow(item)) acc.investment += amount
      else if (item.type === 'EXPENSE') acc.expense += amount
      return acc
    }, { income: 0, expense: 0, investment: 0 })
  }, [statementTransactions])

  const startEditing = (transaction) => {
    setEditingId(transaction.id)
    setEditForm({
      amount: String(transaction.amount ?? ''),
      date: transaction.date || '',
      category_id: transaction.category_id || '',
      description: transaction.description || '',
      type: transaction.type,
      account_id: transaction.account_id || '',
      share: shareFormFrom(transaction),
    })
  }

  const cancelEditing = () => {
    setEditingId('')
  }

  const handleEditSubmit = async (transaction) => {
    const amount = parseMoneyInput(editForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setDataError('Informe um valor valido.')
      return
    }
    const sharing = canShare(transaction, editForm)
    const shareError = sharing ? shareFormError(editForm.share, amount) : ''
    if (shareError) {
      setDataError(shareError)
      return
    }

    setSaving(true)
    setDataError('')
    try {
      // PATCH e parcial; transferencias so aceitam os campos que fazem sentido
      // para elas (o backend recusa converter um tipo no outro).
      const payload = {
        amount,
        date: editForm.date,
        description: editForm.description,
      }
      // A conta so quando mudou: a de um lancamento antigo pode estar
      // arquivada, e o servidor recusa escolher uma conta arquivada.
      if (editForm.account_id && editForm.account_id !== (transaction.account_id || '')) payload.account_id = editForm.account_id
      if (transaction.type !== 'TRANSFER') {
        payload.type = editForm.type
        // A categoria pelo id, e so quando mudou: mandar o nome de volta tirava
        // um lancamento de "Alimentação › Outros" e o punha no "Outros" da raiz.
        if (editForm.category_id !== (transaction.category_id || '')) payload.category_id = editForm.category_id
      }
      // Sem mudar a divisao, o PATCH nem leva os campos (o servidor so confere
      // que o valor novo ainda cabe nela).
      if (sharing && JSON.stringify(editForm.share) !== JSON.stringify(shareFormFrom(transaction))) {
        Object.assign(payload, sharePayload(editForm.share))
      }
      await transactionsApi.update(transaction.id, payload)
      setEditingId('')
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível atualizar o lançamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteTransaction = async (id) => {
    if (!(await confirmAction({ title: 'Excluir este lançamento?', message: 'O saldo da conta é recalculado.', confirmLabel: 'Excluir' }))) return
    try {
      await transactionsApi.remove(id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a transação.')
    }
  }

  // O lancamento sai, o valor volta ao saldo e os itens da fatura reabrem em
  // Lancamentos > Cartoes; o debito automatico nao a paga de novo sozinho.
  const handleUndoInvoicePayment = async (transaction) => {
    if (!(await confirmAction({
      title: `Desfazer "${transaction.description || transaction.category}"?`,
      message: 'O pagamento sai do extrato, o valor volta para o saldo da conta e a fatura fica em aberto de novo em Cartões. O débito automático não a paga outra vez: pague-a pelo botão Pagar.',
      confirmLabel: 'Desfazer pagamento',
    }))) return
    try {
      await ccExpensesApi.undoPayment(transaction.id)
      await fetchData()
      toast('Pagamento desfeito. A fatura está em aberto em Cartões.')
    } catch (error) {
      setDataError(error.message || 'Não foi possível desfazer o pagamento.')
    }
  }

  const invoicePaymentMenu = (transaction) => (
    isInvoicePayment(transaction) ? (
      <Menu
        label={`Ações de ${transaction.description || transaction.category}`}
        items={[
          { label: 'Desfazer pagamento', icon: Undo2, tone: 'danger', onSelect: () => handleUndoInvoicePayment(transaction) },
        ]}
      />
    ) : null
  )

  const setEditField = (key) => (event) => setEditForm({ ...editForm, [key]: event.target.value })

  const accountLabel = (transaction) => (
    transaction.type === 'TRANSFER'
      ? `${accountName(transaction.account_id)} → ${accountName(transaction.transfer_account_id)}`
      : accountName(transaction.account_id)
  )

  // Campos de edicao reaproveitados pela tabela (inline) e pela lista do celular (empilhados).
  const editControls = (transaction) => {
    const isTransfer = transaction.type === 'TRANSFER'
    return {
      date: <input type="date" value={editForm.date} onChange={setEditField('date')} className="app-input" />,
      account: (
        <select value={editForm.account_id} onChange={setEditField('account_id')} className="app-select">
          {/* A conta que o lancamento ja tem, quando ela foi arquivada: fica como esta. */}
          {transaction.account_id && !accounts.some((account) => account.id === transaction.account_id) ? (
            <option value={transaction.account_id}>{accountName(transaction.account_id)} (arquivada)</option>
          ) : null}
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      ),
      category: isTransfer ? (
        <span className="text-zinc-500">{transaction.category}</span>
      ) : (
        <select value={editForm.category_id} onChange={setEditField('category_id')} className="app-select">
          {/* A categoria que o lancamento ja tem, quando ela nao esta na lista
              (arquivada, de outro tipo ou texto livre): fica como esta. */}
          {!categoryOptionsFor(editForm.type).some((category) => category.id === (transaction.category_id || '')) ? (
            <option value={transaction.category_id || ''}>{transaction.category || 'Sem categoria'}</option>
          ) : null}
          {categoryOptionsFor(editForm.type).map((category) => (
            <option key={category.id} value={category.id}>{category.label}</option>
          ))}
        </select>
      ),
      description: <input type="text" value={editForm.description} onChange={setEditField('description')} className="app-input" />,
      type: isTransfer ? (
        <Badge>Transferência</Badge>
      ) : (
        <select value={editForm.type} onChange={setEditField('type')} className="app-select">
          <option value="EXPENSE">Despesa</option>
          <option value="INCOME">Receita</option>
        </select>
      ),
      amount: <input type="text" inputMode="decimal" autoComplete="off" value={editForm.amount} onChange={setEditField('amount')} className="app-input" />,
      share: canShare(transaction, editForm) ? (
        <ShareFields form={editForm.share} type={editForm.type} onChange={(share) => setEditForm({ ...editForm, share })} />
      ) : null,
      actions: (
        <>
          <IconButton label="Salvar alterações" icon={Check} disabled={saving} onClick={() => handleEditSubmit(transaction)} />
          <IconButton label="Cancelar edição" icon={X} onClick={cancelEditing} />
        </>
      ),
    }
  }

  // Comprovante vale para qualquer linha — inclusive as geradas por outra
  // tela (nota de corretagem, recibo da fatura): anexar nao mexe no lancamento.
  const attachmentsButton = (transaction) => (
    transaction.pending ? null : <IconButton label="Comprovantes" icon={Paperclip} size="sm" onClick={() => setAttachmentsFor(transaction)} />
  )

  // Lancamento gerado por outra tela: sem editar aqui, so diz de onde veio.
  const rowActions = (transaction) => (
    !isEditableHere(transaction) ? (
      <>
        <span className="min-w-0 truncate self-center text-xs text-zinc-500" title={originLabel(transaction)}>{originLabel(transaction)}</span>
        {attachmentsButton(transaction)}
        {invoicePaymentMenu(transaction)}
      </>
    ) : (
      <div className="flex min-w-0 justify-end gap-1.5 transition-opacity duration-150 lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100">
        {attachmentsButton(transaction)}
        <Menu
          label={`Ações de ${transaction.description || transaction.category || 'lançamento'}`}
          items={[
            { label: 'Editar lançamento', icon: Pencil, onSelect: () => startEditing(transaction) },
            { label: 'Excluir lançamento', icon: Trash2, tone: 'danger', onSelect: () => handleDeleteTransaction(transaction.id) },
          ]}
        />
      </div>
    )
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title="Extrato"
        description="Entradas, saídas e transferências das suas contas."
        actions={(
          <>
            <Button
              type="button"
              variant="secondary"
              icon={Download}
              disabled={statementTransactions.length === 0}
              onClick={() => setExportOpen(true)}
            >
              Exportar
            </Button>
          </>
        )}
      />

      {viewSwitch}

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />
      {pendingApproval ? (
        <AlertMessage tone="info">
          {pendingNoticeText(pendingApproval)}{' '}
          <Link to={APROVAR_PATH} className="font-semibold underline">Aprovar</Link>
        </AlertMessage>
      ) : null}

      <ProjectionHeader
        balance={balance}
        estimated={balanceEstimated}
        projectedBalanceNextMonth={projectedBalanceNextMonth}
        projectedBalanceGlobal={projectedBalanceGlobal}
      />

      <Panel className="overflow-clip">
        <PanelHeader
          title="Extrato da conta"
          description={filtersActive ? 'Movimentações que atendem aos filtros.' : 'Últimas movimentações registradas.'}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {filtersActive ? (
                <>
                  <Badge tone="success">{formatSignedCurrency(statementTotals.income, 1)}</Badge>
                  <Badge>{formatSignedCurrency(statementTotals.expense, -1)}</Badge>
                  {Math.abs(statementTotals.investment) >= 0.005 ? (
                    <Badge>
                      {statementTotals.investment > 0 ? 'Investido' : 'Resgatado'} {formatSignedCurrency(statementTotals.investment, 0)}
                    </Badge>
                  ) : null}
                </>
              ) : null}
              <Badge>{filtering ? 'Filtrando…' : `${statementTransactions.length} registro(s)`}</Badge>
            </div>
          }
        />

        <div className="space-y-3 border-b border-zinc-100 px-5 py-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
              <input
                type="search"
                aria-label="Buscar no extrato"
                placeholder="Buscar por descrição ou categoria"
                value={filters.q}
                onChange={(event) => updateFilter('q', event.target.value)}
                className="app-input h-11 pl-9"
              />
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                variant={showFilters ? 'subtle' : 'secondary'}
                size="lg"
                icon={SlidersHorizontal}
                onClick={() => setShowFilters((open) => !open)}
                aria-expanded={showFilters}
                className="flex-1 sm:flex-none"
              >
                Filtros
                {hiddenFilterCount > 0 ? (
                  <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-emerald-600 px-1.5 text-xs font-bold text-white">
                    {hiddenFilterCount}
                  </span>
                ) : null}
              </Button>
              {filtersActive ? (
                <Button type="button" variant="secondary" size="lg" icon={X} onClick={() => setFilters(EMPTY_FILTERS)} className="flex-1 sm:flex-none">
                  Limpar filtros
                </Button>
              ) : null}
            </div>
          </div>

          {showFilters ? (
            <div className="grid animate-slide-down grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="De">
                <input type="date" value={filters.from} onChange={(event) => updateFilter('from', event.target.value)} className="app-input" />
              </Field>
              <Field label="Até">
                <input type="date" value={filters.to} onChange={(event) => updateFilter('to', event.target.value)} className="app-input" />
              </Field>
              <Field label="Tipo">
                <select value={filters.type} onChange={(event) => updateFilter('type', event.target.value)} className="app-select">
                  <option value="">Todos</option>
                  <option value="INCOME">Entradas</option>
                  <option value="EXPENSE">Saídas</option>
                  <option value="TRANSFER">Transferências</option>
                </select>
              </Field>
              <Field label="Conta">
                <select value={filters.account_id} onChange={(event) => updateFilter('account_id', event.target.value)} className="app-select">
                  <option value="">Todas</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>{account.name}</option>
                  ))}
                </select>
              </Field>
              <Field label="Categoria">
                <select value={filters.category_id} onChange={(event) => updateFilter('category_id', event.target.value)} className="app-select">
                  <option value="">Todas</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{categoryLabel(category)}</option>
                  ))}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Valor mín.">
                  <input type="number" inputMode="decimal" min="0" step="0.01" value={filters.min_amount} onChange={(event) => updateFilter('min_amount', event.target.value)} className="app-input" />
                </Field>
                <Field label="Valor máx.">
                  <input type="number" inputMode="decimal" min="0" step="0.01" value={filters.max_amount} onChange={(event) => updateFilter('max_amount', event.target.value)} className="app-input" />
                </Field>
              </div>
            </div>
          ) : null}

          {filterError ? <p className="text-sm text-rose-600">{filterError}</p> : null}
        </div>

        {loading || (filtersActive && !filteredTransactions && filtering) ? (
          <ListSkeleton rows={8} />
        ) : statementTransactions.length > 0 ? (
          <>
            {/* >= md: tabela com edicao inline. Largura fixa por coluna e texto
                cortado com reticencias: a linha fica em uma altura so, e sem
                overflow-x o cabecalho gruda no topo da pagina. */}
            <div className="hidden md:block">
              <table className="app-table table-fixed">
                <colgroup>
                  {showAccount ? <col className="w-[18%]" /> : null}
                  <col className="w-[18%]" />
                  <col />
                  <col className="w-40" />
                  <col className="w-44 lg:w-36" />
                </colgroup>
                <thead>
                  <tr>
                    {showAccount ? <th>Conta</th> : null}
                    <th>Categoria</th>
                    <th>Descrição</th>
                    <th className="text-right">Valor</th>
                    <th className="text-right"><span className="sr-only">Ações</span></th>
                  </tr>
                </thead>
                {visibleDays.map((group) => (
                  <tbody key={group.date}>
                    <tr className="hover:bg-transparent">
                      <th colSpan={showAccount ? 5 : 4} scope="colgroup" className="bg-zinc-50/70 !py-2">
                        <div className="flex items-baseline justify-between gap-4">
                          <span className="text-sm font-bold text-zinc-700 first-letter:uppercase">{dayLabel(group.date)}</span>
                          <span className="flex items-baseline">
                            <span className="whitespace-nowrap text-sm font-semibold text-zinc-500 tabular">{formatSignedCurrency(group.total)}</span>
                            {/* Largura da coluna de acoes: o total cai embaixo da coluna Valor. */}
                            <span className="w-44 shrink-0 lg:w-36" aria-hidden="true" />
                          </span>
                        </div>
                      </th>
                    </tr>
                    {group.items.map((transaction) => {
                      if (editingId === transaction.id) {
                        const controls = editControls(transaction)
                        return [
                          <tr key={transaction.id} className="bg-zinc-50">
                            {showAccount ? <td>{controls.account}</td> : null}
                            <td className="space-y-2">{controls.category}{controls.type}</td>
                            <td className="space-y-2">{controls.date}{controls.description}</td>
                            <td>{controls.amount}</td>
                            <td className="text-right">
                              <div className="flex justify-end gap-2">{controls.actions}</div>
                            </td>
                          </tr>,
                          controls.share ? (
                            <tr key={`${transaction.id}-share`} className="bg-zinc-50 hover:bg-zinc-50">
                              <td colSpan={showAccount ? 5 : 4} className="!pt-0">{controls.share}</td>
                            </tr>
                          ) : null,
                        ]
                      }

                      const account = accountLabel(transaction)
                      return (
                        <tr key={transaction.id} className={cx('group', arrived.has(transaction.id) && 'animate-flash-emerald')}>
                          {showAccount ? <td className="truncate text-zinc-600" title={account}>{account}</td> : null}
                          <td className="truncate font-medium text-zinc-800" title={transaction.category}>{transaction.category}</td>
                          <td>
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="truncate text-zinc-700" title={transaction.description}>{transaction.description}</span>
                              <span className="shrink-0"><TypeBadge transaction={transaction} /></span>
                              <AttachmentMark transaction={transaction} />
                            </div>
                            <ShareMark transaction={transaction} />
                          </td>
                          <td className={cx('num font-semibold', amountClass(transaction))}>{amountText(transaction)}</td>
                          <td className="py-1.5 text-right">
                            <div className="flex min-w-0 justify-end gap-1.5">{rowActions(transaction)}</div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                ))}
              </table>
            </div>

            {/* < md: lista de cartoes; editar abre os mesmos campos empilhados */}
            <div className="md:hidden">
              {visibleDays.map((group) => (
                <section key={group.date} aria-label={dayLabel(group.date)}>
                  <h3 className="flex items-baseline justify-between gap-3 bg-zinc-50/70 px-4 py-2 text-sm">
                    <span className="font-bold text-zinc-700 first-letter:uppercase">{dayLabel(group.date)}</span>
                    <span className="whitespace-nowrap font-semibold text-zinc-500 tabular">{formatSignedCurrency(group.total)}</span>
                  </h3>
                  <ul className="divide-y divide-zinc-100">
              {group.items.map((transaction) => {
                if (editingId === transaction.id) {
                  const controls = editControls(transaction)
                  return (
                    <li key={transaction.id} className="space-y-3 bg-zinc-50 px-4 py-4">
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Data">{controls.date}</Field>
                        <Field label="Valor">{controls.amount}</Field>
                      </div>
                      <Field label="Descrição">{controls.description}</Field>
                      <Field label="Categoria">{controls.category}</Field>
                      <div className="grid grid-cols-2 gap-3">
                        <Field label="Tipo">{controls.type}</Field>
                        <Field label="Conta">{controls.account}</Field>
                      </div>
                      {controls.share}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex gap-2">
                          <Button type="button" variant="danger" size="lg" icon={Trash2} onClick={() => handleDeleteTransaction(transaction.id)}>
                            Excluir
                          </Button>
                          <IconButton label="Comprovantes" icon={Paperclip} onClick={() => setAttachmentsFor(transaction)} />
                        </div>
                        <div className="flex gap-2">{controls.actions}</div>
                      </div>
                    </li>
                  )
                }

                const editable = isEditableHere(transaction)
                const content = (
                  <>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-zinc-900">{transaction.description || transaction.category}</p>
                      <p className="mt-0.5 flex min-w-0 items-center gap-1.5 text-xs text-zinc-500">
                        <span className="truncate">
                          {transaction.type === 'TRANSFER' ? accountLabel(transaction) : transaction.category}
                          {editable ? '' : ` · ${originLabel(transaction)}`}
                        </span>
                        <AttachmentMark transaction={transaction} />
                      </p>
                      {transaction.share_mode ? <p className="flex min-w-0"><ShareMark transaction={transaction} /></p> : null}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-0.5">
                      <p className={cx('whitespace-nowrap font-semibold', amountClass(transaction))}>{amountText(transaction)}</p>
                      <TypeBadge transaction={transaction} />
                    </div>
                  </>
                )
                return (
                  <li key={transaction.id} className={cx(arrived.has(transaction.id) && 'animate-flash-emerald')}>
                    {editable ? (
                      <button
                        type="button"
                        onClick={() => startEditing(transaction)}
                        aria-label={`Editar ${transaction.description || transaction.category}`}
                        className="flex min-h-[56px] w-full items-center gap-3 px-4 py-2.5 text-left transition-colors active:bg-zinc-50"
                      >
                        {content}
                      </button>
                    ) : (
                      // Gerado por outra tela: nao edita aqui, mas o toque abre
                      // os comprovantes; o de fatura tem o "⋯" do desfazer.
                      <div className="flex items-center">
                        <button
                          type="button"
                          onClick={() => setAttachmentsFor(transaction)}
                          aria-label={`Comprovantes de ${transaction.description || transaction.category}`}
                          className="flex min-h-[56px] min-w-0 flex-1 items-center gap-3 px-4 py-2.5 text-left transition-colors active:bg-zinc-50"
                        >
                          {content}
                        </button>
                        {isInvoicePayment(transaction) ? <div className="shrink-0 pr-2">{invoicePaymentMenu(transaction)}</div> : null}
                      </div>
                    )}
                  </li>
                )
              })}
                  </ul>
                </section>
              ))}
            </div>

            {hiddenCount > 0 ? (
              <div className="flex flex-col items-center gap-2 border-t border-zinc-100 px-5 py-4 sm:flex-row sm:justify-between">
                <p className="text-sm text-zinc-500">
                  Mostrando {visibleTransactions.length} de {statementTransactions.length}
                </p>
                <Button type="button" variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>
                  Mostrar mais {Math.min(PAGE_SIZE, hiddenCount)}
                </Button>
              </div>
            ) : null}
          </>
        ) : (
          <div className="p-5">
            <EmptyState
              icon={Receipt}
              title="Nenhuma movimentação"
              message={filtersActive ? 'Nenhum lançamento atende aos filtros.' : 'Os lançamentos bancários aparecerão no extrato.'}
              action={filtersActive ? null : <Button type="button" icon={Plus} onClick={() => openNewEntry()}>Novo lançamento</Button>}
            />
          </div>
        )}
      </Panel>

      <AttachmentsSheet
        transaction={attachmentsFor}
        onClose={() => setAttachmentsFor(null)}
        onChanged={fetchData}
      />
      <ExportSheet
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        exportName="transactions"
        title="Exportar extrato"
        description="Com os filtros aplicados na tela; sem filtro, o extrato inteiro."
        onExport={handleExport}
      />
    </div>
  )
}
