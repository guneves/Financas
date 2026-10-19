import { CreditCard, Users } from 'lucide-react'
import { budgetsApi } from '../lib/dataApi'
import { formatCurrency, formatDateBR, formatSignedCurrency } from '../lib/format'
import { useQuery } from '../lib/queries'
import { AlertMessage, Skeleton } from './ui'

// O que soma o realizado de uma categoria do orcamento. As linhas vem de
// GET /api/budgets/<id>/lines, que usa a mesma lista do total: o que abre aqui
// sempre fecha com o valor mostrado. So busca quando a categoria esta aberta.
export default function BudgetLines({ budgetId, month, categoryName, kind }) {
  const query = useQuery({
    queryKey: ['orcamento', 'linhas', budgetId, month],
    queryFn: () => budgetsApi.lines(budgetId, month),
  })

  if (query.isPending) {
    return (
      <div className="space-y-2 pt-3">
        <Skeleton className="h-10" />
        <Skeleton className="h-10" />
      </div>
    )
  }
  if (query.isError) {
    return <AlertMessage className="mt-3" message="Não foi possível carregar os lançamentos." />
  }

  const lines = query.data?.lines || []
  if (!lines.length) {
    return <p className="pt-3 text-sm text-zinc-600">Nenhum lançamento neste mês.</p>
  }

  // Numa categoria de despesa o valor e saida; um estorno volta com "+".
  const sign = kind === 'INCOME' ? 1 : -1
  return (
    <div className="pt-3">
      <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-zinc-50">
        {lines.map((line) => (
          <li key={`${line.source}:${line.id}`} className="flex items-start justify-between gap-3 px-4 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-zinc-900">{line.description || line.category}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-zinc-600">
                <span>{formatDateBR(line.date)}</span>
                {line.source === 'CARD' ? (
                  <span className="inline-flex items-center gap-1">
                    <CreditCard className="h-3 w-3" />
                    {line.card_name || 'Cartão'}
                    {line.installments > 1 ? ` · ${line.installments}x` : ''}
                    {line.refund ? ' · estorno' : ''}
                  </span>
                ) : line.account_name ? (
                  <span>{line.account_name}</span>
                ) : null}
                {line.subcategory && line.category !== categoryName ? <span>{line.category}</span> : null}
                {line.shared ? (
                  <span className="inline-flex items-center gap-1">
                    <Users className="h-3 w-3" />
                    sua parte de {formatCurrency(line.total_amount)}
                  </span>
                ) : null}
              </p>
            </div>
            <span className="num shrink-0 text-sm font-semibold text-zinc-800">
              {formatSignedCurrency(line.amount, Math.sign(line.amount) * sign)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between px-1 text-xs text-zinc-600">
        <span>{lines.length} lançamento(s)</span>
        <span className="num font-semibold">Total {formatCurrency(query.data.spent)}</span>
      </p>
    </div>
  )
}
