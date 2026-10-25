import { useCallback, useEffect, useMemo, useState } from 'react'
import { creditCards } from '../../lib/cardFunctions'
import {
  accountsApi,
  categoriesApi,
  ccExpensesApi,
  creditCardsApi,
  transactionsApi,
} from '../../lib/dataApi'
import { useOutbox } from '../../lib/outbox'
import { PENDING, applyPendingToAccounts, pendingAsTransactions } from '../../lib/outboxRules'
import { invalidateServerData, queryErrorMessage, useQuery } from '../../lib/queries'
import { useHome } from '../../lib/attention'
import { activeAccounts, cardSignedAmount } from '../../lib/transactions'
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
    // So os de credito (041): um cartao so debito nao tem fatura.
    cards: creditCards(cards),
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

  const totalOpenCredit = ccExpenses.reduce((acc, curr) => acc + cardSignedAmount(curr), 0)
  const creditUpToNextMonth = ccExpenses.reduce((acc, curr) => {
    const isPastOrCurrent = curr.invoice_year < currentYear || (curr.invoice_year === currentYear && curr.invoice_month <= currentMonth)
    const isNextMonth = curr.invoice_year === nextYear && curr.invoice_month === nextMonth
    return isPastOrCurrent || isNextMonth ? acc + cardSignedAmount(curr) : acc
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

  // O que foi lancado sem o servidor (lib/outbox.js) entra na leitura: as
  // linhas aparecem no extrato marcadas como pendentes, e os saldos passam a
  // ser uma estimativa — o servidor ainda nao sabe delas.
  const pending = useOutbox()
  const { cards, ccExpenses, categories } = data
  const allAccounts = useMemo(() => applyPendingToAccounts(data.allAccounts, pending), [data.allAccounts, pending])
  const transactions = useMemo(() => {
    if (!pending.length) return data.transactions
    const defaultAccountId = data.allAccounts.find((account) => account.is_default)?.id || ''
    return [...pendingAsTransactions(pending, { defaultAccountId }), ...data.transactions]
  }, [data.transactions, data.allAccounts, pending])
  const balanceEstimated = useMemo(
    // So despesa e receita mexem no saldo (cartao, transferencia, operacao e provento nao).
    () => pending.some((item) => item.status === PENDING && (item.kind === 'EXPENSE' || item.kind === 'INCOME')),
    [pending]
  )
  const accounts = useMemo(() => activeAccounts(allAccounts), [allAccounts])
  // Saldo em contas: o do Inicio (GET /api/home, sem a Corretora), com os
  // pendentes do aparelho por cima — o mesmo numero nas duas telas.
  const home = useHome()
  const balance = home.data?.consolidated_balance || 0
  const { projectedBalanceGlobal, projectedBalanceNextMonth } = useMemo(
    () => projections(balance, ccExpenses),
    [balance, ccExpenses]
  )
  // Incrementa a cada busca que chega: o extrato filtrado o usa para reaplicar os filtros.
  const reloadCount = query.dataUpdatedAt

  const categoryOptions = useMemo(() => buildCategoryOptions(categories), [categories])
  const categoryOptionsFor = useCallback((type) => filterCategoryOptions(categoryOptions, type), [categoryOptions])

  // Entre todas as contas, arquivadas tambem: o lancamento de uma conta
  // arquivada continua no extrato e mostra o nome dela, nao "—".
  const accountName = useCallback((accountId) => {
    return allAccounts.find((account) => account.id === accountId)?.name || '—'
  }, [allAccounts])

  return {
    loading: query.isPending || home.isPending,
    dataError,
    setDataError,
    reloadCount,
    fetchData,
    transactions,
    balance,
    balanceEstimated,
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
