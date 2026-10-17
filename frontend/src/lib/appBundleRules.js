// As regras de quando a tela do APK procura e troca de versao (lib/appBundle.js),
// e o texto de cada resposta do lado nativo (android/.../bundle/BundlePlugin.java).
// Funcoes puras, testadas com node --test.

// Procura de novo ao voltar para o app, no maximo a cada 30 min.
export const CHECK_EVERY_MS = 30 * 60_000
// Troca pela tela baixada ao voltar para o app depois de tanto tempo fora — e so
// se nada estiver aberto por cima (um "+ Novo" pela metade nao se perde).
export const APPLY_AFTER_AWAY_MS = 30 * 60_000

export function shouldCheck(now, lastCheckAt) {
  return !lastCheckAt || now - lastCheckAt >= CHECK_EVERY_MS
}

export function shouldApplyOnResume({ awayMs, hasOpenLayer, staged }) {
  return Boolean(staged) && !hasOpenLayer && awayMs >= APPLY_AFTER_AWAY_MS
}

const STATUS_TEXT = {
  'up-to-date': { tone: 'success', text: 'A tela está na versão do servidor.' },
  staged: { tone: 'info', text: 'Versão nova baixada: entra na próxima vez que o app abrir, ou agora com "Reiniciar agora".' },
  incompatible: { tone: 'warning', text: 'O servidor tem uma versão da tela que precisa de um APK novo.' },
  'other-server': { tone: 'warning', text: 'A versão do servidor foi feita para outro endereço da API e não foi baixada.' },
  'failed-before': { tone: 'warning', text: 'A versão do servidor já falhou neste aparelho e não será baixada de novo. O app segue na versão anterior.' },
  none: { tone: 'neutral', text: 'O servidor não oferece atualização da tela.' },
  busy: { tone: 'neutral', text: 'Já procurando atualização…' },
}

// {tone, text} para o resultado de AppBundle.check(), ou de uma falha dele.
export function checkStatusMessage(result) {
  if (!result) return null
  if (result.status === 'error') {
    return { tone: 'danger', text: result.message || 'Não foi possível procurar atualização.' }
  }
  return STATUS_TEXT[result.status] || { tone: 'neutral', text: `Resposta inesperada: ${result.status}` }
}

// Versao curta para exibir (os 16 hex do bundle.json; 7 bastam a olho).
export function shortVersion(version) {
  return version ? String(version).slice(0, 7) : '—'
}

// O APK novo (android/.../update/ApkUpdatePlugin.java, publicado pelo CI em
// /apk/version.json): "Nova versão disponível" quando o publicado tem versionCode
// maior que o instalado. `required` quando a tela do servidor pede um nivel nativo
// acima do instalado (o check deu "incompatible"): sem o APK novo a tela nao atualiza.
// null quando nao ha o que oferecer.
export function apkPrompt({ apk, bundle }) {
  if (!apk?.newer || !apk.latest) return null
  const installedLevel = Number(apk.nativeLevel) || 0
  const bundleLevel = bundle?.status === 'incompatible' ? Number(bundle.nativeLevel) || 0 : 0
  return {
    versionName: apk.latest.versionName || String(apk.latest.versionCode),
    required: bundleLevel > installedLevel || Number(apk.latest.nativeLevel) > installedLevel,
  }
}

const INSTALL_TEXT = {
  installing: { tone: 'info', text: 'Instalador aberto. Toque em "Atualizar"; os dados do app são mantidos.' },
  'needs-permission': {
    tone: 'warning',
    text: 'Permita "Instalar apps desconhecidos" para o Finanças e volte: o download começa sozinho.',
  },
  'up-to-date': { tone: 'success', text: 'O APK instalado já é o mais novo.' },
  busy: { tone: 'neutral', text: 'Já baixando o APK novo…' },
}

// {tone, text} para o resultado de AppUpdate.install(), ou de uma falha dele.
export function installStatusMessage(result) {
  if (!result) return null
  if (result.status === 'error') {
    return { tone: 'danger', text: result.message || 'Não foi possível baixar o APK novo.' }
  }
  return INSTALL_TEXT[result.status] || { tone: 'neutral', text: `Resposta inesperada: ${result.status}` }
}
