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
import { keepPreviousData, QueryClient, useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { setMutationListener } from './api'
import { changesPositions, scheduleProceedsSync } from './proceedsSync'
import { changeCachedRows, withoutRow, withRow } from './transactionPages'

// O mesmo prazo de lib/queryPersist.js (que importa daqui): uma copia mais
// velha que isto nao e mostrada.
export const PERSISTED_CACHE_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Dado com menos de 30 s nao e rebuscado so por remontar a tela.
      staleTime: 30_000,
      // O cache guardado no aparelho (lib/queryPersist.js) so leva o que ainda
      // esta aqui: com 10 min, uma tela nao aberta na sessao voltava vazia na
      // proxima abertura, com esqueleto. Fica o mesmo prazo da copia guardada.
      gcTime: PERSISTED_CACHE_MAX_AGE_MS,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Para as telas: espera a busca nova. Uma busca que ja esta correndo e
// aproveitada (`cancelRefetch: false`) em vez de recomecar — logo depois de
// uma gravacao o listener abaixo ja disparou todas, e recomecar cada uma fazia
// o servidor calcular a carteira, os graficos e o Inicio duas vezes.
export function invalidateServerData() {
  return queryClient.invalidateQueries(undefined, { cancelRefetch: false })
}

// Toda gravacao que passa por apiFetch invalida o cache sozinha (lib/api.js);
// as telas ainda chamam invalidateServerData() quando querem esperar a busca
// nova antes de seguir (ex.: fechar um sheet so com o dado ja atualizado).
// Aqui a busca em curso e cancelada: ela pode ter comecado antes da gravacao.
// Gravar uma operacao muda a posicao em alguma data, e com ela os proventos
// automaticos: a sincronizacao vem logo depois (lib/proceedsSync.js).
setMutationListener((path) => {
  queryClient.invalidateQueries()
  if (changesPositions(path)) scheduleProceedsSync()
})

// A linha muda na tela na hora, sem esperar o extrato inteiro voltar do servidor
// (a gravacao invalida tudo do mesmo jeito e a leitura nova confirma).
const changeStatement = (change) => queryClient.setQueriesData(
  { queryKey: ['lancamentos'] },
  (data) => changeCachedRows(data, change),
)

export const dropStatementRow = (id) => changeStatement(withoutRow(id))
export const updateStatementRow = (row) => changeStatement(withRow(row))

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

export { keepPreviousData, useInfiniteQuery, useQuery }
