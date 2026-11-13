// Modo privado: o botao do olho (Layout) esconde os saldos das contas, o
// patrimonio e a carteira de investimentos. Lancamentos, faturas, orcamentos,
// operacoes e proventos continuam visiveis — o modo e para abrir o app perto
// de alguem sem expor quanto se tem, nao para esconder o dia a dia.
//
// O estado mora aqui, fora do React, e quem mostra um valor sensivel assina
// com useValuesHidden(): trocar o modo re-renderiza so esses pontos, sem
// remontar a pagina (sem nova busca, sem recontar numeros nem redesenhar
// graficos).
import { useCallback, useSyncExternalStore } from 'react'

const HIDE_VALUES_KEY = '@financeMVP:hideValues'
export const MASKED_CURRENCY = 'R$ ••••••'
export const MASKED_TEXT = '••••••'

let valuesHidden = (() => {
  try {
    return localStorage.getItem(HIDE_VALUES_KEY) === '1'
  } catch {
    return false
  }
})()

const listeners = new Set()

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot() {
  return valuesHidden
}

export function setValuesHidden(hidden) {
  valuesHidden = Boolean(hidden)
  try {
    localStorage.setItem(HIDE_VALUES_KEY, valuesHidden ? '1' : '0')
  } catch {
    // Sem localStorage o modo so dura ate recarregar a pagina.
  }
  listeners.forEach((listener) => listener())
}

export function useValuesHidden() {
  return useSyncExternalStore(subscribe, getSnapshot)
}

// Formatador que mascara quando o modo privado esta ligado. Para valores
// sensiveis: `const money = usePrivateFormatter(formatCurrency)`.
export function usePrivateFormatter(format, masked = MASKED_CURRENCY) {
  const hidden = useValuesHidden()
  return useCallback((...args) => (hidden ? masked : format(...args)), [hidden, format, masked])
}

// Eixo de valores em grafico sensivel: sem rotulos no modo privado — uma
// coluna de "R$ ••••••" nao diz nada e quebra a linha.
export function usePrivateAxisFormatter(format) {
  return usePrivateFormatter(format, '')
}
