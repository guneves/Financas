import { Banknote, Landmark, Receipt } from 'lucide-react'
import { MetricCard } from '../../components/ui'
import { formatCurrency } from '../../lib/format'

// Cabecalho comum a Extrato e Cartoes. Os valores vem da lista completa
// (useLancamentos), nunca do extrato filtrado. Sao saldos: somem no modo privado.
export default function ProjectionHeader({ balance, projectedBalanceNextMonth, projectedBalanceGlobal }) {
  return (
    <div className="stagger grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
      <MetricCard
        icon={Landmark}
        tone={balance >= 0 ? 'success' : 'danger'}
        title="Saldo atual"
        sensitive
        className="col-span-2 md:col-span-1"
        value={formatCurrency(balance)}
        valueClassName={balance >= 0 ? 'text-zinc-950' : 'text-rose-600'}
        subtitle="Movimentações confirmadas"
      />
      <MetricCard
        icon={Banknote}
        tone={projectedBalanceNextMonth >= 0 ? 'neutral' : 'danger'}
        title="Projeção próximo mês"
        sensitive
        value={formatCurrency(projectedBalanceNextMonth)}
        valueClassName={projectedBalanceNextMonth >= 0 ? 'text-zinc-950' : 'text-rose-600'}
        subtitle="Inclui faturas próximas"
      />
      <MetricCard
        icon={Receipt}
        tone={projectedBalanceGlobal >= 0 ? 'neutral' : 'danger'}
        title="Projeção global"
        sensitive
        value={formatCurrency(projectedBalanceGlobal)}
        valueClassName={projectedBalanceGlobal >= 0 ? 'text-zinc-950' : 'text-rose-600'}
        subtitle="Inclui parcelamentos futuros"
      />
    </div>
  )
}
