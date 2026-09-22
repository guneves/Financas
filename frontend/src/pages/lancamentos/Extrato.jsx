import { useEffect, useMemo, useState } from 'react'
import { Check, Pencil, Plus, Receipt, Search, SlidersHorizontal, Trash2, X } from 'lucide-react'
import { transactionsApi } from '../../lib/dataApi'
import { useNewEntry } from '../../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  PageHeader,
  Panel,
  PanelHeader,
  cx,
} from '../../components/ui'
import { formatCurrency } from '../../lib/format'
import { categoryLabel, formatDateBR } from './helpers'
import ProjectionHeader from './ProjectionHeader'
import useLancamentos from './useLancamentos'

const EMPTY_FILTERS = { q: '', from: '', to: '', type: '', account_id: '', category_id: '', min_amount: '', max_amount: '' }

function hasActiveFilters(filters) {
  return Object.values(filters).some((value) => String(value).trim() !== '')
}

// Filtros escondidos atras do botao "Filtros" (tudo menos a busca).
function countHiddenFilters(filters) {
  return Object.entries(filters).filter(([key, value]) => key !== 'q' && String(value).trim() !== '').length
}

function TypeBadge({ type }) {
  if (type === 'TRANSFER') return <Badge tone="info">Transferência</Badge>
  if (type === 'INCOME') return <Badge tone="success">Receita</Badge>
  if (type === 'EXPENSE') return <Badge tone="danger">Despesa</Badge>
  return null
}

function amountClass(transaction) {
  if (transaction.type === 'TRANSFER') return 'text-zinc-500'
  return transaction.type === 'INCOME' ? 'text-emerald-700' : 'text-zinc-950'
}

function amountText(transaction) {
  const prefix = transaction.type === 'TRANSFER' ? '' : transaction.type === 'INCOME' ? '+ ' : '- '
  return `${prefix}${formatCurrency(transaction.amount)}`
}

export default function Extrato() {
  const { openNewEntry } = useNewEntry()
  const {
    dataError,
    setDataError,
    reloadCount,
    fetchData,
    transactions,
    balance,
    projectedBalanceGlobal,
    projectedBalanceNextMonth,
    accounts,
    categories,
    categoryOptionsFor,
    accountName,
  } = useLancamentos()

  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editForm, setEditForm] = useState({ amount: '', date: '', category: '', description: '', type: 'EXPENSE', account_id: '' })
  const [showFilters, setShowFilters] = useState(false)

  // Filtros do extrato: aplicados no backend (GET /api/transactions?...).
  // Sem filtro, o extrato usa a lista completa ja carregada por useLancamentos.
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [filteredTransactions, setFilteredTransactions] = useState(null)
  const [filterError, setFilterError] = useState('')
  const [filtering, setFiltering] = useState(false)
  const filtersActive = hasActiveFilters(filters)
  const hiddenFilterCount = countHiddenFilters(filters)

  const updateFilter = (key, value) => setFilters((prev) => ({ ...prev, [key]: value }))

  useEffect(() => {
    if (!filtersActive) {
      setFilteredTransactions(null)
      setFilterError('')
      setFiltering(false)
      return undefined
    }

    let cancelled = false
    setFiltering(true)
    const timer = setTimeout(async () => {
      try {
        const rows = await transactionsApi.list(filters)
        if (!cancelled) {
          setFilteredTransactions(rows || [])
          setFilterError('')
        }
      } catch (error) {
        if (!cancelled) setFilterError(error.message || 'Não foi possível aplicar os filtros.')
      } finally {
        if (!cancelled) setFiltering(false)
      }
    }, 250)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [filters, filtersActive, reloadCount])

  const statementTransactions = filteredTransactions ?? transactions

  const statementTotals = useMemo(() => {
    return statementTransactions.reduce((acc, item) => {
      const amount = Number(item.amount || 0)
      if (item.type === 'INCOME') acc.income += amount
      if (item.type === 'EXPENSE') acc.expense += amount
      return acc
    }, { income: 0, expense: 0 })
  }, [statementTransactions])

  const startEditing = (transaction) => {
    setEditingId(transaction.id)
    setEditForm({
      amount: String(transaction.amount ?? ''),
      date: transaction.date || '',
      category: transaction.category || '',
      description: transaction.description || '',
      type: transaction.type,
      account_id: transaction.account_id || '',
    })
  }

  const cancelEditing = () => {
    setEditingId('')
  }

  const handleEditSubmit = async (transaction) => {
    const amount = Number(editForm.amount)
    if (!Number.isFinite(amount) || amount <= 0) {
      setDataError('Informe um valor valido.')
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
        account_id: editForm.account_id,
      }
      if (transaction.type !== 'TRANSFER') {
        payload.category = editForm.category
        payload.type = editForm.type
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
    if (!window.confirm('Deseja realmente excluir esta transação? O saldo será recalculado.')) return
    try {
      await transactionsApi.remove(id)
      await fetchData()
    } catch (error) {
      setDataError(error.message || 'Não foi possível excluir a transação.')
    }
  }

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
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>{account.name}</option>
          ))}
        </select>
      ),
      category: isTransfer ? (
        <span className="text-zinc-500">{transaction.category}</span>
      ) : (
        <select value={editForm.category} onChange={setEditField('category')} className="app-select">
          {categoryOptionsFor(editForm.type).map((category) => (
            <option key={category.id} value={category.name}>{category.label}</option>
          ))}
        </select>
      ),
      description: <input type="text" value={editForm.description} onChange={setEditField('description')} className="app-input" />,
      type: isTransfer ? (
        <Badge tone="info">Transferência</Badge>
      ) : (
        <select value={editForm.type} onChange={setEditField('type')} className="app-select">
          <option value="EXPENSE">Despesa</option>
          <option value="INCOME">Receita</option>
        </select>
      ),
      amount: <input type="number" step="0.01" value={editForm.amount} onChange={setEditField('amount')} className="app-input" />,
      actions: (
        <>
          <IconButton label="Salvar alterações" icon={Check} disabled={saving} onClick={() => handleEditSubmit(transaction)} />
          <IconButton label="Cancelar edição" icon={X} onClick={cancelEditing} />
        </>
      ),
    }
  }

  const rowActions = (transaction) => (
    transaction.source_type === 'INVESTMENT_TRANSACTION' ? (
      <Badge>Investimento</Badge>
    ) : transaction.source_type === 'CC_INVOICE_PAYMENT' || transaction.source_type === 'CC_AUTOPAY' ? (
      <Badge>{transaction.source_type === 'CC_AUTOPAY' ? 'Débito automático' : 'Pela fatura'}</Badge>
    ) : (
      <>
        <IconButton label="Editar transação" icon={Pencil} onClick={() => startEditing(transaction)} />
        <IconButton label="Excluir transação" icon={Trash2} variant="danger" onClick={() => handleDeleteTransaction(transaction.id)} />
      </>
    )
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operação"
        title="Extrato"
        description="Entradas, saídas e transferências das suas contas."
        actions={<Button type="button" icon={Plus} onClick={() => openNewEntry()}>Novo</Button>}
      />

      <AlertMessage tone="warning" message={dataError} onDismiss={() => setDataError('')} />

      <ProjectionHeader
        balance={balance}
        projectedBalanceNextMonth={projectedBalanceNextMonth}
        projectedBalanceGlobal={projectedBalanceGlobal}
      />

      <Panel>
        <PanelHeader
          title="Extrato da conta"
          description={filtersActive ? 'Movimentações que atendem aos filtros.' : 'Últimas movimentações registradas.'}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              {filtersActive ? (
                <>
                  <Badge tone="success">+ {formatCurrency(statementTotals.income)}</Badge>
                  <Badge tone="danger">- {formatCurrency(statementTotals.expense)}</Badge>
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
                  <input type="number" min="0" step="0.01" value={filters.min_amount} onChange={(event) => updateFilter('min_amount', event.target.value)} className="app-input" />
                </Field>
                <Field label="Valor máx.">
                  <input type="number" min="0" step="0.01" value={filters.max_amount} onChange={(event) => updateFilter('max_amount', event.target.value)} className="app-input" />
                </Field>
              </div>
            </div>
          ) : null}

          {filterError ? <p className="text-sm text-rose-600">{filterError}</p> : null}
        </div>

        {statementTransactions.length > 0 ? (
          <>
            {/* >= md: tabela com edicao inline */}
            <div className="hidden overflow-x-auto md:block">
              <table className="app-table min-w-[900px]">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Conta</th>
                    <th>Categoria</th>
                    <th>Descrição</th>
                    <th>Tipo</th>
                    <th>Valor</th>
                    <th className="text-right">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {statementTransactions.map((transaction) => {
                    if (editingId === transaction.id) {
                      const controls = editControls(transaction)
                      return (
                        <tr key={transaction.id} className="bg-zinc-50">
                          <td>{controls.date}</td>
                          <td>{controls.account}</td>
                          <td>{controls.category}</td>
                          <td>{controls.description}</td>
                          <td>{controls.type}</td>
                          <td>{controls.amount}</td>
                          <td className="text-right">
                            <div className="flex justify-end gap-2">{controls.actions}</div>
                          </td>
                        </tr>
                      )
                    }

                    return (
                      <tr key={transaction.id}>
                        <td className="text-zinc-600">{formatDateBR(transaction.date)}</td>
                        <td className="text-zinc-700">{accountLabel(transaction)}</td>
                        <td className="font-medium text-zinc-800">{transaction.category}</td>
                        <td className="text-zinc-700">{transaction.description}</td>
                        <td><TypeBadge type={transaction.type} /></td>
                        <td className={cx('font-bold', amountClass(transaction))}>{amountText(transaction)}</td>
                        <td className="text-right">
                          <div className="flex justify-end gap-2">{rowActions(transaction)}</div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* < md: lista de cartoes; editar abre os mesmos campos empilhados */}
            <ul className="divide-y divide-zinc-100 md:hidden">
              {statementTransactions.map((transaction) => {
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
                      <div className="flex justify-end gap-2">{controls.actions}</div>
                    </li>
                  )
                }

                return (
                  <li key={transaction.id} className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-zinc-900">{transaction.description || transaction.category}</p>
                        <p className="mt-0.5 truncate text-sm text-zinc-600">
                          {formatDateBR(transaction.date)} · {transaction.type === 'TRANSFER' ? accountLabel(transaction) : transaction.category}
                        </p>
                      </div>
                      <p className={cx('shrink-0 whitespace-nowrap font-bold', amountClass(transaction))}>{amountText(transaction)}</p>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <TypeBadge type={transaction.type} />
                      <div className="flex gap-2">{rowActions(transaction)}</div>
                    </div>
                  </li>
                )
              })}
            </ul>
          </>
        ) : (
          <div className="p-5">
            <EmptyState icon={Receipt} title="Nenhuma movimentação" message={filtersActive ? 'Nenhum lançamento atende aos filtros.' : 'Os lançamentos bancários aparecerão no extrato.'} />
          </div>
        )}
      </Panel>
    </div>
  )
}
