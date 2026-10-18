import { useMemo, useState } from 'react'
import { Bar, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart3, ChevronDown } from 'lucide-react'
import { CHART, ChartTooltip, FLOW, LegendDot, SERIES, axisProps, compactAxis, useChartAnimation } from '../../components/charts'
import { AlertMessage, EmptyState, Expand, Panel, PanelHeader, SegmentedControl, Skeleton, cx } from '../../components/ui'
import { contributionsApi } from '../../lib/dataApi'
import { formatCurrency, formatSignedCurrency, monthLabel, shortMonthLabel } from '../../lib/format'
import { usePrivateAxisFormatter, usePrivateFormatter } from '../../lib/privacy'
import { keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import { ASSET_CLASSES, getClassLabel } from './helpers'

const PERIODS = [
  { value: 6, label: '6m' },
  { value: 12, label: '12m' },
  { value: 24, label: '24m' },
  { value: 60, label: '5a' },
]

// Aporte e dinheiro indo para a carteira: o azul de Investimentos no Inicio.
// Resgate volta para a conta e e desenhado abaixo do zero (a posicao carrega o
// sinal); laranja, a cor categorica seguinte, porque nao e ganho nem perda.
// O liquido vai no rodape do tooltip: como serie, o `absolute` (que mostra o
// resgate em modulo) apagaria o sinal dele.
const COLORS = { aportes: FLOW.investment, resgates: SERIES[1] }
const NAMES = { aportes: 'Aportes', resgates: 'Resgates' }

// Aportes x resgates por mes (GET /api/investments/contributions), em reais:
// compra pelo valor bruto, venda/resgate pelo bruto recebido; bonificacao fora.
export default function AportesChart() {
  const [open, setOpen] = useState(true)
  const [months, setMonths] = useState(12)
  const [assetClass, setAssetClass] = useState('')
  const money = usePrivateFormatter(formatCurrency)
  const signedMoney = usePrivateFormatter(formatSignedCurrency)
  const axisMoney = usePrivateAxisFormatter(compactAxis)
  const chartAnimation = useChartAnimation()

  const query = useQuery({
    queryKey: ['investimentos', 'aportes', months, assetClass],
    queryFn: () => contributionsApi.get({ months, asset_class: assetClass || undefined }),
    placeholderData: keepPreviousData,
    enabled: open,
  })
  const data = query.data

  const chartData = useMemo(() => (data?.months || []).map((item) => ({
    month: item.month,
    aportes: Number(item.aportes || 0),
    resgates: -Number(item.resgates || 0),
    liquido: Number(item.liquido || 0),
  })), [data])

  const totals = data?.totals

  return (
    <Panel className="overflow-clip">
      <PanelHeader
        title="Aportes e resgates"
        description="Por mês, em reais: compras contra vendas e resgates (valores brutos, sem custos). Bonificações não entram."
        actions={(
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="inline-flex h-11 items-center gap-1.5 rounded-full px-2.5 text-sm lg:h-8 font-semibold text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-950"
          >
            {open ? 'Ocultar' : 'Mostrar'}
            <ChevronDown className={cx('h-4 w-4 transition-transform', open && 'rotate-180')} />
          </button>
        )}
      />
      <Expand open={open}>
        <div className="space-y-4 p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <SegmentedControl items={PERIODS} value={months} onChange={setMonths} />
            <select
              value={assetClass}
              onChange={(event) => setAssetClass(event.target.value)}
              className="app-select sm:w-56"
              aria-label="Classe de ativo"
            >
              <option value="">Todas as classes</option>
              {ASSET_CLASSES.map((key) => <option key={key} value={key}>{getClassLabel(key)}</option>)}
            </select>
          </div>

          <AlertMessage message={queryErrorMessage(query, 'Não foi possível carregar os aportes.')} />

          {query.isPending ? (
            <Skeleton className="h-64 w-full" />
          ) : data && totals.count === 0 ? (
            <EmptyState icon={BarChart3} title="Nenhuma operação no período." message="Compras, vendas e resgates registrados aparecem aqui, mês a mês." className="min-h-40" />
          ) : data ? (
            <>
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <dt className="text-xs text-zinc-500">Aportes</dt>
                  <dd className="font-semibold tabular text-zinc-950">{money(totals.aportes)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-zinc-500">Resgates</dt>
                  <dd className="font-semibold tabular text-zinc-950">{money(totals.resgates)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-zinc-500">Líquido</dt>
                  <dd className="font-semibold tabular text-zinc-950">{signedMoney(totals.liquido)}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <LegendDot color={COLORS.aportes} label="Aportes" />
                <LegendDot color={COLORS.resgates} label="Resgates" />
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} stackOffset="sign" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke={CHART.grid} />
                    <XAxis dataKey="month" {...axisProps} tickFormatter={shortMonthLabel} interval="preserveStartEnd" minTickGap={12} />
                    <YAxis tickFormatter={axisMoney} {...axisProps} width={56} />
                    <ReferenceLine y={0} stroke={CHART.axis} />
                    <Tooltip
                      cursor={{ fill: 'rgb(var(--zinc-950) / 0.05)' }}
                      content={(
                        <ChartTooltip
                          absolute
                          names={NAMES}
                          valueFormatter={money}
                          labelFormatter={(label) => monthLabel(label)}
                          footer={(payload) => `Líquido ${signedMoney(payload?.[0]?.payload?.liquido)}`}
                        />
                      )}
                    />
                    <Bar dataKey="aportes" stackId="flow" fill={COLORS.aportes} maxBarSize={24} radius={[4, 4, 0, 0]} {...chartAnimation} />
                    <Bar dataKey="resgates" stackId="flow" fill={COLORS.resgates} maxBarSize={24} {...chartAnimation} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : null}
        </div>
      </Expand>
    </Panel>
  )
}
