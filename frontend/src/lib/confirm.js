// Confirmacao de acao destrutiva, no lugar de window.confirm. Mesmo desenho de
// lib/toast.js: o estado mora fora do React e o <ConfirmHost /> (ui.jsx,
// montado uma vez no Layout) assina com useSyncExternalStore. Quem chama faz
// `if (!(await confirmAction({...}))) return` — o handler continua linear.
import { useSyncExternalStore } from 'react'

let current = null
const listeners = new Set()

function emit() {
  listeners.forEach((listener) => listener())
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot() {
  return current
}

// title: pergunta curta ("Excluir a compra?"); message: o que acontece;
// confirmLabel: verbo do botao ("Excluir"); tone: 'danger' (padrao) ou 'neutral'.
export function confirmAction({ title, message = '', confirmLabel = 'Confirmar', tone = 'danger' }) {
  // Uma pergunta por vez: a anterior, se houver, conta como cancelada.
  current?.resolve(false)
  return new Promise((resolve) => {
    current = { title, message, confirmLabel, tone, resolve }
    emit()
  })
}

export function settleConfirm(answer) {
  if (!current) return
  const { resolve } = current
  current = null
  emit()
  resolve(answer)
}

export function useConfirmRequest() {
  return useSyncExternalStore(subscribe, getSnapshot)
}
