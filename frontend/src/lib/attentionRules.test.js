import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  MAX_DISMISSED_KEYS,
  addDismissed,
  invoiceMonthKey,
  isPastDue,
  overdueDetail,
  undismissedItems,
} from './attentionRules.js'

// As regras dos avisos sao do servidor desde a proposta home-attention-invoices.md:
// os casos que moravam aqui estao em backend/tests/test_attention.py e
// test_cc_invoices.py (fatura vencida, fechada, debito automatico, chaves,
// estorno, proxima fatura, a mais proxima). Ficam o texto e as dispensas.

const item = (key, kind) => ({ key, kind })

test('dispensar esconde so os casos dispensados', () => {
  const items = [item('recorrencias:3@x2', 'RECURRING'), item('orcamento:2026-10:1', 'OVER_BUDGET')]
  const dismissed = addDismissed([], [items[0].key])
  assert.deepEqual(undismissedItems(items, dismissed).map((entry) => entry.kind), ['OVER_BUDGET'])
  // Um caso novo (outra chave) volta.
  assert.deepEqual(undismissedItems([item('recorrencias:3@2026-10-01x1', 'RECURRING')], dismissed).length, 1)
})

test('a lista de dispensados nao cresce sem fim e nao repete', () => {
  const many = Array.from({ length: MAX_DISMISSED_KEYS + 5 }, (_, index) => `k${index}`)
  const kept = addDismissed([], many)
  assert.equal(kept.length, MAX_DISMISSED_KEYS)
  assert.equal(kept.at(-1), `k${MAX_DISMISSED_KEYS + 4}`)
  assert.deepEqual(addDismissed(['a', 'b'], ['a']), ['b', 'a'])
})

test('o texto da fatura vencida: uma, ou a mais antiga de varias', () => {
  const nubank = { card_name: 'Nubank', due_date: '2026-10-10' }
  assert.equal(overdueDetail([nubank]), 'Nubank · venceu em 10/10/2026')
  assert.equal(overdueDetail([nubank, { card_name: 'Itaú', due_date: '2026-10-25' }]), '2 faturas · a mais antiga venceu em 10/10/2026')
})

test('vencida so depois do dia do vencimento; o mes da fatura com zero', () => {
  assert.equal(isPastDue('2026-11-10', '2026-11-10'), false)
  assert.equal(isPastDue('2026-11-10', '2026-11-11'), true)
  assert.equal(isPastDue(null, '2026-11-11'), false)
  assert.equal(invoiceMonthKey({ invoice_year: 2026, invoice_month: 9 }), '2026-09')
})
