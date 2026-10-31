import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mergeTransactionPages, nextPageCursor, changeCachedRows, withoutRow, withRow } from './transactionPages.js'

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

test('a row leaves or changes in both cached shapes at once', () => {
  const rows = [{ id: 'a', amount: 1 }, { id: 'b', amount: 2 }]
  assert.deepEqual(changeCachedRows({ transactions: rows, cards: [] }, withoutRow('a')), { transactions: [rows[1]], cards: [] })
  const paged = { pages: [{ items: rows, count: 2 }], pageParams: [''] }
  assert.deepEqual(changeCachedRows(paged, withRow({ id: 'b', amount: 9 })).pages[0].items[1], { id: 'b', amount: 9 })
  assert.deepEqual(changeCachedRows([{ id: 'card' }], withoutRow('card')), [{ id: 'card' }])
  assert.equal(changeCachedRows(undefined, withoutRow('a')), undefined)
})
