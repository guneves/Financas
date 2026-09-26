import { useState } from 'react'
import { Copy, Download, FileText } from 'lucide-react'
import { taxReportApi } from '../../lib/dataApi'
import { formatCurrency, monthKey } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'
import { keepPreviousData, queryErrorMessage, useQuery } from '../../lib/queries'
import { toast } from '../../lib/toast'
import { ExemptionMeter } from '../../components/ExemptionMeter'
import { AlertMessage, Badge, Button, EmptyState, IconButton, ListSkeleton, PageHeader, Panel, PanelHeader } from '../../components/ui'

const MONTH_NAMES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

function monthName(key) {
  const [year, month] = String(key).split('-')
  return `${MONTH_NAMES[Number(month) - 1]}/${year}`
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast('Discriminação copiada.')
  } catch {
    toast('Não foi possível copiar; selecione o texto na tabela.', { tone: 'info' })
  }
}

// Relatorio anual de IR (GET /api/tax-report): apoio para a declaracao, a
// partir do que foi lancado. Padrao: o ano passado (o que se declara agora).
export default function ImpostoRenda() {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const [year, setYear] = useState(() => new Date().getFullYear() - 1)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const reportQuery = useQuery({
    queryKey: ['investimentos', 'ir', year],
    queryFn: () => taxReportApi.get(year),
    placeholderData: keepPreviousData,
  })
  const report = reportQuery.data
  const years = report?.available_years?.length ? report.available_years : [year]
  const yearOptions = [...new Set([year, ...years, new Date().getFullYear()])].sort((a, b) => b - a)
  const months = report?.renda_variavel?.months || []
  const activeMonths = months.filter((item) => item.stocks.sales || item.reits.sales || item.darf || item.darf_carried)

  const handleExport = async () => {
    setExporting(true)
    setExportError('')
    try {
      const filename = await taxReportApi.exportFile(year)
      toast(`${filename} baixado.`)
    } catch (error) {
      setExportError(error.message || 'Não foi possível exportar.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Imposto de renda"
        description="Bens e direitos, renda variável mês a mês, rendimentos e exterior — para montar a declaração."
        actions={(
          <>
            <select
              aria-label="Ano-calendário"
              className="app-select h-10 w-auto"
              value={year}
              onChange={(event) => setYear(Number(event.target.value))}
            >
              {yearOptions.map((option) => <option key={option} value={option}>Ano-calendário {option}</option>)}
            </select>
            <Button type="button" variant="secondary" icon={Download} loading={exporting} disabled={!report} onClick={handleExport}>
              Exportar .xlsx
            </Button>
          </>
        )}
      />

      <AlertMessage message={exportError || queryErrorMessage(reportQuery, 'Não foi possível montar o relatório.')} onDismiss={exportError ? () => setExportError('') : undefined} />
      <ExemptionMeter month={monthKey()} />
      {report ? <AlertMessage tone="info" message={report.disclaimer} /> : null}

      {reportQuery.isPending ? (
        <Panel><ListSkeleton rows={6} /></Panel>
      ) : report ? (
        <>
          <Panel className="overflow-clip">
            <PanelHeader
              title="Bens e direitos"
              description={`Situação em 31/12/${year - 1} e 31/12/${year}, pelo custo de aquisição (não pelo valor de mercado).`}
              actions={<Badge>{report.bens_e_direitos.length} item(ns)</Badge>}
            />
            {report.bens_e_direitos.length ? (
              <ul className="divide-y divide-zinc-100">
                {report.bens_e_direitos.map((item) => (
                  <li key={item.key} className="flex flex-wrap items-start gap-3 px-5 py-3">
                    <div className="min-w-[12rem] flex-1">
                      <p className="text-sm font-semibold text-zinc-900">
                        {item.ticker} <span className="font-normal text-zinc-500">· grupo {item.group}, código {item.code} — {item.code_label}</span>
                      </p>
                      <p className="mt-1 text-xs text-zinc-600">{item.description}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-right text-sm">
                      <div>
                        <p className="text-xs text-zinc-500">31/12/{year - 1}</p>
                        <p className="num font-medium text-zinc-700">{privateMoney(item.cost_previous)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-zinc-500">31/12/{year}</p>
                        <p className="num font-semibold text-zinc-950">{privateMoney(item.cost)}</p>
                      </div>
                    </div>
                    <IconButton label={`Copiar discriminação de ${item.ticker}`} icon={Copy} size="sm" onClick={() => copyText(item.description)} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="p-5"><EmptyState icon={FileText} title="Nada a declarar em bens" message={`Nenhuma posição em 31/12/${year - 1} nem em 31/12/${year}.`} className="min-h-32" /></div>
            )}
          </Panel>

          <Panel className="overflow-clip">
            <PanelHeader
              title="Renda variável"
              description="Ações: vendas de até R$ 20 mil no mês são isentas; acima, 15% sobre o ganho menos o prejuízo acumulado. FII: 20%, sem isenção. DARF abaixo de R$ 10 acumula."
              actions={<Badge tone={report.renda_variavel.totals.tax_due ? 'warning' : 'neutral'}>DARF no ano {formatCurrency(report.renda_variavel.totals.tax_due)}</Badge>}
            />
            {activeMonths.length ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-zinc-500">
                    <th className="px-5 py-2 font-medium">Mês</th>
                    <th className="num px-3 py-2 font-medium">Vendas ações</th>
                    <th className="num px-3 py-2 font-medium">Resultado ações</th>
                    <th className="num px-3 py-2 font-medium">Resultado FII</th>
                    <th className="num px-3 py-2 font-medium">Prejuízo usado</th>
                    <th className="num px-5 py-2 font-medium">DARF</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {activeMonths.map((item) => (
                    <tr key={item.month}>
                      <td className="px-5 py-2 text-zinc-700">
                        {monthName(item.month)}
                        {item.stocks.exempt && item.stocks.sales ? <Badge className="ml-2">isento</Badge> : null}
                      </td>
                      <td className="num px-3 py-2">{formatCurrency(item.stocks.sales)}</td>
                      <td className="num px-3 py-2">{formatCurrency(item.stocks.result)}</td>
                      <td className="num px-3 py-2">{formatCurrency(item.reits.result)}</td>
                      <td className="num px-3 py-2">{formatCurrency(item.stocks.loss_used + item.reits.loss_used)}</td>
                      <td className="num px-5 py-2 font-semibold">
                        {item.darf ? formatCurrency(item.darf) : item.darf_carried ? <span className="text-xs font-normal text-zinc-500">acumula {formatCurrency(item.darf_carried)}</span> : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-5"><EmptyState icon={FileText} title="Nenhuma venda no ano" message="Sem venda de ações ou FII, não há apuração mensal." className="min-h-32" /></div>
            )}
            <p className="border-t border-zinc-100 px-5 py-3 text-xs text-zinc-500">
              Prejuízo a compensar ao fim de {year}: ações {formatCurrency(report.renda_variavel.totals.stock_loss_balance)} · FII {formatCurrency(report.renda_variavel.totals.reit_loss_balance)}.
            </p>
          </Panel>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Panel>
              <PanelHeader title="Rendimentos isentos" />
              <IncomeList items={report.rendimentos_isentos.map((item) => ({ line: item.line, value: item.amount }))} />
            </Panel>
            <Panel>
              <PanelHeader title="Tributação exclusiva" description="Já tributados na fonte: informe o bruto e o IR retido." />
              <IncomeList items={report.tributacao_exclusiva.map((item) => ({ line: item.line, value: item.gross, withheld: item.withheld }))} />
            </Panel>
          </div>

          <Panel>
            <PanelHeader
              title="Aplicações no exterior"
              description="Ativos em moeda estrangeira: apuração anual, 15% sobre o resultado do ano (Lei 14.754/2023), com o prejuízo levado para o ano seguinte."
            />
            <div className="grid grid-cols-2 gap-4 p-5 text-sm sm:grid-cols-4">
              <Figure label="Resultado do ano" value={formatCurrency(report.exterior.result)} />
              <Figure label="Prejuízo compensado" value={formatCurrency(report.exterior.loss_used)} />
              <Figure label="Imposto estimado" value={formatCurrency(report.exterior.tax)} />
              <Figure label="Prejuízo a compensar" value={formatCurrency(report.exterior.loss_balance)} />
            </div>
          </Panel>

          {report.ganho_de_capital.length ? (
            <Panel>
              <PanelHeader title="Ganho de capital (GCAP)" description="Venda de gado e de outros bens em reais: apure no programa GCAP." />
              <ul className="divide-y divide-zinc-100">
                {report.ganho_de_capital.map((item) => (
                  <li key={`${item.date}-${item.ticker}`} className="flex items-center justify-between gap-3 px-5 py-2 text-sm">
                    <span className="text-zinc-700">{item.ticker} · {item.date}</span>
                    <span className="num">resultado {formatCurrency(item.result)} · IR est. {formatCurrency(item.tax_estimate)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          ) : null}
        </>
      ) : null}
    </div>
  )
}

function IncomeList({ items }) {
  if (!items.length) return <p className="px-5 py-4 text-sm text-zinc-500">Nada no ano.</p>
  return (
    <ul className="divide-y divide-zinc-100">
      {items.map((item) => (
        <li key={item.line} className="flex items-start justify-between gap-3 px-5 py-2.5 text-sm">
          <span className="text-zinc-700">{item.line}</span>
          <span className="num text-right">
            <span className="font-semibold text-zinc-950">{formatCurrency(item.value)}</span>
            {item.withheld !== undefined ? <span className="block text-xs text-zinc-500">IR retido {formatCurrency(item.withheld)}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function Figure({ label, value }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="num font-semibold text-zinc-950">{value}</p>
    </div>
  )
}
