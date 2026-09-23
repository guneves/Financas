import { SummaryPanel } from '../../components/ui'
import { formatCurrency } from '../../lib/format'
import { usePrivateFormatter, useValuesHidden } from '../../lib/privacy'

// Cabecalho comum a Extrato e Cartoes: um bloco so, o saldo em destaque e as
// duas projecoes ao lado (eram tres cartoes iguais). Os valores vem da lista
// completa (useLancamentos), nunca do extrato filtrado. Sao saldos: somem no
// modo privado — e o vermelho de saldo negativo some junto.
export default function ProjectionHeader({ balance, projectedBalanceNextMonth, projectedBalanceGlobal }) {
  const privateMoney = usePrivateFormatter(formatCurrency)
  const hidden = useValuesHidden()
  const tone = (value) => (!hidden && value < 0 ? 'loss' : 'neutral')
  return (
    <SummaryPanel
      lead={{ label: 'Saldo em contas', value: privateMoney(balance), hint: 'Movimentações confirmadas', tone: tone(balance) }}
      figures={[
        { label: 'Projeção próximo mês', hint: 'Inclui faturas próximas', value: privateMoney(projectedBalanceNextMonth), tone: tone(projectedBalanceNextMonth) },
        { label: 'Projeção global', hint: 'Inclui parcelamentos futuros', value: privateMoney(projectedBalanceGlobal), tone: tone(projectedBalanceGlobal) },
      ]}
    />
  )
}
