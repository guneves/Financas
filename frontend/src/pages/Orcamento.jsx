import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Pencil,
  Plus,
  Settings,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { budgetsApi, categoriesApi } from '../lib/dataApi'
import { formatCurrency, monthKey, monthLabel, shiftMonth } from '../lib/format'
import { useDataVersion } from '../lib/newEntry'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Field,
  IconButton,
  MetricCard,
  PageHeader,
  Panel,
  PanelHeader,
  cx,
} from '../components/ui'

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

function ProgressBar({ percent, status }) {
  const width = Math.min(Math.max(Number(percent || 0), 0), 100)
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
      <div className={cx('bar-grow h-full rounded-full transition-[width] duration-500 ease-out-quint', BAR_COLORS[status] || BAR_COLORS.OK)} style={{ width: `${width}%` }} />
    </div>
  )
}

export default function Orcamento() {
  const [month, setMonth] = useState(() => monthKey())
  const [budget, setBudget] = useState({ month: monthKey(), items: [], totals: {} })
  const [categories, setCategories] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [budgetForm, setBudgetForm] = useState(emptyBudgetForm)
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editValue, setEditValue] = useState('')

  // Sobe quando o "+ Novo" do Layout salva um lançamento: o realizado do mês muda.
  const dataVersion = useDataVersion()

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [month, dataVersion])

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

  const totals = budget.totals || {}

  // O formulario fica aberto depois de salvar: montar o mes costuma ser
  // varias categorias seguidas, e a nova linha aparece logo abaixo.
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

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Planejamento"
        title="Orçamento"
        description="Quanto você planejou gastar em cada categoria neste mês, e quanto já saiu."
        actions={
          <div className="flex items-center gap-1">
            <IconButton label="Mês anterior" icon={ChevronLeft} onClick={() => setMonth(shiftMonth(month, -1))} />
            <span className="inline-block min-w-40 text-center text-sm font-semibold text-zinc-800 first-letter:uppercase">
              {monthLabel(month)}
            </span>
            <IconButton label="Próximo mês" icon={ChevronRight} onClick={() => setMonth(shiftMonth(month, 1))} />
          </div>
        }
      />

      <AlertMessage message={error} onDismiss={() => setError('')} />

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
          title="Categorias do mês"
          description={`Plano de ${monthLabel(month)}. O realizado vem das movimentações em conta; compras no cartão só entram no mês em que a fatura é paga, na categoria "Pagamento Fatura".`}
        />

        <div className="flex flex-col gap-3 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
          <Collapsible
            label="Adicionar categoria ao mês"
            icon={Plus}
            open={formOpen}
            onOpenChange={setFormOpen}
            className="min-w-0 flex-1"
            buttonClassName="h-11 lg:h-10"
          >
            <form onSubmit={handleCreateBudget} className="grid grid-cols-1 gap-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-4">
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
                <label className="flex min-h-11 items-center gap-2 text-sm text-zinc-700 lg:min-h-0">
                  <input
                    type="checkbox"
                    checked={budgetForm.rollover}
                    onChange={(event) => setBudgetForm({ ...budgetForm, rollover: event.target.checked })}
                    className="h-4 w-4 rounded border-zinc-300"
                  />
                  Acumular sobra do mês anterior
                </label>
                <Button type="submit" icon={Check} loading={saving} disabled={!availableCategories.length} className="h-11 lg:h-10">
                  Salvar
                </Button>
              </div>
              <p className="text-sm text-zinc-600 sm:col-span-2 xl:col-span-4">
                {availableCategories.length
                  ? 'Uma categoria por mês. Subcategoria sem orçamento próprio soma no orçamento do pai.'
                  : 'Todas as categorias ativas já têm orçamento neste mês.'}
              </p>
            </form>
          </Collapsible>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" icon={Copy} onClick={handleCopyPreviousMonth} loading={saving} className="h-11 lg:h-10">
              Copiar mês anterior
            </Button>
            <Link
              to="/ajustes#categorias"
              className="inline-flex h-11 items-center gap-2 rounded-lg px-2 text-sm font-semibold text-emerald-700 hover:text-emerald-800 lg:h-10"
            >
              <Settings className="h-4 w-4" />
              Gerenciar categorias
            </Link>
          </div>
        </div>

        {loading ? (
          <p className="px-5 py-8 text-center text-sm text-zinc-600">Carregando...</p>
        ) : !budget.items?.length ? (
          <EmptyState
            icon={Target}
            title="Nenhum orçamento neste mês"
            message="Adicione uma categoria ao mês, ou copie o plano do mês anterior."
            className="m-5"
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
                    <p className="mt-0.5 text-sm text-zinc-600">
                      {formatCurrency(item.spent)} de {formatCurrency(item.available)}
                      {item.carryover ? ` (inclui ${formatCurrency(item.carryover)} acumulado)` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
                    {editingId === item.id ? (
                      <>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={editValue}
                          onChange={(event) => setEditValue(event.target.value)}
                          aria-label="Valor planejado"
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
                          aria-pressed={Boolean(item.rollover)}
                          className={cx(
                            'inline-flex h-11 items-center rounded-full border px-3 text-xs font-semibold transition lg:h-8',
                            item.rollover
                              ? 'border-sky-200 bg-sky-50 text-sky-700'
                              : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
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
                {item.note ? <p className="mt-2 text-sm text-zinc-600">{item.note}</p> : null}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
