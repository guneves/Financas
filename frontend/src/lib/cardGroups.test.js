import test from 'node:test'
import assert from 'node:assert/strict'
import { debitRow, mergeCardGroups } from './cardGroups.js'

const purchase = (id, date, extra = {}) => ({ id, date, description: `Compra ${id}`, category: 'Mercado', category_id: 'c1', amount: 10, ...extra })

test('a card with invoices gets its debit purchases in the same group', () => {
  const groups = mergeCardGroups(
    [{ cardId: 'btg', cardName: 'BTG', invoices: [{}], total: 50 }],
    [{ card_id: 'btg', card_name: 'BTG', credit_enabled: true, purchases: [purchase('a', '2026-10-15'), purchase('b', '2026-10-02')] }],
  )
  assert.equal(groups.length, 1)
  assert.deepEqual(groups[0].debit.rows.map((row) => row.id), ['a', 'b'])
  assert.equal(groups[0].withoutInvoices, undefined)
})

test('a debit-only card with purchases comes after the credit cards', () => {
  const groups = mergeCardGroups(
    [{ cardId: 'nu', cardName: 'Nubank', invoices: [{}], total: 50 }],
    [
      { card_id: 'flash', card_name: 'Flash', credit_enabled: false, purchases: [purchase('f', '2026-10-10')] },
      { card_id: 'empty', card_name: 'Vazio', credit_enabled: false, purchases: [] },
    ],
  )
  assert.deepEqual(groups.map((group) => [group.cardId, Boolean(group.withoutInvoices)]), [['nu', false], ['flash', true]])
  assert.equal(groups[0].debit, null)
  assert.deepEqual(groups[1].invoices, [])
})

test('a debit row reads the server fields', () => {
  const row = debitRow(purchase('x', '2026-10-03', { attachment_count: 2, description: '' }))
  assert.equal(row.purchaseKey, 'debit:x')
  assert.equal(row.purchase_date, '2026-10-03')
  assert.equal(row.description, 'Mercado')
  assert.equal(row.attachmentCount, 2)
})

test('no data is no groups', () => {
  assert.deepEqual(mergeCardGroups([], undefined), [])
  assert.deepEqual(mergeCardGroups(undefined, []), [])
})
