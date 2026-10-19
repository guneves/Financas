import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, SlidersHorizontal, Trash2 } from 'lucide-react'
import { monthlyPlanApi } from '../lib/dataApi'
import { formatCurrency, monthLabel } from '../lib/format'
import {
  FLAG_TONES,
  flagText,
  formatPlanPercent,
  incomeReceivedText,
  livePlanText,
  livePlanTotals,
  moneyInputValue,
  parseMoneyInput,
  percentRoom,
  planFlagKey,
  sortFlags,
  spendStatus,
  visibleFlags,
} from '../lib/monthlyPlan'
import { dismissPlanFlag, useDismissedPlanFlags } from '../lib/planFlags'
import { toast } from '../lib/toast'
import { confirmAction } from '../lib/confirm'
import { AlertMessage, Button, Field, Panel, PanelHeader, PercentSlider, Sheet, cx } from './ui'
import { BudgetProgressBar } from './BudgetProgress'

// Uma linha da renda: Investir, Gastar ou Sem destino. % e R$ a esquerda, o
// realizado a direita; a barra e o rodape so quando ha o que medir.
function PlanLevel({ label, percent, amount, realized, progress, status, children }) {
  return (
    <div className="px-5 py-4 sm:px-6">
      <div className="flex items-baseline justify-between gap-3">
        <p className="min-w-0 font-semibold text-zinc-900">
          {label} <span className="tabular font-normal text-zinc-600">· {formatPlanPercent(percent)}</span>
        </p>
        <p className="tabular whitespace-nowrap text-base font-bold text-zinc-950">{formatCurrency(amount)}</p>
      </div>
      {realized ? <p className="mt-0.5 text-sm text-zinc-600">{realized}</p> : null}
      {progress !== undefined ? <BudgetProgressBar percent={progress} status={status} className="mt-2.5 h-2.5" /> : null}
      {children}
    </div>
  )
}

// Renda do mes no Orcamento: quanto se espera receber e como ela se divide em
// Investir, Gastar e Sem destino, com o realizado de cada um e os alertas do
// plano. Todo numero vem de GET /api/monthly-plan (services/monthly_plan.py).
export default function MonthlyPlanPanel({ data, onEdit }) {
  const plan = data.plan
  const actual = data.actual || {}
  const progress = data.progress || {}
  const flags = sortFlags(data.flags)
  // O X tira o alerta so desta tela e deste aparelho; a barra do Gastar
  // continua lendo todos.
  const shownFlags = visibleFlags(flags, data.month, useDismissedPlanFlags())
  const investRemaining = Number(progress.invest_remaining || 0)
  const unallocatedPercent = Number(data.unallocated?.percent || 0)

  return (
    <Panel>
      <PanelHeader
        title="Renda do mês"
        actions={<Button variant="secondary" icon={SlidersHorizontal} onClick={onEdit}>Editar plano</Button>}
      />

      {/* Fora do PanelHeader: a descricao dele some no celular, e esta linha e o ponto do painel. */}
      <div className="border-b border-zinc-100 px-5 py-3 sm:px-6">
        <p className="tabular text-sm font-semibold text-zinc-900">
          {incomeReceivedText(data.income?.received, data.income?.planned)}
        </p>
        {plan.inherited ? (
          <p className="mt-0.5 text-sm text-zinc-500">
            Plano definido em <span className="inline-block first-letter:uppercase">{monthLabel(plan.source_month)}</span>.
          </p>
        ) : null}
      </div>

      <div className="divide-y divide-zinc-100">
        <PlanLevel
          label="Investir"
          percent={data.invest.percent}
          amount={data.invest.amount}
          realized={`${formatCurrency(actual.invested)} investidos até agora`}
          progress={progress.invest_percent ?? 0}
          status="OK"
        >
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3">
            <p className="text-sm text-zinc-600">
              {investRemaining > 0 ? `Falta investir ${formatCurrency(investRemaining)}` : 'Aporte do mês feito'}
            </p>
            {Number(data.invest.amount) > 0 ? (
              <Link
                to="/investimentos/alocacao"
                className="-mr-2 inline-flex h-11 items-center gap-1 rounded-full px-2 text-sm font-semibold text-emerald-700 hover:bg-zinc-100 lg:h-8"
              >
                Como dividir
                <ArrowRight className="h-4 w-4" />
              </Link>
            ) : null}
          </div>
        </PlanLevel>

        <PlanLevel
          label="Gastar"
          percent={data.spend.percent}
          amount={data.spend.amount}
          realized={`${formatCurrency(actual.spent)} gastos até agora`}
          progress={progress.spend_percent ?? (actual.spent > 0 ? 100 : 0)}
          status={spendStatus(flags)}
        />

        {unallocatedPercent > 0 ? (
          <PlanLevel label="Sem destino" percent={data.unallocated.percent} amount={data.unallocated.amount} />
        ) : null}
      </div>

      {shownFlags.length ? (
        <ul className="space-y-2 border-t border-zinc-100 px-5 py-4 sm:px-6" aria-label="Alertas do plano">
          {shownFlags.map((flag) => (
            <li key={`${flag.code}-${flag.goal_id || ''}`}>
              <AlertMessage
                tone={FLAG_TONES[flag.tone]}
                message={flagText(flag)}
                onDismiss={() => dismissPlanFlag(planFlagKey(flag, data.month))}
                dismissLabel="Dispensar"
                className="animate-none"
              />
            </li>
          ))}
        </ul>
      ) : null}

      <p className="border-t border-zinc-100 px-5 py-3 text-xs text-zinc-500 sm:px-6">
        Gasto: saídas das contas e compras no cartão (inteiras, no mês da compra), sem transferências, pagamento de fatura e aportes.
        Investido: aportes menos resgates das operações da carteira no mês.
      </p>
    </Panel>
  )
}

// Investir e Gastar sao numeros (os controles deslizantes); a renda e texto.
const percentValue = (value) => (value === null || value === undefined || value === '' ? null : Number(value))

const formFromPlan = (plan) => {
  if (!plan) return { income: '', invest: 0, spend: 0 }
  if (plan.needs_income) {
    // Plano antigo: os % ficam em branco para o servidor converter os reais de antes.
    return { income: moneyInputValue(plan.income_amount), invest: null, spend: null }
  }
  return {
    income: moneyInputValue(plan.income_amount),
    invest: percentValue(plan.invest_percent),
    spend: percentValue(plan.spend_percent),
  }
}

// "Plano do mes": Renda, Investir % e Gastar %, nessa ordem, com os R$ ao vivo.
// Os % deslizam: cada um para onde o outro deixa (os dois somam ate 100%).
// O mesmo sheet cria o plano, edita e, num plano antigo sem renda, pede a renda
// para converte-lo. Abre com o foco na renda.
export function MonthlyPlanSheet({ open, onClose, month, plan }) {
  const [form, setForm] = useState(() => formFromPlan(plan))
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [wasOpen, setWasOpen] = useState(open)

  // Cada abertura parte do plano que a tela mostra; uma releitura com o sheet
  // aberto nao apaga o que se esta digitando.
  if (open !== wasOpen) {
    setWasOpen(open)
    if (open) {
      setForm(formFromPlan(plan))
      setFormError('')
    }
  }

  const needsIncome = Boolean(plan?.needs_income)
  const totals = livePlanTotals({
    income: parseMoneyInput(form.income),
    invest: form.invest,
    spend: form.spend,
    legacy: needsIncome ? plan.legacy : null,
  })

  const handleSave = async (event) => {
    event.preventDefault()
    if (totals.blocked) {
      setFormError(totals.blocked)
      return
    }
    setSaving(true)
    setFormError('')
    try {
      const income = parseMoneyInput(form.income)
      await monthlyPlanApi.save(totals.convert
        ? { month, income_amount: income }
        : { month, income_amount: income, invest_percent: form.invest, spend_percent: form.spend })
      onClose()
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
      onClose()
      toast('Plano removido.')
    } catch (requestError) {
      setFormError(requestError.message || 'Não foi possível remover o plano.')
    } finally {
      setSaving(false)
    }
  }

  const ownPlan = plan && !plan.inherited
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })
  const setPercent = (key) => (value) => setForm((current) => ({ ...current, [key]: value }))
  const amountOf = (amount) => (
    <span className="text-sm font-semibold text-zinc-600">{amount === null ? 'R$ —' : formatCurrency(amount)}</span>
  )

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title="Plano do mês"
      description={`Vale a partir de ${monthLabel(month)}, até você salvar outro.`}
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          {ownPlan ? (
            <Button variant="danger" icon={Trash2} onClick={handleRemove} disabled={saving}>Remover deste mês</Button>
          ) : <span />}
          <Button type="submit" form="monthly-plan-form" icon={Check} loading={saving} disabled={Boolean(totals.blocked)}>
            Salvar plano
          </Button>
        </div>
      }
    >
      <form id="monthly-plan-form" onSubmit={handleSave} className="space-y-4">
        {needsIncome ? (
          <AlertMessage tone="warning" className="animate-none">
            <p className="font-semibold">Informe a renda para converter o plano em porcentagens.</p>
            <p className="mt-0.5 font-normal">
              O plano antigo era investir {formatCurrency(plan.legacy?.invest_amount)} e gastar {formatCurrency(plan.legacy?.spend_amount)}.
              Com os % em branco, eles viram a parte da renda que esses valores representam.
            </p>
          </AlertMessage>
        ) : null}
        <AlertMessage message={formError} onDismiss={() => setFormError('')} />
        <Field label="Renda do mês (R$)">
          <input
            type="text" inputMode="decimal" autoComplete="off" placeholder="0,00"
            value={form.income} onChange={set('income')}
            className="app-input h-14 text-2xl font-bold tabular" required autoFocus
          />
        </Field>
        <PercentSlider
          label="Investir (% da renda)"
          value={form.invest}
          onChange={setPercent('invest')}
          room={percentRoom(form.spend)}
          aside={amountOf(totals.investAmount)}
          hint={needsIncome && form.invest === null ? 'Em branco: converte o valor antigo' : undefined}
        />
        <PercentSlider
          label="Gastar (% da renda)"
          value={form.spend}
          onChange={setPercent('spend')}
          room={percentRoom(form.invest)}
          aside={amountOf(totals.spendAmount)}
          hint={needsIncome && form.spend === null ? 'Em branco: converte o valor antigo' : undefined}
        />
        {needsIncome && (form.invest !== null || form.spend !== null) ? (
          <Button
            type="button"
            variant="subtle"
            size="sm"
            onClick={() => setForm((current) => ({ ...current, invest: null, spend: null }))}
          >
            Converter os valores antigos
          </Button>
        ) : null}
        <p
          className={cx('tabular rounded-2xl bg-zinc-50 px-4 py-3 text-sm', totals.over ? 'font-semibold text-rose-600' : 'text-zinc-700')}
          aria-live="polite"
        >
          {livePlanText(totals)}
        </p>
        {totals.blocked && totals.blocked !== formError ? (
          <p className="text-sm text-zinc-600">{totals.blocked}</p>
        ) : null}
      </form>
    </Sheet>
  )
}
