import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Archive,
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Pencil,
  Plus,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { budgetsApi, categoriesApi } from '../lib/dataApi'
import { formatCurrency, monthKey, monthLabel, shiftMonth } from '../lib/format'
import {
  Badge,
  Button,
  EmptyState,
  Field,
  IconButton,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  cx,
} from '../components/ui'

const KIND_LABELS = {
  INCOME: 'Receita',
  EXPENSE: 'Despesa',
  BOTH: 'Ambos',
}

const STATUS_TONES = {
  OK: 'success',
  WARNING: 'warning',
  OVER: 'danger',
}

const STATUS_LABELS = {
  OK: 'No plano',
  WARNING: 'Perto do limite',
  OVER: 'Estourou',
}

const BAR_COLORS = {
  OK: 'bg-emerald-500',
  WARNING: 'bg-amber-500',
  OVER: 'bg-rose-500',
}

const emptyBudgetForm = () => ({ category_id: '', planned_amount: '', rollover: false, note: '' })
const emptyCategoryForm = () => ({ name: '', kind: 'EXPENSE', parent_id: '' })

function ProgressBar({ percent, status }) {
  const width = Math.min(Math.max(Number(percent || 0), 0), 100)
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
      <div className={cx('bar-grow h-full rounded-full transition-all duration-700 ease-out', BAR_COLORS[status] || BAR_COLORS.OK)} style={{ width: `${width}%` }} />
    </div>
  )
}

export default function Orcamento() {
  const [tab, setTab] = useState('BUDGET')
  const [month, setMonth] = useState(() => monthKey())
  const [budget, setBudget] = useState({ month: monthKey(), items: [], totals: {} })
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [budgetForm, setBudgetForm] = useState(emptyBudgetForm)
  const [editingId, setEditingId] = useState('')
  const [editValue, setEditValue] = useState('')
  const [categoryForm, setCategoryForm] = useState(emptyCategoryForm)
  const [editingCategoryId, setEditingCategoryId] = useState('')
  const [categoryEdit, setCategoryEdit] = useState({ name: '', kind: 'EXPENSE' })

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month])

  const loadAll = async () => {
    setLoading(true)
    setError('')
    try {
      const [budgetData, categoryData] = await Promise.all([
        budgetsApi.month(month),
        categoriesApi.list({ include_archived: 1 }),
      ])
      setBudget(budgetData || { month, items: [], totals: {} })
      setCategories(categoryData || [])
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível carregar o orçamento.')
    } finally {
      setLoading(false)
    }
  }

  const activeCategories = useMemo(
    () => categories.filter((category) => !category.archived_at),
    [categories]
  )

  const budgetedIds = useMemo(
    () => new Set((budget.items || []).map((item) => item.category_id)),
    [budget]
  )

  const availableCategories = useMemo(
    () => activeCategories.filter((category) => !budgetedIds.has(category.id)),
    [activeCategories, budgetedIds]
  )

  const rootCategories = useMemo(
    () => activeCategories.filter((category) => !category.parent_id),
    [activeCategories]
  )

  const totals = budget.totals || {}

  const handleCreateBudget = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await budgetsApi.create({
        category_id: budgetForm.category_id,
        month,
        planned_amount: Number(budgetForm.planned_amount || 0),
        rollover: budgetForm.rollover,
        note: budgetForm.note || undefined,
      })
      setBudgetForm(emptyBudgetForm())
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar o orçamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveEdit = async (item) => {
    setSaving(true)
    setError('')
    try {
      await budgetsApi.update(item.id, { planned_amount: Number(editValue || 0) })
      setEditingId('')
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar o orçamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleRollover = async (item) => {
    setSaving(true)
    try {
      await budgetsApi.update(item.id, { rollover: !item.rollover })
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar o orçamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveBudget = async (item) => {
    if (!window.confirm(`Remover o orçamento de "${item.category_name}" em ${monthLabel(month)}?`)) return
    setSaving(true)
    try {
      await budgetsApi.remove(item.id)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível remover o orçamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleCopyPreviousMonth = async () => {
    setSaving(true)
    setError('')
    try {
      const result = await budgetsApi.copy({ to_month: month })
      await loadAll()
      if (result && result.created === 0 && result.skipped === 0) {
        setError(`Nenhum orçamento em ${monthLabel(shiftMonth(month, -1))} para copiar.`)
      }
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível copiar o mês anterior.')
    } finally {
      setSaving(false)
    }
  }

  const handleCreateCategory = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      await categoriesApi.create({
        name: categoryForm.name,
        kind: categoryForm.kind,
        parent_id: categoryForm.parent_id || undefined,
      })
      setCategoryForm(emptyCategoryForm())
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível criar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveCategory = async (category) => {
    setSaving(true)
    setError('')
    try {
      await categoriesApi.update(category.id, { name: categoryEdit.name, kind: categoryEdit.kind })
      setEditingCategoryId('')
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleArchiveCategory = async (category) => {
    if (!window.confirm(`Arquivar "${category.name}"? Os lançamentos continuam, e dá para reativar depois.`)) return
    setSaving(true)
    setError('')
    try {
      await categoriesApi.archive(category.id)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível arquivar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  const handleRestoreCategory = async (category) => {
    setSaving(true)
    setError('')
    try {
      await categoriesApi.update(category.id, { archived_at: null })
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível reativar a categoria.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Planejamento"
        title="Orçamento"
        description="Quanto você planejou gastar em cada categoria neste mês, e quanto já saiu."
        actions={
          <div className="flex items-center gap-2">
            <IconButton label="Mês anterior" icon={ChevronLeft} onClick={() => setMonth(shiftMonth(month, -1))} />
            <span className="min-w-40 text-center text-sm font-semibold capitalize text-zinc-800">
              {monthLabel(month)}
            </span>
            <IconButton label="Próximo mês" icon={ChevronRight} onClick={() => setMonth(shiftMonth(month, 1))} />
          </div>
        }
      />

      {error ? (
        <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      <SegmentedControl
        value={tab}
        onChange={setTab}
        items={[
          { value: 'BUDGET', label: 'Orçamento', icon: Target },
          { value: 'CATEGORIES', label: 'Categorias', icon: Pencil },
        ]}
      />

      {tab === 'BUDGET' ? (
        <div className="space-y-6">
          <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard title="Planejado" value={formatCurrency(totals.planned)} icon={Target} tone="info" />
            <MetricCard
              title="Disponível"
              value={formatCurrency(totals.available)}
              subtitle={totals.carryover ? `Inclui ${formatCurrency(totals.carryover)} do mês anterior` : null}
              tone="neutral"
            />
            <MetricCard title="Realizado" value={formatCurrency(totals.spent)} tone="warning" />
            <MetricCard
              title="Saldo do plano"
              value={formatCurrency(totals.remaining)}
              subtitle={totals.over_count ? `${totals.over_count} categoria(s) estourada(s)` : 'Nenhuma categoria estourada'}
              valueClassName={Number(totals.remaining || 0) < 0 ? 'text-rose-600' : 'text-emerald-600'}
              tone={totals.over_count ? 'danger' : 'success'}
            />
          </div>

          <Panel>
            <PanelHeader
              title="Novo orçamento"
              description="Uma categoria por mês. Subcategoria sem orçamento próprio soma no orçamento do pai."
              actions={
                <Button variant="secondary" icon={Copy} onClick={handleCopyPreviousMonth} loading={saving}>
                  Copiar mês anterior
                </Button>
              }
            />
            <form onSubmit={handleCreateBudget} className="grid gap-4 px-5 py-4 md:grid-cols-4">
              <Field label="Categoria">
                <select
                  value={budgetForm.category_id}
                  onChange={(event) => setBudgetForm({ ...budgetForm, category_id: event.target.value })}
                  className="app-select"
                  required
                >
                  <option value="">Selecione</option>
                  {availableCategories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.parent_name ? `${category.parent_name} › ${category.name}` : category.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Valor planejado">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0,00"
                  value={budgetForm.planned_amount}
                  onChange={(event) => setBudgetForm({ ...budgetForm, planned_amount: event.target.value })}
                  className="app-input"
                  required
                />
              </Field>
              <Field label="Observação" hint="Opcional">
                <input
                  type="text"
                  value={budgetForm.note}
                  onChange={(event) => setBudgetForm({ ...budgetForm, note: event.target.value })}
                  className="app-input"
                />
              </Field>
              <div className="flex flex-col justify-end gap-2">
                <label className="flex items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={budgetForm.rollover}
                    onChange={(event) => setBudgetForm({ ...budgetForm, rollover: event.target.checked })}
                    className="h-4 w-4 rounded border-zinc-300"
                  />
                  Acumular sobra do mês anterior
                </label>
                <Button type="submit" icon={Plus} loading={saving} disabled={!availableCategories.length}>
                  Adicionar
                </Button>
              </div>
            </form>
          </Panel>

          <Panel>
            <PanelHeader
              title="Categorias do mês"
              description={`Plano de ${monthLabel(month)}. O realizado vem das movimentações em conta; compras no cartão só entram no mês em que a fatura é paga, na categoria "Pagamento Fatura".`}
            />
            {loading ? (
              <p className="px-5 py-8 text-center text-sm text-zinc-500">Carregando...</p>
            ) : !budget.items?.length ? (
              <EmptyState
                icon={Target}
                title="Nenhum orçamento neste mês"
                message="Adicione uma categoria acima, ou copie o plano do mês anterior."
              />
            ) : (
              <div className="divide-y divide-zinc-100">
                {budget.items.map((item) => (
                  <div key={item.id} className="px-5 py-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-zinc-900">
                          {item.parent_name ? `${item.parent_name} › ${item.category_name}` : item.category_name}
                        </p>
                        <p className="mt-0.5 text-sm text-zinc-500">
                          {formatCurrency(item.spent)} de {formatCurrency(item.available)}
                          {item.carryover ? ` (inclui ${formatCurrency(item.carryover)} acumulado)` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
                        {editingId === item.id ? (
                          <>
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              value={editValue}
                              onChange={(event) => setEditValue(event.target.value)}
                              className="app-input w-32"
                            />
                            <IconButton label="Salvar" icon={Check} variant="primary" onClick={() => handleSaveEdit(item)} />
                            <IconButton label="Cancelar" icon={X} onClick={() => setEditingId('')} />
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              onClick={() => handleToggleRollover(item)}
                              className={cx(
                                'rounded-full border px-2.5 py-1 text-xs font-semibold transition',
                                item.rollover
                                  ? 'border-sky-200 bg-sky-50 text-sky-700'
                                  : 'border-zinc-200 bg-white text-zinc-500 hover:bg-zinc-50'
                              )}
                              title="Acumular a sobra do mês anterior"
                            >
                              Acumula
                            </button>
                            <IconButton
                              label="Editar valor"
                              icon={Pencil}
                              onClick={() => {
                                setEditingId(item.id)
                                setEditValue(String(item.planned_amount))
                              }}
                            />
                            <IconButton label="Remover" icon={Trash2} variant="danger" onClick={() => handleRemoveBudget(item)} />
                          </>
                        )}
                      </div>
                    </div>
                    <div className="mt-3 flex items-center gap-3">
                      <ProgressBar percent={item.percent} status={item.status} />
                      <span
                        className={cx(
                          'w-28 shrink-0 text-right text-sm font-semibold',
                          item.remaining < 0 ? 'text-rose-600' : 'text-zinc-700'
                        )}
                      >
                        {formatCurrency(item.remaining)}
                      </span>
                    </div>
                    {item.note ? <p className="mt-2 text-xs text-zinc-500">{item.note}</p> : null}
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      ) : (
        <div className="space-y-6">
          <Panel>
            <PanelHeader title="Nova categoria" description="Uma subcategoria precisa de uma categoria pai — só existe um nível." />
            <form onSubmit={handleCreateCategory} className="grid gap-4 px-5 py-4 md:grid-cols-4">
              <Field label="Nome">
                <input
                  type="text"
                  placeholder="Ex: Delivery"
                  value={categoryForm.name}
                  onChange={(event) => setCategoryForm({ ...categoryForm, name: event.target.value })}
                  className="app-input"
                  required
                />
              </Field>
              <Field label="Tipo">
                <select
                  value={categoryForm.kind}
                  onChange={(event) => setCategoryForm({ ...categoryForm, kind: event.target.value })}
                  className="app-select"
                >
                  <option value="EXPENSE">Despesa</option>
                  <option value="INCOME">Receita</option>
                  <option value="BOTH">Ambos</option>
                </select>
              </Field>
              <Field label="Categoria pai" hint="Opcional">
                <select
                  value={categoryForm.parent_id}
                  onChange={(event) => setCategoryForm({ ...categoryForm, parent_id: event.target.value })}
                  className="app-select"
                >
                  <option value="">Nenhuma (categoria raiz)</option>
                  {rootCategories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="flex items-end">
                <Button type="submit" icon={Plus} loading={saving} className="w-full">
                  Criar categoria
                </Button>
              </div>
            </form>
          </Panel>

          <Panel>
            <PanelHeader
              title="Categorias"
              description="Renomear arrasta junto o texto gravado nos lançamentos. Arquivar não apaga histórico."
            />
            {loading ? (
              <p className="px-5 py-8 text-center text-sm text-zinc-500">Carregando...</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="app-table">
                  <thead>
                    <tr>
                      <th>Categoria</th>
                      <th>Tipo</th>
                      <th>Situação</th>
                      <th className="text-right">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    {categories.map((category) => {
                      const isEditing = editingCategoryId === category.id
                      return (
                        <tr key={category.id}>
                          <td>
                            {isEditing ? (
                              <input
                                type="text"
                                value={categoryEdit.name}
                                onChange={(event) => setCategoryEdit({ ...categoryEdit, name: event.target.value })}
                                className="app-input w-48"
                              />
                            ) : (
                              <span className={category.parent_id ? 'text-zinc-600' : 'font-semibold text-zinc-900'}>
                                {category.parent_name ? `${category.parent_name} › ${category.name}` : category.name}
                              </span>
                            )}
                          </td>
                          <td>
                            {isEditing ? (
                              <select
                                value={categoryEdit.kind}
                                onChange={(event) => setCategoryEdit({ ...categoryEdit, kind: event.target.value })}
                                className="app-select w-32"
                              >
                                <option value="EXPENSE">Despesa</option>
                                <option value="INCOME">Receita</option>
                                <option value="BOTH">Ambos</option>
                              </select>
                            ) : (
                              KIND_LABELS[category.kind] || category.kind
                            )}
                          </td>
                          <td>
                            {category.archived_at ? (
                              <Badge tone="neutral">Arquivada</Badge>
                            ) : (
                              <Badge tone="success">Ativa</Badge>
                            )}
                          </td>
                          <td>
                            <div className="flex justify-end gap-2">
                              {isEditing ? (
                                <>
                                  <IconButton
                                    label="Salvar"
                                    icon={Check}
                                    variant="primary"
                                    onClick={() => handleSaveCategory(category)}
                                  />
                                  <IconButton label="Cancelar" icon={X} onClick={() => setEditingCategoryId('')} />
                                </>
                              ) : category.archived_at ? (
                                <Button size="sm" variant="secondary" onClick={() => handleRestoreCategory(category)}>
                                  Reativar
                                </Button>
                              ) : (
                                <>
                                  <IconButton
                                    label="Editar"
                                    icon={Pencil}
                                    onClick={() => {
                                      setEditingCategoryId(category.id)
                                      setCategoryEdit({ name: category.name, kind: category.kind })
                                    }}
                                  />
                                  <IconButton
                                    label="Arquivar"
                                    icon={Archive}
                                    variant="danger"
                                    onClick={() => handleArchiveCategory(category)}
                                  />
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      )}
    </div>
  )
}
