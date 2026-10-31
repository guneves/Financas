import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  cardAmountSign,
  isCardRow,
  mergeStatement,
  oldestDate,
  reviewCategoryType,
  reviewHasCategory,
  reviewNoticeText,
  reviewCanBeRepasse,
  reviewPayload,
  reviewPlace,
  reviewSign,
  statementKey,
  waitingNoticeText,
} from './review.js'

const tx = (id, date, created_at = `${date}T10:00:00Z`) => ({ id, date, created_at, type: 'EXPENSE' })
const card = (id, date, extra = {}) => ({ id, client_id: `c-${id}`, date, created_at: `${date}T12:00:00Z`, type: 'CARD', ...extra })

test('card purchases are interleaved by date, newest first', () => {
  const merged = mergeStatement([tx('t2', '2026-10-12'), tx('t1', '2026-10-10')], [card('p1', '2026-10-11'), card('p0', '2026-10-09')])
  assert.deepEqual(merged.map(statementKey), ['t2', 'card:c-p1', 't1', 'card:c-p0'])
  assert.equal(isCardRow(merged[1]), true)
  assert.equal(isCardRow(merged[0]), false)
})

test('on the same day the later one comes first', () => {
  const merged = mergeStatement([tx('t1', '2026-10-10', '2026-10-10T09:00:00Z')], [card('p1', '2026-10-10')])
  assert.deepEqual(merged.map(statementKey), ['card:c-p1', 't1'])
})

test('without purchases the list is the same object', () => {
  const list = [tx('t1', '2026-10-10')]
  assert.equal(mergeStatement(list, []), list)
  assert.equal(mergeStatement(list, undefined), list)
})

test('a paged statement shows only purchases down to the oldest loaded day', () => {
  const merged = mergeStatement([tx('t1', '2026-10-10')], [card('p1', '2026-10-11'), card('p0', '2026-10-01')], { until: '2026-10-10' })
  assert.deepEqual(merged.map(statementKey), ['card:c-p1', 't1'])
  assert.equal(oldestDate(merged), '2026-10-10')
  assert.equal(oldestDate([]), '')
})

test('a purchase goes out, a refund comes back', () => {
  assert.equal(cardAmountSign({ type: 'CARD' }), -1)
  assert.equal(cardAmountSign({ type: 'REFUND' }), 1)
})

test('the review line says where it came from', () => {
  assert.equal(reviewPlace({ table: 'cc_expenses', card_name: 'Itaú Visa', installments: 3 }), 'Itaú Visa · 3x')
  assert.equal(reviewPlace({ table: 'cc_expenses', card_name: 'Itaú Visa', installments: 1 }), 'Itaú Visa')
  assert.equal(reviewPlace({ table: 'transactions', type: 'EXPENSE', account_name: 'Itaú' }), 'Itaú')
  assert.equal(reviewPlace({ table: 'transactions', type: 'TRANSFER', account_name: 'Itaú', transfer_account_name: 'BB' }), 'Itaú → BB')
})

test('signs and category types follow the movement', () => {
  assert.equal(reviewSign({ type: 'EXPENSE' }), -1)
  assert.equal(reviewSign({ type: 'CARD' }), -1)
  assert.equal(reviewSign({ type: 'INCOME' }), 1)
  assert.equal(reviewSign({ type: 'REFUND' }), 1)
  assert.equal(reviewSign({ type: 'TRANSFER' }), 0)
  assert.equal(reviewCategoryType({ type: 'REFUND' }), 'INCOME')
  assert.equal(reviewCategoryType({ type: 'CARD' }), 'EXPENSE')
  assert.equal(reviewHasCategory({ type: 'TRANSFER' }), false)
})

test('the payload sends a category only when the owner changed it', () => {
  const items = [
    { table: 'transactions', id: 'a', type: 'EXPENSE', category_id: 'food' },
    { table: 'cc_expenses', id: 'b', type: 'CARD', category_id: 'food' },
    { table: 'transactions', id: 'c', type: 'TRANSFER', category_id: null },
  ]
  const chosen = { 'transactions:a': 'food', 'cc_expenses:b': 'fun', 'transactions:c': 'fun' }
  assert.deepEqual(reviewPayload(items, chosen), [
    { table: 'transactions', id: 'a' },
    { table: 'cc_expenses', id: 'b', category_id: 'fun' },
    { table: 'transactions', id: 'c' },
  ])
  assert.deepEqual(reviewPayload(items), items.map(({ table, id }) => ({ table, id })))
})

test('notices count in Portuguese and vanish at zero', () => {
  assert.equal(reviewNoticeText(0), '')
  assert.match(reviewNoticeText(1), /^1 lançamento gravado sozinho espera/)
  assert.match(reviewNoticeText(3), /^3 lançamentos gravados sozinhos esperam/)
  assert.equal(waitingNoticeText(0), '')
  assert.match(waitingNoticeText(2), /^2 movimentos/)
})

test('um repasse vai com a marca, e so uma receita pode ser', () => {
  const income = { table: 'transactions', id: 'a', type: 'INCOME' }
  assert.deepEqual(reviewPayload([{ ...income, repasse: true }]), [{ table: 'transactions', id: 'a', repasse: true }])
  assert.equal(reviewCanBeRepasse(income), true)
  assert.equal(reviewCanBeRepasse({ table: 'transactions', id: 'b', type: 'EXPENSE' }), false)
  assert.equal(reviewCanBeRepasse({ table: 'cc_expenses', id: 'c', type: 'REFUND' }), false)
})
