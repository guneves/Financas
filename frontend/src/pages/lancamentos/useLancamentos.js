import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  accountsApi,
  categoriesApi,
  ccExpensesApi,
  creditCardsApi,
  transactionsApi,
} from '../../lib/dataApi'
import { useDataVersion } from '../../lib/newEntry'
import {
  buildCategoryOptions,
  filterCategoryOptions,
  getNow,
  readStoredJson,
  readStoredNumber,
} from './helpers'

// Carga compartilhada por Extrato e Cartoes. Movida de Transactions.jsx:
// a lista completa (sem filtro) alimenta o saldo e as projecoes do cabecalho.
// O extrato filtrado e uma busca separada, feita em Extrato.jsx — o saldo nunca
// sai da lista filtrada.
export default function useLancamentos() {
  const dataVersion = useDataVersion()
  const [dataError, setDataError] = useState('')
  // Incrementado a cada recarga: o extrato filtrado o usa para reaplicar os filtros.
  const [reloadCount, setReloadCount] = useState(0)

  const [transactions, setTransactions] = useState(() => {
    return readStoredJson('@financeMVP:transactions', [])
  })
  const [balance, setBalance] = useState(() => {
    return readStoredNumber('@financeMVP:balance')
  })
  const [cards, setCards] = useState(() => {
    return readStoredJson('@financeMVP:cards', [])
  })
  const [ccExpenses, setCcExpenses] = useState(() => {
    return readStoredJson('@financeMVP:ccExpenses', [])
  })
  const [projectedBalanceGlobal, setProjectedBalanceGlobal] = useState(() => {
    return readStoredNumber('@financeMVP:projectedBalanceGlobal')
  })
  const [projectedBalanceNextMonth, setProjectedBalanceNextMonth] = useState(() => {
    return readStoredNumber('@financeMVP:projectedBalanceNextMonth')
  })
  const [accounts, setAccounts] = useState(() => {
    return readStoredJson('@financeMVP:accounts', [])
  })
  const [categories, setCategories] = useState(() => {
    return readStoredJson('@financeMVP:categories', [])
  })

  const fetchData = useCallback(async () => {
    setDataError('')

    try {
      const [tData, cData, ccData, accountData, categoryData] = await Promise.all([
        transactionsApi.list(),
        creditCardsApi.list(),
        ccExpensesApi.list({ status: 'OPEN' }),
        accountsApi.list(),
        categoriesApi.list(),
      ])

      const safeTransactions = tData || []
      const safeCards = cData || []
      const safeCreditExpenses = ccData || []
      const safeAccounts = accountData || []
      const safeCategories = categoryData || []

      setTransactions(safeTransactions)
      localStorage.setItem('@financeMVP:transactions', JSON.stringify(safeTransactions))
      // Reaplica os filtros ativos depois de lancar/editar/excluir.
      setReloadCount((version) => version + 1)

      setAccounts(safeAccounts)
      localStorage.setItem('@financeMVP:accounts', JSON.stringify(safeAccounts))

      setCategories(safeCategories)
      localStorage.setItem('@financeMVP:categories', JSON.stringify(safeCategories))

      // TRANSFER fica de fora: ela move dinheiro entre contas proprias e nao
      // muda o consolidado. O saldo por conta vem pronto de /api/accounts.
      const currentBalance = safeTransactions.reduce((acc, curr) => {
        if (curr.type === 'TRANSFER') return acc
        const amount = Number(curr.amount || 0)
        return curr.type === 'INCOME' ? acc + amount : acc - amount
      }, 0)
      setBalance(currentBalance)
      localStorage.setItem('@financeMVP:balance', currentBalance.toString())

      setCards(safeCards)
      localStorage.setItem('@financeMVP:cards', JSON.stringify(safeCards))

      setCcExpenses(safeCreditExpenses)
      localStorage.setItem('@financeMVP:ccExpenses', JSON.stringify(safeCreditExpenses))

      const today = getNow()
      const currentMonth = today.getMonth() + 1
      const currentYear = today.getFullYear()

      let nextMonth = currentMonth + 1
      let nextYear = currentYear
      if (nextMonth > 12) {
        nextMonth = 1
        nextYear += 1
      }

      const totalOpenCredit = safeCreditExpenses.reduce((acc, curr) => acc + Number(curr.amount || 0), 0)
      const projGlobal = currentBalance - totalOpenCredit
      setProjectedBalanceGlobal(projGlobal)
      localStorage.setItem('@financeMVP:projectedBalanceGlobal', projGlobal.toString())

      const creditUpToNextMonth = safeCreditExpenses.reduce((acc, curr) => {
        const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
        const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth

        if (isPastOrCurrent || isNextMonth) {
          return acc + Number(curr.amount || 0)
        }
        return acc
      }, 0)

      const projNextMonth = currentBalance - creditUpToNextMonth
      setProjectedBalanceNextMonth(projNextMonth)
      localStorage.setItem('@financeMVP:projectedBalanceNextMonth', projNextMonth.toString())
    } catch (error) {
      console.warn('Erro ao carregar movimentacoes:', error)
      setDataError(error.message || 'Nao foi possivel carregar os dados financeiros.')
    }
  }, [])

  // dataVersion: recarrega depois de um "+ Novo" salvo no Layout.
  useEffect(() => {
    fetchData()
  }, [fetchData, dataVersion])

  const categoryOptions = useMemo(() => buildCategoryOptions(categories), [categories])
  const categoryOptionsFor = useCallback((type) => filterCategoryOptions(categoryOptions, type), [categoryOptions])

  const accountName = useCallback((accountId) => {
    return accounts.find((account) => account.id === accountId)?.name || '—'
  }, [accounts])

  return {
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
