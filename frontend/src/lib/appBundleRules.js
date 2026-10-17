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
  staged: { tone: 'info', text: 'Versão nova baixada: entra na próxima vez que o app abrir.' },
  incompatible: { tone: 'warning', text: 'O servidor tem uma versão que precisa de um APK novo. Instale o APK atualizado.' },
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
