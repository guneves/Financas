import test from 'node:test'
import assert from 'node:assert/strict'
import {
  accountLabel,
  balanceCheck,
  connectedItemId,
  firstSyncDaysError,
  itemProblem,
  itemStatus,
  mappedId,
  mappingChoices,
  mappingPayload,
  syncSummary,
  syncHoursLabel,
  syncHoursChoices,
  checkSummary,
} from './openFinance.js'

test('item status in Portuguese with the badge tone', () => {
  assert.deepEqual(itemStatus({ status: 'UPDATED' }), { label: 'Atualizada', tone: 'success' })
  assert.equal(itemStatus({ status: 'LOGIN_ERROR', needs_owner: true }).tone, 'danger')
  assert.equal(itemStatus({ status: 'UPDATED', needs_owner: true }).label, 'Precisa de você no banco')
  assert.equal(itemStatus({ status: 'NEW_THING' }).label, 'NEW_THING')
})

test("Pluggy's own message wins, then what the owner must do", () => {
  assert.equal(itemProblem({ error_message: 'Seu plano permite apenas um CPF.' }), 'Seu plano permite apenas um CPF.')
  assert.match(itemProblem({ needs_owner: true }), /Reconectar/)
  assert.match(itemProblem({ last_sync_error: 'timeout' }), /falhou: timeout/)
  assert.equal(itemProblem({ status: 'UPDATED' }), '')
})

test('account labels show the card final', () => {
  assert.equal(accountLabel({ type: 'CREDIT', name: 'Mastercard Black', number: '5555 **** 9437' }), 'Mastercard Black · final 9437')
  assert.equal(accountLabel({ type: 'BANK', name: 'Conta Corrente', number: '0001/12345-0' }), 'Conta Corrente · 0001/12345-0')
  assert.equal(accountLabel({ type: 'BANK' }), 'Conta')
})

test('a bank account maps to an active BRL account, never the Corretora nor one already used', () => {
  const accounts = [
    { id: 'a', name: 'Itaú', type: 'CHECKING' },
    { id: 'b', name: 'Corretora', type: 'BROKERAGE' },
    { id: 'c', name: 'Velha', type: 'CHECKING', archived_at: '2026-01-01' },
    { id: 'd', name: 'Dólar', type: 'CHECKING', currency: 'USD' },
    { id: 'e', name: 'BB', type: 'CHECKING' },
  ]
  const account = { id: 'x', type: 'BANK' }
  const items = [{ accounts: [{ id: 'y', account_id: 'e' }, { id: 'x', account_id: 'a' }] }]
  assert.deepEqual(mappingChoices(account, { accounts, items }).map((choice) => choice.value), ['a'])
})

test('a card maps only to a card with credit', () => {
  const cards = [
    { id: 'k1', name: 'Visa', credit_enabled: 1 },
    { id: 'k2', name: 'Flash', credit_enabled: 0 },
    { id: 'k3', name: 'Velho', credit_enabled: 1, archived_at: 'x' },
  ]
  assert.deepEqual(mappingChoices({ id: 'x', type: 'CREDIT' }, { cards }).map((choice) => choice.value), ['k1'])
})

test('the mapping payload uses the field of the account type', () => {
  assert.deepEqual(mappingPayload({ type: 'CREDIT' }, 'k1'), { card_id: 'k1' })
  assert.deepEqual(mappingPayload({ type: 'BANK' }, ''), { account_id: null })
  assert.equal(mappedId({ type: 'CREDIT', card_id: 'k1', account_id: 'a' }), 'k1')
})

test('balance check compares to the cent and never for cards', () => {
  assert.deepEqual(balanceCheck({ type: 'BANK', pluggy_balance: 1000, app_balance: 1000 }), { state: 'match', difference: 0 })
  assert.deepEqual(balanceCheck({ type: 'BANK', pluggy_balance: 1000.1, app_balance: 1000 }), { state: 'drift', difference: 0.1 })
  assert.equal(balanceCheck({ type: 'CREDIT', pluggy_balance: -800, app_balance: 0 }).state, 'none')
  assert.equal(balanceCheck({ type: 'BANK', pluggy_balance: 10 }).state, 'none')
})

test('the widget item id', () => {
  assert.equal(connectedItemId({ item: { id: 'abc' } }), 'abc')
  assert.equal(connectedItemId(null), '')
})

test('sync summary', () => {
  assert.equal(syncSummary({ counts: { new: 2, merged: 1 }, removed: 1 }), '2 movimentos novos no Aprovar, 1 juntou-se a um aviso, 1 saiu (o banco desfez).')
  assert.equal(syncSummary({ counts: { known: 4 } }), 'Nada novo.')
})

test('first sync days', () => {
  assert.equal(firstSyncDaysError('30'), '')
  assert.equal(firstSyncDaysError('0'), 'De 1 a 365 dias.')
  assert.equal(firstSyncDaysError('abc'), 'Informe um número de dias.')
})

test('sync hours labels and choices', () => {
  assert.equal(syncHoursLabel(0), 'Desligada')
  assert.equal(syncHoursLabel(6), 'A cada 6 h')
  assert.deepEqual(syncHoursChoices(6).map((choice) => choice.value), [0, 1, 3, 6, 12, 24])
  assert.deepEqual(syncHoursChoices(2).map((choice) => choice.value), [0, 1, 2, 3, 6, 12, 24])
  assert.deepEqual(syncHoursChoices(30).map((choice) => choice.value), [0, 1, 3, 6, 12, 24])
  assert.deepEqual(syncHoursChoices(null).map((choice) => choice.value), [0, 1, 3, 6, 12, 24])
})

test('check summary', () => {
  assert.deepEqual(checkSummary(null), { state: 'none', text: '' })
  assert.deepEqual(checkSummary({ bank_only_count: 0, app_only_count: 0, awaiting_count: 0 }), { state: 'match', text: 'Movimentos conferem' })
  assert.deepEqual(checkSummary({ bank_only_count: 0, app_only_count: 0, awaiting_count: 2 }), { state: 'match', text: 'Movimentos conferem · 2 esperam no Aprovar' })
  assert.deepEqual(checkSummary({ bank_only_count: 1, app_only_count: 3, awaiting_count: 1 }), { state: 'drift', text: '1 só no banco · 3 só no app · 1 espera no Aprovar' })
  assert.deepEqual(checkSummary({ bank_only_count: 2, app_only_count: 0 }), { state: 'drift', text: '2 só no banco' })
})
