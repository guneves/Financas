// As telas nativas do APK (Kotlin + Compose, mobile-docs/native/): a web pergunta
// uma vez quais existem (NativeScreens.routes()) e abre a nativa so para uma
// tela listada. No navegador, ou num APK sem o plugin, a lista e vazia e tudo
// segue nas telas React. Regras puras em nativeScreensRules.js (testadas).
//
// Eventos do APK: "dataChanged" (uma tela nativa gravou ou guardou na fila) e
// "navigate" (uma tela nativa pediu uma rota que ainda e React). Quem escuta se
// inscreve em onNativeEvent(); lib/nativeApp.js atualiza os dados e a fila, o
// Layout navega e marca a gravacao.
import { Capacitor, registerPlugin } from '@capacitor/core'
import { routesFrom } from './nativeScreensRules'

const NativeScreens = registerPlugin('NativeScreens')

let routes = []
let started = false
const listeners = new Set()

function emit(type, data) {
  listeners.forEach((listener) => {
    try {
      listener(type, data || {})
    } catch (error) {
      console.warn('Evento da tela nativa:', error)
    }
  })
}

// Chamado uma vez (lib/nativeApp.js). Nada no navegador.
export async function startNativeScreens() {
  if (started || !Capacitor.isNativePlatform()) return
  started = true
  try {
    routes = routesFrom(await NativeScreens.routes())
  } catch {
    // APK de antes do plugin (ou sem o metodo): nenhuma tela nativa.
    routes = []
    return
  }
  NativeScreens.addListener('dataChanged', (data) => emit('dataChanged', data)).catch(() => {})
  NativeScreens.addListener('navigate', (data) => emit('navigate', data)).catch(() => {})
}

// Este APK tem a tela em nativo?
export function hasNativeScreen(screen) {
  return routes.includes(screen)
}

// Abre a tela nativa. Rejeita se o APK nao conseguiu (quem chama volta para a React).
export function openNativeScreen({ screen, params }) {
  return NativeScreens.open({ screen, params })
}

// listener(type, data): type = 'dataChanged' | 'navigate'. Devolve o cancelamento.
export function onNativeEvent(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
