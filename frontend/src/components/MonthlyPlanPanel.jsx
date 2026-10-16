import { useState } from 'react'
import { Check, PiggyBank, SlidersHorizontal, Trash2 } from 'lucide-react'
import { monthlyPlanApi } from '../lib/dataApi'
import { formatCurrency, monthLabel } from '../lib/format'
import { FLAG_TONES, flagText, moneyInputValue, parseMoneyInput, sortFlags, spendStatus } from '../lib/monthlyPlan'
import { keepPreviousData, useQuery, useReportQueryError } from '../lib/queries'
import { toast } from '../lib/toast'
import { confirmAction } from '../lib/confirm'
import { AlertMessage, Button, EmptyState, Field, Panel, PanelHeader, Sheet, Skeleton, cx } from './ui'
import { BudgetProgressBar } from './BudgetProgress'

const emptyForm = { income: '', spend: '', invest: '' }

function PlanRow({ label, done, planned, percent, status, remainingLabel, remaining, remainingTone }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="font-semibold text-zinc-900">{label}</p>
        <p className="num text-sm text-zinc-600">
          <span className="font-semibold text-zinc-900">{formatCurrency(done)}</span> de {formatCurrency(planned)}
        </p>
      </div>
      <BudgetProgressBar percent={percent} status={status} className="mt-2 h-2.5" />
      <p className={cx('mt-1.5 text-sm', remainingTone === 'loss' ? 'font-semibold text-rose-600' : 'text-zinc-600')}>
        {remainingLabel} {formatCurrency(remaining)}
      </p>
    </div>
  )
}

// Plano do mes no topo do Orcamento: quanto gastar e investir, em reais, e os
// alertas para chegar nas metas. O calculo e todo do servidor.
export default function MonthlyPlanPanel({ month }) {
  const [error, setError] = useState('')
  const [sheetOpen, setSheetOpen] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)

  const query = useQuery({
    queryKey: ['plano-do-mes', month],
    queryFn: () => monthlyPlanApi.month(month),
    placeholderData: keepPreviousData,
  })
  useReportQueryError(query, setError, 'Não foi possível carregar o plano do mês.')
  const data = query.data
  const plan = data?.plan
  const actual = data?.actual || {}
  const progress = data?.progress || {}
  const flags = sortFlags(data?.flags)

  const openSheet = () => {
    setForm(plan
      ? {
          income: moneyInputValue(plan.income_amount),
          spend: moneyInputValue(plan.spend_amount),
          invest: moneyInputValue(plan.invest_amount),
        }
      : emptyForm)
    setFormError('')
    setSheetOpen(true)
  }

  const income = parseMoneyInput(form.income)
  const spend = parseMoneyInput(form.spend)
  const invest = parseMoneyInput(form.invest)
  const leftover = income !== null && !Number.isNaN(income) ? income - (spend || 0) - (invest || 0) : null

  const handleSave = async (event) => {
    event.preventDefault()
    if (spend === null || Number.isNaN(spend) || invest === null || Number.isNaN(invest) || Number.isNaN(income)) {
      setFormError('Informe valores em reais, como 2.500,00.')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      await monthlyPlanApi.save({ month, spend_amount: spend, invest_amount: invest, income_amount: income })
      setSheetOpen(false)
      toast(`Plano salvo a partir de ${monthLabel(month)}.`)
    } catch (requestError) {
      setFormError(requestError.message || 'Não foi possível salvar o plano.')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async () => {
    if (!(await confirmAction({
      title: `Remover o plano de ${monthLabel(month)}?`,
      message: 'O mês volta a usar o plano anterior, se houver. Nenhum lançamento muda.',
      confirmLabel: 'Remover',
    }))) return
    setSaving(true)
    try {
      await monthlyPlanApi.remove(month)
      setSheetOpen(false)
      toast('Plano removido.')
    } catch (requestError) {
      setFormError(requestError.message || 'Não foi possível remover o plano.')
    } finally {
      setSaving(false)
    }
  }

  const ownPlan = plan && !plan.inherited
  const overSpent = Number(progress.spend_remaining) < 0

  return (
    <Panel>
      <PanelHeader
        title="Plano do mês"
        description="Quanto você decidiu gastar e investir por mês, em reais. Vale a partir do mês em que é salvo, até você trocar."
        actions={plan ? (
          <Button variant="secondary" icon={SlidersHorizontal} onClick={openSheet}>Editar plano</Button>
        ) : null}
      />

      <div className="space-y-5 p-5 sm:px-6">
        <AlertMessage message={error} onDismiss={() => setError('')} />

        {query.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : !plan ? (
          <EmptyState
            icon={PiggyBank}
            title="Sem plano para este mês"
            message="Defina quanto vai gastar e quanto vai investir. O app avisa quando o ritmo sair do plano e se o aporte cobre as suas metas."
            action={<Button icon={SlidersHorizontal} onClick={openSheet}>Definir plano</Button>}
          />
        ) : (
          <>
            {plan.inherited ? (
              <p className="text-sm text-zinc-600">
                Plano definido em <span className="first-letter:uppercase">{monthLabel(plan.source_month)}</span>.
              </p>
            ) : null}

            <div className="grid gap-5 md:grid-cols-2">
              <PlanRow
                label="Gastar"
                done={actual.spent}
                planned={plan.spend_amount}
                percent={progress.spend_percent ?? (actual.spent > 0 ? 100 : 0)}
                status={spendStatus(flags)}
                remainingLabel={overSpent ? 'Acima do plano:' : 'Ainda pode gastar:'}
                remaining={Math.abs(Number(progress.spend_remaining || 0))}
                remainingTone={overSpent ? 'loss' : 'neutral'}
              />
              <PlanRow
                label="Investir"
                done={actual.invested}
                planned={plan.invest_amount}
                percent={progress.invest_percent ?? 0}
                status="OK"
                remainingLabel="Falta investir:"
                remaining={progress.invest_remaining}
              />
            </div>

            {plan.income_amount !== null ? (
              <p className="text-sm text-zinc-600">
                Renda esperada {formatCurrency(plan.income_amount)} · recebido no mês {formatCurrency(actual.income)} · sobra planejada{' '}
                <span className={cx('font-semibold', plan.planned_leftover < 0 ? 'text-rose-600' : 'text-zinc-900')}>
                  {formatCurrency(plan.planned_leftover)}
                </span>
              </p>
            ) : null}

            {flags.length ? (
              <ul className="space-y-2" aria-label="Alertas do plano">
                {flags.map((flag) => (
                  <li key={`${flag.code}-${flag.goal_id || ''}`}>
                    <AlertMessage tone={FLAG_TONES[flag.tone]} message={flagText(flag)} className="animate-none" />
                  </li>
                ))}
              </ul>
            ) : null}

            <p className="text-xs text-zinc-500">
              Gasto: saídas das contas e compras no cartão (inteiras, no mês da compra), sem transferências, pagamento de fatura e aportes.
              Investido: aportes menos resgates das operações da carteira no mês.
            </p>
          </>
        )}
      </div>

      <Sheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title="Plano do mês"
        description={`Vale a partir de ${monthLabel(month)}, até você salvar outro.`}
        footer={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
            {ownPlan ? (
              <Button variant="danger" icon={Trash2} onClick={handleRemove} disabled={saving}>Remover deste mês</Button>
            ) : <span />}
            <Button type="submit" form="monthly-plan-form" icon={Check} loading={saving}>Salvar plano</Button>
          </div>
        }
      >
        <form id="monthly-plan-form" onSubmit={handleSave} className="space-y-4">
          <AlertMessage message={formError} onDismiss={() => setFormError('')} />
          <Field label="Quanto vou gastar no mês">
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0,00"
              value={form.spend} onChange={(event) => setForm({ ...form, spend: event.target.value })}
              className="app-input" required autoFocus
            />
          </Field>
          <Field label="Quanto vou investir no mês">
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0,00"
              value={form.invest} onChange={(event) => setForm({ ...form, invest: event.target.value })}
              className="app-input" required
            />
          </Field>
          <Field label="Renda esperada no mês" hint="Opcional — avisa se o plano não cabe nela">
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0,00"
              value={form.income} onChange={(event) => setForm({ ...form, income: event.target.value })}
              className="app-input"
            />
          </Field>
          {leftover !== null ? (
            <p className={cx('text-sm', leftover < 0 ? 'font-semibold text-rose-600' : 'text-zinc-600')}>
              {leftover < 0
                ? `O plano passa da renda em ${formatCurrency(-leftover)}.`
                : `Sobra planejada: ${formatCurrency(leftover)}.`}
            </p>
          ) : null}
        </form>
      </Sheet>
    </Panel>
  )
}
