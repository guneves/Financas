// "Precisa de atencao" fora do Inicio: o sino do cabecalho le os mesmos avisos
// (lib/attentionRules.js), com as mesmas queries do Inicio — as chaves sao as
// dele, entao o cache e um so e nada e buscado duas vezes.
//
// Dispensar um aviso no Inicio e por aparelho (localStorage) e por caso: o
// mesmo aviso nao volta ao Inicio, um novo volta. O sino mostra todos.
import { useMemo, useSyncExternalStore } from 'react'
import { accountsApi, budgetsApi, ccExpensesApi, creditCardsApi, recurringApi, transactionsApi } from './dataApi'
import { getLocalDateString, monthKey } from './format'
import { useOutbox } from './outbox'
import { applyPendingToAccounts } from './outboxRules'
import { useQuery } from './queries'
import { activeAccounts } from './transactions'
import {
  addDismissed,
  attentionItems,
  autopayShortfalls,
  nextInvoices,
  openCardExpenses,
  overdueInvoices,
  payableInvoices,
} from './attentionRules'

const DISMISSED_KEY = '@financeMVP:attentionDismissed'
const NO_ITEMS = []

let dismissed = (() => {
  try {
    const stored = JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]')
    return Array.isArray(stored) ? stored.filter((key) => typeof key === 'string') : []
  } catch {
    return []
  }
})()

const listeners = new Set()

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function dismissAttention(keys) {
  dismissed = addDismissed(dismissed, keys)
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(dismissed))
  } catch {
    // Sem localStorage a dispensa so dura ate recarregar a pagina.
  }
  listeners.forEach((listener) => listener())
}

export function useDismissedAttention() {
  return useSyncExternalStore(subscribe, () => dismissed)
}

// As queries do Inicio, as mesmas chaves. As movimentacoes trazem todas as
// compras do cartao e todas as contas (arquivadas inclusive).
export function useInicioMovements() {
  return useQuery({
    queryKey: ['inicio', 'movimentos'],
    queryFn: async () => {
      const [transactions, ccExpenses, accounts] = await Promise.all([
        transactionsApi.list(),
        ccExpensesApi.list(),
        accountsApi.list({ include_archived: 1 }),
      ])
      return { transactions: transactions || [], ccExpenses: ccExpenses || [], allAccounts: accounts || [] }
    },
  })
}

export function useInicioCards() {
  return useQuery({ queryKey: ['inicio', 'cartoes'], queryFn: () => creditCardsApi.list() })
}

export function useInicioRecurring() {
  return useQuery({ queryKey: ['inicio', 'recorrencias'], queryFn: () => recurringApi.list() })
}

export function useInicioBudget(month) {
  return useQuery({ queryKey: ['inicio', 'orcamento', month], queryFn: () => budgetsApi.month(month) })
}

// Os avisos de agora, para o sino. O Inicio monta os seus com as mesmas regras
// a partir do que ja carregou (as contas com os lancamentos pendentes do
// aparelho, como aqui).
export function useAttentionItems() {
  const movements = useInicioMovements()
  const cards = useInicioCards()
  const recurring = useInicioRecurring()
  const month = monthKey(new Date())
  const todayText = getLocalDateString()
  const budget = useInicioBudget(month)
  const pending = useOutbox()

  const serverAccounts = movements.data?.allAccounts || NO_ITEMS
  const ccExpenses = movements.data?.ccExpenses || NO_ITEMS
  const cardRows = cards.data || NO_ITEMS
  const recurringItems = recurring.data?.items || NO_ITEMS
  const budgetData = budget.data || null

  return useMemo(() => {
    const accounts = activeAccounts(applyPendingToAccounts(serverAccounts, pending))
    const open = openCardExpenses(ccExpenses)
    const limit = new Date()
    limit.setDate(limit.getDate() + 31)
    return attentionItems({
      overdue: overdueInvoices(open, todayText),
      // A proxima fatura de cada cartao, nao a do mes que vem: a mesma regra
      // do Inicio e da tela Cartoes.
      payable: payableInvoices(nextInvoices(open, todayText).flatMap((invoice) => invoice.items)),
      shortfalls: autopayShortfalls({ cards: cardRows, accounts, openExpenses: open, todayText, limitText: getLocalDateString(limit) }),
      recurringItems,
      budget: budgetData,
    })
  }, [serverAccounts, pending, ccExpenses, cardRows, recurringItems, budgetData, todayText])
}
