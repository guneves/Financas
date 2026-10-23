// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { NEW_ENTRY_SCREEN, newEntryOpenRequest, noticeFrom, routeFrom, routesFrom } from './nativeScreensRules.js'

test('rotas nativas: so a lista de textos; APK antigo ou resposta estranha e nenhuma', () => {
  assert.deepEqual(routesFrom({ routes: ['new-entry'] }), ['new-entry'])
  assert.deepEqual(routesFrom({ routes: ['new-entry', 3, null, ''] }), ['new-entry'])
  assert.deepEqual(routesFrom({ routes: [] }), [])
  assert.deepEqual(routesFrom({}), [])
  assert.deepEqual(routesFrom(null), [])
  assert.deepEqual(routesFrom({ routes: 'new-entry' }), [])
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
