import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  bankingAccounts,
  bankingTransactions,
  consolidatedBalance,
  isInvestmentInflow,
  isInvestmentOutflow,
  openingBalanceTotal,
} from './transactions.js'

const accounts = [
  { id: 'banco', type: 'CHECKING', balance: 1000, initial_balance: 800 },
  { id: 'poupanca', type: 'SAVINGS', balance: 500, initial_balance: 500 },
  { id: 'corretora', type: 'BROKERAGE', balance: 7000, initial_balance: 5000 },
]

test('a Corretora account is not saldo em conta', () => {
  assert.equal(consolidatedBalance(accounts), 1500)
  assert.equal(openingBalanceTotal(accounts), 1300)
  assert.deepEqual(bankingAccounts(accounts).map((account) => account.id), ['banco', 'poupanca'])
})

test('what happens inside the Corretora stays out of the banking view', () => {
  const rows = [
    { id: 'compra', type: 'EXPENSE', account_id: 'corretora', amount: 200, source_type: 'INVESTMENT_TRANSACTION' },
    { id: 'provento', type: 'INCOME', account_id: 'corretora', amount: 30, source_type: 'INVESTMENT_PROCEED' },
    { id: 'mercado', type: 'EXPENSE', account_id: 'banco', amount: 50, category: 'Alimentação' },
  ]
  assert.deepEqual(bankingTransactions(rows, accounts).map((row) => row.id), ['mercado'])
})

test('a transfer into the Corretora is an aporte, out of it a resgate', () => {
  const rows = [
    { id: 'ida', type: 'TRANSFER', account_id: 'banco', transfer_account_id: 'corretora', amount: 300 },
    { id: 'volta', type: 'TRANSFER', account_id: 'corretora', transfer_account_id: 'poupanca', amount: 100 },
  ]
  const [ida, volta] = bankingTransactions(rows, accounts)
  assert.equal(ida.type, 'EXPENSE')
  assert.equal(ida.account_id, 'banco')
  assert.ok(isInvestmentOutflow(ida))
  assert.equal(volta.type, 'INCOME')
  assert.equal(volta.account_id, 'poupanca')
  assert.ok(isInvestmentInflow(volta))
})

test('transfers between banks stay transfers; between brokerages they leave', () => {
  const two = [...accounts, { id: 'xp', type: 'BROKERAGE', balance: 0 }]
  const rows = [
    { id: 'bancos', type: 'TRANSFER', account_id: 'banco', transfer_account_id: 'poupanca', amount: 10 },
    { id: 'corretoras', type: 'TRANSFER', account_id: 'corretora', transfer_account_id: 'xp', amount: 10 },
  ]
  const result = bankingTransactions(rows, two)
  assert.deepEqual(result.map((row) => [row.id, row.type]), [['bancos', 'TRANSFER']])
})

test('without a Corretora nothing changes', () => {
  const rows = [{ id: 'a', type: 'EXPENSE', account_id: 'banco', amount: 1 }]
  assert.equal(bankingTransactions(rows, accounts.slice(0, 2)), rows)
})

test('the Corretora balance is summed apart, for the investments area', async () => {
  const { portfolioCashBalance } = await import('./transactions.js')
  assert.equal(portfolioCashBalance(accounts), 7000)
  assert.equal(portfolioCashBalance(accounts.slice(0, 2)), 0)
})
