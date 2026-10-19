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

const formatPercent = (value) => `${Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`

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

// Plano do mes no topo do Orcamento: a renda e quanto dela investir e gastar,
// em %, e os alertas para chegar nas metas. O calculo e todo do servidor (os
// reais saem dos %). Versao de transicao: o redesenho da tela vem depois.
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

  const needsIncome = Boolean(plan?.needs_income)

  const openSheet = () => {
    setForm(plan
      ? {
          income: needsIncome ? '' : moneyInputValue(plan.income_amount),
          spend: moneyInputValue(plan.spend_percent),
          invest: moneyInputValue(plan.invest_percent),
        }
      : emptyForm)
    setFormError('')
    setSheetOpen(true)
  }

  const income = parseMoneyInput(form.income)
  const spend = parseMoneyInput(form.spend)
  const invest = parseMoneyInput(form.invest)
  // Plano antigo sem renda: com os dois % em branco, o servidor converte os
  // reais de antes sobre a renda informada.
  const convertLegacy = needsIncome && spend === null && invest === null
  const leftover = !convertLegacy && spend !== null && invest !== null && !Number.isNaN(spend) && !Number.isNaN(invest)
    ? 100 - spend - invest
    : null

  const handleSave = async (event) => {
    event.preventDefault()
    if (income === null || Number.isNaN(income) || income <= 0) {
      setFormError('Informe a renda do mês em reais, como 5.000,00.')
      return
    }
    if (!convertLegacy && (spend === null || Number.isNaN(spend) || invest === null || Number.isNaN(invest))) {
      setFormError('Informe quanto da renda investir e gastar, em %, como 20 ou 33,33.')
      return
    }
    setSaving(true)
    setFormError('')
    try {
      await monthlyPlanApi.save(convertLegacy
        ? { month, income_amount: income }
        : { month, income_amount: income, spend_percent: spend, invest_percent: invest })
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
      message: 'O mês volta a usar o plano anterior, com as categorias dele, se houver. Nenhum lançamento muda.',
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
  const overSpent = Number(data?.plan_balance) < 0

  return (
    <Panel>
      <PanelHeader
        title="Plano do mês"
        description="Da sua renda, quanto investir e quanto gastar. Vale a partir do mês em que é salvo, até você trocar."
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
            message="Informe a renda do mês e quanto dela vai investir e gastar. O app avisa quando o ritmo sair do plano e se o aporte cobre as suas metas."
            action={<Button icon={SlidersHorizontal} onClick={openSheet}>Definir plano</Button>}
          />
        ) : needsIncome ? (
          <EmptyState
            icon={PiggyBank}
            title="O plano precisa da renda"
            message={`O plano agora parte da renda do mês. O antigo era gastar ${formatCurrency(plan.legacy?.spend_amount)} e investir ${formatCurrency(plan.legacy?.invest_amount)}: informe a renda para convertê-lo em percentuais.`}
            action={<Button icon={SlidersHorizontal} onClick={openSheet}>Informar renda</Button>}
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
                label={`Gastar · ${formatPercent(plan.spend_percent)}`}
                done={actual.spent}
                planned={plan.spend_amount}
                percent={progress.spend_percent ?? (actual.spent > 0 ? 100 : 0)}
                status={spendStatus(flags)}
                remainingLabel={overSpent ? 'Acima do plano:' : 'Ainda pode gastar:'}
                remaining={Math.abs(Number(data?.plan_balance || 0))}
                remainingTone={overSpent ? 'loss' : 'neutral'}
              />
              <PlanRow
                label={`Investir · ${formatPercent(plan.invest_percent)}`}
                done={actual.invested}
                planned={plan.invest_amount}
                percent={progress.invest_percent ?? 0}
                status="OK"
                remainingLabel="Falta investir:"
                remaining={progress.invest_remaining}
              />
            </div>

            <p className="text-sm text-zinc-600">
              Renda do mês {formatCurrency(plan.income_amount)} · recebido {formatCurrency(actual.income)} · sem destino{' '}
              <span className={cx('font-semibold', plan.unallocated_amount < 0 ? 'text-rose-600' : 'text-zinc-900')}>
                {formatCurrency(plan.unallocated_amount)} ({formatPercent(plan.unallocated_percent)})
              </span>
              {data?.daily_available !== null && data?.daily_available !== undefined
                ? <> · disponível por dia {formatCurrency(data.daily_available)}</>
                : null}
            </p>

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
          <Field label="Renda do mês (R$)">
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0,00"
              value={form.income} onChange={(event) => setForm({ ...form, income: event.target.value })}
              className="app-input" required autoFocus
            />
          </Field>
          <Field label="Investir (% da renda)" hint={needsIncome ? 'Em branco: converte o plano antigo' : undefined}>
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0"
              value={form.invest} onChange={(event) => setForm({ ...form, invest: event.target.value })}
              className="app-input" required={!needsIncome}
            />
          </Field>
          <Field label="Gastar (% da renda)" hint={needsIncome ? 'Em branco: converte o plano antigo' : undefined}>
            <input
              type="text" inputMode="decimal" autoComplete="off" placeholder="0"
              value={form.spend} onChange={(event) => setForm({ ...form, spend: event.target.value })}
              className="app-input" required={!needsIncome}
            />
          </Field>
          {leftover !== null ? (
            <p className={cx('text-sm', leftover < 0 ? 'font-semibold text-rose-600' : 'text-zinc-600')}>
              {leftover < 0
                ? `Investir e gastar passam de 100% da renda em ${formatPercent(-leftover)}.`
                : `Sem destino: ${formatPercent(leftover)} da renda.`}
            </p>
          ) : null}
        </form>
      </Sheet>
    </Panel>
  )
}
