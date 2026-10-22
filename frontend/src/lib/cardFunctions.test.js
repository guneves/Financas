import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  cardFormPayload,
  cardFunctionLabel,
  cardFunctionOf,
  cardMethods,
  creditCards,
  debitPurchasePayload,
  hasCredit,
  hasDebit,
  resolveCardMethod,
} from './cardFunctions.js'

const itau = { id: 'i', name: 'Itaú', credit_enabled: 1, debit_account_id: null }
const btg = { id: 'b', name: 'BTG', credit_enabled: 1, debit_account_id: 'conta-btg' }
const flash = { id: 'f', name: 'Flash', credit_enabled: 0, debit_account_id: 'conta-flash' }

test('the functions of each card', () => {
  assert.equal(hasCredit(itau), true)
  assert.equal(hasDebit(itau), false)
  assert.equal(hasCredit(flash), false)
  assert.equal(hasDebit(flash), true)
  // Um cartao de antes da 041 (sem as colunas) e credito.
  assert.equal(hasCredit({ id: 'x', name: 'Velho' }), true)
  assert.deepEqual([itau, btg, flash].map(cardFunctionOf), ['CREDIT', 'BOTH', 'DEBIT'])
  assert.deepEqual([itau, btg, flash].map(cardFunctionLabel), ['Crédito', 'Crédito e débito', 'Débito'])
})

test('a debit-only card is out of the credit lists', () => {
  assert.deepEqual(creditCards([itau, btg, flash]).map((card) => card.id), ['i', 'b'])
  assert.deepEqual(creditCards(undefined), [])
})

test('the purchase method follows the card', () => {
  assert.deepEqual(cardMethods(btg), ['CREDIT', 'DEBIT'])
  assert.deepEqual(cardMethods(flash), ['DEBIT'])
  assert.equal(resolveCardMethod(btg, 'DEBIT'), 'DEBIT')
  assert.equal(resolveCardMethod(itau, 'DEBIT'), 'CREDIT')
  assert.equal(resolveCardMethod(flash, 'CREDIT'), 'DEBIT')
  assert.equal(resolveCardMethod(undefined, 'DEBIT'), 'CREDIT')
})

test('the Ajustes form becomes the API body', () => {
  assert.deepEqual(
    cardFormPayload({ name: ' Nubank ', functions: 'CREDIT', due_day: '10', closing_day: '3', autopay_account_id: '' }).payload,
    { name: 'Nubank', credit_enabled: true, debit_account_id: null, due_day: 10, closing_day: 3, autopay_account_id: null },
  )
  assert.deepEqual(
    cardFormPayload({ name: 'Flash', functions: 'DEBIT', debit_account_id: 'conta-flash', due_day: '', closing_day: '', autopay_account_id: 'x' }).payload,
    { name: 'Flash', credit_enabled: false, debit_account_id: 'conta-flash', autopay_account_id: null },
  )
  assert.deepEqual(
    cardFormPayload({ name: 'BTG', functions: 'BOTH', debit_account_id: 'conta-btg', due_day: 15, closing_day: 8 }).payload,
    { name: 'BTG', credit_enabled: true, debit_account_id: 'conta-btg', due_day: 15, closing_day: 8 },
  )
})

test('what the form still needs', () => {
  assert.match(cardFormPayload({ name: '' }).error, /nome/)
  assert.match(cardFormPayload({ name: 'Flash', functions: 'DEBIT' }).error, /débito/)
  assert.match(cardFormPayload({ name: 'Itaú', functions: 'CREDIT', due_day: '32', closing_day: '3' }).error, /vencimento/)
  assert.match(cardFormPayload({ name: 'BTG', functions: 'BOTH', debit_account_id: 'c', due_day: '', closing_day: '' }).error, /vencimento/)
})

test('a debit purchase is an expense in the card account', () => {
  assert.deepEqual(
    debitPurchasePayload(flash, { amount: 46.81, date: '2026-10-21', categoryId: 'cat', category: 'Alimentação', description: 'Padaria' }),
    { amount: 46.81, date: '2026-10-21', category_id: 'cat', category: 'Alimentação', description: 'Padaria', type: 'EXPENSE', account_id: 'conta-flash' },
  )
})
