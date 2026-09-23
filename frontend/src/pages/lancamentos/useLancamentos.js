import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  accountsApi,
  categoriesApi,
  ccExpensesApi,
  creditCardsApi,
  transactionsApi,
} from '../../lib/dataApi'
import { invalidateServerData, queryErrorMessage, useQuery } from '../../lib/queries'
import { activeAccounts, consolidatedBalance } from '../../lib/transactions'
import {
  buildCategoryOptions,
  filterCategoryOptions,
  getNow,
} from './helpers'

// Carga compartilhada por Extrato e Cartoes (uma query so, chave
// ['lancamentos']): a lista completa (sem filtro) alimenta o saldo e as
// projecoes do cabecalho. O extrato filtrado e uma busca separada, feita em
// Extrato.jsx — o saldo nunca sai da lista filtrada.
async function fetchLancamentos() {
  const [transactions, cards, ccExpenses, accounts, categories] = await Promise.all([
    transactionsApi.list(),
    creditCardsApi.list(),
    ccExpensesApi.list({ status: 'OPEN' }),
    accountsApi.list({ include_archived: 1 }),
    categoriesApi.list(),
  ])
  return {
    transactions: transactions || [],
    cards: cards || [],
    ccExpenses: ccExpenses || [],
    allAccounts: accounts || [],
    categories: categories || [],
  }
}

const EMPTY = { transactions: [], cards: [], ccExpenses: [], allAccounts: [], categories: [] }

// Saldo projetado: o saldo de hoje menos o cartao em aberto (todo, ou ate a
// fatura do mes que vem).
function projections(balance, ccExpenses) {
  const today = getNow()
  const currentMonth = today.getMonth() + 1
  const currentYear = today.getFullYear()
  let nextMonth = currentMonth + 1
  let nextYear = currentYear
  if (nextMonth > 12) {
    nextMonth = 1
    nextYear += 1
  }

  const totalOpenCredit = ccExpenses.reduce((acc, curr) => acc + Number(curr.amount || 0), 0)
  const creditUpToNextMonth = ccExpenses.reduce((acc, curr) => {
    const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
    const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth
    return isPastOrCurrent || isNextMonth ? acc + Number(curr.amount || 0) : acc
  }, 0)

  return {
    projectedBalanceGlobal: balance - totalOpenCredit,
    projectedBalanceNextMonth: balance - creditUpToNextMonth,
  }
}

export default function useLancamentos() {
  const query = useQuery({ queryKey: ['lancamentos'], queryFn: fetchLancamentos })
  const data = query.data || EMPTY
  const [dataError, setDataError] = useState('')

  useEffect(() => {
    if (query.error) {
      console.warn('Erro ao carregar movimentacoes:', query.error)
      setDataError(queryErrorMessage(query, 'Não foi possível carregar os dados financeiros.'))
    }
  }, [query.error])

  // Recarrega depois de gravar: invalida o cache inteiro (lib/queries.js) e
  // espera a tela aberta buscar de novo.
  const fetchData = useCallback(() => invalidateServerData(), [])

  const { transactions, cards, ccExpenses, allAccounts, categories } = data
  const accounts = useMemo(() => activeAccounts(allAccounts), [allAccounts])
  // A soma dos saldos por conta (lib/transactions.js): inclui o saldo
  // inicial de cada conta, que a soma dos lancamentos deixava de fora.
  const balance = useMemo(() => consolidatedBalance(allAccounts), [allAccounts])
  const { projectedBalanceGlobal, projectedBalanceNextMonth } = useMemo(
    () => projections(balance, ccExpenses),
    [balance, ccExpenses]
  )
  // Incrementa a cada busca que chega: o extrato filtrado o usa para reaplicar os filtros.
  const reloadCount = query.dataUpdatedAt

  const categoryOptions = useMemo(() => buildCategoryOptions(categories), [categories])
  const categoryOptionsFor = useCallback((type) => filterCategoryOptions(categoryOptions, type), [categoryOptions])

  const accountName = useCallback((accountId) => {
    return accounts.find((account) => account.id === accountId)?.name || '—'
  }, [accounts])

  return {
    loading: query.isPending,
    dataError,
    setDataError,
    reloadCount,
    fetchData,
    transactions,
    balance,
    cards,
    ccExpenses,
    projectedBalanceGlobal,
    projectedBalanceNextMonth,
    accounts,
    categories,
    categoryOptionsFor,
    accountName,
  }
}
