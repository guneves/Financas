import { ArrowLeftRight } from 'lucide-react'
import { Panel, PanelHeader, SummaryPanel } from '../../components/ui'
import { investmentsApi } from '../../lib/dataApi'
import { formatCurrency, formatDateBR, formatSignedCurrency } from '../../lib/format'
import { MASKED_CURRENCY, usePrivateFormatter, useValuesHidden } from '../../lib/privacy'
import { useQuery } from '../../lib/queries'

// Conta investimento (049): o caixa da Corretora como a corretora o ve. Cada
// compra ou venda mexe no caixa na liquidacao (D+2 na B3), entao "Saldo hoje"
// e o que ja liquidou, "Em transito" o que ainda vai liquidar (com a data) e
// os proventos anunciados, e "Saldo" o que sobra depois de tudo. O servidor
// faz a conta (GET /api/investments/settlement).
export default function ContaInvestimento() {
  const money = usePrivateFormatter(formatCurrency)
  const hidden = useValuesHidden()
  const query = useQuery({ queryKey: ['investimentos', 'liquidacao'], queryFn: () => investmentsApi.settlement() })
  const view = query.data
  if (!view) return null
  const transit = view.in_transit || []
  const signed = (value) => (hidden ? MASKED_CURRENCY : formatSignedCurrency(value))
  const pluggy = view.pluggy
  const pluggyHint = pluggy
    ? Math.abs(pluggy.difference || 0) < 0.01
      ? 'Confere com a corretora'
      : `Corretora: ${money(pluggy.balance)} (${signed(pluggy.difference)})`
    : view.account_name

  return (
    <div className="space-y-3">
      <SummaryPanel
        lead={{ label: 'Saldo hoje', value: money(view.settled), hint: pluggyHint }}
        figures={[
          {
            label: 'Em trânsito',
            value: signed(view.in_transit_total),
            hint: transit.length ? `${transit.length} a liquidar` : 'Nada a liquidar',
            tone: hidden || !view.in_transit_total ? 'neutral' : view.in_transit_total > 0 ? 'gain' : 'loss',
          },
          { label: 'Saldo', value: money(view.expected), hint: 'Depois de tudo liquidar' },
        ]}
      />
      {transit.length ? (
        <Panel>
          <PanelHeader title="Valores em trânsito" description="Cada operação mexe no caixa na data de liquidação." />
          <ul className="divide-y divide-zinc-100">
            {transit.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-3 px-5 py-3 sm:px-6">
                <div className="flex min-w-0 items-center gap-3">
                  <ArrowLeftRight className="h-4 w-4 shrink-0 text-zinc-400" aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-zinc-900">{item.description}</p>
                    <p className="text-xs text-zinc-500">
                      {item.kind === 'proceed' ? 'Pagamento' : 'Liquida'} em {formatDateBR(item.date)}
                    </p>
                  </div>
                </div>
                <span className={`num text-sm font-bold ${hidden ? 'text-zinc-900' : item.amount >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {signed(item.amount)}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  )
}
