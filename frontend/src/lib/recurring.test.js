import { test } from 'node:test'
import assert from 'node:assert/strict'
import { recurringAccountOptions, recurringEditPatch } from './recurring.js'

const accounts = [
  { id: 'nubank', name: 'Nubank' },
  { id: 'itau', name: 'Itaú' },
]

test('a recurrence in an archived account can pick another one', () => {
  // A lista de /api/accounts nao traz a arquivada: ela aparece so como a atual.
  const item = { id: 'r', amount: 100, account_id: 'velha' }
  const options = recurringAccountOptions(item, accounts)
  assert.deepEqual(options.map((option) => option.id), ['velha', 'nubank', 'itau'])
  assert.equal(options[0].label, 'Conta arquivada')
  assert.equal(options[0].disabled, true)
  assert.deepEqual(recurringEditPatch(item, { amount: '100', account_id: 'nubank' }), { account_id: 'nubank' })
})

test('the edit sends only what changed', () => {
  const item = { id: 'r', amount: 100, account_id: 'itau' }
  assert.deepEqual(recurringAccountOptions(item, accounts).map((option) => option.id), ['nubank', 'itau'])
  assert.deepEqual(recurringEditPatch(item, { amount: '100', account_id: 'itau' }), {})
  assert.deepEqual(recurringEditPatch(item, { amount: '120,50', account_id: 'itau' }), { amount: 120.5 })
  assert.deepEqual(recurringEditPatch(item, { amount: '1.200', account_id: 'nubank' }), { amount: 1200, account_id: 'nubank' })
})

test('a recurrence without an account shows no archived option', () => {
  const item = { id: 'r', amount: 10, account_id: null }
  assert.deepEqual(recurringAccountOptions(item, accounts).map((option) => option.id), ['nubank', 'itau'])
  assert.deepEqual(recurringEditPatch(item, { amount: '10', account_id: '' }), {})
})
