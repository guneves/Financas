import { Panel, cx } from '../../components/ui'
import { formatCurrency } from '../../lib/format'
import { usePrivateFormatter } from '../../lib/privacy'

// Cabecalho comum a Extrato e Cartoes: um bloco so, o saldo em destaque e as
// duas projecoes ao lado (eram tres cartoes iguais). Os valores vem da lista
// completa (useLancamentos), nunca do extrato filtrado. Sao saldos: somem no
// modo privado.
export default function ProjectionHeader({ balance, projectedBalanceNextMonth, projectedBalanceGlobal }) {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const figures = [
    { label: 'Projeção próximo mês', hint: 'Inclui faturas próximas', value: projectedBalanceNextMonth },
    { label: 'Projeção global', hint: 'Inclui parcelamentos futuros', value: projectedBalanceGlobal },
  ]
  return (
    <Panel className="grid animate-fade-up grid-cols-2 gap-x-4 gap-y-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] lg:items-end">
      <div className="col-span-2 min-w-0 lg:col-span-1">
        <p className="text-sm font-semibold text-zinc-600">Saldo em contas</p>
        <p className={cx('mt-1 whitespace-nowrap text-3xl font-extrabold tracking-tight tabular sm:text-4xl', balance < 0 ? 'text-rose-600' : 'text-zinc-950')}>
          {privateMoney(balance)}
        </p>
        <p className="mt-1 text-sm text-zinc-500">Movimentações confirmadas</p>
      </div>
      {figures.map((figure) => (
        <div key={figure.label} className="min-w-0 lg:border-l lg:border-zinc-200/70 lg:pl-5">
          <p className="text-sm font-semibold text-zinc-600">{figure.label}</p>
          <p className={cx('mt-1 whitespace-nowrap text-lg font-bold tabular sm:text-xl', figure.value < 0 ? 'text-rose-600' : 'text-zinc-950')}>
            {privateMoney(figure.value)}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500 sm:text-sm">{figure.hint}</p>
        </div>
      ))}
    </Panel>
  )
}
