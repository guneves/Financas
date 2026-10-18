import { useEffect, useMemo, useState } from 'react'
import { RotateCcw } from 'lucide-react'
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART, ChartTooltip, FLOW, LegendDot, SERIES, axisProps, compactAxis, useChartAnimation } from '../../components/charts'
import { AlertMessage, Button, Field, PageHeader, Panel, PanelHeader, SummaryPanel } from '../../components/ui'
import { DEFAULT_FORM, calculate, durationText, periodLabel } from '../../lib/compoundInterest'
import { formatCurrency, formatPercent } from '../../lib/format'
import useDebouncedValue from '../../lib/useDebouncedValue'

// O ultimo calculo fica neste aparelho: abrir a aba de novo volta ao que estava.
const FORM_STORAGE_KEY = '@financeMVP:calculadoraJuros'
const REAL_COLOR = SERIES[3]

function readStoredForm() {
  try {
    const saved = JSON.parse(localStorage.getItem(FORM_STORAGE_KEY) || 'null')
    return saved && typeof saved === 'object' ? { ...DEFAULT_FORM, ...saved } : DEFAULT_FORM
  } catch {
    return DEFAULT_FORM
  }
}

function storeForm(form) {
  try {
    localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(form))
  } catch {
    // Sem armazenamento (aba privada): o calculo funciona igual.
  }
}

// Ate 5 anos, um ponto por mes; acima disso, um por ano (100 anos sao 1200 meses).
function chartPoints(schedule) {
  const last = schedule.length - 1
  const step = last > 60 ? 12 : 1
  return schedule
    .filter((row) => row.month % step === 0 || row.month === last)
    .map((row) => ({ month: row.month, invested: row.invested, interest: row.interest, real: row.real, balance: row.balance }))
}

function GrowthChart({ schedule, withReal }) {
  const chartAnimation = useChartAnimation()
  const data = useMemo(() => chartPoints(schedule), [schedule])
  const names = { invested: 'Total investido', interest: 'Juros', real: 'Em reais de hoje' }
  return (
    <>
      <div className="mb-3 flex flex-wrap gap-4">
        <LegendDot color={FLOW.investment} label="Total investido" />
        <LegendDot color={SERIES[2]} label="Juros" />
        {withReal ? <LegendDot color={REAL_COLOR} label="Em reais de hoje" shape="line" /> : null}
      </div>
      <div className="h-64" aria-label="Evolução do patrimônio simulado">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={CHART.grid} />
            <XAxis dataKey="month" {...axisProps} tickFormatter={periodLabel} interval="preserveStartEnd" minTickGap={16} />
            <YAxis {...axisProps} width={56} tickFormatter={compactAxis} />
            <Tooltip
              cursor={{ stroke: CHART.axis }}
              content={(
                <ChartTooltip
                  names={names}
                  labelFormatter={periodLabel}
                  footer={(payload) => `Saldo: ${formatCurrency(payload[0]?.payload?.balance)}`}
                />
              )}
            />
            <Area type="monotone" dataKey="invested" stackId="saldo" stroke={FLOW.investment} fill={FLOW.investment} fillOpacity={0.25} strokeWidth={2} {...chartAnimation} />
            <Area type="monotone" dataKey="interest" stackId="saldo" stroke={SERIES[2]} fill={SERIES[2]} fillOpacity={0.3} strokeWidth={2} {...chartAnimation} />
            {withReal ? (
              <Line type="monotone" dataKey="real" stroke={REAL_COLOR} strokeWidth={2} strokeDasharray="5 4" dot={false} {...chartAnimation} />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}

function YearsTable({ years, withReal }) {
  const yearLabel = (row) => (row.months === 12 ? `Ano ${row.year}` : `Ano ${row.year} (${row.months} ${row.months === 1 ? 'mês' : 'meses'})`)
  return (
    <>
      <ul className="divide-y divide-zinc-100 lg:hidden">
        {years.map((row) => (
          <li key={row.year} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-zinc-900">{yearLabel(row)}</p>
              <p className="text-xs text-zinc-500 tabular">
                Juros no ano {formatCurrency(row.interestInYear)} · investido {formatCurrency(row.invested)}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-sm font-semibold tabular text-zinc-950">{formatCurrency(row.balance)}</p>
              {withReal ? <p className="text-xs text-zinc-500 tabular">hoje {formatCurrency(row.real)}</p> : null}
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden lg:block">
        <table className="app-table">
          <thead>
            <tr>
              <th>Ano</th>
              <th className="text-right">Aportes no ano</th>
              <th className="text-right">Juros no ano</th>
              <th className="text-right">Total investido</th>
              <th className="text-right">Juros acumulados</th>
              <th className="text-right">Saldo</th>
              {withReal ? <th className="text-right">Em reais de hoje</th> : null}
            </tr>
          </thead>
          <tbody>
            {years.map((row) => (
              <tr key={row.year}>
                <td className="font-semibold text-zinc-900">{yearLabel(row)}</td>
                <td className="num tabular">{formatCurrency(row.investedInYear)}</td>
                <td className="num tabular">{formatCurrency(row.interestInYear)}</td>
                <td className="num tabular">{formatCurrency(row.invested)}</td>
                <td className="num tabular">{formatCurrency(row.interest)}</td>
                <td className="num tabular font-semibold text-zinc-950">{formatCurrency(row.balance)}</td>
                {withReal ? <td className="num tabular">{formatCurrency(row.real)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export default function Calculadora() {
  const [form, setForm] = useState(readStoredForm)
  // O grafico e a tabela esperam a digitacao parar; o resumo tambem, para nao piscar.
  const settled = useDebouncedValue(form, 250)
  const result = useMemo(() => calculate(settled), [settled])

  useEffect(() => { storeForm(settled) }, [settled])

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))
  const ok = !result.error
  const withReal = ok && result.input.inflationPercent !== null

  const rateHint = ok
    ? form.rateUnit === 'month'
      ? `Equivale a ${formatPercent(result.input.annualRatePercent, 2)} ao ano.`
      : `Equivale a ${formatPercent(result.input.monthlyRatePercent, 4)} ao mês.`
    : null

  const figures = ok
    ? [
      { label: 'Total investido', value: formatCurrency(result.invested) },
      { label: 'Juros', value: formatCurrency(result.interest), tone: result.interest < 0 ? 'loss' : result.interest > 0 ? 'gain' : 'neutral' },
      withReal
        ? { label: 'Em reais de hoje', value: formatCurrency(result.real), hint: `Taxa real ${formatPercent(result.realAnnualRatePercent, 2)} a.a.` }
        : { label: 'Rende por mês no fim', value: formatCurrency(result.monthlyIncomeAtEnd), hint: 'Saldo final × taxa mensal' },
    ]
    : []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Calculadora de juros compostos"
        description="Simule quanto um valor inicial e aportes mensais viram com juros sobre juros. É só uma conta: nada é gravado e a carteira não muda."
        actions={(
          <Button variant="secondary" icon={RotateCcw} onClick={() => setForm(DEFAULT_FORM)}>
            Limpar
          </Button>
        )}
      />

      <Panel className="p-4 sm:p-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Valor inicial">
            <input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0,00" value={form.initial} onChange={set('initial')} className="app-input" />
          </Field>
          <Field label="Aporte mensal">
            <input type="number" inputMode="decimal" min="0" step="0.01" placeholder="0,00" value={form.monthly} onChange={set('monthly')} className="app-input" />
          </Field>
          <Field label="Aporte feito no">
            <select value={form.timing} onChange={set('timing')} className="app-select">
              <option value="end">Fim de cada mês</option>
              <option value="start">Início de cada mês</option>
            </select>
          </Field>
          <Field label="Taxa de juros (%)" hint={rateHint}>
            <div className="flex gap-2">
              {/* Sem inputMode decimal: a taxa pode ser negativa e o teclado decimal nao tem o sinal. */}
              <input type="number" step="0.01" placeholder="Ex.: 10" value={form.rate} onChange={set('rate')} className="app-input min-w-0 flex-1" />
              <select value={form.rateUnit} onChange={set('rateUnit')} className="app-select w-32 shrink-0" aria-label="Unidade da taxa">
                <option value="year">ao ano</option>
                <option value="month">ao mês</option>
              </select>
            </div>
          </Field>
          <Field label="Período">
            <div className="flex gap-2">
              <input type="number" inputMode="decimal" min="0" step="1" placeholder="Ex.: 10" value={form.period} onChange={set('period')} className="app-input min-w-0 flex-1" />
              <select value={form.periodUnit} onChange={set('periodUnit')} className="app-select w-32 shrink-0" aria-label="Unidade do período">
                <option value="year">anos</option>
                <option value="month">meses</option>
              </select>
            </div>
          </Field>
          <Field label="Inflação anual (%)" hint="Opcional: mostra o valor final em reais de hoje.">
            <input type="number" step="0.01" placeholder="Ex.: 4,5" value={form.inflation} onChange={set('inflation')} className="app-input" />
          </Field>
        </div>
      </Panel>

      <AlertMessage tone="warning" message={result.error} />

      {ok ? (
        <>
          <SummaryPanel
            lead={{
              label: 'Valor final',
              value: formatCurrency(result.final),
              hint: `Depois de ${durationText(result.input.months)}`,
            }}
            figures={figures}
          />

          <Panel>
            <PanelHeader title="Evolução" description="O que você pôs e o que os juros somaram, mês a mês." />
            <div className="p-4 sm:p-6">
              <GrowthChart schedule={result.schedule} withReal={withReal} />
            </div>
          </Panel>

          <Panel className="overflow-clip">
            <PanelHeader title="Ano a ano" description="Saldo no fim de cada ano, com os aportes e os juros do ano." />
            <YearsTable years={result.years} withReal={withReal} />
          </Panel>
        </>
      ) : null}
    </div>
  )
}
