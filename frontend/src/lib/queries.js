// Estado do servidor centralizado (TanStack Query). Cada tela le pelo
// `useQuery` com uma chave propria; o cache mora aqui, fora das paginas, entao
// voltar a uma tela mostra o que ela tinha enquanto a busca nova corre.
//
// Regra de invalidacao, de proposito simples: toda gravacao invalida tudo
// (`invalidateServerData()`). Quase tudo aqui se toca — um lancamento mexe no
// saldo, no orcamento, no Inicio e na fatura — e o app e local, entao refazer
// as buscas da tela aberta custa pouco. As telas fechadas so buscam de novo
// quando voltam a abrir.
//
// O cache e por usuario: trocar de sessao (entrar, sair) limpa tudo.
import { useEffect } from 'react'
import { keepPreviousData, QueryClient, useQuery } from '@tanstack/react-query'
import { setMutationListener } from './api'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Dado com menos de 30 s nao e rebuscado so por remontar a tela.
      staleTime: 30_000,
      gcTime: 10 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export function invalidateServerData() {
  return queryClient.invalidateQueries()
}

// Toda gravacao que passa por apiFetch invalida o cache sozinha (lib/api.js);
// as telas ainda chamam invalidateServerData() quando querem esperar a busca
// nova antes de seguir (ex.: fechar um sheet so com o dado ja atualizado).
setMutationListener(() => {
  invalidateServerData()
})

export function clearServerData() {
  queryClient.clear()
}

// Mensagem de erro de uma query (ou '' se nao houver).
export function queryErrorMessage(query, fallback) {
  if (!query?.error) return ''
  return query.error.message || fallback
}

// Joga o erro de uma query no AlertMessage da tela (o mesmo estado que os
// handlers de gravacao usam), uma vez por erro novo.
export function useReportQueryError(query, report, fallback) {
  useEffect(() => {
    if (query.error) report(query.error.message || fallback)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.error])
}

// Cache antigo das telas, de antes do TanStack Query: dados financeiros no
// localStorage sobreviviam ao logout. Sai uma vez, no carregamento do app.
const LEGACY_CACHE_KEYS = [
  'accounts', 'assets', 'balance', 'cards', 'categories', 'ccExpenses',
  'projectedBalanceGlobal', 'projectedBalanceNextMonth', 'transactions',
]

export function dropLegacyCaches() {
  try {
    LEGACY_CACHE_KEYS.forEach((key) => localStorage.removeItem(`@financeMVP:${key}`))
  } catch {
    // Sem localStorage: nada a limpar.
  }
}

export { keepPreviousData, useQuery }
