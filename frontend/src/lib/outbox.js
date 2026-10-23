// A fila de envio: os lancamentos do "+ Novo" que ainda nao chegaram ao
// servidor (mobile-docs/steps-to-production.md, "Where the outbox lives").
//
// Uma fila, um remetente. No navegador a fila mora no IndexedDB e quem envia
// e este modulo. No APK os dois passam a ser nativos (o envio precisa
// funcionar com o app fechado): `setOutboxBackend()` troca o armazenamento e
// o remetente, e o resto — telas, regras, estados — fica igual.
//
// So criacao entra aqui, e so quando o pedido nao chegou ao servidor
// (ApiNetworkError). Cada item leva um client_id, entao reenviar nunca
// duplica (migration 024). As regras estao em outboxRules.js, com testes.
import { useSyncExternalStore } from 'react'
import { ApiNetworkError, apiFetch, getStoredAuth } from './api'
import { OUTBOX_STORE, storeAll, storeDelete, storePut } from './offlineStore'
import {
  ALREADY_DELIVERED_MESSAGE,
  NEEDS_ATTENTION,
  PENDING,
  buildItem,
  deliveredDiffers,
  editedItem,
  endpointFor,
  newClientId,
  outcomeOf,
  sendOrder,
} from './outboxRules'

// Enquanto ha pendentes e o servidor nao responde, tenta de novo neste passo.
// O evento `online` nao basta: no PC o backend pode estar parado com a rede no ar.
const RETRY_MS = 30_000

// Uma criacao sem resposta neste prazo vai para a fila (o client_id torna o
// reenvio seguro). Sem isso, no celular com a VPN de pe e sem rede, o Salvar
// ficava girando. Sem rede nenhuma nem se tenta (backend.isOffline); o prazo
// e para sinal fraco ou o PC desligado.
const CREATE_TIMEOUT_MS = 6_000

const browserBackend = {
  all: () => storeAll(OUTBOX_STORE),
  put: (item) => storePut(OUTBOX_STORE, item),
  remove: (clientId) => storeDelete(OUTBOX_STORE, clientId),
  // Devolve { ok: true, data } | { network: true } | { status, message }.
  async send(item) {
    try {
      const data = await apiFetch(endpointFor(item.kind), { method: 'POST', body: JSON.stringify(item.payload), timeoutMs: CREATE_TIMEOUT_MS })
      return { ok: true, data }
    } catch (error) {
      if (error instanceof ApiNetworkError) return { network: true }
      return { status: error.status || 0, message: error.message }
    }
  },
  isOffline: () => navigator.onLine === false,
  // No navegador o envio so acontece com a tela aberta, por flush().
  sendsOnItsOwn: false,
}

let backend = browserBackend

// Fase 5 (APK): o plugin nativo entra aqui (lib/nativeApp.js), com all, put,
// remove e um flush que envia do lado nativo e devolve o resumo da rodada.
export function setOutboxBackend(next) {
  backend = { ...browserBackend, ...next }
  return load()
}

let items = []
let loaded = false
let flushing = null
const listeners = new Set()

const currentUserId = () => getStoredAuth()?.user?.id || ''

function emit() {
  listeners.forEach((listener) => listener())
}

function setItems(next) {
  items = sendOrder(next)
  emit()
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

const NO_ITEMS = []
let visibleCache = { source: null, userId: null, value: NO_ITEMS }

// So os itens de quem esta logado: a fila sobrevive ao logout (um login
// vencido nao pode perder lancamento), mas outro usuario nao a ve.
function getSnapshot() {
  const userId = currentUserId()
  if (visibleCache.source !== items || visibleCache.userId !== userId) {
    const value = userId ? items.filter((item) => item.user_id === userId) : NO_ITEMS
    visibleCache = { source: items, userId, value: value.length ? value : NO_ITEMS }
  }
  return visibleCache.value
}

export function useOutbox() {
  return useSyncExternalStore(subscribe, getSnapshot)
}

export function outboxItems() {
  return getSnapshot()
}

// O remetente nativo mexeu na fila sem a tela pedir (enviou, ou o servidor recusou).
export function reloadOutbox() {
  return load()
}

async function load() {
  try {
    setItems((await backend.all()) || [])
  } catch (error) {
    console.warn('Fila de envio indisponivel:', error)
    setItems([])
  }
  loaded = true
}

async function save(item) {
  await backend.put(item)
  setItems([...items.filter((entry) => entry.client_id !== item.client_id), item])
}

async function removeItem(clientId) {
  await backend.remove(clientId)
  setItems(items.filter((entry) => entry.client_id !== clientId))
}

export async function enqueue({ kind, payload }) {
  if (!loaded) await load()
  const item = buildItem({ kind, payload, userId: currentUserId() })
  await save(item)
  return item
}

// Editar um item da fila: o mesmo client_id, de volta a pendente (editedItem,
// em outboxRules.js; o "+ Novo" nativo grava o mesmo item pelo OutboxRules.java).
export async function updateItem(clientId, { kind, payload }) {
  const current = items.find((entry) => entry.client_id === clientId)
  if (!current) return null
  const next = editedItem(current, { kind, payload })
  await save(next)
  return next
}

export function discardItem(clientId) {
  return removeItem(clientId)
}

// Envia a fila de quem esta logado, um item por vez, na ordem. Devolve
// { sent, kept, attention, stopped }. Chamadas simultaneas dividem a mesma rodada.
export function flush({ retryAttention = false } = {}) {
  if (flushing) return flushing
  flushing = (async () => {
    const summary = { sent: 0, kept: 0, attention: 0, stopped: '' }
    if (!loaded) await load()
    if (backend.sendsOnItsOwn) {
      // APK: a rodada acontece no Java, com o mesmo resumo e as mesmas regras.
      const native = await backend.flush?.({ retryAttention })
      await load()
      return { ...summary, ...(native || {}) }
    }
    const queue = getSnapshot().filter((item) => item.status === PENDING || retryAttention)
    if (!queue.length) return summary
    if (!getStoredAuth()?.access_token) {
      summary.stopped = 'login'
      summary.kept = queue.length
      return summary
    }

    for (let index = 0; index < queue.length; index += 1) {
      const item = queue[index]
      const result = await backend.send(item)
      const outcome = outcomeOf(result)
      if (outcome === 'done' && item.edited && deliveredDiffers(item, result.data)) {
        // A primeira tentativa tinha chegado e a resposta se perdeu: o servidor
        // devolveu o lancamento antigo, sem a correcao. Nao some em silencio.
        await save({ ...item, status: NEEDS_ATTENTION, last_error: ALREADY_DELIVERED_MESSAGE })
        summary.attention += 1
      } else if (outcome === 'done') {
        await removeItem(item.client_id)
        summary.sent += 1
      } else if (outcome === 'attention') {
        await save({ ...item, status: NEEDS_ATTENTION, last_error: result.message || 'O servidor recusou este lançamento.' })
        summary.attention += 1
      } else {
        // retry ou stop: este e os proximos ficam como estao.
        summary.stopped = outcome === 'stop' ? 'login' : 'offline'
        summary.kept = queue.length - index
        break
      }
    }
    return summary
  })().finally(() => {
    flushing = null
  })
  return flushing
}

// Um lancamento do "+ Novo". Tenta o servidor; se o pedido nao chegou, guarda
// na fila. Devolve { queued: false, data } ou { queued: true, item }. Um erro
// que o servidor respondeu (validacao, 401...) sobe como sempre.
export async function createEntry(kind, payload) {
  const body = { ...payload, client_id: payload.client_id || newClientId() }
  const offline = await Promise.resolve(backend.isOffline?.()).catch(() => false)
  if (offline) return { queued: true, item: await enqueue({ kind, payload: body }) }
  try {
    const data = await apiFetch(endpointFor(kind), { method: 'POST', body: JSON.stringify(body), timeoutMs: CREATE_TIMEOUT_MS })
    return { queued: false, data }
  } catch (error) {
    if (!(error instanceof ApiNetworkError)) throw error
    const item = await enqueue({ kind, payload: body })
    return { queued: true, item }
  }
}

let started = false

// Chamado uma vez no carregamento do app (main.jsx): le a fila e liga os
// gatilhos de envio — abrir, voltar para a aba, voltar a rede, e o passo lento.
export async function startOutbox() {
  if (started) return
  started = true
  await load()
  const tryFlush = () => {
    if (getSnapshot().some((item) => item.status === PENDING)) flush().catch(() => {})
  }
  window.addEventListener('online', tryFlush)
  window.addEventListener('finance-auth-change', () => {
    emit()
    tryFlush()
  })
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') tryFlush()
  })
  setInterval(() => {
    if (document.visibilityState === 'visible') tryFlush()
  }, RETRY_MS)
  tryFlush()
}
