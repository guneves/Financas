import { useState } from 'react'
import { Flag, Pencil, Plus, Trash2 } from 'lucide-react'
import { goalsApi } from '../lib/dataApi'
import { formatCurrency, formatPercent, monthLabel } from '../lib/format'
import { usePrivateFormatter } from '../lib/privacy'
import { invalidateServerData, queryErrorMessage, useQuery } from '../lib/queries'
import { confirmAction } from '../lib/confirm'
import { toast } from '../lib/toast'
import {
  AlertMessage,
  Badge,
  Button,
  EmptyState,
  Field,
  ListSkeleton,
  Menu,
  PageHeader,
  Panel,
  SegmentedControl,
  Sheet,
} from '../components/ui'
import { BudgetProgressBar } from '../components/BudgetProgress'
import { getClassLabel } from './investimentos/helpers'

const KINDS = [
  { value: 'NET_WORTH', label: 'Patrimônio' },
  { value: 'PORTFOLIO', label: 'Carteira' },
  { value: 'ASSET_CLASS', label: 'Classe' },
  { value: 'MONTHLY_INCOME', label: 'Renda' },
]

const KIND_HINTS = {
  NET_WORTH: 'Carteira de investimentos + saldo das contas.',
  PORTFOLIO: 'Valor líquido da carteira de investimentos.',
  ASSET_CLASS: 'Valor líquido de uma classe de ativo.',
  MONTHLY_INCOME: 'Média mensal dos proventos líquidos recebidos nos últimos 12 meses.',
}

const CLASSES = ['STOCKS', 'REIT', 'FIXED_INCOME', 'OTHER']

const emptyForm = () => ({
  name: '',
  kind: 'NET_WORTH',
  asset_class: 'STOCKS',
  target_amount: '',
  monthly_contribution: '',
  annual_return_percent: '',
  target_date: '',
})

function formFromGoal(goal) {
  return {
    name: goal.name,
    kind: goal.kind,
    asset_class: goal.asset_class || 'STOCKS',
    target_amount: String(goal.target_amount),
    monthly_contribution: goal.monthly_contribution ? String(goal.monthly_contribution) : '',
    annual_return_percent: goal.annual_return_percent !== null ? String(goal.annual_return_percent) : '',
    target_date: goal.target_date || '',
  }
}

function payloadFromForm(form) {
  const number = (value) => (value === '' ? null : Number(String(value).replace(',', '.')))
  return {
    name: form.name,
    kind: form.kind,
    asset_class: form.kind === 'ASSET_CLASS' ? form.asset_class : null,
    target_amount: number(form.target_amount),
    monthly_contribution: number(form.monthly_contribution) ?? 0,
    annual_return_percent: number(form.annual_return_percent),
    target_date: form.target_date || null,
  }
}

function GoalSheet({ open, goal, onClose }) {
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [openedFor, setOpenedFor] = useState(null)

  // Cada abertura parte da meta editada (ou de um formulario limpo).
  const key = open ? (goal?.id || 'new') : null
  if (key !== openedFor) {
    setOpenedFor(key)
    if (key) {
      setForm(goal ? formFromGoal(goal) : emptyForm())
      setError('')
    }
  }

  const set = (field) => (event) => setForm({ ...form, [field]: event.target.value })
  const isIncome = form.kind === 'MONTHLY_INCOME'

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = payloadFromForm(form)
      if (goal) await goalsApi.update(goal.id, payload)
      else await goalsApi.create(payload)
      await invalidateServerData()
      toast(goal ? 'Meta atualizada.' : 'Meta criada.')
      onClose()
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível salvar a meta.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={goal ? 'Editar meta' : 'Nova meta'}
      description={KIND_HINTS[form.kind]}
      footer={(
        <div className="flex justify-end">
          <Button type="submit" form="goal-form" icon={Flag} loading={saving}>{goal ? 'Salvar' : 'Criar meta'}</Button>
        </div>
      )}
    >
      <form id="goal-form" onSubmit={handleSubmit} className="space-y-4">
        <AlertMessage message={error} onDismiss={() => setError('')} />
        <SegmentedControl items={KINDS} value={form.kind} onChange={(kind) => setForm({ ...form, kind })} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nome" className="sm:col-span-2">
            <input type="text" required maxLength={120} placeholder="Ex.: Primeiros 100 mil" value={form.name} onChange={set('name')} className="app-input" />
          </Field>
          {form.kind === 'ASSET_CLASS' ? (
            <Field label="Classe de ativo" className="sm:col-span-2">
              <select value={form.asset_class} onChange={set('asset_class')} className="app-select">
                {CLASSES.map((item) => <option key={item} value={item}>{getClassLabel(item)}</option>)}
              </select>
            </Field>
          ) : null}
          <Field label={isIncome ? 'Renda mensal desejada' : 'Valor da meta'}>
            <input type="number" inputMode="decimal" required min="0.01" step="0.01" placeholder="0,00" value={form.target_amount} onChange={set('target_amount')} className="app-input" />
          </Field>
          {!isIncome ? (
            <Field label="Aporte mensal" hint="Quanto você pretende pôr por mês.">
              <input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0,00" value={form.monthly_contribution} onChange={set('monthly_contribution')} className="app-input" />
            </Field>
          ) : null}
          {!isIncome ? (
            <Field label="Rentabilidade esperada ao ano (%)" hint="Opcional. Sem ela, a previsão conta só os aportes.">
              <input type="number" inputMode="decimal" min="-99" max="100" step="0.01" placeholder="Ex.: 8" value={form.annual_return_percent} onChange={set('annual_return_percent')} className="app-input" />
            </Field>
          ) : null}
          {!isIncome ? (
            <Field label="Quero chegar até" hint="Opcional. Mostra o aporte mensal necessário.">
              <input type="date" value={form.target_date} onChange={set('target_date')} className="app-input" />
            </Field>
          ) : null}
        </div>
      </form>
    </Sheet>
  )
}

function Figure({ label, value, hint }) {
  return (
    <div className="min-w-0 rounded-2xl bg-zinc-50 px-3 py-2.5">
      <p className="text-xs font-medium text-zinc-500">{label}</p>
      <p className="num mt-0.5 whitespace-normal break-words text-left font-semibold text-zinc-900">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-zinc-500">{hint}</p> : null}
    </div>
  )
}

// 'AAAA-MM' -> 'out/2028': cabe no quadro mesmo no celular.
function shortMonthYear(key) {
  const [year, month] = String(key).split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
  return `${name}/${year}`
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`
}

function forecastText(goal) {
  if (goal.reached) return 'Alcançada'
  if (goal.kind === 'MONTHLY_INCOME') return '—'
  if (!goal.estimated_month) return 'Sem previsão'
  return shortMonthYear(goal.estimated_month)
}

function forecastHint(goal) {
  if (goal.reached || goal.kind === 'MONTHLY_INCOME') return ''
  if (!goal.estimated_month) return 'Informe um aporte mensal'
  const years = Math.floor(goal.estimated_months / 12)
  const months = goal.estimated_months % 12
  const parts = [years ? plural(years, 'ano', 'anos') : '', months ? plural(months, 'mês', 'meses') : ''].filter(Boolean)
  return parts.length ? `em ${parts.join(' e ')}` : ''
}

// Metas (GET /api/goals): o plano fica gravado; atual, progresso e previsao
// sao calculados no servidor a cada leitura.
export default function Metas() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [sheet, setSheet] = useState({ open: false, goal: null })
  const [error, setError] = useState('')

  const query = useQuery({ queryKey: ['metas'], queryFn: goalsApi.list })
  const goals = query.data || []

  const handleRemove = async (goal) => {
    if (!(await confirmAction({ title: `Remover a meta "${goal.name}"?`, message: 'Só o plano sai; nenhum lançamento muda.', confirmLabel: 'Remover' }))) return
    try {
      await goalsApi.remove(goal.id)
      toast('Meta removida.')
    } catch (requestError) {
      setError(requestError.message || 'Não foi possível remover a meta.')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Metas"
        description="Onde você quer chegar, quanto falta e quando chega no ritmo atual."
        actions={<Button type="button" icon={Plus} onClick={() => setSheet({ open: true, goal: null })}>Nova meta</Button>}
      />

      <AlertMessage message={error || queryErrorMessage(query, 'Não foi possível carregar as metas.')} onDismiss={error ? () => setError('') : undefined} />

      {query.isPending ? (
        <Panel><ListSkeleton rows={3} /></Panel>
      ) : !goals.length ? (
        <Panel className="p-5">
          <EmptyState
            icon={Flag}
            title="Nenhuma meta ainda"
            message="Patrimônio, carteira, uma classe de ativo ou renda mensal de proventos: diga o alvo e o aporte, e a previsão aparece aqui."
            action={<Button type="button" icon={Plus} onClick={() => setSheet({ open: true, goal: null })}>Nova meta</Button>}
            className="min-h-48"
          />
        </Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {goals.map((goal) => (
            <Panel key={goal.id} className="p-5 sm:p-6">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-[17px] font-bold tracking-tight text-zinc-950">{goal.name}</p>
                  <p className="mt-0.5 text-sm text-zinc-500">
                    {goal.kind_label}{goal.asset_class ? ` · ${getClassLabel(goal.asset_class)}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {goal.reached ? <Badge tone="success">Alcançada</Badge> : null}
                  {!goal.reached && goal.on_track === false ? <Badge tone="warning">Fora do prazo</Badge> : null}
                  {!goal.reached && goal.on_track === true ? <Badge>No prazo</Badge> : null}
                  <Menu
                    label={`Ações da meta ${goal.name}`}
                    items={[
                      { label: 'Editar', icon: Pencil, onSelect: () => setSheet({ open: true, goal }) },
                      { label: 'Remover', icon: Trash2, tone: 'danger', onSelect: () => handleRemove(goal) },
                    ]}
                  />
                </div>
              </div>

              <div className="mt-4 flex items-center gap-3">
                <BudgetProgressBar percent={goal.percent} status="OK" />
                <span className="num w-16 shrink-0 text-right text-sm font-semibold text-zinc-700">{formatPercent(Math.min(goal.percent, 999), 1)}</span>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Figure label="Atual" value={privateMoney(goal.current)} />
                <Figure label="Faltam" value={privateMoney(goal.remaining)} />
                <Figure label="Objetivo" value={privateMoney(goal.target_amount)} />
                {goal.kind === 'MONTHLY_INCOME'
                  ? <Figure label="Recebido em 12 meses" value={formatCurrency(goal.income_last_12_months)} />
                  : <Figure label="Previsão" value={forecastText(goal)} hint={forecastHint(goal)} />}
              </div>

              {goal.kind !== 'MONTHLY_INCOME' ? (
                <p className="mt-3 text-sm text-zinc-600">
                  Aporte de {formatCurrency(goal.monthly_contribution)}/mês
                  {goal.annual_return_percent !== null ? ` a ${formatPercent(goal.annual_return_percent, 1)} ao ano` : ', sem rentabilidade'}
                  {goal.target_month && !goal.reached && goal.required_contribution !== null
                    ? `. Para chegar em ${monthLabel(goal.target_month)}: ${formatCurrency(goal.required_contribution)}/mês.`
                    : '.'}
                </p>
              ) : null}
            </Panel>
          ))}
        </div>
      )}

      <GoalSheet open={sheet.open} goal={sheet.goal} onClose={() => setSheet({ open: false, goal: sheet.goal })} />
    </div>
  )
}
