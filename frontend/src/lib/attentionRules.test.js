import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  ATTENTION_LINKS,
  MAX_DISMISSED_KEYS,
  addDismissed,
  attentionLink,
  attentionText,
  bellBadge,
  bellLabel,
  invoiceMonthKey,
  isPastDue,
  overdueDetail,
  undismissedItems,
} from './attentionRules.js'

// As regras dos avisos sao do servidor desde a proposta home-attention-invoices.md:
// os casos que moravam aqui estao em backend/tests/test_attention.py e
// test_cc_invoices.py (fatura vencida, fechada, debito automatico, chaves,
// estorno, proxima fatura, a mais proxima). Ficam o texto e as dispensas.
// Os mesmos casos estao em android/.../rules/AttentionRulesTest.kt.

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

const NBSP = '\u00A0'
const masked = () => 'R$ ••••••'

test('o texto de cada aviso, com os numeros do servidor', () => {
  const overdue = {
    kind: 'INVOICE_OVERDUE',
    total: 1234.5,
    item_count: 3,
    invoices: [{ card_name: 'Nubank', due_date: '2026-10-10' }],
  }
  assert.deepEqual(attentionText(overdue), {
    title: `Fatura vencida: R$${NBSP}1.234,50`,
    detail: 'Nubank · venceu em 10/10/2026 · 3 lançamento(s)',
  })
  assert.deepEqual(attentionText({ kind: 'INVOICE_PAYABLE', total: 80 }), {
    title: `Fatura fechada: R$${NBSP}80,00`,
    detail: 'O pagamento já está liberado.',
  })
  assert.deepEqual(attentionText({ kind: 'RECURRING', count: 1 }), { title: '1 recorrência vencida', detail: '' })
  assert.deepEqual(attentionText({ kind: 'RECURRING', count: 4 }), { title: '4 recorrências vencidas', detail: '' })
  assert.deepEqual(attentionText({ kind: 'OVER_BUDGET', category_name: 'Alimentação › Mercado', spent: 650, available: 600 }), {
    title: 'Alimentação › Mercado passou do orçamento',
    detail: `R$${NBSP}650,00 de R$${NBSP}600,00`,
  })
  assert.deepEqual(attentionText({ kind: 'OUTRO' }), { title: '', detail: '' })
})

test('debito automatico sem saldo: o saldo e o que falta somem no modo privado', () => {
  const shortfall = { kind: 'AUTOPAY_SHORTFALL', account_name: 'Itaú', total: 900, balance: 300.1, missing: 599.9, first_due: '2026-11-05' }
  assert.deepEqual(attentionText(shortfall), {
    title: `Débito automático sem saldo: faltam R$${NBSP}599,90`,
    detail: `Itaú tem R$${NBSP}300,10 para R$${NBSP}900,00 a debitar · o primeiro em 05/11/2026`,
  })
  assert.deepEqual(attentionText(shortfall, masked), {
    title: 'Débito automático sem saldo: faltam R$ ••••••',
    detail: `Itaú tem R$ •••••• para R$${NBSP}900,00 a debitar · o primeiro em 05/11/2026`,
  })
})

test('para onde cada aviso leva', () => {
  assert.deepEqual(attentionLink('INVOICE_OVERDUE'), { to: '/lancamentos/cartoes', label: 'Ver faturas' })
  assert.deepEqual(attentionLink('AUTOPAY_SHORTFALL'), { to: '/lancamentos/cartoes', label: 'Ver faturas' })
  assert.deepEqual(attentionLink('RECURRING'), { to: '/planejamento/recorrentes', label: 'Ver recorrentes' })
  assert.deepEqual(attentionLink('OVER_BUDGET'), { to: '/planejamento/orcamento', label: 'Ver orçamento' })
  assert.equal(attentionLink('OUTRO'), null)
  assert.equal(Object.keys(ATTENTION_LINKS).length, 5)
})

test('o selo do sino: todos os avisos, 9+ acima de nove', () => {
  assert.equal(bellBadge(0), '')
  assert.equal(bellBadge(1), '1')
  assert.equal(bellBadge(9), '9')
  assert.equal(bellBadge(10), '9+')
  assert.equal(bellLabel(0), 'Precisa de atenção: nenhum aviso')
  assert.equal(bellLabel(1), 'Precisa de atenção: 1 aviso')
  assert.equal(bellLabel(3), 'Precisa de atenção: 3 avisos')
})
