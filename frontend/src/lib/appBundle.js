// A tela do APK se atualiza sozinha (mobile-docs/steps-to-production.md, "A tela
// se atualiza sozinha"). O lado nativo (android/.../bundle/BundlePlugin.java)
// baixa a tela que o servidor serve e a abre na proxima vez; aqui so se diz
// quando procurar, quando trocar, e que esta tela desenhou (ready).
//
// ready() e o que segura uma tela ruim: uma tela baixada abre "em teste" e, se
// nao chamar ready() em 30 s, o app volta para a tela que veio no APK e nunca
// mais baixa aquela versao. Por isso startAppBundle() roda num efeito depois do
// primeiro desenho (main.jsx), nao no carregamento do modulo.
//
// No navegador nada daqui roda: o Flask ja serve a tela nova.
import { Capacitor, registerPlugin } from '@capacitor/core'
import { App } from '@capacitor/app'
import { API_BASE_URL } from './api'
import { hasOpenLayer } from './layers'
import { shouldApplyOnResume, shouldCheck } from './appBundleRules'

const AppBundle = registerPlugin('AppBundle')

let started = false
let lastCheckAt = 0
let hiddenAt = null
let lastResult = null
const subscribers = new Set()

function publish(result) {
  lastResult = result
  for (const subscriber of subscribers) subscriber(result)
}

export function isAppBundleAvailable() {
  return Capacitor.isNativePlatform()
}

export function getLastCheck() {
  return lastResult
}

export function subscribeAppBundle(callback) {
  subscribers.add(callback)
  return () => subscribers.delete(callback)
}

export async function checkForUpdate() {
  lastCheckAt = Date.now()
  let result
  try {
    result = await AppBundle.check({ baseUrl: API_BASE_URL })
  } catch (error) {
    result = { status: 'error', message: error?.message }
  }
  publish(result)
  return result
}

export function appBundleInfo() {
  return AppBundle.info()
}

// Troca agora (recarrega a tela). false quando nao ha nada esperando.
export async function applyAppBundle() {
  const { applied } = await AppBundle.apply()
  return applied
}

// Volta para a tela que veio no APK; a versao em uso nao e baixada de novo.
export function resetAppBundle() {
  return AppBundle.reset()
}

async function onResume() {
  const awayMs = hiddenAt ? Date.now() - hiddenAt : 0
  hiddenAt = null
  try {
    const { staged } = await AppBundle.info()
    if (shouldApplyOnResume({ awayMs, hasOpenLayer: hasOpenLayer(), staged }) && await applyAppBundle()) return
  } catch (error) {
    console.warn('Troca de tela:', error)
  }
  if (shouldCheck(Date.now(), lastCheckAt)) checkForUpdate()
}

// Uma vez, depois que a tela desenhou (main.jsx).
export async function startAppBundle() {
  if (!isAppBundleAvailable() || started) return
  started = true
  try {
    await AppBundle.ready()
  } catch (error) {
    console.warn('AppBundle indisponivel:', error)
    return
  }
  App.addListener('pause', () => { hiddenAt = Date.now() })
  App.addListener('resume', onResume)
  checkForUpdate()
}
