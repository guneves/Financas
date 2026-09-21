// Kit de graficos compartilhado.
//
// Toda pagina que desenha um grafico importa cores, eixos e tooltip daqui, para
// que os graficos do app leiam como um sistema so. A paleta categorica segue uma
// ordem fixa validada para daltonismo (azul, laranja, verde-agua, amarelo...) —
// a cor segue a entidade, nunca a posicao no ranking, e nunca e "ciclada".
import { useId, useMemo, useState } from 'react'
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { formatCurrency } from '../lib/format'
import { cx } from './ui'

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
export const OTHER_COLOR = '#a1a1aa'

// Entradas e saidas: verde/vermelho por convencao, mas o par fica na faixa de
// alerta para daltonismo — por isso os graficos de fluxo desenham as saidas
// abaixo do zero. A posicao carrega o sinal; a cor so reforca.
export const FLOW = {
  income: '#1baf7a',
  expense: '#e34948',
  net: '#18181b',
}

export const CHART = {
  grid: '#eeeeec',
  axis: '#d4d4d8',
  tick: '#8a8a93',
  ink: '#18181b',
}

export const ANIMATION = {
  isAnimationActive: true,
  animationDuration: 900,
  animationEasing: 'ease-out',
}

export const axisProps = {
  tick: { fill: CHART.tick, fontSize: 12 },
  tickLine: false,
  axisLine: false,
}

export function compactCurrency(value) {
  const numeric = Number(value || 0)
  const absolute = Math.abs(numeric)
  const sign = numeric < 0 ? '-' : ''
  if (absolute >= 1_000_000) {
    return `${sign}R$ ${(absolute / 1_000_000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} mi`
  }
  if (absolute >= 1000) {
    return `${sign}R$ ${(absolute / 1000).toLocaleString('pt-BR', { maximumFractionDigits: absolute >= 10000 ? 0 : 1 })} mil`
  }
  return `${sign}R$ ${absolute.toLocaleString('pt-BR', { maximumFractionDigits: 0 })}`
}

// Tooltip unico do app. `rows` permite trocar o rotulo de cada serie; valores
// negativos (saidas desenhadas abaixo do zero) aparecem em modulo.
export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  names = {},
  valueFormatter = formatCurrency,
  absolute = false,
  footer,
}) {
  if (!active || !payload?.length) return null
  const rows = payload.filter((item) => item.value !== null && item.value !== undefined)
  if (!rows.length) return null

  return (
    <div className="min-w-44 animate-scale-in rounded-lg border border-zinc-200 bg-white/95 px-3 py-2.5 text-sm shadow-lift backdrop-blur">
      {label !== undefined && label !== null ? (
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {labelFormatter ? labelFormatter(label, payload) : label}
        </p>
      ) : null}
      <div className="space-y-1">
        {rows.map((item) => {
          const color = item.color || item.payload?.fill || item.stroke
          const value = absolute ? Math.abs(Number(item.value)) : item.value
          return (
            <div key={item.dataKey || item.name} className="flex items-center justify-between gap-4">
              <span className="flex items-center gap-2 text-zinc-600">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                {names[item.dataKey] || names[item.name] || item.name}
              </span>
              <span className="font-semibold tabular text-zinc-950">{valueFormatter(value)}</span>
            </div>
          )
        })}
      </div>
      {footer ? <div className="mt-2 border-t border-zinc-100 pt-2 text-xs text-zinc-500">{footer(payload)}</div> : null}
    </div>
  )
}

export function LegendDot({ color, label, className = '', shape = 'dot' }) {
  return (
    <span className={cx('inline-flex items-center gap-1.5 text-xs font-medium text-zinc-600', className)}>
      <span
        className={cx('shrink-0', shape === 'line' ? 'h-0.5 w-3.5 rounded-full' : 'h-2.5 w-2.5 rounded-full')}
        style={{ backgroundColor: color }}
      />
      {label}
    </span>
  )
}

// Linha minima com lavagem de area — cabe dentro de um MetricCard.
export function Sparkline({ data, dataKey = 'value', color = SERIES[0], formatter = formatCurrency, labelKey = 'label' }) {
  const gradientId = useId().replace(/:/g, '')
  if (!data || data.length < 2) return null

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Tooltip
          cursor={{ stroke: CHART.axis, strokeWidth: 1 }}
          content={(
            <ChartTooltip
              labelFormatter={(_, payload) => payload?.[0]?.payload?.[labelKey]}
              names={{ [dataKey]: 'Valor' }}
              valueFormatter={formatter}
            />
          )}
        />
        <Area
          type="monotone"
          dataKey={dataKey}
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 2, stroke: '#fff' }}
          {...ANIMATION}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// Rosca com total no centro e legenda ranqueada ao lado. Passar o mouse numa
// fatia (ou numa linha da legenda) apaga as outras.
//
// `data`: [{ name, value, color? }]. Mais de `maxSlices` itens viram "Outros".
export function DonutChart({
  data,
  centerLabel = 'Total',
  formatter = formatCurrency,
  maxSlices = 6,
  height = 220,
  legend = true,
}) {
  const [hovered, setHovered] = useState(null)

  const slices = useMemo(() => {
    const sorted = [...(data || [])].filter((item) => item.value > 0).sort((a, b) => b.value - a.value)
    const colored = sorted.map((item, index) => ({ ...item, color: item.color || SERIES[index] || OTHER_COLOR }))
    if (colored.length <= maxSlices) return colored
    const head = colored.slice(0, maxSlices - 1)
    const rest = colored.slice(maxSlices - 1).reduce((acc, item) => acc + item.value, 0)
    return [...head, { name: 'Outros', value: rest, color: OTHER_COLOR }]
  }, [data, maxSlices])

  const total = slices.reduce((acc, item) => acc + item.value, 0)
  const focus = hovered !== null ? slices[hovered] : null

  return (
    <div className={cx('grid items-center gap-5', legend && 'sm:grid-cols-[minmax(0,220px)_1fr]')}>
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              innerRadius="68%"
              outerRadius="96%"
              paddingAngle={slices.length > 1 ? 2 : 0}
              cornerRadius={4}
              stroke="#fff"
              strokeWidth={2}
              startAngle={90}
              endAngle={-270}
              onMouseLeave={() => setHovered(null)}
              {...ANIMATION}
              animationDuration={1000}
            >
              {slices.map((slice, index) => (
                <Cell
                  key={slice.name}
                  fill={slice.color}
                  fillOpacity={hovered === null || hovered === index ? 1 : 0.28}
                  onMouseEnter={() => setHovered(index)}
                  style={{ transition: 'fill-opacity 200ms ease', outline: 'none', cursor: 'pointer' }}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="max-w-[60%] truncate text-xs font-semibold uppercase tracking-wide text-zinc-500">
            {focus ? focus.name : centerLabel}
          </span>
          <span className="mt-0.5 text-lg font-bold tabular tracking-tight text-zinc-950">
            {formatter(focus ? focus.value : total)}
          </span>
          {focus && total > 0 ? (
            <span className="text-xs font-semibold tabular text-zinc-500">
              {((focus.value / total) * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%
            </span>
          ) : null}
        </div>
      </div>

      {legend ? (
        <ul className="space-y-1">
          {slices.map((slice, index) => {
            const share = total > 0 ? (slice.value / total) * 100 : 0
            return (
              <li
                key={slice.name}
                onMouseEnter={() => setHovered(index)}
                onMouseLeave={() => setHovered(null)}
                className={cx(
                  'rounded-lg px-2.5 py-2 transition-colors',
                  hovered === index ? 'bg-zinc-50' : ''
                )}
              >
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex min-w-0 items-center gap-2 font-medium text-zinc-700">
                    <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: slice.color }} />
                    <span className="truncate">{slice.name}</span>
                  </span>
                  <span className="flex shrink-0 items-baseline gap-2">
                    <span className="text-xs font-semibold tabular text-zinc-400">
                      {share.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%
                    </span>
                    <span className="font-semibold tabular text-zinc-950">{formatter(slice.value)}</span>
                  </span>
                </div>
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-zinc-100">
                  <div
                    className="bar-grow h-full rounded-full"
                    style={{ width: `${share}%`, backgroundColor: slice.color, animationDelay: `${index * 60}ms` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
