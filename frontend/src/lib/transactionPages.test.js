import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mergeTransactionPages, nextPageCursor } from './transactionPages.js'

const page = (ids, extra = {}) => ({
  items: ids.map((id) => ({ id })),
  next_cursor: null,
  count: 5,
  totals: { income: 1, expense: 2, investment: 0 },
  day_totals: {},
  ...extra,
})

test('pages join in order and the totals come from the first page', () => {
  const merged = mergeTransactionPages([
    page(['a', 'b'], { next_cursor: 'c1', day_totals: { '2026-03-02': -60 } }),
    page(['c'], { totals: { income: 9, expense: 9, investment: 9 }, day_totals: { '2026-03-02': -60, '2026-03-01': -5 } }),
  ])
  assert.deepEqual(merged.items.map((item) => item.id), ['a', 'b', 'c'])
  assert.deepEqual(merged.totals, { income: 1, expense: 2, investment: 0 })
  assert.deepEqual(merged.dayTotals, { '2026-03-02': -60, '2026-03-01': -5 })
  assert.equal(merged.count, 5)
  assert.equal(merged.hasMore, false)
})

test('more to load while the last page has a cursor', () => {
  assert.equal(mergeTransactionPages([page(['a'], { next_cursor: 'x' })]).hasMore, true)
  assert.equal(nextPageCursor({ next_cursor: 'x' }), 'x')
  assert.equal(nextPageCursor({ next_cursor: null }), undefined)
})

test('no pages is an empty statement', () => {
  const merged = mergeTransactionPages(undefined)
  assert.deepEqual(merged.items, [])
  assert.equal(merged.count, 0)
  assert.equal(merged.hasMore, false)
})
