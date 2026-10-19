// Proventos automaticos (backend: services/proceeds_sync.py). O servidor faz
// a conta — posicao na data com x valor da StatusInvest — e guarda o historico
// de cada ticker por algumas horas, entao pedir de novo custa pouco.
//
// Quando pedir:
// - ao abrir uma tela que mostra proventos (`useProceedsSync`), no maximo a
//   cada MIN_INTERVAL_MS por sessao: traz o que foi anunciado desde a ultima vez;
// - logo depois de gravar uma operacao ou evento corporativo
//   (`scheduleProceedsSync`, chamado por lib/queries.js): uma compra lancada
//   com data no passado traz os proventos que pagou, e apagar uma tira.
//
// Falha (sem rede, fonte fora) e silenciosa: os proventos gravados continuam
// la, e a proxima abertura tenta de novo.
//
// A sincronizacao e um POST, mas quase sempre nao muda nada: ela so invalida o
// cache (e refaz os graficos da tela aberta) quando criou, mudou ou tirou um
// provento. Antes, abrir Investimentos calculava cada grafico duas vezes.
import { useEffect } from 'react'
import { apiFetch, notifyMutation } from './api'

const SYNC_PATH = '/api/investment-proceeds/sync'

function changedSomething(result) {
  if (!result) return false
  return ['created', 'updated', 'removed'].some((field) => Number(result[field] || 0) > 0)
}

const MIN_INTERVAL_MS = 10 * 60 * 1000
const AFTER_WRITE_DELAY_MS = 1500

let lastRunAt = 0
let inFlight = null
let pendingTimer = null

export function syncProceeds({ force = false } = {}) {
  if (inFlight) return inFlight
  lastRunAt = Date.now()
  inFlight = apiFetch(SYNC_PATH, {
    method: 'POST',
    body: JSON.stringify(force ? { force: true } : {}),
    invalidate: false,
  })
    .then((result) => {
      if (changedSomething(result)) notifyMutation(SYNC_PATH)
      return result
    })
    .catch((error) => {
      console.warn('Sincronizacao de proventos falhou:', error)
      return null
    })
    .finally(() => {
      inFlight = null
    })
  return inFlight
}

// Escritas que mudam a posicao de um ativo em alguma data.
export function changesPositions(path) {
  return /^\/api\/(investments|corporate-actions)(\/|\?|$)/.test(path || '')
}

export function scheduleProceedsSync() {
  if (pendingTimer) clearTimeout(pendingTimer)
  pendingTimer = setTimeout(() => {
    pendingTimer = null
    syncProceeds()
  }, AFTER_WRITE_DELAY_MS)
}

export function useProceedsSync() {
  useEffect(() => {
    if (Date.now() - lastRunAt >= MIN_INTERVAL_MS) syncProceeds()
  }, [])
}
