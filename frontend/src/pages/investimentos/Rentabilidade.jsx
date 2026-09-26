import { useMemo, useState } from 'react'
import { TrendingUp } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART, ChartTooltip, LegendDot, OTHER_COLOR, SERIES, axisProps, useChartAnimation } from '../../components/charts'
import {
  AlertMessage,
  Badge,
  EmptyState,
  ListSkeleton,
  PageHeader,
  Panel,
  PanelHeader,
  SegmentedControl,
  Skeleton,
  SummaryPanel,
  cx,
} from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency, formatPercent, shortMonthLabel } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import { getClassLabel } from './helpers'

// O backend limita a janela a 60 meses (GET /api/investments/returns).
const PERIODS = [
  { value: 6, label: '6M' },
  { value: 12, label: '1A' },
  { value: 24, label: '2A' },
  { value: 36, label: '3A' },
  { value: 60, label: '5A' },
]
const DEFAULT_PERIOD = 12
const PERIOD_STORAGE_KEY = '@financeMVP:rentabilidadePeriod'
const MONTH_NAMES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

function readStoredPeriod() {
  try {
    const saved = Number(localStorage.getItem(PERIOD_STORAGE_KEY))
    return PERIODS.some((period) => period.value === saved) ? saved : DEFAULT_PERIOD
  } catch {
    return DEFAULT_PERIOD
  }
}

function hasValue(value) {
  return value !== null && value !== undefined
}

// Verde/vermelho so para ganho e perda; sem dado, um traco neutro.
function toneOf(value) {
  if (!hasValue(value)) return 'muted'
  if (value > 0) return 'gain'
  if (value < 0) return 'loss'
  return 'neutral'
}

const TONE_CLASS = {
  gain: 'text-emerald-700',
  loss: 'text-rose-600',
  neutral: 'text-zinc-700',
  muted: 'text-zinc-400',
}

function signedPercent(value) {
  return hasValue(value) ? formatPercent(value, 2, { signed: true }) : '—'
}

function Pct({ value, className = '' }) {
  return <span className={cx('tabular', TONE_CLASS[toneOf(value)], className)}>{signedPercent(value)}</span>
}

function percentAxis(value) {
  return `${Number(value || 0).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}

function ReturnsChart({ series, cdiAvailable }) {
  const chartAnimation = useChartAnimation()
  const data = useMemo(() => series.map((item) => ({
    month: item.month_key,
    carteira: item.accumulated_percent,
    cdi: cdiAvailable ? item.cdi_accumulated_percent : null,
  })), [series, cdiAvailable])

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-4">
        <LegendDot color={SERIES[0]} label="Carteira (TWR)" shape="line" />
        {cdiAvailable ? <LegendDot color={OTHER_COLOR} label="CDI" shape="line" /> : null}
      </div>
      <div className="h-64" aria-label="Rentabilidade acumulada da carteira">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={CHART.grid} />
            <XAxis dataKey="month" {...axisProps} tickFormatter={shortMonthLabel} interval="preserveStartEnd" minTickGap={12} />
            <YAxis {...axisProps} width={56} tickFormatter={percentAxis} />
            <ReferenceLine y={0} stroke={CHART.axis} />
            <Tooltip
              cursor={{ stroke: CHART.axis }}
              content={(
                <ChartTooltip
                  names={{ carteira: 'Carteira', cdi: 'CDI' }}
                  labelFormatter={shortMonthLabel}
                  valueFormatter={signedPercent}
                />
              )}
            />
            {cdiAvailable ? (
              <Line
                type="monotone"
                dataKey="cdi"
                stroke={OTHER_COLOR}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
                {...chartAnimation}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="carteira"
              stroke={SERIES[0]}
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 5, strokeWidth: 2, stroke: 'rgb(var(--white))' }}
              {...chartAnimation}
              animationBegin={80}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}

// Ano x mes. No desktop uma tabela; no celular, um bloco por ano (grade de meses).
function YearMonthTable({ years }) {
  const rows = [...years].reverse()
  return (
    <>
      <div className="hidden lg:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-zinc-500">
              <th className="px-5 py-2 text-left font-medium">Ano</th>
              {MONTH_NAMES.map((name) => <th key={name} className="num px-2 py-2 font-medium">{name}</th>)}
              <th className="num px-5 py-2 font-medium">No ano</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {rows.map((row) => (
              <tr key={row.year}>
                <td className="px-5 py-2 font-semibold text-zinc-800">{row.year}</td>
                {row.months.map((value, index) => (
                  <td key={index} className="num px-2 py-2"><Pct value={value} /></td>
                ))}
                <td className="num px-5 py-2 font-semibold"><Pct value={row.total_percent} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="divide-y divide-zinc-100 lg:hidden">
        {rows.map((row) => (
          <section key={row.year} className="px-4 py-3">
            <div className="mb-2 flex items-baseline justify-between">
              <h3 className="text-sm font-semibold text-zinc-800">{row.year}</h3>
              <span className="text-sm font-semibold"><Pct value={row.total_percent} /></span>
            </div>
            <dl className="grid grid-cols-4 gap-x-3 gap-y-2 text-xs">
              {row.months.map((value, index) => (
                <div key={index} className="min-w-0">
                  <dt className="text-zinc-500">{MONTH_NAMES[index]}</dt>
                  <dd className="font-medium"><Pct value={value} /></dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </>
  )
}

function AssetsTable({ assets, privateMoney }) {
  return (
    <>
      <ul className="divide-y divide-zinc-100 lg:hidden">
        {assets.map((asset) => (
          <li key={asset.key} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-zinc-900">{asset.ticker}</p>
              <p className="text-xs text-zinc-500">
                {getClassLabel(asset.class)} · desde {shortMonthLabel(asset.since)}{asset.capped ? '*' : ''}
                {asset.open ? '' : ' · encerrado'}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-sm font-semibold"><Pct value={asset.twr_percent} /></p>
              <p className="text-xs text-zinc-500 tabular">{asset.open ? privateMoney(asset.current_value) : '—'}</p>
            </div>
          </li>
        ))}
      </ul>
      <div className="hidden lg:block">
        <table className="app-table table-fixed">
          <colgroup>
            <col />
            <col className="w-36" />
            <col className="w-32" />
            <col className="w-40" />
            <col className="w-32" />
          </colgroup>
          <thead>
            <tr>
              <th>Ativo</th>
              <th>Classe</th>
              <th>Desde</th>
              <th className="text-right">Valor bruto</th>
              <th className="text-right">TWR</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => (
              <tr key={asset.key}>
                <td className="font-semibold text-zinc-900">
                  {asset.ticker}
                  {asset.open ? null : <Badge className="ml-2">encerrado</Badge>}
                </td>
                <td className="text-zinc-600">{getClassLabel(asset.class)}</td>
                <td className="text-zinc-600">
                  {shortMonthLabel(asset.since)}
                  {asset.capped ? <span title="Comprado antes da janela: conta a partir do início dela."> *</span> : null}
                </td>
                <td className="num">{asset.open ? privateMoney(asset.current_value) : '—'}</td>
                <td className="num font-semibold"><Pct value={asset.twr_percent} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// Rentabilidade ponderada no tempo (TWR): nao depende de quando o dinheiro
// entrou, entao compara com o CDI. Percentuais ficam visiveis no modo privado;
// so os valores em reais somem.
export default function Rentabilidade() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [months, setMonths] = useState(readStoredPeriod)
  const returnsQuery = useQuery({
    queryKey: ['investimentos', 'rentabilidade', months],
    queryFn: () => investmentsApi.returns({ months }),
    placeholderData: keepPreviousData,
  })
  const data = returnsQuery.data
  const error = queryErrorMessage(returnsQuery, 'Não foi possível calcular a rentabilidade.')

  const changePeriod = (value) => {
    setMonths(value)
    try {
      localStorage.setItem(PERIOD_STORAGE_KEY, String(value))
    } catch {
      // Preferencia so desta sessao.
    }
  }

  const periodHint = data?.period
    ? `${shortMonthLabel(data.period.start)} a ${shortMonthLabel(data.period.end)} · TWR, valor bruto`
    : 'TWR, valor bruto'
  const empty = data && !hasValue(data.twr_percent) && !(data.assets || []).length
  const lastValue = data?.series?.length ? data.series[data.series.length - 1].value : null
  const anyCapped = (data?.assets || []).some((asset) => asset.capped)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Rentabilidade"
        description="Retorno ponderado no tempo (TWR): aportes e resgates não distorcem o percentual, então dá para comparar com o CDI."
        actions={<SegmentedControl items={PERIODS} value={months} onChange={changePeriod} />}
      />

      <AlertMessage tone="warning" message={error} />

      {returnsQuery.isPending ? (
        <Panel><ListSkeleton rows={5} /></Panel>
      ) : empty ? (
        <Panel className="p-5">
          <EmptyState
            icon={TrendingUp}
            title="Sem rentabilidade no período"
            message="A rentabilidade aparece depois da primeira compra registrada em Operações."
          />
        </Panel>
      ) : data ? (
        <>
          <SummaryPanel
            lead={{
              label: 'Rentabilidade no período',
              value: signedPercent(data.twr_percent),
              hint: periodHint,
              tone: toneOf(data.twr_percent),
            }}
            figures={[
              { label: 'No ano', value: signedPercent(data.ytd_percent), tone: toneOf(data.ytd_percent) },
              {
                label: '% do CDI',
                value: hasValue(data.percent_of_cdi) ? formatPercent(data.percent_of_cdi, 0) : '—',
                hint: hasValue(data.cdi_percent) ? `CDI no período: ${formatPercent(data.cdi_percent)}` : 'CDI indisponível',
              },
              {
                label: 'Carteira hoje',
                value: hasValue(lastValue) ? privateMoney(lastValue) : '—',
                hint: 'Valor bruto',

              },
            ]}
          />

          <Panel>
            <PanelHeader
              title="Rentabilidade acumulada"
              description={data.cdi_available ? 'Carteira e CDI acumulados desde o início da janela.' : 'Carteira acumulada desde o início da janela.'}
            />
            <div className="p-5" aria-busy={returnsQuery.isFetching}>
              {returnsQuery.isFetching && !data.series.length ? (
                <Skeleton className="h-64 w-full" />
              ) : (
                <ReturnsChart series={data.series} cdiAvailable={data.cdi_available} />
              )}
            </div>
          </Panel>

          <Panel className="overflow-clip">
            <PanelHeader title="Mês a mês" description="Retorno de cada mês e o acumulado no ano. O mês atual vai até hoje." />
            <YearMonthTable years={data.years || []} />
          </Panel>

          <Panel className="overflow-clip">
            <PanelHeader
              title="Por ativo"
              description="TWR de cada ativo desde a primeira compra, limitado à janela escolhida."
              actions={<Badge>{(data.assets || []).length} ativo(s)</Badge>}
            />
            {(data.assets || []).length ? (
              <AssetsTable assets={data.assets} privateMoney={privateMoney} />
            ) : (
              <div className="p-5"><EmptyState icon={TrendingUp} title="Nenhum ativo no período" message="Nenhuma posição ou operação na janela escolhida." className="min-h-32" /></div>
            )}
            {anyCapped ? (
              <p className="border-t border-zinc-100 px-5 py-3 text-xs text-zinc-500">
                * Comprado antes da janela: o retorno conta a partir do início dela ({shortMonthLabel(data.period.start)}). Escolha um período maior para ver mais.
              </p>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader title="Como é calculado" description={data.basis_label} />
            <ul className="list-disc space-y-1 px-5 pb-5 pl-9 text-xs text-zinc-600">
              {(data.notes || []).map((note) => <li key={note}>{note}</li>)}
            </ul>
          </Panel>
        </>
      ) : null}
    </div>
  )
}
