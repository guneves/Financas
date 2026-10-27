import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ITEM_CATEGORY,
  ambiguousText,
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
  recurringText,
  recurringToggle,
  sourceLabel,
  splitOccurredAt,
  splittableSources,
  targetFields,
  targetText,
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
  // O teclado do celular digita virgula; o do PC, ponto. Os dois valem.
  assert.deepEqual(changesFromDraft(item, { ...draft, amount: '45,90' }), { version: 3 })
  assert.deepEqual(changesFromDraft(item, { ...draft, amount: '1.234,56' }), { version: 3, amount: 1234.56 })
  assert.deepEqual(changesFromDraft(item, { ...draft, amount: 'R$ 50.5' }), { version: 3, amount: 50.5 })
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
  // Uma notificacao e uma transacao do Open Finance da mesma compra tambem se separam;
  // a que saiu do banco (REMOVED) nao conta.
  assert.equal(splittableSources({ sources: [
    { source: 'notification', role: 'SOURCE' }, { source: 'open_finance', role: 'SOURCE' },
  ] }).length, 2)
  assert.deepEqual(splittableSources({ sources: [
    { source: 'notification', role: 'SOURCE' }, { source: 'open_finance', role: 'REMOVED' },
  ] }), [])
})

test('an Open Finance source says the bank, the account and the installment', () => {
  assert.equal(
    sourceLabel({
      source: 'open_finance', connector_name: 'Itaú', account_name: 'Mastercard Black', description: 'LOJA X',
      installment_number: 1, total_installments: 3, role: 'SOURCE',
    }),
    'Open Finance Itaú · Mastercard Black · LOJA X · parcela 1/3',
  )
  assert.equal(
    sourceLabel({ source: 'open_finance', connector_name: 'BB', description: 'PIX', role: 'REMOVED' }),
    'Open Finance BB · PIX · saiu do banco',
  )
  assert.equal(sourceLabel({ source: 'open_finance' }), 'Open Finance')
})

test('ready items, remember and the texts', () => {
  assert.deepEqual(readyIds([{ id: 'a', ready: true }, { id: 'b', ready: false }]), ['a'])
  assert.equal(offersRemember({ needs: ['card'], confirm: [] }), true)
  assert.equal(offersRemember({ needs: [], confirm: [] }), false)
  assert.match(reasonText({ reason: 'own_transfer' }), /não conta como entrada nem saída/)
  assert.match(reasonText({ reason: 'external_transfer' }), /Com outra pessoa/)
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

test('recurringText: the occurrence approving settles, the opt-out and the settled one', () => {
  const recurring = { description: 'Netflix', date: '2026-10-05', amount: 55.9, exact_amount: true, settled: false }
  assert.equal(recurringText({ recurring: null }), '')
  assert.match(recurringText({ recurring }), /^Recorrente: ao aprovar, "Netflix" de 05\/10 fica como feita/)
  assert.match(
    recurringText({ recurring: { ...recurring, exact_amount: false } }),
    /\(previsto R\$\s55,90\)/
  )
  assert.equal(recurringText({ recurring, recurring_off: true }), 'Não marca "Netflix" de 05/10 em Recorrentes.')
  assert.equal(
    recurringText({ recurring: { ...recurring, settled: true } }),
    'Marcou "Netflix" de 05/10 como feita em Recorrentes.'
  )
})

test('recurringToggle: the PATCH body keeps the version', () => {
  assert.deepEqual(recurringToggle({ version: 3 }, false), { version: 3, recurring: false })
  assert.deepEqual(recurringToggle({ version: 4 }, true), { version: 4, recurring: true })
})

test('the category goes by id: same name under two parents is two categories', () => {
  const withId = { ...item, category: 'Outros', category_id: 'lazer-outros' }
  const draft = draftFromItem(withId)
  assert.equal(draft.category_id, 'lazer-outros')
  // Sem mexer na categoria, nada dela vai no pedido.
  assert.deepEqual(changesFromDraft(withId, { ...draft, description: 'Cinema' }), { version: 3, description: 'Cinema' })
  assert.deepEqual(changesFromDraft(withId, { ...draft, category_id: 'raiz-outros' }), { version: 3, category_id: 'raiz-outros' })
  // "Sugerida pelas regras" limpa as duas: o servidor escolhe ao aprovar.
  assert.deepEqual(changesFromDraft(withId, { ...draft, category_id: '' }), { version: 3, category: null, category_id: null })
  // Um item so com o nome fica como esta ate o dono escolher outra.
  const nameOnly = draftFromItem(item)
  assert.equal(nameOnly.category_id, ITEM_CATEGORY)
  assert.deepEqual(changesFromDraft(item, nameOnly), { version: 3 })
  assert.deepEqual(changesFromDraft(item, { ...nameOnly, category_id: 'mercado' }), { version: 3, category_id: 'mercado' })
})

test('targetText: where the item goes, only once it is known', () => {
  assert.equal(targetText({ entry_type: 'EXPENSE', account_id: 'a1', account_name: 'Itaú Conta corrente' }), 'Itaú Conta corrente')
  assert.equal(targetText({ entry_type: 'CARD', card_id: 'c1', card_name: 'Itaú Visa', installments: 3 }), 'Itaú Visa · 3x')
  assert.equal(
    targetText({ entry_type: 'TRANSFER', account_id: 'a1', account_name: 'Itaú', transfer_account_id: 'a2', transfer_account_name: 'BTG' }),
    'Itaú → BTG'
  )
  // Falta escolher (ou credito/debito ainda aberto): nada, o seletor ja esta la.
  assert.equal(targetText({ entry_type: 'EXPENSE', account_id: null }), '')
  assert.equal(targetText({ entry_type: 'TRANSFER', account_id: 'a1', transfer_account_id: null }), '')
  assert.equal(targetText({ entry_type: null, account_id: 'a1' }), '')
})

test('targetFields: the pickers "Trocar" opens for each type', () => {
  assert.deepEqual(targetFields({ entry_type: 'CARD' }), ['card'])
  assert.deepEqual(targetFields({ entry_type: 'INCOME' }), ['account'])
  assert.deepEqual(targetFields({ entry_type: 'TRANSFER' }), ['account', 'transfer_account'])
  assert.deepEqual(targetFields({ entry_type: null }), [])
})

test('an ambiguous item never offers to remember, and says why', () => {
  assert.equal(offersRemember({ needs: ['account'], confirm: [], ambiguous: true }), false)
  assert.match(ambiguousText({ ambiguous: true, entry_type: 'EXPENSE' }), /mais de uma conta neste banco/)
  assert.match(ambiguousText({ ambiguous: true, entry_type: 'CARD' }), /mais de um cartão/)
  assert.equal(ambiguousText({ ambiguous: false }), '')
})
