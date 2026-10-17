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
// O APK novo (android/.../update/ApkUpdatePlugin.java) e procurado junto: quando o
// CI publicou um mais novo que o instalado, a tela mostra "Nova versão disponível"
// (components/ApkUpdateBanner.jsx) e installApk() baixa e abre o instalador.
//
// No navegador nada daqui roda: o Flask ja serve a tela nova.
import { Capacitor, registerPlugin } from '@capacitor/core'
import { App } from '@capacitor/app'
import { API_BASE_URL } from './api'
import { hasOpenLayer } from './layers'
import { shouldApplyOnResume, shouldCheck } from './appBundleRules'

const AppBundle = registerPlugin('AppBundle')
const AppUpdate = registerPlugin('AppUpdate')

let started = false
let lastCheckAt = 0
let hiddenAt = null
let lastResult = null
let apkState = null
let apkInstall = null
// O dono foi a tela "Instalar apps desconhecidos": ao voltar, a instalacao segue.
let installAfterPermission = false
const subscribers = new Set()

function notify() {
  for (const subscriber of subscribers) subscriber(lastResult)
}

function publish(result) {
  lastResult = result
  notify()
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

// O APK publicado: {installedCode, nativeLevel, latest, newer, canInstall}, ou null.
export function getApkState() {
  return apkState
}

// O resultado da ultima instalacao pedida ({status}), para o texto na tela.
export function getApkInstall() {
  return apkInstall
}

async function checkApk() {
  try {
    apkState = await AppUpdate.latest({ baseUrl: API_BASE_URL })
  } catch (error) {
    // Sem o APK publicado (ou sem rede) a tela segue; Ajustes mostra so a tela.
    console.warn('APK publicado:', error)
  }
  notify()
  return apkState
}

export async function checkForUpdate() {
  lastCheckAt = Date.now()
  const apk = checkApk()
  let result
  try {
    result = await AppBundle.check({ baseUrl: API_BASE_URL })
  } catch (error) {
    result = { status: 'error', message: error?.message }
  }
  publish(result)
  await apk
  return result
}

// "Nova versão disponível": baixa o APK e abre o instalador do Android. Na
// primeira vez o Android pede a permissao de instalar; installAfterPermission
// faz o download seguir quando o dono volta de la.
export async function installApk() {
  let result
  try {
    result = await AppUpdate.install({ baseUrl: API_BASE_URL })
  } catch (error) {
    result = { status: 'error', message: error?.message }
  }
  installAfterPermission = result.status === 'needs-permission'
  apkInstall = result
  notify()
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
  if (installAfterPermission) {
    installAfterPermission = false
    const apk = await checkApk()
    if (apk?.canInstall) installApk()
    return
  }
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
