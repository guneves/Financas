import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildMonthlyFlow } from './cashFlow.js'
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

const keys = ['2026-02', '2026-03']

test('a card purchase counts in its purchase month and the invoice payment does not', () => {
  const flow = buildMonthlyFlow({
    keys,
    transactions: [
      { type: 'EXPENSE', amount: 300, date: '2026-03-10', category: 'Pagamento Fatura Nubank', source_type: 'CC_INVOICE_PAYMENT' },
      { type: 'EXPENSE', amount: 50, date: '2026-03-11', category: 'Pagamento Fatura antigo' },
      { type: 'INCOME', amount: 1000, date: '2026-02-01', category: 'Salário' },
    ],
    ccExpenses: [
      { amount: 100, purchase_date: '2026-02-20' },
      { amount: 100, purchase_date: '2026-02-20' },
      { amount: 100, purchase_date: '2026-02-20' },
    ],
  })
  assert.equal(flow[0].expense, -300)
  assert.equal(flow[1].expense, 0)
  // O saldo e o das contas: o pagamento da fatura sai em marco.
  assert.equal(flow[0].balance, 1000)
  assert.equal(flow[1].balance, 650)
})

test('other people stay apart from income and expense, but in the result', () => {
  const flow = buildMonthlyFlow({
    keys,
    openingBalance: 100,
    transactions: [
      { ...pizza, date: '2026-03-05' },
      { type: 'INCOME', amount: 40.1, date: '2026-03-06', category: 'Pix', share_mode: 'OTHERS', share_person: 'Ana' },
      { type: 'INCOME', amount: 500, date: '2026-03-01', category: 'Salário' },
      { type: 'EXPENSE', amount: 200, date: '2026-03-02', source_type: 'INVESTMENT_TRANSACTION', category: 'Aporte' },
      { type: 'TRANSFER', amount: 999, date: '2026-03-02' },
      { type: 'EXPENSE', amount: 5, date: '2026-01-31' },
    ],
    ccExpenses: [{ amount: 60, purchase_date: '2026-03-08', share_mode: 'OTHERS', share_person: 'Bruno' }],
  })
  const march = flow[1]
  assert.equal(march.income, 500)
  assert.equal(march.expense, -39.9)
  assert.equal(march.othersPaid, 100.1)
  assert.equal(march.othersReceived, 40.1)
  assert.equal(march.others, -60)
  assert.equal(march.invested, 200)
  assert.equal(march.net, 200.1)
  assert.equal(march.balance, 355.1)
})
