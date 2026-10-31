import { test } from 'node:test'
import assert from 'node:assert/strict'
import { transactionEditForm, transactionEditPayload, transferEditError } from './transactionEdit.js'

const transfer = {
  id: 't', type: 'TRANSFER', amount: 500, date: '2026-10-10', description: 'Reserva',
  account_id: 'nubank', transfer_account_id: 'poupanca', category: 'Transferencia',
}

test('a transfer edit can change the destination account', () => {
  const form = transactionEditForm(transfer)
  assert.equal(form.transfer_account_id, 'poupanca')
  const payload = transactionEditPayload(transfer, { ...form, transfer_account_id: 'itau' }, 500)
  assert.equal(payload.transfer_account_id, 'itau')
  assert.equal('account_id' in payload, false)
  // Uma transferencia nao leva tipo nem categoria (o servidor recusa converter).
  assert.equal('type' in payload, false)
  assert.equal('category_id' in payload, false)
})

test('the accounts go only when they changed', () => {
  const form = transactionEditForm(transfer)
  const payload = transactionEditPayload(transfer, form, 500)
  assert.deepEqual(payload, { amount: 500, date: '2026-10-10', description: 'Reserva' })
  const moved = transactionEditPayload(transfer, { ...form, account_id: 'itau' }, 500)
  assert.equal(moved.account_id, 'itau')
  assert.equal('transfer_account_id' in moved, false)
})

test('a despesa sends its type and the category id only when changed', () => {
  const expense = {
    id: 'e', type: 'EXPENSE', amount: 30, date: '2026-10-11', description: 'Almoço',
    account_id: 'nubank', category_id: 'alimentacao-outros', category: 'Outros',
  }
  const form = transactionEditForm(expense)
  assert.equal(form.transfer_account_id, '')
  assert.deepEqual(transactionEditPayload(expense, form, 30),
    { amount: 30, date: '2026-10-11', description: 'Almoço', type: 'EXPENSE' })
  const recategorized = transactionEditPayload(expense, { ...form, category_id: 'lazer' }, 30)
  assert.equal(recategorized.category_id, 'lazer')
  // O destino nunca vai numa despesa, mesmo que o formulario o tenha.
  assert.equal('transfer_account_id' in transactionEditPayload(expense, { ...form, transfer_account_id: 'x' }, 30), false)
})

test('the share goes only when it changed', () => {
  const expense = { id: 'e', type: 'EXPENSE', amount: 100, date: '2026-10-11', account_id: 'a', category_id: 'c' }
  const form = transactionEditForm(expense)
  assert.equal('share_mode' in transactionEditPayload(expense, form, 100, { sharing: true }), false)
  const split = { ...form, share: { share_mode: 'SPLIT', share_others_amount: '40', share_person: 'Ana' } }
  const payload = transactionEditPayload(expense, split, 100, { sharing: true })
  assert.equal(payload.share_mode, 'SPLIT')
  assert.equal('share_mode' in transactionEditPayload(expense, split, 100, { sharing: false }), false)
})

const form = (extra) => ({ amount: '10', date: '2026-10-01', description: 'x', category_id: '', share: {}, ...extra })

test('an expense turned into a transfer leaves its own account', () => {
  const row = { id: '1', type: 'EXPENSE', account_id: 'a' }
  const payload = transactionEditPayload(row, form({ type: 'TRANSFER', account_id: 'a', transfer_account_id: 'b' }), 10)
  assert.equal(payload.type, 'TRANSFER')
  assert.deepEqual([payload.account_id, payload.transfer_account_id], ['a', 'b'])
  assert.equal('category_id' in payload, false)
})

test('an income turned into a transfer enters its own account', () => {
  const row = { id: '1', type: 'INCOME', account_id: 'a' }
  const payload = transactionEditPayload(row, form({ type: 'TRANSFER', account_id: 'a', transfer_account_id: 'b' }), 10)
  assert.deepEqual([payload.account_id, payload.transfer_account_id], ['b', 'a'])
})

test('a conversion needs another account', () => {
  const row = { id: '1', type: 'EXPENSE', account_id: 'a' }
  assert.match(transferEditError(row, form({ type: 'TRANSFER', transfer_account_id: '' })), /outra conta/)
  assert.match(transferEditError(row, form({ type: 'TRANSFER', transfer_account_id: 'a' })), /diferente/)
  assert.equal(transferEditError(row, form({ type: 'TRANSFER', transfer_account_id: 'b' })), '')
  assert.equal(transferEditError(row, form({ type: 'EXPENSE', transfer_account_id: '' })), '')
})
