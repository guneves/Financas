// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  NEEDS_ATTENTION,
  PENDING,
  applyPendingToAccounts,
  buildItem,
  countByStatus,
  deliveredDiffers,
  endpointFor,
  newClientId,
  outcomeOf,
  pendingAccountDeltas,
  pendingAsTransactions,
  sendOrder,
} from './outboxRules.js'

const item = (kind, payload, extra = {}) => ({
  client_id: `id-${Math.random()}`,
  kind,
  payload,
  status: PENDING,
  created_at: '2026-10-12T10:00:00.000Z',
  ...extra,
})

test('cada formulario tem a sua rota; transferencia nao vai para /api/transactions', () => {
  assert.equal(endpointFor('EXPENSE'), '/api/transactions')
  assert.equal(endpointFor('INCOME'), '/api/transactions')
  assert.equal(endpointFor('TRANSFER'), '/api/transfers')
  assert.equal(endpointFor('CARD'), '/api/cc-expenses/purchases')
  assert.throws(() => endpointFor('INVESTMENT'))
})

test('o client_id tem o formato que o servidor aceita', () => {
  const pattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$/
  for (let i = 0; i < 50; i += 1) assert.match(newClientId(), pattern)
  assert.notEqual(newClientId(), newClientId())
})

test('o item leva o client_id dentro do payload, e mantem o que ja veio', () => {
  const built = buildItem({ kind: 'EXPENSE', payload: { amount: 10 }, userId: 'u1' })
  assert.equal(built.payload.client_id, built.client_id)
  assert.equal(built.status, PENDING)
  assert.equal(built.user_id, 'u1')

  const kept = buildItem({ kind: 'EXPENSE', payload: { amount: 10, client_id: 'ja-existia-123' } })
  assert.equal(kept.client_id, 'ja-existia-123')
})

test('resposta do envio: gravou sai, sem rede e 5xx esperam, 401 para, recusa pede atencao', () => {
  assert.equal(outcomeOf({ ok: true }), 'done')
  assert.equal(outcomeOf({ network: true }), 'retry')
  assert.equal(outcomeOf({ status: 500 }), 'retry')
  assert.equal(outcomeOf({ status: 503 }), 'retry')
  assert.equal(outcomeOf({ status: 401 }), 'stop')
  assert.equal(outcomeOf({ status: 400 }), 'attention')
  assert.equal(outcomeOf({ status: 409 }), 'attention')
  assert.equal(outcomeOf({ status: 404 }), 'attention')
  // Sem nada que diga que o servidor recebeu, o item nunca e descartado.
  assert.equal(outcomeOf({}), 'retry')
  assert.equal(outcomeOf(undefined), 'retry')
})

test('a fila sai na ordem em que foi lancada', () => {
  const late = item('EXPENSE', { amount: 1 }, { created_at: '2026-10-12T12:00:00.000Z', client_id: 'b' })
  const early = item('EXPENSE', { amount: 2 }, { created_at: '2026-10-12T09:00:00.000Z', client_id: 'a' })
  assert.deepEqual(sendOrder([late, early]).map((entry) => entry.client_id), ['a', 'b'])
})

test('despesa tira da conta, receita poe', () => {
  const deltas = pendingAccountDeltas([
    item('EXPENSE', { amount: 25.9, account_id: 'main' }),
    item('INCOME', { amount: 100, account_id: 'main' }),
    item('EXPENSE', { amount: 10, account_id: 'other' }),
  ])
  assert.equal(deltas.get('main'), 7410)
  assert.equal(deltas.get('other'), -1000)
})

test('transferencia mexe nas duas contas e deixa o consolidado onde estava', () => {
  const accounts = [
    { id: 'main', balance: 1000, is_default: true },
    { id: 'savings', balance: 50 },
  ]
  const result = applyPendingToAccounts(accounts, [
    item('TRANSFER', { amount: 300, account_id: 'main', transfer_account_id: 'savings' }),
  ])
  assert.equal(result[0].balance, 700)
  assert.equal(result[1].balance, 350)
  const total = (list) => list.reduce((acc, account) => acc + account.balance, 0)
  assert.equal(total(result), total(accounts))
})

test('compra no cartao pendente nao toca em nenhuma conta', () => {
  const accounts = [{ id: 'main', balance: 1000, is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('CARD', { total_amount: 900, installments: 3, card_id: 'c1' }),
  ])
  assert.equal(result, accounts)
})

test('lancamento sem conta cai na conta padrao, como no servidor', () => {
  const accounts = [{ id: 'a', balance: 10 }, { id: 'main', balance: 100, is_default: true }]
  const result = applyPendingToAccounts(accounts, [item('EXPENSE', { amount: 30 })])
  assert.equal(result[0].balance, 10)
  assert.equal(result[1].balance, 70)
  assert.equal(result[1].balance_estimated, true)
})

test('item recusado pelo servidor nao entra no saldo estimado', () => {
  const accounts = [{ id: 'main', balance: 100, is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('EXPENSE', { amount: 30, account_id: 'main' }, { status: NEEDS_ATTENTION }),
  ])
  assert.equal(result, accounts)
})

test('centavos nao se perdem na soma', () => {
  const accounts = [{ id: 'main', balance: 0.3, balance_brl: 0.3, currency: 'BRL', is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('EXPENSE', { amount: 0.1, account_id: 'main' }),
    item('EXPENSE', { amount: 0.2, account_id: 'main' }),
  ])
  assert.equal(result[0].balance, 0)
  assert.equal(result[0].balance_brl, 0)
})

test('conta em moeda estrangeira: o saldo convertido nao e estimado sem cotacao', () => {
  const accounts = [{ id: 'usd', balance: 100, balance_brl: 550, currency: 'USD' }]
  const result = applyPendingToAccounts(accounts, [item('EXPENSE', { amount: 10, account_id: 'usd' })])
  assert.equal(result[0].balance, 90)
  assert.equal(result[0].balance_brl, 550)
})

test('sem pendentes a lista de contas volta a mesma (nada a recalcular)', () => {
  const accounts = [{ id: 'main', balance: 1 }]
  assert.equal(applyPendingToAccounts(accounts, []), accounts)
})

test('linhas do extrato: mais recente primeiro, sem a compra no cartao', () => {
  const rows = pendingAsTransactions([
    item('EXPENSE', { amount: 5, date: '2026-10-12', category: 'Mercado', description: 'Pao' }, { client_id: 'a', created_at: '2026-10-12T09:00:00.000Z' }),
    item('CARD', { total_amount: 90, purchase_date: '2026-10-12' }, { client_id: 'b', created_at: '2026-10-12T09:30:00.000Z' }),
    item('TRANSFER', { amount: 7, date: '2026-10-12', account_id: 'x', transfer_account_id: 'y' }, { client_id: 'c', created_at: '2026-10-12T10:00:00.000Z' }),
  ], { defaultAccountId: 'main' })
  assert.deepEqual(rows.map((row) => row.id), ['pending:c', 'pending:a'])
  assert.equal(rows[1].account_id, 'main')
  assert.equal(rows[0].type, 'TRANSFER')
  assert.equal(rows[0].transfer_account_id, 'y')
  assert.ok(rows.every((row) => row.pending))
})

test('item corrigido: o servidor devolver a versao antiga nao passa por entregue', () => {
  const edited = item('EXPENSE', { amount: 5, date: '2026-10-12', account_id: 'main' })
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), false)
  assert.equal(deliveredDiffers(edited, { amount: 50, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-11', type: 'EXPENSE', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'INCOME', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'other' }), true)
  // Sem conta no envio, o servidor escolheu a padrao: nao e diferenca.
  const noAccount = item('EXPENSE', { amount: 5, date: '2026-10-12' })
  assert.equal(deliveredDiffers(noAccount, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), false)

  const transfer = item('TRANSFER', { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'b' })
  assert.equal(deliveredDiffers(transfer, { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'b' }), false)
  assert.equal(deliveredDiffers(transfer, { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'c' }), true)

  const card = item('CARD', { total_amount: 100, installments: 3, purchase_date: '2026-10-12', card_id: 'c1' })
  const rows = [33.34, 33.33, 33.33].map((amount) => ({ amount, purchase_date: '2026-10-12', card_id: 'c1' }))
  assert.equal(deliveredDiffers(card, rows), false)
  assert.equal(deliveredDiffers(card, rows.slice(0, 2)), true)
  assert.equal(deliveredDiffers({ ...card, payload: { ...card.payload, total_amount: 90 } }, rows), true)
})

test('contagem por estado', () => {
  assert.deepEqual(
    countByStatus([item('EXPENSE', {}), item('EXPENSE', {}), item('EXPENSE', {}, { status: NEEDS_ATTENTION })]),
    { [PENDING]: 2, [NEEDS_ATTENTION]: 1 }
  )
})
