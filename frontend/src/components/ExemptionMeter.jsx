import { taxReportApi } from '../lib/dataApi'
import { formatCurrency, formatPercent, monthLabel } from '../lib/format'
import { keepPreviousData, useQuery } from '../lib/queries'
import useDebouncedValue from '../lib/useDebouncedValue'
import { AlertMessage, Badge, Panel, PanelHeader, Skeleton, cx } from './ui'

// Isentometro (GET /api/tax-report/exemption): vendas de acoes do mes contra o
// limite de R$ 20 mil. Mesma apuracao do relatorio anual. ETFs e BDRs nao entram
// no limite (pagam 15% sobre todo ganho); o IR deles aparece a parte.

function meterTone(data) {
  if (!data.exempt) return 'bg-rose-500'
  return data.percent >= 80 ? 'bg-amber-500' : 'bg-emerald-500'
}

export function ExemptionMeter({ month, className = '' }) {
  const query = useQuery({
    queryKey: ['investimentos', 'isencao', month],
    queryFn: () => taxReportApi.exemption({ month }),
    placeholderData: keepPreviousData,
  })
  const data = query.data

  return (
    <Panel className={cx('overflow-clip', className)}>
      <PanelHeader
        title={`Isenção de ações — ${monthLabel(month)}`}
        description="Vender até R$ 20.000 em ações no mês deixa o ganho isento. ETFs, BDRs e FIIs não têm isenção."
        actions={data ? (
          data.exempt ? <Badge tone="success">Isento até aqui</Badge> : <Badge tone="danger">Passou do limite</Badge>
        ) : null}
      />
      <div className="px-5 py-4 sm:px-6">
        {!data ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <>
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="text-zinc-700">
                <span className="num font-semibold text-zinc-950">{formatCurrency(data.stock_sales)}</span> vendidos de {formatCurrency(data.limit)}
              </span>
              <span className="text-zinc-600">
                {data.exempt
                  ? <>Ainda cabem <span className="num font-semibold text-zinc-900">{formatCurrency(data.remaining)}</span></>
                  : <>IR estimado de ações: <span className="num font-semibold text-rose-600">{formatCurrency(data.stock_tax)}</span></>}
              </span>
            </div>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-zinc-100">
              <div className={cx('bar-grow h-full rounded-full', meterTone(data))} style={{ width: `${Math.min(data.percent, 100)}%` }} />
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
              <span>{formatPercent(data.percent, 1)} do limite</span>
              {data.stock_result ? <span>Resultado das vendas: {formatCurrency(data.stock_result)}</span> : null}
              {data.exempt && data.stock_tax ? <span>IR de ETFs e BDRs: {formatCurrency(data.stock_tax)}</span> : null}
              {data.stock_loss_balance ? <span>Prejuízo a compensar: {formatCurrency(data.stock_loss_balance)}</span> : null}
              {data.reit_sales ? <span>FII vendidos: {formatCurrency(data.reit_sales)} (IR {formatCurrency(data.reit_tax)})</span> : null}
              {data.darf ? <span>DARF do mês: {formatCurrency(data.darf)}</span> : null}
            </div>
          </>
        )}
      </div>
    </Panel>
  )
}

// Aviso no formulario de venda, antes de salvar: a venda faz o mes passar de
// R$ 20 mil? So acoes em reais (FII nao tem isencao; exterior e anual). Com o
// ticker, o servidor diz se o papel e ETF ou BDR (`eligible` false).
export function SaleExemptionNotice({ date, amount, ticker }) {
  const month = String(date || '').slice(0, 7)
  const planned = useDebouncedValue(Math.round(Number(amount || 0) * 100) / 100, 400)
  const enabled = /^\d{4}-\d{2}$/.test(month) && planned > 0
  const query = useQuery({
    queryKey: ['investimentos', 'isencao', month, planned, ticker || ''],
    queryFn: () => taxReportApi.exemption({ month, planned_sale: planned, ...(ticker ? { ticker } : {}) }),
    enabled,
    placeholderData: keepPreviousData,
  })
  const data = enabled ? query.data : null
  if (!data || data.month !== month) return null

  // A isencao de R$ 20 mil e so de acoes: ETF e BDR pagam 15% sobre todo ganho,
  // e o ETF de renda fixa tem o IR retido na fonte.
  if (data.eligible === false) {
    return (
      <AlertMessage tone="info">
        {data.kind === 'ETF_RF'
          ? 'ETF de renda fixa: o IR é retido na fonte pelo administrador, fora do DARF e da isenção de R$ 20 mil das ações.'
          : 'ETFs e BDRs não têm a isenção de vendas até R$ 20 mil das ações: o ganho é tributado em 15%, e esta venda não conta no limite.'}
      </AlertMessage>
    )
  }

  if (data.would_exceed) {
    return (
      <AlertMessage tone="warning">
        Com esta venda, as vendas de ações de {monthLabel(month)} somam {formatCurrency(data.sales_after)} e passam de {formatCurrency(data.limit)}: o ganho do mês inteiro deixa de ser isento (15%). Cabem {formatCurrency(data.remaining)} sem perder a isenção.
      </AlertMessage>
    )
  }
  if (!data.exempt) {
    return (
      <AlertMessage tone="info">
        As vendas de ações de {monthLabel(month)} já passaram de {formatCurrency(data.limit)}: o ganho deste mês é tributado (15%).
      </AlertMessage>
    )
  }
  return (
    <p className="text-sm text-zinc-600">
      Isenção de {monthLabel(month)}: depois desta venda, ainda cabem {formatCurrency(Math.max(data.limit - data.sales_after, 0))} em vendas de ações.
    </p>
  )
}
