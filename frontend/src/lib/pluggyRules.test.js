import test from 'node:test'
import assert from 'node:assert/strict'
import {
  bankMark,
  candidateKindLabel,
  differenceText,
  itemStatusLabel,
  lastSyncAt,
  linkPayload,
  linkTargets,
  matchedBankNotice,
  reviewCount,
  reviewNoticeText,
  reviewReasonText,
  syncChangedData,
  syncSummary,
} from './pluggyRules.js'

test('only a sync that changed something asks the screens to read again', () => {
  assert.equal(syncChangedData({ status: 'ok', created: 0, attached: 0, waiting: 3, skipped: 2 }), false)
  assert.equal(syncChangedData({ status: 'ok', attached: 1 }), true)
  assert.equal(syncChangedData({ status: 'ok', review: 1 }), true)
  assert.equal(syncChangedData(null), false)
})

test('the sync summary says what happened', () => {
  assert.equal(syncSummary({ status: 'ok', created: 1, attached: 2, review: 0 }), 'Banco: 1 novo, 2 conferidos.')
  assert.equal(syncSummary({ status: 'ok' }), 'Nada novo no banco.')
  assert.equal(syncSummary({ status: 'not_configured' }), 'A Pluggy não está configurada no servidor.')
  assert.match(syncSummary({ status: 'partial', created: 1, failed: ['Itaú'] }), /Itaú/)
  assert.match(syncSummary({ status: 'error', message: 'fora do ar' }), /fora do ar/)
})

test('the review reason names what the bank row looks like', () => {
  const transfer = reviewReasonText({
    reason: 'out_of_reach',
    candidates: [{ kind: 'transfer' }, { kind: 'entry' }],
  })
  assert.match(transfer, /transferência/)
  assert.doesNotMatch(transfer, /lançamento,/)
  assert.match(reviewReasonText({ reason: 'several_candidates' }), /mais de um/)
  assert.match(reviewReasonText({ reason: 'installments_differ' }), /parcelas/)
  assert.equal(candidateKindLabel('invoice_payment'), 'Pagamento de fatura')
  assert.equal(candidateKindLabel('?'), 'Lançamento')
})

test('a difference is described in the bank\'s terms', () => {
  assert.equal(differenceText(null), '')
  assert.equal(differenceText({ date: '2026-10-11' }, String, (value) => value.split('-').reverse().join('/')), 'No banco: data 11/10/2026.')
  assert.equal(differenceText({ amount: 10.5 }, (value) => `R$ ${value}`), 'No banco: valor R$ 10.5.')
})

test('a card goes to a card, an account to an active account', () => {
  const accounts = [{ id: 'a1', name: 'Itaú' }, { id: 'a2', name: 'Velha', archived_at: '2026-01-01' }]
  const cards = [{ id: 'c1', name: 'Visa' }]
  assert.deepEqual(linkTargets({ type: 'BANK' }, { accounts, cards }), [{ id: 'a1', name: 'Itaú' }])
  assert.deepEqual(linkTargets({ type: 'CREDIT' }, { accounts, cards }), [{ id: 'c1', name: 'Visa' }])
})

test('the link payload carries the right target', () => {
  assert.deepEqual(
    linkPayload({ type: 'CREDIT', name: 'Visa', number: '1234' }, { itemRowId: 'i', targetId: 'c1', since: '2026-10-17' }),
    { item: 'i', type: 'CREDIT', name: 'Visa · 1234', since: '2026-10-17', card_id: 'c1' },
  )
  assert.deepEqual(
    linkPayload({ type: 'BANK', name: 'Conta' }, { itemRowId: 'i', targetId: 'a1', since: '2026-10-01' }),
    { item: 'i', type: 'BANK', name: 'Conta', since: '2026-10-01', account_id: 'a1' },
  )
})

test('the newest sync, the review count and the bank mark', () => {
  assert.equal(lastSyncAt([{ last_sync_at: '2026-10-17T10:00:00Z' }, { last_sync_at: null }, { last_sync_at: '2026-10-17T12:00:00Z' }]), '2026-10-17T12:00:00Z')
  assert.equal(lastSyncAt([]), '')
  assert.equal(reviewCount({ counts: { REVIEW: 2, IMPORTED: 5 } }), 2)
  assert.equal(reviewCount(undefined), 0)
  assert.equal(bankMark({ external_id: 'pluggy:1', source_type: 'PLUGGY' }), 'Veio do banco (Pluggy)')
  assert.equal(bankMark({ external_id: 'pluggy:1', source_type: null }), 'Conferido pelo banco (Pluggy)')
  assert.equal(bankMark({ source_type: 'PLUGGY' }), '')
})

test('a confirmation that met the bank row says so', () => {
  assert.match(matchedBankNotice({ matched_bank: true }, 'Despesa de R$ 10,00'), /já estava no extrato/)
  assert.match(matchedBankNotice([{ matched_bank: true }], 'Compra'), /já estava/)
  assert.equal(matchedBankNotice({ id: 'x' }, 'Despesa'), '')
})

test('the Extrato notice agrees in number, and the item status is in Portuguese', () => {
  assert.equal(reviewNoticeText(0), '')
  assert.equal(reviewNoticeText(1), '1 transação do banco espera você decidir se já está lançada.')
  assert.equal(reviewNoticeText(2), '2 transações do banco esperam você decidir se já estão lançadas.')
  assert.equal(itemStatusLabel('UPDATED'), 'Atualizada')
  assert.equal(itemStatusLabel('LOGIN_ERROR'), 'Erro de login no banco')
  assert.equal(itemStatusLabel('NOVO_STATUS'), 'NOVO_STATUS')
  assert.equal(itemStatusLabel(null), 'Sem status')
})
