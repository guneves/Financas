import { test } from 'node:test'
import assert from 'node:assert/strict'
import { OP_KEY_METADATA, launchFormFromPrefill, opKeyMetadata } from './investmentPrefill.js'

test('an equity buy that waits opens the buy form with its cash in the Corretora', () => {
  const form = launchFormFromPrefill({
    kind: 'operation', asset_class: 'STOCKS', treasury: false, ticker_or_name: 'PETR4', quantity: 10,
    average_price: 30, cash_account_id: 'corretora',
    metadata: { purchase_date: '2026-10-20', other_costs: 2.5, [OP_KEY_METADATA]: 'pluggy-inv:1' },
  })
  assert.equal(form.mode, 'BUY')
  assert.equal(form.assetType, 'STOCKS')
  assert.deepEqual([form.ticker, form.quantity, form.price, form.otherCosts, form.date], ['PETR4', '10', '30', '2.5', '2026-10-20'])
  assert.deepEqual(form.cash, { enabled: true, accountId: 'corretora', missing: false, fresh: false })
  assert.equal(form.opKey, 'pluggy-inv:1')
})

test('a sale opens the sell form at the sale price', () => {
  const form = launchFormFromPrefill({
    kind: 'operation', asset_class: 'STOCKS', ticker_or_name: 'BOVA11', quantity: -5, average_price: 130,
    cash_account_id: 'corretora', metadata: { sale_date: '2026-10-22', sale_price: 131, other_costs: 0 },
  })
  assert.deepEqual([form.mode, form.quantity, form.price, form.date, form.otherCosts], ['SELL', '5', '131', '2026-10-22', ''])
})

test('a fixed income buy keeps what Pluggy knew and never takes the Corretora', () => {
  const form = launchFormFromPrefill({
    kind: 'operation', asset_class: 'FIXED_INCOME', treasury: false, ticker_or_name: 'CDB BANCO X', quantity: 1,
    average_price: 1500, cash_account_id: null,
    metadata: { fixed_income_type: 'LCI', purchase_date: '2026-10-20', other_costs: 0, [OP_KEY_METADATA]: 'k' },
  })
  assert.deepEqual([form.assetType, form.quantity, form.price], ['FIXED_INCOME', '1', '1500'])
  assert.equal(form.fixedIncome.fixed_income_type, 'LCI')
  assert.equal(form.fixedIncome.rate, '')
  assert.equal(form.cash.enabled, false)
})

test('a Tesouro buy opens as Tesouro with its titles', () => {
  const form = launchFormFromPrefill({
    kind: 'operation', asset_class: 'FIXED_INCOME', treasury: true, ticker_or_name: 'Tesouro IPCA+ 2045',
    quantity: 1, average_price: 850, cash_account_id: null,
    metadata: { fixed_income_type: 'TESOURO', treasury_units: 0.85, purchase_date: '2026-10-20' },
  })
  assert.equal(form.assetType, 'TESOURO')
  assert.equal(form.treasuryUnits, '0.85')
})

test('only operations open the form', () => {
  assert.equal(launchFormFromPrefill(null), null)
  assert.equal(launchFormFromPrefill({ kind: 'proceed' }), null)
  assert.deepEqual(opKeyMetadata(''), {})
  assert.deepEqual(opKeyMetadata('k'), { [OP_KEY_METADATA]: 'k' })
})
