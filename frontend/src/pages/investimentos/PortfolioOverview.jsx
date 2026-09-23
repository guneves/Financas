import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART, ChartTooltip, DonutChart, FLOW, LegendDot, axisProps, compactCurrency, useChartAnimation } from '../../components/charts'
import { AlertMessage, Panel, PanelHeader, SegmentedControl, Skeleton } from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency } from '../../lib/format'
import { usePrivateAxisFormatter, usePrivateFormatter } from '../../lib/privacy'
import { useDataVersion } from '../../lib/newEntry'

// O backend limita o historico a 60 meses (GET /api/investments/history).
const PERIODS = [
  { value: 6, label: '6M' },
  { value: 12, label: '1A' },
  { value: 24, label: '2A' },
  { value: 36, label: '3A' },
  { value: 60, label: '5A' },
]
const DEFAULT_PERIOD = 12
const PERIOD_STORAGE_KEY = '@financeMVP:patrimonioPeriod'

function readStoredPeriod() {
  try {
    const saved = Number(localStorage.getItem(PERIOD_STORAGE_KEY))
    return PERIODS.some((period) => period.value === saved) ? saved : DEFAULT_PERIOD
  } catch {
    return DEFAULT_PERIOD
  }
}

// Alocacao por classe (valor bruto de mercado) e evolucao mensal do patrimonio.
// A barra de cada mes e o valor aplicado com o ganho de capital empilhado em
// cima; num mes de perda, a base vira o patrimonio e a perda (vermelha) completa
// a barra ate o valor aplicado — a altura total nunca esconde o prejuizo.
export default function PortfolioOverview({ assets, getClassLabel }) {
  const chartAnimation = useChartAnimation()
  // A carteira inteira some no modo privado; as proporcoes (%) ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const privateAxis = usePrivateAxisFormatter(compactCurrency)
  const allocation = useMemo(() => {
    const byClass = {}
    assets.forEach((asset) => {
      const label = getClassLabel(asset.class)
      byClass[label] = (byClass[label] || 0) + Number(asset.current_value || 0)
    })
    return Object.entries(byClass).map(([name, value]) => ({ name, value }))
  }, [assets, getClassLabel])

  const [months, setMonths] = useState(readStoredPeriod)
  const [evolution, setEvolution] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const changePeriod = (value) => {
    setMonths(value)
    try {
      localStorage.setItem(PERIOD_STORAGE_KEY, String(value))
    } catch {
      // Preferencia so desta sessao.
    }
  }

  // dataVersion: recarrega depois de um "+ Novo" (ex.: Investimento) salvo no Layout.
  const dataVersion = useDataVersion()
  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError('')
    investmentsApi.history({ months })
      .then((data) => {
        if (!cancelled) setEvolution(data?.evolution || [])
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Não foi possível carregar a evolução do patrimônio.')
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => { cancelled = true }
  }, [months, dataVersion])

  const chartData = useMemo(() => evolution.map((item) => {
    const applied = Number(item.valorAplicado || 0)
    const patrimonio = Number(item.patrimonio || 0)
    const gain = Number(item.ganhoCapitalReal || 0)
    return {
      month: item.month,
      applied,
      patrimonio,
      gain,
      base: gain >= 0 ? applied : patrimonio,
      ganho: Math.max(gain, 0),
      perda: Math.max(-gain, 0),
    }
  }), [evolution])

  const hasLoss = chartData.some((item) => item.perda > 0)
  const periodLabel = PERIODS.find((period) => period.value === months)?.label

  return (
    <div className="stagger grid grid-cols-1 gap-6 xl:grid-cols-3">
      <Panel>
        <PanelHeader title="Alocação" description="Valor de mercado bruto por classe de ativo." />
        <div className="p-5">
          <DonutChart data={allocation} centerLabel="Carteira" height={190} stacked formatter={privateMoney} />
        </div>
      </Panel>

      <Panel className="xl:col-span-2">
        <PanelHeader
          title="Evolução do Patrimônio"
          description="Valor aplicado e ganho de capital no fim de cada mês."
          actions={<SegmentedControl items={PERIODS} value={months} onChange={changePeriod} />}
        />
        <div className="p-5">
          <AlertMessage tone="warning" message={error} className="mb-4" />
          <div className="mb-3 flex flex-wrap gap-4">
            <LegendDot color={FLOW.investment} label="Valor aplicado" />
            <LegendDot color={FLOW.income} label="Ganho de capital" />
            {hasLoss ? <LegendDot color={FLOW.expense} label="Perda de capital" /> : null}
          </div>
          {isLoading && chartData.length === 0 ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <div className="h-64" aria-busy={isLoading} aria-label={`Evolução do patrimônio, ${periodLabel}`}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={CHART.grid} />
                  <XAxis dataKey="month" {...axisProps} interval="preserveStartEnd" minTickGap={12} />
                  <YAxis {...axisProps} width={72} tickFormatter={privateAxis} />
                  <Tooltip
                    cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                    content={({ active, payload, label }) => {
                      const row = payload?.[0]?.payload
                      if (!row) return null
                      return (
                        <ChartTooltip
                          active={active}
                          label={label}
                          payload={[
                            { dataKey: 'applied', value: row.applied, color: FLOW.investment },
                            { dataKey: 'gain', value: row.gain, color: row.gain >= 0 ? FLOW.income : FLOW.expense },
                          ]}
                          names={{ applied: 'Valor aplicado', gain: row.gain >= 0 ? 'Ganho de capital' : 'Perda de capital' }}
                          valueFormatter={(value) => privateMoney(Math.abs(value))}
                          footer={() => `Patrimônio: ${privateMoney(row.patrimonio)}`}
                        />
                      )
                    }}
                  />
                  <Bar dataKey="base" stackId="patrimonio" fill={FLOW.investment} maxBarSize={32} {...chartAnimation} />
                  <Bar dataKey="ganho" stackId="patrimonio" fill={FLOW.income} maxBarSize={32} radius={[4, 4, 0, 0]} {...chartAnimation} />
                  <Bar dataKey="perda" stackId="patrimonio" fill={FLOW.expense} maxBarSize={32} radius={[4, 4, 0, 0]} {...chartAnimation} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}
