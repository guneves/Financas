// Copia do cache de leitura (lib/queries.js) no aparelho, para o app abrir
// sem o servidor com o que ja tinha visto: contas, categorias, cartoes, o
// ultimo extrato. E so leitura velha — ao abrir, cada tela busca de novo, e
// o que chegar substitui o que veio daqui.
//
// A copia e de um usuario so e some quando a sessao muda (sair, entrar com
// outra conta), junto com o cache em memoria.
import { dehydrate, hydrate } from '@tanstack/react-query'
import { getStoredAuth } from './api'
import { CACHE_STORE, storeDelete, storeGet, storePut } from './offlineStore'
import { PERSISTED_CACHE_MAX_AGE_MS } from './queries'

const CACHE_KEY = 'react-query'
const SAVE_DELAY_MS = 1000
// Uma copia mais velha que isto nao e mostrada: um saldo de um mes atras
// engana mais do que ajuda.
const MAX_AGE_MS = PERSISTED_CACHE_MAX_AGE_MS
// A copia guardada por outro build nao volta: a forma de uma resposta pode ter
// mudado (o Orcamento quebrou numa de antes de 038) e a tela nova leria a velha.
const BUILD_ID = import.meta.env.VITE_BUILD_ID || ''

const currentUserId = () => getStoredAuth()?.user?.id || ''

export async function restoreQueryCache(queryClient) {
  const userId = currentUserId()
  if (!userId) return false
  try {
    const saved = await storeGet(CACHE_STORE, CACHE_KEY)
    if (!saved || saved.user_id !== userId || saved.build_id !== BUILD_ID) return false
    if (Date.now() - saved.saved_at > MAX_AGE_MS) return false
    hydrate(queryClient, saved.state)
    return true
  } catch (error) {
    console.warn('Cache local indisponivel:', error)
    return false
  }
}

export function persistQueryCache(queryClient) {
  let timer = null
  const save = () => {
    timer = null
    const userId = currentUserId()
    if (!userId) return
    const state = dehydrate(queryClient, {
      shouldDehydrateQuery: (query) => query.state.status === 'success',
    })
    storePut(CACHE_STORE, { key: CACHE_KEY, user_id: userId, build_id: BUILD_ID, saved_at: Date.now(), state })
      .catch((error) => console.warn('Nao foi possivel guardar o cache local:', error))
  }
  return queryClient.getQueryCache().subscribe((event) => {
    // So quando chega dado novo; observadores entrando e saindo nao contam.
    if (event.type !== 'updated' || event.action?.type !== 'success') return
    if (timer) clearTimeout(timer)
    timer = setTimeout(save, SAVE_DELAY_MS)
  })
}

export function clearPersistedQueryCache() {
  return storeDelete(CACHE_STORE, CACHE_KEY).catch(() => {})
}
