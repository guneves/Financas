import test from 'node:test'
import assert from 'node:assert/strict'
import { purchaseEditPayload } from './cardPurchaseEdit.js'

const purchase = { description: 'Loja', category_id: 'cat-a' }

test('sends only what changed', () => {
  assert.deepEqual(purchaseEditPayload(purchase, { description: 'Loja', category_id: 'cat-b' }), { payload: { category_id: 'cat-b' } })
  assert.deepEqual(purchaseEditPayload(purchase, { description: ' Cinema ', category_id: 'cat-a' }), { payload: { description: 'Cinema' } })
  assert.deepEqual(
    purchaseEditPayload(purchase, { description: 'Cinema', category_id: 'cat-b' }),
    { payload: { description: 'Cinema', category_id: 'cat-b' } },
  )
})

test('nothing changed is a null payload', () => {
  assert.deepEqual(purchaseEditPayload(purchase, { description: 'Loja ', category_id: 'cat-a' }), { payload: null })
})

test('an empty category keeps the current one', () => {
  assert.deepEqual(purchaseEditPayload({ description: 'Loja', category_id: null }, { description: 'Loja', category_id: '' }), { payload: null })
})

test('the description is required and bounded', () => {
  assert.ok(purchaseEditPayload(purchase, { description: '  ', category_id: 'cat-a' }).error)
  assert.ok(purchaseEditPayload(purchase, { description: 'x'.repeat(501), category_id: 'cat-a' }).error)
})
