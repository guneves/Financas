// Extrato do banco pela Pluggy (backend: services/pluggy_sync.py). O servidor
// le o que o banco registrou e confere com o que ja esta lancado: o que
// confirma um lancamento marca esse lancamento; o resto (o que faltava, o que
// pode ser duplicata) espera o dono em Lançamentos › Aprovar.
//
// Quando pedir: ao abrir o Extrato ou Aprovar (`usePluggySync`), no maximo a
// cada MIN_INTERVAL_MS por sessao — o servidor tem o proprio limite. Sem
// credenciais no servidor, tambem so a cada MIN_INTERVAL_MS: um app aberto ha
// dias ve a Pluggy assim que o .env do servidor for corrigido. Falha e
// silenciosa: o extrato gravado continua la, e a proxima abertura tenta de novo.
//
// Nao e uma "gravacao" para lib/api.js (que invalidaria todo o cache a cada
// abertura): so quando o servidor diz que mudou algo e que as telas releem.
import { useEffect } from 'react'
import { apiFetch } from './api'
import { invalidateServerData } from './queries'
import { syncChangedData } from './pluggyRules'

const MIN_INTERVAL_MS = 10 * 60 * 1000

let lastRunAt = 0
let inFlight = null

export function syncPluggy({ force = false } = {}) {
  if (inFlight) return inFlight
  lastRunAt = Date.now()
  inFlight = apiFetch('/api/pluggy/sync', {
    method: 'POST',
    body: JSON.stringify(force ? { force: true } : {}),
  })
    .then(async (result) => {
      if (syncChangedData(result)) await invalidateServerData()
      return result
    })
    .catch((error) => {
      if (force) throw error
      console.warn('Sincronizacao com a Pluggy falhou:', error)
      return null
    })
    .finally(() => {
      inFlight = null
    })
  return inFlight
}

export function usePluggySync() {
  useEffect(() => {
    if (Date.now() - lastRunAt >= MIN_INTERVAL_MS) syncPluggy()
  }, [])
}
