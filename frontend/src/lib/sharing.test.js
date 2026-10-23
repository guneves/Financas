import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  groupReceivables,
  othersAmount,
  ownAmount,
  settlePayload,
  shareFormError,
  sharePayload,
  shareSummary,
} from './sharing.js'

const pizza = { type: 'EXPENSE', amount: 80, share_mode: 'SPLIT', share_others_amount: 40.1, share_person: 'Ana' }

test('the owner part of a split, an all-others and a plain row', () => {
  assert.equal(othersAmount(pizza), 40.1)
  assert.equal(ownAmount(pizza), 39.9)
  assert.equal(ownAmount({ amount: 50, share_mode: 'OTHERS' }), 0)
  assert.equal(ownAmount({ amount: 50 }), 50)
  assert.equal(othersAmount({ amount: 50 }), 0)
})

test('the list line says who and the owner part', () => {
  assert.match(shareSummary(pizza), /^Dividida com Ana · sua parte R\$\s39,90$/)
  assert.equal(shareSummary({ amount: 10, share_mode: 'OTHERS', share_person: 'Bruno' }), 'De Bruno')
  assert.equal(shareSummary({ amount: 10 }), '')
})

test('the form needs a name, and a split smaller than the total', () => {
  assert.equal(shareFormError({ share_mode: '' }, 80), '')
  assert.match(shareFormError({ share_mode: 'OTHERS', share_person: ' ' }, 80), /nome/)
  assert.match(shareFormError({ share_mode: 'SPLIT', share_person: 'Ana', share_others_amount: '' }, 80), /parte/)
  assert.match(shareFormError({ share_mode: 'SPLIT', share_person: 'Ana', share_others_amount: '80' }, 80), /menor/)
  assert.equal(shareFormError({ share_mode: 'SPLIT', share_person: 'Ana', share_others_amount: '40' }, 80), '')
})

test('the payload clears with null and trims the name', () => {
  assert.deepEqual(sharePayload({ share_mode: '' }), { share_mode: null })
  assert.deepEqual(sharePayload({ share_mode: 'OTHERS', share_person: ' Ana ', share_others_amount: '9' }), {
    share_mode: 'OTHERS', share_person: 'Ana',
  })
  assert.deepEqual(sharePayload({ share_mode: 'SPLIT', share_person: 'Ana', share_others_amount: '12.5' }), {
    share_mode: 'SPLIT', share_person: 'Ana', share_others_amount: 12.5,
  })
})

test('receivables group by person, case and spaces aside, biggest first', () => {
  const groups = groupReceivables([
    { kind: 'TRANSACTION', id: 't1', person: 'Ana', others_amount: 40.1 },
    { kind: 'CARD_PURCHASE', id: 'c1', person: 'bruno', others_amount: 100 },
    { kind: 'TRANSACTION', id: 't2', person: ' ana ', others_amount: 0.2 },
  ])
  assert.deepEqual(groups.map((group) => [group.person, group.total, group.items.length]), [
    ['bruno', 100, 1],
    ['Ana', 40.3, 2],
  ])
  assert.deepEqual(settlePayload(groups[1].items), { transaction_ids: ['t1', 't2'], cc_expense_ids: [], settled: true })
})

// O fluxo do mes (o cartao no mes da compra, o pagamento da fatura fora, outras
// pessoas a parte) e do servidor: estes dois casos, com as mesmas entradas,
// estao em backend/tests/test_home.py (test_from_sharing_*).
