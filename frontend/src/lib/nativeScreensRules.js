// As regras da ponte com as telas nativas do APK (lib/nativeScreens.js), como
// funcoes puras: nada de Capacitor, React ou rede, entao os testes rodam com
// `node --test` (nativeScreensRules.test.js).
//
// O APK lista as telas que tem em nativo (NativeScreens.routes()); a web abre
// a nativa so para uma tela listada. Um APK antigo nao lista nada (ou nem tem
// o plugin) e tudo segue nas telas React. O par nativo e
// android/.../ui/nav/NativeScreensPlugin.kt.

// O "+ Novo" (despesa, receita, transferencia, cartao): ui/newentry/ no APK.
export const NEW_ENTRY_SCREEN = 'new-entry'

const NEW_ENTRY_TYPES = ['EXPENSE', 'INCOME', 'TRANSFER', 'CARD']

// A resposta de routes(): so os nomes que sao texto; qualquer outra coisa e
// "nenhuma tela nativa".
export function routesFrom(result) {
  const routes = result?.routes
  if (!Array.isArray(routes)) return []
  return routes.filter((route) => typeof route === 'string' && route)
}

// O pedido de abertura do "+ Novo": o tipo pedido (ou Despesa) e, para
// Pendentes › Corrigir, o client_id do item da fila (o APK le o item na fila
// nativa, que e a mesma da tela).
export function newEntryOpenRequest({ type, editingItem = null } = {}) {
  if (editingItem?.client_id) {
    const kind = NEW_ENTRY_TYPES.includes(editingItem.kind) ? editingItem.kind : 'EXPENSE'
    return { screen: NEW_ENTRY_SCREEN, params: { type: kind, client_id: editingItem.client_id } }
  }
  return { screen: NEW_ENTRY_SCREEN, params: { type: NEW_ENTRY_TYPES.includes(type) ? type : 'EXPENSE' } }
}

// O aviso que veio com "dataChanged" ({ notice: { message, tone, duration } }):
// o toast que a tela nativa mostraria se ainda estivesse aberta. null sem aviso.
export function noticeFrom(event) {
  const notice = event?.notice
  const message = typeof notice?.message === 'string' ? notice.message : ''
  if (!message) return null
  const options = {}
  if (notice.tone === 'success' || notice.tone === 'info') options.tone = notice.tone
  const duration = Number(notice.duration)
  if (Number.isFinite(duration) && duration > 0) options.duration = duration
  return { message, options }
}

// "navigate" ({ route }): so um caminho da propria web ("/ajustes#contas").
export function routeFrom(event) {
  const route = event?.route
  return typeof route === 'string' && route.startsWith('/') && !route.startsWith('//') ? route : ''
}
