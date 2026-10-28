import test from 'node:test'
import assert from 'node:assert/strict'

import {
  brlHint,
  crossCurrencyOf,
  globalAccounts,
  globalStatement,
  globalTotals,
  impliedRate,
  isGlobalAccount,
} from './globalAccount.js'
import { formatForeignCurrency, formatSignedForeignCurrency } from './format.js'

const WISE = 'wise'
const BTG = 'btg'
const byId = { [WISE]: { id: WISE, name: 'Wise' }, [BTG]: { id: BTG, name: 'BTG conta corrente' } }

test('so a conta em outra moeda e global', () => {
  assert.equal(isGlobalAccount({ currency: 'USD' }), true)
  assert.equal(isGlobalAccount({ currency: 'usd' }), true)
  assert.equal(isGlobalAccount({ currency: 'BRL' }), false)
  assert.equal(isGlobalAccount({}), false)
  assert.equal(isGlobalAccount(null), false)
  assert.deepEqual(
    globalAccounts([
      { id: 'a', currency: 'BRL' },
      { id: 'b', currency: 'USD' },
      { id: 'c', currency: 'USD', archived_at: '2026-10-01' },
    ]).map((account) => account.id),
    ['b'],
  )
})

test('o Pix de reais entra em dolar; sem o dolar, a conferir', () => {
  const rows = [
    { id: '1', type: 'TRANSFER', account_id: BTG, transfer_account_id: WISE, amount: 253.53, transfer_amount: 46.1 },
    { id: '2', type: 'TRANSFER', account_id: BTG, transfer_account_id: WISE, amount: 101.43, transfer_amount: null },
    { id: '3', type: 'EXPENSE', account_id: WISE, amount: 9.99 },
    { id: '4', type: 'INCOME', account_id: WISE, amount: 0.5 },
    { id: '5', type: 'TRANSFER', account_id: WISE, transfer_account_id: BTG, amount: 10 },
    { id: '6', type: 'EXPENSE', account_id: BTG, amount: 70 },
  ]
  const statement = globalStatement(rows, WISE, byId)
  assert.deepEqual(
    statement.map((row) => [row.id, row.direction, row.native, row.pending, row.counterpart]),
    [
      ['1', 1, 46.1, false, 'BTG conta corrente'],
      ['2', 1, null, true, 'BTG conta corrente'],
      ['3', -1, 9.99, false, null],
      ['4', 1, 0.5, false, null],
      ['5', -1, 10, false, 'BTG conta corrente'],
    ],
  )
  assert.deepEqual(globalTotals(statement), { in: 46.6, out: 19.99, pending: 1 })
  assert.equal(impliedRate(statement[0]), 5.4996)
  assert.equal(impliedRate(statement[1]), null)
})

test('a linha em reais: o saldo convertido, ou nada sem cambio', () => {
  assert.equal(brlHint({ currency: 'USD', balance: 101.72, balance_brl: 559.46 }), 559.46)
  assert.equal(brlHint({ currency: 'USD', balance: 101.72, balance_brl: null }), null)
  assert.equal(brlHint({ currency: 'BRL', balance: 10, balance_brl: 10 }), null)
})

test('formatador em dolar', () => {
  // O espaco depois do simbolo e inquebravel (Intl).
  assert.equal(formatForeignCurrency(46.1), 'US$ 46,10')
  assert.equal(formatForeignCurrency(1234.5), 'US$ 1.234,50')
  assert.equal(formatSignedForeignCurrency(9.99, -1), '−US$ 9,99')
  assert.equal(formatSignedForeignCurrency(46.1, 1), '+US$ 46,10')
  assert.equal(formatSignedForeignCurrency(0, 1), 'US$ 0,00')
})

test('so uma transferencia entre moedas pede o valor no destino', () => {
  assert.equal(crossCurrencyOf({ currency: 'BRL' }, { currency: 'USD' }), 'USD')
  assert.equal(crossCurrencyOf({ currency: 'USD' }, { currency: 'BRL' }), 'BRL')
  assert.equal(crossCurrencyOf({}, { currency: 'BRL' }), null)
  assert.equal(crossCurrencyOf({ currency: 'USD' }, { currency: 'usd' }), null)
  assert.equal(crossCurrencyOf(null, { currency: 'USD' }), null)
})
