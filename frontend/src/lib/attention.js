// "Precisa de atencao" fora do Inicio: o sino do cabecalho le os mesmos avisos
// que o Inicio, de GET /api/attention (services/attention.py), com a mesma
// chave de query — o pedido e um so.
//
// Dispensar um aviso no Inicio e por aparelho (localStorage) e por caso: o
// mesmo aviso nao volta ao Inicio, um novo volta. O sino mostra todos.
import { useMemo, useSyncExternalStore } from 'react'
import { accountsApi, attentionApi, budgetsApi, ccExpensesApi, homeApi, transactionsApi } from './dataApi'
import { useOutbox } from './outbox'
import { applyPendingToHome } from './outboxRules'
import { useQuery } from './queries'
import { addDismissed } from './attentionRules'

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

// As movimentacoes do Inicio: todo o historico, para os paineis que ainda o
// leem no cliente (categorias, ritmo, parcelamentos, a projecao das faturas).
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

export function useInicioBudget(month) {
  return useQuery({ queryKey: ['inicio', 'orcamento', month], queryFn: () => budgetsApi.month(month) })
}

// Os 12 meses do fluxo do Inicio, o saldo em contas e a proxima fatura de cada
// cartao (GET /api/home). Os lancamentos guardados no aparelho entram por cima
// (applyPendingToHome): o saldo vira estimativa e a despesa entra no "Saiu".
export const HOME_MONTHS = 12

export function useHome() {
  const query = useQuery({ queryKey: ['inicio', 'home'], queryFn: () => homeApi.get({ months: HOME_MONTHS }) })
  const pending = useOutbox()
  const data = useMemo(() => (query.data ? applyPendingToHome(query.data, pending) : query.data), [query.data, pending])
  return { ...query, data }
}

// Os avisos de agora (o sino e os cartoes do Inicio).
export function useAttentionItems() {
  const query = useQuery({ queryKey: ['atencao'], queryFn: () => attentionApi.list() })
  return query.data?.items || NO_ITEMS
}
