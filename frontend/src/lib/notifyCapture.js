// Ajustes › Notificações dos bancos, so no APK (mobile-docs/steps-to-production.md,
// Fase 6). O leitor e Java (android/.../notify/): o Android o liga quando o dono
// permite o acesso as notificacoes, e ele ouve so os apps da lista, com o app
// fechado tambem. Ainda nao ha parser: com a captura ligada, cada notificacao
// desses apps e guardada palavra por palavra numa tabela do aparelho, para os
// parsers serem escritos contra o texto real.
//
// Os textos nunca vao ao servidor: saem do aparelho so pela exportacao (a folha
// de compartilhar do Android). No navegador nada daqui roda.
import { Capacitor, registerPlugin } from '@capacitor/core'
import { App } from '@capacitor/app'

const Notify = registerPlugin('Notify')

export function isNotifyAvailable() {
  return Capacitor.isNativePlatform()
}

// {granted, captureOn, captureSince, connectedAt, disconnectedAt, acceptsShell, sdk,
//  installer, apps: [{package, label, installed, count, lastPostedAt}], total}
export function getNotifyStatus() {
  return Notify.status()
}

export function setCapture(on) {
  return Notify.setCapture({ on })
}

// As ultimas guardadas, mais recentes primeiro: {package, app, postedAt, title, text, via}.
export async function latestCaptured(limit = 20) {
  return (await Notify.latest({ limit })).items || []
}

// 'json' ou 'text'. Abre a folha de compartilhar; resolve {count, file}.
export function exportCapture(format) {
  return Notify.export({ format })
}

export function clearCapture() {
  return Notify.clear()
}

export function openAccessSettings() {
  return Notify.openAccessSettings()
}

export function openAppDetails() {
  return Notify.openAppDetails()
}

// O leitor guardou algo (ou o Android o ligou), ou o dono voltou dos Ajustes do
// Android depois de mexer no acesso: quem assina rele o estado.
export function subscribeNotify(callback) {
  const handles = [Notify.addListener('changed', callback), App.addListener('resume', callback)]
  return () => {
    for (const handle of handles) {
      Promise.resolve(handle).then((listener) => listener.remove()).catch(() => {})
    }
  }
}
