// O que muda quando a tela roda dentro do APK (Capacitor), e so ali
// (mobile-docs/steps-to-production.md, Fase 5). No navegador nada daqui roda.
//
// - A fila de envio passa a ser nativa: SQLite no aparelho e um remetente do
//   WorkManager, que envia com o app fechado (android/.../outbox/). A tela so
//   le, grava e pede uma rodada; quem fala com o servidor e o Java.
// - O remetente nativo precisa do endereco da API e do token: entram no login,
//   saem no logout (o evento finance-auth-change de lib/api.js).
// - O botao voltar do Android fecha o que estiver aberto, depois volta de tela.
// - As barras do sistema seguem o tema do app (lib/theme.js).
// - O modo privado (o olho) e um so com as telas nativas: cada troca vai para o
//   Java, e ao voltar para a WebView vale o que a nativa deixou.
// - Telas nativas (lib/nativeScreens.js): o "+ Novo" abre em Kotlin quando o
//   APK o lista; ao gravar, o APK avisa ("dataChanged") e aqui a fila e os
//   dados sao relidos, com o toast que a tela nativa mandou.
import { Capacitor, registerPlugin } from '@capacitor/core'
import { App } from '@capacitor/app'
import { API_BASE_URL, getStoredAuth } from './api'
import { reloadOutbox, setOutboxBackend } from './outbox'
import { invalidateServerData } from './queries'
import { closeTopLayer } from './layers'
import { onNativeEvent, startNativeScreens } from './nativeScreens'
import { noticeFrom, privacyFromNative } from './nativeScreensRules'
import { onValuesHiddenChange, setValuesHidden, valuesHiddenNow } from './privacy'
import { toast } from './toast'

const Outbox = registerPlugin('Outbox')
const Shell = registerPlugin('Shell')

export function isNativeApp() {
  return Capacitor.isNativePlatform()
}

const nativeOutboxBackend = {
  all: async () => (await Outbox.all()).items || [],
  put: (item) => Outbox.put({ item }),
  remove: (clientId) => Outbox.remove({ clientId }),
  flush: ({ retryAttention = false } = {}) => Outbox.flush({ retryAttention }),
  isOffline: async () => !(await Outbox.hasNetwork()).online,
  sendsOnItsOwn: true,
}

function syncSession() {
  const auth = getStoredAuth()
  const token = auth?.access_token
  const userId = auth?.user?.id
  const call = token && userId
    ? Outbox.setSession({ baseUrl: API_BASE_URL, token, userId: String(userId) })
    : Outbox.clearSession()
  return call.catch((error) => console.warn('Sessao do envio nativo:', error))
}

// O fundo de cada tema (os mesmos de lib/theme.js e de res/values*/app_colors.xml).
// Nao le o meta theme-color: na abertura o index.html poe a classe `dark` mas
// deixa o meta no valor claro, e as barras ficavam claras sob um app escuro.
function applyTheme() {
  const dark = document.documentElement.classList.contains('dark')
  Shell.setTheme({ dark, background: dark ? '#0B1210' : '#EFF2ED' }).catch(() => {})
}

// O modo privado no APK (native-level 5): o Java guarda a ultima escolha, de
// qualquer um dos lados. Um APK sem os metodos recusa a chamada e o modo fica
// so na web, como antes.
function pushValuesHidden() {
  Shell.setValuesHidden({ hidden: valuesHiddenNow() }).catch(() => {})
}

async function pullValuesHidden() {
  let stored = null
  try {
    stored = privacyFromNative(await Shell.getValuesHidden())
  } catch {
    return
  }
  // Nada guardado ainda (primeira abertura neste APK): vale o da web.
  if (stored === null) pushValuesHidden()
  else if (stored !== valuesHiddenNow()) setValuesHidden(stored)
}

// Algo aberto por cima da tela (sheet, confirmacao, menu)? O voltar fecha so o
// de cima, como o Esc (lib/layers.js).
function onBackButton({ canGoBack }) {
  if (closeTopLayer()) return
  if (canGoBack && window.location.pathname !== '/') {
    window.history.back()
    return
  }
  // Na tela inicial o voltar sai do app sem mata-lo: a fila e o cache continuam.
  App.minimizeApp().catch(() => {})
}

// Chamado uma vez no main.jsx, antes de startOutbox().
export async function startNativeApp() {
  if (!isNativeApp()) return
  if (!API_BASE_URL.startsWith('http')) {
    console.warn('APK gerado sem VITE_API_BASE_URL: o envio nativo nao tem para onde ir.')
  }
  await setOutboxBackend(nativeOutboxBackend)
  // O remetente nativo enviou (ou o servidor recusou) com a tela aberta: relê a
  // fila e, se algo chegou ao servidor, os saldos e o extrato.
  Outbox.addListener('changed', ({ sent }) => {
    reloadOutbox()
    if (sent) invalidateServerData()
  })
  await syncSession()
  window.addEventListener('finance-auth-change', syncSession)
  // Uma tela nativa gravou (ou guardou na fila): a pilula de pendentes, os
  // saldos e o extrato se atualizam, e o toast dela aparece aqui.
  onNativeEvent((type, data) => {
    if (type !== 'dataChanged') return
    reloadOutbox()
    invalidateServerData()
    const notice = noticeFrom(data)
    if (notice) toast(notice.message, notice.options)
  })
  await startNativeScreens()
  applyTheme()
  window.addEventListener('finance-theme-change', applyTheme)
  // O olho: o que esta guardado no APK vale na abertura e ao voltar de uma
  // tela nativa (que pode ter trocado o modo); cada troca daqui vai para la.
  await pullValuesHidden()
  onValuesHiddenChange(pushValuesHidden)
  App.addListener('resume', () => { pullValuesHidden() })
  App.addListener('backButton', onBackButton)
}
