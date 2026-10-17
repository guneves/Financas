import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  NO_PORTFOLIO_ACCOUNT_MESSAGE,
  PICK_ACCOUNT_MESSAGE,
  cashLinkFromMetadata,
  cashLinkMetadata,
  emptyCashLink,
  pickPortfolioAccountId,
  portfolioAccounts,
} from './portfolioAccount.js'

const accounts = [
  { id: 'corrente', type: 'CHECKING', currency: 'BRL', is_default: true },
  { id: 'antiga', type: 'BROKERAGE', currency: 'BRL', archived_at: '2026-01-01' },
  { id: 'dolar', type: 'BROKERAGE', currency: 'USD' },
  { id: 'btg', type: 'BROKERAGE', currency: 'BRL' },
  { id: 'xp', type: 'BROKERAGE', currency: 'BRL' },
]

test('only active brokerage accounts in reais are the portfolio, in list order', () => {
  assert.deepEqual(portfolioAccounts(accounts).map((account) => account.id), ['btg', 'xp'])
  assert.equal(pickPortfolioAccountId(accounts), 'btg')
  assert.equal(pickPortfolioAccountId([accounts[0]]), '')
  assert.equal(pickPortfolioAccountId(undefined), '')
})

test('a new operation comes out of an account by default', () => {
  assert.equal(emptyCashLink().enabled, true)
  assert.deepEqual(cashLinkMetadata({ ...emptyCashLink(), accountId: 'btg' }), { cash_account_id: 'btg' })
})

test('the flag sends null, never an absent key the backend would fill in', () => {
  assert.deepEqual(cashLinkMetadata({ enabled: false, accountId: 'btg' }), { cash_account_id: null })
})

test('a new operation without a portfolio account is refused, even with the flag', () => {
  assert.throws(() => cashLinkMetadata({ enabled: true, accountId: '', missing: true }), { message: NO_PORTFOLIO_ACCOUNT_MESSAGE })
  assert.throws(() => cashLinkMetadata({ enabled: false, accountId: '', missing: true }), { message: NO_PORTFOLIO_ACCOUNT_MESSAGE })
})

test('editing an old operation is not blocked by the missing account', () => {
  assert.deepEqual(cashLinkMetadata({ enabled: false, accountId: '', missing: true }, { editing: true }), { cash_account_id: null })
})

test('linked with no account chosen asks for one', () => {
  assert.throws(() => cashLinkMetadata({ enabled: true, accountId: '' }), { message: PICK_ACCOUNT_MESSAGE })
})

test('reading the saved link back', () => {
  assert.deepEqual(cashLinkFromMetadata({ cash_account_id: ' btg ' }), { enabled: true, accountId: 'btg', missing: false })
  assert.equal(cashLinkFromMetadata({}).enabled, false)
})
