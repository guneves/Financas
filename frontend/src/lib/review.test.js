import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  cardAmountSign,
  isCardRow,
  mergeStatement,
  oldestDate,
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

test('the waiting notice counts in Portuguese and vanishes at zero', () => {
  assert.equal(waitingNoticeText(0), '')
  assert.match(waitingNoticeText(1), /^1 movimento/)
  assert.match(waitingNoticeText(2), /^2 movimentos/)
})
