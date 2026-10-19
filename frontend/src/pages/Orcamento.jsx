import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  ChevronDown,
  Pencil,
  PiggyBank,
  Plus,
  Settings,
  SlidersHorizontal,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { budgetsApi, categoriesApi, monthlyPlanApi } from '../lib/dataApi'
import { formatCurrency, monthKey, monthLabel, shiftMonth } from '../lib/format'
import { categoryAmountPreview, formatPlanPercent, moneyInputValue, parseMoneyInput } from '../lib/monthlyPlan'
import { usePrivateFormatter } from '../lib/privacy'
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
  Skeleton,
  SummaryPanel,
  cx,
} from '../components/ui'
import {
  BUDGET_STATUS_LABELS as STATUS_LABELS,
  BUDGET_STATUS_TONES as STATUS_TONES,
  BudgetProgressBar as ProgressBar,
} from '../components/BudgetProgress'
import { confirmAction } from '../lib/confirm'
import MonthlyPlanPanel, { MonthlyPlanSheet } from '../components/MonthlyPlanPanel'
import BudgetLines from '../components/BudgetLines'

const emptyBudgetForm = () => ({ category_id: '', planned_percent: '', rollover: false, note: '' })

// "12,5" -> 12.5; vazio ou invalido -> NaN (o servidor tambem recusa).
const parsePercent = (value) => parseMoneyInput(value) ?? Number.NaN

const NO_ITEMS = []
const NO_CATEGORIES = []

// O R$ de um % digitado, ao lado do campo: "= R$ 350,00".
function AmountPreview({ spendAmount, value, className = '' }) {
  const amount = categoryAmountPreview(spendAmount, parseMoneyInput(value))
  return (
    <span className={cx('tabular whitespace-nowrap text-sm font-semibold text-zinc-700', className)} aria-live="polite">
      = {amount === null ? 'R$ —' : formatCurrency(amount)}
    </span>
  )
}

export default function Orcamento() {
  const [month, setMonth] = useState(() => monthKey())
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)

  const [budgetForm, setBudgetForm] = useState(emptyBudgetForm)
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editValue, setEditValue] = useState('')
  const [openLines, setOpenLines] = useState(() => new Set())

  // Modo privado: o Saldo do plano e o Disponivel por dia somem (lib/privacy.js).
  const privateMoney = usePrivateFormatter(formatCurrency)

  const toggleLines = (id) => setOpenLines((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  // O plano do mes inteiro numa leitura (services/monthly_plan.py): renda,
  // Investir, Gastar, Saldo do plano, Disponivel por dia e as categorias. A
  // mesma chave do Inicio, entao o cache e um so. Categorias arquivadas
  // inclusive: um orcamento antigo pode apontar para uma.
  const planQuery = useQuery({
    queryKey: ['plano-do-mes', month],
    queryFn: () => monthlyPlanApi.month(month),
    placeholderData: keepPreviousData,
  })
  const categoriesQuery = useQuery({
    queryKey: ['categorias', 'todas'],
    queryFn: () => categoriesApi.list({ include_archived: 1 }),
  })
  useReportQueryError(planQuery, setError, 'Não foi possível carregar o plano do mês.')
  useReportQueryError(categoriesQuery, setError, 'Não foi possível carregar as categorias.')
  const data = planQuery.data
  const plan = data?.plan || null
  const hasFigures = Boolean(plan && !plan.needs_income)
  const categoryBlock = data?.categories
  const items = categoryBlock?.items || NO_ITEMS
  const categoryTotals = categoryBlock?.totals || {}
  const spendAmount = data?.spend?.amount ?? null
  const categories = categoriesQuery.data || NO_CATEGORIES
  const loading = planQuery.isPending

  const loadAll = () => invalidateServerData()

  const activeCategories = useMemo(
    () => categories.filter((category) => !category.archived_at),
    [categories]
  )

  const budgetedIds = useMemo(() => new Set(items.map((item) => item.category_id)), [items])

  const availableCategories = useMemo(
    () => activeCategories.filter((category) => !budgetedIds.has(category.id)),
    [activeCategories, budgetedIds]
  )

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

  const balance = data?.plan_balance
  const daily = data?.daily_available
  const unassigned = categoryBlock?.unassigned || {}

  return (
    <div className="space-y-6">
      <PageHeader
        title="Orçamento"
        description="Da renda do mês, quanto investir e quanto gastar, e o limite de cada categoria."
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

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 rounded-[1.75rem]" />
          <Skeleton className="h-64 rounded-[1.75rem]" />
        </div>
      ) : !plan ? (
        <Panel>
          <EmptyState
            icon={PiggyBank}
            title="Comece pelo plano do mês"
            message="Informe a renda do mês e quanto dela vai investir e gastar. Depois, divida o Gastar entre as categorias."
            action={<Button icon={SlidersHorizontal} onClick={() => setSheetOpen(true)}>Definir plano</Button>}
            className="m-5"
          />
        </Panel>
      ) : plan.needs_income ? (
        <Panel>
          <EmptyState
            icon={PiggyBank}
            title="O plano precisa da renda"
            message="Informe a renda para converter o plano em porcentagens."
            action={<Button icon={SlidersHorizontal} onClick={() => setSheetOpen(true)}>Informar renda</Button>}
            className="m-5"
          />
        </Panel>
      ) : (
        <>
          {/* Saldo do plano: Gastar R$ - gasto do mes, o numero principal da tela. */}
          <SummaryPanel
            lead={{
              label: 'Saldo do plano',
              value: balance === null || balance === undefined ? '—' : privateMoney(balance),
              hint: 'Do que você planejou gastar, quanto ainda pode',
              tone: Number(balance || 0) < 0 ? 'loss' : 'neutral',
            }}
            figures={[
              {
                label: 'Disponível por dia',
                value: daily === null || daily === undefined ? '—' : privateMoney(daily),
                hint: data.period === 'PAST' ? 'Mês encerrado' : 'Até o fim do mês',
                tone: Number(daily || 0) < 0 ? 'loss' : 'neutral',
              },
            ]}
          />

          <MonthlyPlanPanel data={data} onEdit={() => setSheetOpen(true)} />
        </>
      )}

      {hasFigures ? (
        <Panel>
          <PanelHeader
            title="Categorias do mês"
            description={`Cada categoria leva um % do Gastar (${formatCurrency(spendAmount)}). O realizado soma os lançamentos em conta, sem transferências, e as compras no cartão, inteiras, no mês da compra; o pagamento da fatura não conta de novo.`}
          />

          <div className="flex flex-col gap-3 border-b border-zinc-100 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
            <Collapsible
              label="Adicionar categoria ao mês"
              icon={Plus}
              open={formOpen}
              onOpenChange={setFormOpen}
              className="min-w-0 flex-1"
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
                  <div className="flex items-center gap-3">
                    <input
                      type="text" inputMode="decimal" autoComplete="off"
                      placeholder="0"
                      value={budgetForm.planned_percent}
                      onChange={(event) => setBudgetForm({ ...budgetForm, planned_percent: event.target.value })}
                      className="app-input min-w-0 flex-1"
                      required
                    />
                    <AmountPreview spendAmount={spendAmount} value={budgetForm.planned_percent} />
                  </div>
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
                  <Button type="submit" icon={Check} loading={saving} disabled={!availableCategories.length}>
                    Salvar
                  </Button>
                </div>
                <p className="text-sm text-zinc-600 sm:col-span-2 xl:col-span-4">
                  {availableCategories.length
                    ? 'Juntas, as categorias levam no máximo 100% do Gastar. Subcategoria sem orçamento próprio soma no orçamento do pai.'
                    : 'Todas as categorias ativas já têm orçamento neste mês.'}
                </p>
              </form>
            </Collapsible>
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" icon={Copy} onClick={handleCopyPreviousMonth} loading={saving}>
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

          {!items.length ? (
            <EmptyState
              icon={Target}
              title="Nenhuma categoria neste mês"
              message="Adicione uma categoria ao mês, ou copie as do mês anterior."
              className="m-5"
            />
          ) : (
            <div className="divide-y divide-zinc-100">
              {items.map((item) => (
                <div key={item.id} className="px-5 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-zinc-900">
                        {item.parent_name ? `${item.parent_name} › ${item.category_name}` : item.category_name}
                      </p>
                      <p className="tabular mt-0.5 text-sm text-zinc-600">
                        {item.needs_income
                          ? `${item.planned_percent === null ? `antes ${formatCurrency(item.legacy_amount)}` : `${formatPlanPercent(item.planned_percent)} do Gastar`} · falta a renda do plano`
                          : <>{formatPlanPercent(item.planned_percent)} · <span className="font-semibold text-zinc-900">{formatCurrency(item.planned_amount)}</span></>}
                      </p>
                    </div>
                    <Badge tone={STATUS_TONES[item.status]} className="shrink-0">{STATUS_LABELS[item.status]}</Badge>
                  </div>

                  {editingId === item.id ? (
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <input
                        type="text" inputMode="decimal" autoComplete="off"
                        value={editValue}
                        onChange={(event) => setEditValue(event.target.value)}
                        aria-label="% do Gastar"
                        className="app-input w-28"
                        autoFocus
                      />
                      <AmountPreview spendAmount={spendAmount} value={editValue} />
                      <div className="ml-auto flex items-center gap-2">
                        <IconButton label="Salvar" icon={Check} variant="primary" onClick={() => handleSaveEdit(item)} />
                        <IconButton label="Cancelar" icon={X} onClick={() => setEditingId('')} />
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-3 flex items-center gap-3">
                    <ProgressBar percent={item.percent} status={item.status} />
                    <span
                      className={cx(
                        'tabular w-28 shrink-0 text-right text-sm font-semibold',
                        item.remaining < 0 ? 'text-rose-600' : 'text-zinc-700'
                      )}
                    >
                      {item.remaining === null ? '—' : formatCurrency(item.remaining)}
                    </span>
                  </div>
                  <p className="tabular mt-1.5 text-sm text-zinc-600">
                    {formatCurrency(item.spent)} gastos
                    {item.available !== null ? ` de ${formatCurrency(item.available)}` : ''}
                    {item.carryover ? ` (inclui ${formatCurrency(item.carryover)} acumulado)` : ''}
                  </p>
                  {item.note ? <p className="mt-1 text-sm text-zinc-600">{item.note}</p> : null}

                  <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => toggleLines(item.id)}
                      aria-expanded={openLines.has(item.id)}
                      aria-controls={`linhas-${item.id}`}
                      className="-ml-2 inline-flex h-11 items-center gap-1 rounded-full px-2 text-sm font-semibold text-zinc-700 hover:bg-zinc-100 hover:text-zinc-950 lg:h-8"
                    >
                      <ChevronDown
                        className={cx('h-4 w-4 transition-transform', openLines.has(item.id) && 'rotate-180')}
                      />
                      {openLines.has(item.id) ? 'Ocultar lançamentos' : 'Ver lançamentos'}
                    </button>
                    {editingId === item.id ? null : (
                      <div className="flex items-center gap-2">
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
                      </div>
                    )}
                  </div>
                  <Expand open={openLines.has(item.id)} id={`linhas-${item.id}`}>
                    <BudgetLines budgetId={item.id} month={month} categoryName={item.category_name} kind={item.category_kind} />
                  </Expand>
                </div>
              ))}
            </div>
          )}

          {/* Sem categoria: o Gastar que nenhuma categoria leva (100% - categorias). */}
          <div className="flex items-baseline justify-between gap-3 border-t border-zinc-100 bg-zinc-50/60 px-5 py-4">
            <div className="min-w-0">
              <p className="font-semibold text-zinc-900">Sem categoria</p>
              <p className="mt-0.5 text-sm text-zinc-600">O resto do Gastar, para o que não tem categoria no mês</p>
            </div>
            <p className={cx('tabular whitespace-nowrap text-right text-sm', Number(unassigned.percent) < 0 ? 'font-semibold text-rose-600' : 'text-zinc-600')}>
              {formatPlanPercent(unassigned.percent)} ·{' '}
              <span className={cx('font-semibold', Number(unassigned.amount) < 0 ? 'text-rose-600' : 'text-zinc-900')}>
                {formatCurrency(unassigned.amount)}
              </span>
            </p>
          </div>
          {categoryTotals.over_count ? (
            <p className="border-t border-zinc-100 px-5 py-3 text-sm font-semibold text-rose-600">
              {categoryTotals.over_count === 1 ? '1 categoria estourou' : `${categoryTotals.over_count} categorias estouraram`} neste mês.
            </p>
          ) : null}
        </Panel>
      ) : null}

      <MonthlyPlanSheet open={sheetOpen} onClose={() => setSheetOpen(false)} month={month} plan={plan} />
    </div>
  )
}
