import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART, ChartTooltip, DonutChart, FLOW, LegendDot, axisProps, compactAxis, useChartAnimation } from '../../components/charts'
import { AlertMessage, Panel, PanelHeader, SegmentedControl, Skeleton } from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency, shortMonthLabel } from '../../lib/format'
import { usePrivateAxisFormatter, usePrivateFormatter } from '../../lib/privacy'
import { keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'

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

const NO_POINTS = []

// Alocacao por categoria (valor bruto de mercado: Acoes, ETFs, FIIs, Renda
// fixa, Tesouro Direto...; `category_label` da posicao) e evolucao mensal do patrimonio.
// A barra de cada mes e o valor aplicado com o ganho de capital empilhado em
// cima; num mes de perda, a base vira o patrimonio e a perda (vermelha) completa
// a barra ate o valor aplicado — a altura total nunca esconde o prejuizo.
// As barras sao brutas (valor de mercado), a mesma base do "Carteira" no topo
// da Posicao e da rosca ao lado; o liquido do IR estimado da renda fixa fica no
// tooltip, como o "Liquido estimado" do resumo.
export default function PortfolioOverview({ assets, getClassLabel }) {
  const chartAnimation = useChartAnimation()
  // A carteira inteira some no modo privado; as proporcoes (%) ficam.
  const privateMoney = usePrivateFormatter(formatCurrency)
  const privateAxis = usePrivateAxisFormatter(compactAxis)
  const allocation = useMemo(() => {
    const byClass = {}
    assets.forEach((asset) => {
      const label = asset.category_label || getClassLabel(asset.class)
      byClass[label] = (byClass[label] || 0) + Number(asset.current_value || 0)
    })
    return Object.entries(byClass).map(([name, value]) => ({ name, value }))
  }, [assets, getClassLabel])

  const [months, setMonths] = useState(readStoredPeriod)
  // Uma query por periodo: trocar de 12 para 24 meses e voltar nao busca de novo.
  const historyQuery = useQuery({
    queryKey: ['investimentos', 'historico', months],
    queryFn: () => investmentsApi.history({ months }),
    placeholderData: keepPreviousData,
  })
  const evolution = historyQuery.data?.evolution || NO_POINTS
  const isLoading = historyQuery.isFetching
  const error = queryErrorMessage(historyQuery, 'Não foi possível carregar a evolução do patrimônio.')

  const changePeriod = (value) => {
    setMonths(value)
    try {
      localStorage.setItem(PERIOD_STORAGE_KEY, String(value))
    } catch {
      // Preferencia so desta sessao.
    }
  }


  const chartData = useMemo(() => evolution.map((item) => {
    const applied = Number(item.valorAplicado || 0)
    const patrimonio = Number(item.patrimonioBruto ?? item.patrimonio ?? 0)
    const gain = Number(item.ganhoCapitalBruto ?? item.ganhoCapitalReal ?? 0)
    return {
      month: item.month,
      applied,
      patrimonio,
      patrimonioLiquido: Number(item.patrimonio || 0),
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
        <PanelHeader title="Alocação" description="Valor de mercado bruto por categoria de ativo." />
        <div className="p-5">
          <DonutChart data={allocation} centerLabel="Carteira" height={190} stacked formatter={privateMoney} />
        </div>
      </Panel>

      <Panel className="xl:col-span-2">
        <PanelHeader
          title="Evolução do Patrimônio"
          description="Valor aplicado e ganho de capital bruto (valor de mercado) no fim de cada mês."
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
                  <XAxis dataKey="month" {...axisProps} tickFormatter={shortMonthLabel} interval="preserveStartEnd" minTickGap={12} />
                  <YAxis {...axisProps} width={56} tickFormatter={privateAxis} />
                  <Tooltip
                    cursor={{ fill: 'rgb(var(--zinc-950) / 0.05)' }}
                    content={({ active, payload, label }) => {
                      const row = payload?.[0]?.payload
                      if (!row) return null
                      return (
                        <ChartTooltip
                          active={active}
                          label={shortMonthLabel(label)}
                          payload={[
                            { dataKey: 'applied', value: row.applied, color: FLOW.investment },
                            { dataKey: 'gain', value: row.gain, color: row.gain >= 0 ? FLOW.income : FLOW.expense },
                          ]}
                          names={{ applied: 'Valor aplicado', gain: row.gain >= 0 ? 'Ganho de capital' : 'Perda de capital' }}
                          valueFormatter={(value) => privateMoney(Math.abs(value))}
                          footer={() => (
                            <>
                              <p>Patrimônio bruto: {privateMoney(row.patrimonio)}</p>
                              {row.patrimonioLiquido !== row.patrimonio ? (
                                <p>Líquido de IR estimado: {privateMoney(row.patrimonioLiquido)}</p>
                              ) : null}
                            </>
                          )}
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
