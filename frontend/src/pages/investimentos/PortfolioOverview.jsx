import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ANIMATION, CHART, ChartTooltip, DonutChart, FLOW, axisProps } from '../../components/charts'
import { Panel, PanelHeader } from '../../components/ui'
import { formatCurrency } from '../../lib/format'

// Alocacao por classe (valor bruto de mercado) e rentabilidade de cada ativo.
// Rentabilidade e divergente: verde acima de zero, vermelho abaixo, e a barra
// cresce para lados opostos — o sinal nao depende so da cor.
export default function PortfolioOverview({ assets, getClassLabel }) {
  const allocation = useMemo(() => {
    const byClass = {}
    assets.forEach((asset) => {
      const label = getClassLabel(asset.class)
      byClass[label] = (byClass[label] || 0) + Number(asset.current_value || 0)
    })
    return Object.entries(byClass).map(([name, value]) => ({ name, value }))
  }, [assets, getClassLabel])

  const performance = useMemo(() => {
    const sorted = assets
      .map((asset) => ({
        name: asset.name,
        value: Number(asset.profitability_percent || 0),
        current: Number(asset.current_value || 0),
      }))
      .sort((a, b) => b.value - a.value)
    return sorted.length > 12 ? [...sorted.slice(0, 6), ...sorted.slice(-6)] : sorted
  }, [assets])

  const chartHeight = Math.max(performance.length * 30 + 24, 160)

  return (
    <div className="stagger grid grid-cols-1 gap-6 xl:grid-cols-2">
      <Panel>
        <PanelHeader title="Alocação" description="Valor de mercado bruto por classe de ativo." />
        <div className="p-5">
          <DonutChart data={allocation} centerLabel="Carteira" height={190} />
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Rentabilidade por ativo"
          description={performance.length < assets.length ? 'Os 6 melhores e os 6 piores, do maior para o menor.' : 'Do maior para o menor retorno.'}
        />
        <div className="p-5">
          <div style={{ height: chartHeight }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={performance} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid horizontal={false} stroke={CHART.grid} />
                <XAxis type="number" {...axisProps} tickFormatter={(value) => `${value}%`} />
                <YAxis type="category" dataKey="name" {...axisProps} width={96} tick={{ fill: '#52525b', fontSize: 12 }} />
                <ReferenceLine x={0} stroke={CHART.axis} />
                <Tooltip
                  cursor={{ fill: 'rgba(24,24,27,0.04)' }}
                  content={(
                    <ChartTooltip
                      names={{ value: 'Rentabilidade' }}
                      valueFormatter={(value) => `${value > 0 ? '+' : ''}${Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`}
                      footer={(payload) => `Valor atual: ${formatCurrency(payload?.[0]?.payload?.current)}`}
                    />
                  )}
                />
                <Bar dataKey="value" maxBarSize={18} radius={[0, 4, 4, 0]} {...ANIMATION}>
                  {performance.map((item, index) => (
                    <Cell key={`${item.name}-${index}`} fill={item.value >= 0 ? FLOW.income : FLOW.expense} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Panel>
    </div>
  )
}
