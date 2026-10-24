// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  HOME_SCREEN,
  HOME_WEB_ROUTE,
  INBOX_SCREEN,
  NATIVE_PAGE_FALLBACK_ROUTE,
  EXTRATO_SCREEN,
  CARTOES_SCREEN,
  AJUSTES_SCREEN,
  ORCAMENTO_SCREEN,
  signOutFrom,
  themePreferenceFrom,
  NEW_ENTRY_SCREEN,
  nativePageExit,
  nativePageOpenRequest,
  newEntryOpenRequest,
  noticeFrom,
  pendingStartRoute,
  START_ROUTE_MAX_AGE_MS,
  privacyFromNative,
  routeFrom,
  routesFrom,
  wantsWebPage,
} from './nativeScreensRules.js'

test('rotas nativas: so a lista de textos; APK antigo ou resposta estranha e nenhuma', () => {
  assert.deepEqual(routesFrom({ routes: ['new-entry'] }), ['new-entry'])
  assert.deepEqual(routesFrom({ routes: ['new-entry', 3, null, ''] }), ['new-entry'])
  assert.deepEqual(routesFrom({ routes: [] }), [])
  assert.deepEqual(routesFrom({}), [])
  assert.deepEqual(routesFrom(null), [])
  assert.deepEqual(routesFrom({ routes: 'new-entry' }), [])
  assert.deepEqual(routesFrom({ routes: ['new-entry', 'inbox'] }), [NEW_ENTRY_SCREEN, INBOX_SCREEN])
})

test('abrir o "+ Novo": o tipo pedido, ou despesa', () => {
  assert.deepEqual(newEntryOpenRequest({ type: 'CARD' }), { screen: NEW_ENTRY_SCREEN, params: { type: 'CARD' } })
  assert.deepEqual(newEntryOpenRequest({ type: 'INCOME' }).params, { type: 'INCOME' })
  assert.deepEqual(newEntryOpenRequest({}).params, { type: 'EXPENSE' })
  assert.deepEqual(newEntryOpenRequest().params, { type: 'EXPENSE' })
  assert.deepEqual(newEntryOpenRequest({ type: 'BUY' }).params, { type: 'EXPENSE' })
})

test('Corrigir um pendente abre o item da fila pelo client_id', () => {
  const editingItem = { client_id: 'abc12345', kind: 'TRANSFER', payload: { amount: 5 } }
  assert.deepEqual(newEntryOpenRequest({ type: 'CARD', editingItem }), {
    screen: NEW_ENTRY_SCREEN,
    params: { type: 'TRANSFER', client_id: 'abc12345' },
  })
  assert.deepEqual(newEntryOpenRequest({ editingItem: { client_id: 'x1234567', kind: 'BUY' } }).params, { type: 'EXPENSE', client_id: 'x1234567' })
})

test('o aviso que a tela nativa manda vira o toast da web', () => {
  assert.deepEqual(
    noticeFrom({ notice: { message: 'Despesa de R$ 10,00 registrada.', tone: 'success', duration: 4000 } }),
    { message: 'Despesa de R$ 10,00 registrada.', options: { tone: 'success', duration: 4000 } },
  )
  assert.deepEqual(noticeFrom({ notice: { message: 'Sem conexão: ...', tone: 'info', duration: 6000 } }).options, { tone: 'info', duration: 6000 })
  assert.deepEqual(noticeFrom({ notice: { message: 'x', tone: 'danger', duration: 'abc' } }).options, {})
  assert.equal(noticeFrom({}), null)
  assert.equal(noticeFrom({ notice: { message: '' } }), null)
  assert.equal(noticeFrom(null), null)
})

test('navigate: so um caminho da propria web', () => {
  assert.equal(routeFrom({ route: '/ajustes#contas' }), '/ajustes#contas')
  assert.equal(routeFrom({ route: 'https://exemplo.com' }), '')
  assert.equal(routeFrom({ route: '//exemplo.com' }), '')
  assert.equal(routeFrom({}), '')
})

test('Aprovar abre a pagina nativa, sem parametros', () => {
  assert.equal(INBOX_SCREEN, 'inbox')
  assert.deepEqual(nativePageOpenRequest(INBOX_SCREEN), { screen: 'inbox', params: {} })
})

test('depois de abrir a nativa, a WebView volta para a tela de antes (ou o Extrato da web)', () => {
  assert.deepEqual(nativePageExit({ hasHistory: true }), { back: true, route: '' })
  assert.deepEqual(nativePageExit({ hasHistory: false }), { back: false, route: NATIVE_PAGE_FALLBACK_ROUTE })
  // ?web=1: o Extrato e nativo tambem, e a volta nao pode abri-lo de novo.
  assert.deepEqual(nativePageExit(), { back: false, route: '/lancamentos/extrato?web=1' })
  assert.equal(wantsWebPage(NATIVE_PAGE_FALLBACK_ROUTE.split('?')[1]), true)
})

test('Extrato e Cartoes abrem nativos; o Extrato leva a vista da URL', () => {
  assert.equal(EXTRATO_SCREEN, 'extrato')
  assert.equal(CARTOES_SCREEN, 'cartoes')
  assert.deepEqual(nativePageOpenRequest(EXTRATO_SCREEN, '?ver=investimentos'), { screen: 'extrato', params: { view: 'investimentos' } })
  assert.deepEqual(nativePageOpenRequest(EXTRATO_SCREEN, '?ver=contas&q=uber'), { screen: 'extrato', params: { view: 'contas' } })
  assert.deepEqual(nativePageOpenRequest(EXTRATO_SCREEN, '?ver=outra'), { screen: 'extrato', params: {} })
  assert.deepEqual(nativePageOpenRequest(EXTRATO_SCREEN), { screen: 'extrato', params: {} })
  assert.deepEqual(nativePageOpenRequest(CARTOES_SCREEN, '?ver=investimentos'), { screen: 'cartoes', params: {} })
})

test('Inicio abre a pagina nativa; ?web=1 fica na web', () => {
  assert.equal(HOME_SCREEN, 'home')
  assert.deepEqual(nativePageOpenRequest(HOME_SCREEN), { screen: 'home', params: {} })
  assert.deepEqual(routesFrom({ routes: ['new-entry', 'inbox', 'home'] }), ['new-entry', 'inbox', HOME_SCREEN])
  assert.equal(HOME_WEB_ROUTE, '/inicio?web=1')
  assert.equal(wantsWebPage('?web=1'), true)
  assert.equal(wantsWebPage('?a=2&web=1'), true)
  assert.equal(wantsWebPage(''), false)
  assert.equal(wantsWebPage('?web=0'), false)
  assert.equal(wantsWebPage(undefined), false)
  // O link da nativa para o Inicio da web e uma rota da propria web.
  assert.equal(routeFrom({ route: HOME_WEB_ROUTE }), HOME_WEB_ROUTE)
})

test('o modo privado do APK: so true/false; o resto e "nada guardado"', () => {
  assert.equal(privacyFromNative({ hidden: true }), true)
  assert.equal(privacyFromNative({ hidden: false }), false)
  assert.equal(privacyFromNative({}), null)
  assert.equal(privacyFromNative({ hidden: 'true' }), null)
  assert.equal(privacyFromNative(null), null)
})

test('a rota guardada pela nativa vale so por dois minutos depois de lida', () => {
  const at = 1_000_000
  assert.equal(pendingStartRoute({ route: '/lancamentos/cartoes', at }, at), '/lancamentos/cartoes')
  assert.equal(pendingStartRoute({ route: '/ajustes', at }, at + START_ROUTE_MAX_AGE_MS), '/ajustes')
  assert.equal(pendingStartRoute({ route: '/ajustes', at }, at + START_ROUTE_MAX_AGE_MS + 1), '')
  assert.equal(pendingStartRoute({ route: '/ajustes', at }, at - 1), '')
  assert.equal(pendingStartRoute({ route: 'https://x', at }, at), '')
  assert.equal(pendingStartRoute({ at }, at), '')
  assert.equal(pendingStartRoute(null, at), '')
})

test('Ajustes: a secao nativa vai junto; Regras e Integracoes ficam na web', () => {
  assert.deepEqual(nativePageOpenRequest(AJUSTES_SCREEN, '', '#categorias'), { screen: 'ajustes', params: { section: 'categorias' } })
  assert.deepEqual(nativePageOpenRequest(AJUSTES_SCREEN, '', ''), { screen: 'ajustes', params: {} })
  assert.deepEqual(nativePageOpenRequest(AJUSTES_SCREEN, '', '#outra'), { screen: 'ajustes', params: {} })
  assert.deepEqual(nativePageOpenRequest(ORCAMENTO_SCREEN, '?ver=contas', '#x'), { screen: 'orcamento', params: {} })
  assert.equal(wantsWebPage('', '#regras-de-importacao'), true)
  assert.equal(wantsWebPage('', '#integracoes'), true)
  assert.equal(wantsWebPage('', '#contas'), false)
  assert.equal(wantsWebPage('?web=1', '#contas'), true)
  assert.equal(wantsWebPage(''), false)
})

test('o tema e o Sair pedidos pela tela nativa', () => {
  assert.equal(themePreferenceFrom({ preference: 'dark' }), 'dark')
  assert.equal(themePreferenceFrom({ preference: 'roxo' }), '')
  assert.equal(themePreferenceFrom({}), '')
  assert.equal(themePreferenceFrom(null), '')
  assert.equal(signOutFrom({ signOut: true }), true)
  assert.equal(signOutFrom({ signOut: 'true' }), false)
  assert.equal(signOutFrom(undefined), false)
})
