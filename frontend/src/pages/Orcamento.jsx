import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  ChevronDown,
  Pencil,
  Plus,
  Settings,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { budgetsApi, categoriesApi } from '../lib/dataApi'
import { formatCurrency, monthKey, monthLabel, shiftMonth } from '../lib/format'
import { moneyInputValue, parseMoneyInput } from '../lib/monthlyPlan'
import { invalidateServerData, keepPreviousData, useQuery, useReportQueryError } from '../lib/queries'
import {
  AlertMessage,
  Badge,
  Button,
  Collapsible,
  EmptyState,
  Expand,
  ListSkeleton,
  Field,
  IconButton,
  Menu,
  PageHeader,
  Panel,
  PanelHeader,
  SummaryPanel,
  cx,
} from '../components/ui'
import {
  BUDGET_STATUS_LABELS as STATUS_LABELS,
  BUDGET_STATUS_TONES as STATUS_TONES,
  BudgetProgressBar as ProgressBar,
} from '../components/BudgetProgress'
import { confirmAction } from '../lib/confirm'
import MonthlyPlanPanel from '../components/MonthlyPlanPanel'
import BudgetLines from '../components/BudgetLines'

const emptyBudgetForm = () => ({ category_id: '', planned_percent: '', rollover: false, note: '' })

// "12,5" -> 12.5; vazio ou invalido -> NaN (o servidor tambem recusa).
const parsePercent = (value) => parseMoneyInput(value) ?? Number.NaN
const formatPercent = (value) => `${Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`

const EMPTY_BUDGET = { items: [], totals: {} }
const NO_CATEGORIES = []

export default function Orcamento() {
  const [month, setMonth] = useState(() => monthKey())
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const [budgetForm, setBudgetForm] = useState(emptyBudgetForm)
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editValue, setEditValue] = useState('')
  const [openLines, setOpenLines] = useState(() => new Set())

  const toggleLines = (id) => setOpenLines((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  // Orcamento do mes e categorias (arquivadas inclusive: um orcamento antigo
  // pode apontar para uma). Qualquer gravacao invalida o cache (lib/queries.js).
  const budgetQuery = useQuery({
    queryKey: ['orcamento', month],
    queryFn: () => budgetsApi.month(month),
    placeholderData: keepPreviousData,
  })
  const categoriesQuery = useQuery({
    queryKey: ['categorias', 'todas'],
    queryFn: () => categoriesApi.list({ include_archived: 1 }),
  })
  useReportQueryError(budgetQuery, setError, 'Não foi possível carregar o orçamento.')
  useReportQueryError(categoriesQuery, setError, 'Não foi possível carregar as categorias.')
  const budget = budgetQuery.data || EMPTY_BUDGET
  const categories = categoriesQuery.data || NO_CATEGORIES
  const loading = budgetQuery.isPending || categoriesQuery.isPending

  const loadAll = () => invalidateServerData()

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
        planned_percent: parsePercent(budgetForm.planned_percent),
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
      await budgetsApi.update(item.id, { planned_percent: parsePercent(editValue) }, month)
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
      await budgetsApi.update(item.id, { rollover: !item.rollover }, month)
      await loadAll()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível atualizar o orçamento.')
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveBudget = async (item) => {
    if (!(await confirmAction({ title: `Remover o orçamento de "${item.category_name}"?`, message: `Só o plano de ${monthLabel(month)} sai; nenhum lançamento muda.`, confirmLabel: 'Remover' }))) return
    setSaving(true)
    try {
      await budgetsApi.remove(item.id, month)
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
        title="Orçamento"
        description="Quanto você vai gastar e investir no mês, e o limite de cada categoria."
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

      <MonthlyPlanPanel month={month} />

      {/* Saldo do plano: Gastar do plano - gasto do mes (o mesmo numero do plano). */}
      <SummaryPanel
        lead={{
          label: 'Saldo do plano',
          value: totals.plan_balance === null || totals.plan_balance === undefined ? '—' : formatCurrency(totals.plan_balance),
          hint: totals.plan_balance === null || totals.plan_balance === undefined
            ? 'Informe a renda no plano do mês'
            : totals.over_count ? `${totals.over_count} categoria(s) estourada(s)` : 'Nenhuma categoria estourada',
          tone: Number(totals.plan_balance || 0) < 0 ? 'loss' : 'neutral',
        }}
        figures={[
          {
            label: 'Planejado',
            value: formatCurrency(totals.planned),
            hint: `${formatPercent(totals.assigned_percent)} do Gastar · sem categoria ${formatPercent(totals.unassigned_percent)}`,
          },
          {
            label: 'Disponível',
            value: formatCurrency(totals.available),
            hint: totals.carryover ? `Inclui ${formatCurrency(totals.carryover)} acumulado` : 'Planejado + sobras',
          },
          { label: 'Realizado', value: formatCurrency(totals.spent), hint: 'Saídas e compras no cartão no mês' },
        ]}
      />

      <Panel>
        <PanelHeader
          title="Categorias do mês"
          description={`Plano de ${monthLabel(month)}. O realizado soma os lançamentos em conta, sem transferências, e as compras no cartão, inteiras, no mês da compra; o pagamento da fatura não conta de novo.`}
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
            <form onSubmit={handleCreateBudget} className="grid grid-cols-1 gap-4 rounded-2xl border border-zinc-200 bg-zinc-50 p-4 sm:grid-cols-2 xl:grid-cols-4">
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
              <Field label="% do Gastar">
                <input
                  type="text" inputMode="decimal" autoComplete="off"
                  placeholder="0"
                  value={budgetForm.planned_percent}
                  onChange={(event) => setBudgetForm({ ...budgetForm, planned_percent: event.target.value })}
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
                  ? 'Cada categoria leva um % do Gastar do plano; juntas, no máximo 100%. Subcategoria sem orçamento próprio soma no orçamento do pai.'
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
              className="inline-flex h-11 items-center gap-2 rounded-full px-3 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950 lg:h-10"
            >
              <Settings className="h-4 w-4" />
              Gerenciar categorias
            </Link>
          </div>
        </div>

        {loading ? (
          <ListSkeleton rows={5} />
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
                      {item.needs_income
                        ? `${formatCurrency(item.spent)} gastos · ${item.planned_percent === null ? `antes ${formatCurrency(item.legacy_amount)}` : `${formatPercent(item.planned_percent)} do Gastar`} · falta a renda do plano`
                        : `${formatCurrency(item.spent)} de ${formatCurrency(item.available)} · ${formatPercent(item.planned_percent)} do Gastar`}
                      {item.carryover ? ` (inclui ${formatCurrency(item.carryover)} acumulado)` : ''}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={STATUS_TONES[item.status]}>{STATUS_LABELS[item.status]}</Badge>
                    {editingId === item.id ? (
                      <>
                        <input
                          type="text" inputMode="decimal" autoComplete="off"
                          value={editValue}
                          onChange={(event) => setEditValue(event.target.value)}
                          aria-label="% do Gastar"
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
                              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                              : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                          )}
                          title="Acumular a sobra do mês anterior"
                        >
                          Acumula
                        </button>
                        <Menu
                          label={`Ações do orçamento de ${item.category_name}`}
                          size="md"
                          items={[
                            {
                              label: 'Editar % do Gastar',
                              icon: Pencil,
                              onSelect: () => {
                                setEditingId(item.id)
                                setEditValue(moneyInputValue(item.planned_percent))
                              },
                            },
                            { label: 'Remover do mês', icon: Trash2, tone: 'danger', onSelect: () => handleRemoveBudget(item) },
                          ]}
                        />
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
                    {item.remaining === null ? '—' : formatCurrency(item.remaining)}
                  </span>
                </div>
                {item.note ? <p className="mt-2 text-sm text-zinc-600">{item.note}</p> : null}
                <button
                  type="button"
                  onClick={() => toggleLines(item.id)}
                  aria-expanded={openLines.has(item.id)}
                  aria-controls={`linhas-${item.id}`}
                  className="mt-2 -ml-2 inline-flex h-11 items-center gap-1 rounded-full px-2 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950 lg:h-8"
                >
                  <ChevronDown
                    className={cx('h-4 w-4 transition-transform', openLines.has(item.id) && 'rotate-180')}
                  />
                  {openLines.has(item.id) ? 'Ocultar lançamentos' : 'Ver lançamentos'}
                </button>
                <Expand open={openLines.has(item.id)} id={`linhas-${item.id}`}>
                  <BudgetLines budgetId={item.id} month={month} categoryName={item.category_name} kind={item.category_kind} />
                </Expand>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
