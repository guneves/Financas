import test from 'node:test'
import assert from 'node:assert/strict'
import {
  amountSign,
  approveReadySummary,
  candidateKindLabel,
  changesFromDraft,
  composeOccurredAt,
  decisionText,
  draftFromItem,
  entryTypeLabel,
  hintText,
  matchedInboxNotice,
  offersRemember,
  onlySamsung,
  pendingNoticeText,
  quickChoice,
  readyIds,
  reasonText,
  sourceLabel,
  splitOccurredAt,
  splittableSources,
  whenText,
} from './inboxRules.js'

const item = {
  id: 'i1',
  version: 3,
  entry_type: 'CARD',
  direction: 'OUT',
  amount: 45.9,
  occurred_at: '2026-10-17T22:30:00-03:00',
  description: 'PADARIA',
  category: 'Outros',
  account_id: null,
  card_id: 'c1',
  transfer_account_id: null,
  installments: 1,
}

test('the time is shown as the source said it, without converting the time zone', () => {
  assert.equal(whenText('2026-10-17T22:30:00-03:00'), '17/10/2026 às 22:30')
  assert.equal(whenText('2026-10-18T01:30:00+00:00'), '18/10/2026 às 01:30')
  assert.equal(whenText('2026-10-10'), '10/10/2026')
  assert.equal(whenText(''), '')
  assert.deepEqual(splitOccurredAt('2026-10-10'), { date: '2026-10-10', time: '' })
  assert.equal(composeOccurredAt('2026-10-10', '08:05'), '2026-10-10T08:05')
  assert.equal(composeOccurredAt('2026-10-10', ''), '2026-10-10')
})

test('the edit sends only what changed, with the version', () => {
  const draft = draftFromItem(item)
  assert.deepEqual(changesFromDraft(item, draft), { version: 3 })
  assert.deepEqual(
    changesFromDraft(item, { ...draft, amount: '50', description: ' Padaria ', time: '21:00' }),
    { version: 3, amount: 50, description: 'Padaria', occurred_at: '2026-10-17T21:00' },
  )
  assert.deepEqual(changesFromDraft(item, { ...draft, card_id: '' }), { version: 3, card_id: null })
  // Sem tipo escolhido (compra vaga), nao manda tipo.
  const vague = { ...item, entry_type: null }
  assert.deepEqual(changesFromDraft(vague, draftFromItem(vague)), { version: 3 })
})

test('a quick choice picks the type that goes with credit or debit', () => {
  assert.deepEqual(quickChoice(item, { method: 'CARD' }), { version: 3, entry_type: 'CARD' })
  assert.deepEqual(quickChoice(item, { method: 'DEBIT' }), { version: 3, entry_type: 'EXPENSE' })
  assert.deepEqual(quickChoice({ ...item, direction: 'IN' }, { method: 'DEBIT' }), { version: 3, entry_type: 'INCOME' })
  assert.deepEqual(quickChoice(item, { card_id: 'c2' }), { version: 3, card_id: 'c2' })
})

test('sources say where each report came from', () => {
  assert.equal(
    sourceLabel({ source: 'notification', app_label: 'Itaú', kind: 'CREDIT_PURCHASE', card_last4: '1234' }),
    'Notificação Itaú · compra no crédito · final 1234',
  )
  assert.equal(onlySamsung({ sources: [{ source: 'notification', app: 'com.samsung.android.spay' }] }), true)
  assert.equal(onlySamsung({ sources: [
    { source: 'notification', app: 'com.samsung.android.spay' }, { source: 'notification', app: 'com.itau' },
  ] }), false)
})

test('a transfer has no sign; money out is negative, money in positive', () => {
  assert.equal(amountSign(item), -1)
  assert.equal(amountSign({ ...item, direction: 'IN', entry_type: 'INCOME' }), 1)
  assert.equal(amountSign({ ...item, entry_type: 'TRANSFER' }), 0)
  assert.equal(entryTypeLabel(null), 'Crédito ou débito?')
  assert.equal(entryTypeLabel('TRANSFER'), 'Transferência')
})

test('only items with two or more live sources can be split', () => {
  assert.deepEqual(splittableSources({ sources: [{ source: 'notification', role: 'SOURCE' }] }), [])
  const sources = [
    { source: 'notification', role: 'SOURCE' },
    { source: 'notification', role: 'PAIRED' },
    { source: 'notification', role: 'CANCELLED' },
  ]
  assert.equal(splittableSources({ sources }).length, 2)
})

test('ready items, remember and the texts', () => {
  assert.deepEqual(readyIds([{ id: 'a', ready: true }, { id: 'b', ready: false }]), ['a'])
  assert.equal(offersRemember({ needs: ['card'], confirm: [] }), true)
  assert.equal(offersRemember({ needs: [], confirm: [] }), false)
  assert.match(reasonText({ reason: 'own_transfer' }), /não conta como entrada nem saída/)
  assert.equal(reasonText({ reason: 'new' }), '')
  assert.equal(pendingNoticeText(0), '')
  assert.match(pendingNoticeText(2), /^2 movimentos/)
  assert.equal(decisionText({ state: 'REMOVED', reason: 'declined' }), 'Compra negada pelo banco')
  assert.equal(candidateKindLabel('invoice_payment'), 'Pagamento de fatura')
  assert.equal(candidateKindLabel('?'), 'Lançamento')
  assert.equal(decisionText({ state: 'MATCHED', reason: 'created_elsewhere' }), 'Lançado pelo "+ Novo"')
  assert.equal(approveReadySummary({ approved: ['a', 'b'], skipped: [{ id: 'c' }] }), '2 aprovados, 1 ficou para você decidir.')
  assert.equal(matchedInboxNotice({ matched_inbox: true }, 'Despesa').startsWith('Despesa: já esperava'), true)
  assert.equal(matchedInboxNotice([{ id: 'x' }], 'Compra'), '')
  assert.equal(
    hintText({ label: 'Samsung Wallet · sem crédito/débito · final 1234', entry_type: 'CARD', card_name: 'Itaú Visa' }),
    'Samsung Wallet · sem crédito/débito · final 1234 → Itaú Visa',
  )
})
