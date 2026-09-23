// Aviso curto de que algo deu certo ("Provento registrado."). Erro continua
// no AlertMessage da pagina: ele precisa ficar ate ser lido, o toast some.
//
// Mesmo desenho de lib/privacy.js: o estado mora fora do React e o <Toaster />
// (ui.jsx, montado uma vez no Layout) assina com useSyncExternalStore. Assim
// qualquer handler chama toast() sem prop nem contexto, e um toast disparado
// logo antes de trocar de pagina continua na tela.
import { useSyncExternalStore } from 'react'

const EXIT_MS = 160
const MAX_TOASTS = 3

let toasts = []
let nextId = 1
const listeners = new Set()

function emit() {
  listeners.forEach((listener) => listener())
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot() {
  return toasts
}

export function dismissToast(id) {
  if (!toasts.some((item) => item.id === id && !item.leaving)) return
  toasts = toasts.map((item) => (item.id === id ? { ...item, leaving: true } : item))
  emit()
  setTimeout(() => {
    toasts = toasts.filter((item) => item.id !== id)
    emit()
  }, EXIT_MS)
}

// tone: 'success' (padrao) ou 'info'.
export function toast(message, { tone = 'success', duration = 4000 } = {}) {
  if (!message) return null
  const id = nextId++
  toasts = [...toasts, { id, message, tone, leaving: false }].slice(-MAX_TOASTS)
  emit()
  setTimeout(() => dismissToast(id), duration)
  return id
}

export function useToasts() {
  return useSyncExternalStore(subscribe, getSnapshot)
}
