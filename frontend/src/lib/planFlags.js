// Alertas do plano do mes dispensados neste aparelho (localStorage), como o
// "Precisa de atencao" do Inicio (lib/attention.js). Nada vai ao servidor: a
// chave de cada alerta e a regra de quais voltam estao em lib/monthlyPlan.js.
import { useSyncExternalStore } from 'react'
import { addDismissed } from './attentionRules'

const DISMISSED_KEY = '@financeMVP:planFlagsDismissed'

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

export function dismissPlanFlag(key) {
  dismissed = addDismissed(dismissed, [key])
  try {
    localStorage.setItem(DISMISSED_KEY, JSON.stringify(dismissed))
  } catch {
    // Sem localStorage a dispensa so dura ate recarregar a pagina.
  }
  listeners.forEach((listener) => listener())
}

export function useDismissedPlanFlags() {
  return useSyncExternalStore(subscribe, () => dismissed)
}
