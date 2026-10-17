// Os textos de Ajustes › Notificações dos bancos, sem navegador nem React (testados
// com node --test). Quem fala com o leitor nativo e lib/notifyCapture.js; o estado
// vem de NotifyPlugin.status() (android/.../notify/NotifyPlugin.java).

// Android 13: o acesso as notificacoes de um app instalado por um arquivo APK aberto
// no celular fica bloqueado ate "Permitir configurações restritas".
export const RESTRICTED_SETTINGS_SDK = 33

// O comando que posta uma notificacao de teste pelo caminho normal (so o APK de teste a guarda).
export const ADB_TEST_COMMAND = 'adb shell cmd notification post -S bigtext -t "Compra aprovada" teste "Compra de R$ 10,00 em LOJA TESTE"'

function pad(value, size = 2) {
  return String(value).padStart(size, '0')
}

// Hora local do aparelho; com segundos na lista, para comparar o Samsung Wallet com o banco.
export function formatStamp(ms, { seconds = false } = {}) {
  if (!ms) return ''
  const date = new Date(ms)
  const day = `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}${seconds ? `:${pad(date.getSeconds())}` : ''}`
  return `${day} ${time}`
}

export function countLabel(count) {
  if (!count) return 'nenhuma'
  return count === 1 ? '1 notificação' : `${count} notificações`
}

export function accessMessage(status) {
  if (!status) return null
  if (status.granted) {
    return { tone: 'success', text: 'Acesso permitido: o Android entrega ao Finanças as notificações dos apps abaixo, mesmo com o app fechado.' }
  }
  return { tone: 'warning', text: 'Sem acesso às notificações. Toque em “Abrir acesso às notificações” e ligue o Finanças.' }
}

// Se o Android ligou mesmo o leitor (o acesso pode estar permitido e o leitor parado).
export function listenerMessage(status) {
  if (!status?.granted) return null
  const { connectedAt = 0, disconnectedAt = 0 } = status
  if (connectedAt && connectedAt >= disconnectedAt) return `Leitor ligado pelo Android em ${formatStamp(connectedAt)}.`
  if (disconnectedAt) {
    return `O Android desligou o leitor em ${formatStamp(disconnectedAt)}. Se não voltar sozinho, desligue e ligue o acesso de novo.`
  }
  return 'O Android ainda não ligou o leitor. Feche e abra o app; se continuar assim, desligue e ligue o acesso de novo.'
}

// A explicacao das configuracoes restritas abre sozinha quando e o caso provavel.
export function showsRestrictedHelp(status) {
  return Boolean(status) && !status.granted && Number(status.sdk) >= RESTRICTED_SETTINGS_SDK
}

const INSTALLERS = {
  'com.android.shell': 'o cabo USB (adb install)',
  'br.financas.app': 'o próprio app (Nova versão disponível)',
  'com.android.packageinstaller': 'o instalador do Android (arquivo APK aberto no celular)',
  'com.google.android.packageinstaller': 'o instalador do Android (arquivo APK aberto no celular)',
  'com.samsung.android.packageinstaller': 'o instalador do Android (arquivo APK aberto no celular)',
  'com.android.vending': 'a Play Store',
}

// Quem instalou o APK (NotifyPlugin.installer): e o que decide se o Android 13+ trava o acesso.
export function installerLabel(installer) {
  if (!installer) return 'desconhecido'
  return INSTALLERS[installer] || installer
}

export function captureMessage(status) {
  if (!status) return ''
  const total = Number(status.total) || 0
  if (status.captureOn) {
    const since = status.captureSince ? ` desde ${formatStamp(status.captureSince)}` : ''
    return total
      ? `Ligada${since}: ${countLabel(total)} guardada${total === 1 ? '' : 's'}.`
      : `Ligada${since}. Nada chegou ainda dos apps abaixo.`
  }
  return total
    ? `Desligada. ${countLabel(total)} guardada${total === 1 ? '' : 's'} continua${total === 1 ? '' : 'm'} aqui até exportar ou apagar.`
    : 'Desligada: nenhuma notificação é guardada.'
}

// Os apps ouvidos, na ordem do Java; o shell do adb (APK de teste) so quando guardou algo.
export function appRows(status) {
  return (status?.apps || [])
    .filter((app) => app.count > 0 || app.package !== 'com.android.shell')
    .map((app) => {
      let detail = 'nada ainda'
      if (app.count > 0) detail = `${countLabel(app.count)} · última ${formatStamp(app.lastPostedAt)}`
      else if (app.installed === false) detail = 'não instalado'
      return { ...app, detail }
    })
}
