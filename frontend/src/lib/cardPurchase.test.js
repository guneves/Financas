import { test } from 'node:test'
import assert from 'node:assert/strict'
import { purchaseInstallments, refundPrefillAmount } from './cardPurchase.js'

// R$ 100 em 3x: 33,34 + 33,33 + 33,33 (o servidor poe o centavo na primeira).
const installments = [
  { id: 'a', amount: 33.34, installment_info: '1/3', status: 'PAID' },
  { id: 'b', amount: 33.33, installment_info: '2/3', status: 'OPEN' },
  { id: 'c', amount: 33.33, installment_info: '3/3', status: 'OPEN' },
]

test('the refund prefill is the purchase total, not one installment times the count', () => {
  // Aberta pela parcela 2/3: 33,33 x 3 = 99,99 deixava um centavo de fora.
  const second = { id: 'b', amount: 33.33, installmentTotal: 3 }
  assert.equal(refundPrefillAmount(second, installments), 100)
  // Pela 1/3: 33,34 x 3 = 100,02.
  const first = { id: 'a', amount: 33.34, installmentTotal: 3 }
  assert.equal(refundPrefillAmount(first, installments), 100)
})

test('without the installments the prefill falls back to the estimate, in cents', () => {
  assert.equal(refundPrefillAmount({ amount: 33.33, installmentTotal: 3 }, []), 99.99)
  assert.equal(refundPrefillAmount({ amount: 0.1, installmentTotal: 3 }, null), 0.3)
  assert.equal(refundPrefillAmount({ amount: 50 }, []), 50)
})

test("a legacy purchase's installments are those within a cent and of the same count", () => {
  const other = { id: 'x', amount: 40, installment_info: '1/3', status: 'OPEN' }
  const twelve = { id: 'y', amount: 33.33, installment_info: '1/12', status: 'OPEN' }
  const found = purchaseInstallments([...installments, other, twelve], { amount: 33.33, installmentTotal: 3 })
  assert.deepEqual(found.map((item) => item.id), ['a', 'b', 'c'])
})
