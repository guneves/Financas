import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  MAX_DISMISSED_KEYS,
  addDismissed,
  attentionItems,
  autopayShortfalls,
  isPastDue,
  nearestOpenInvoice,
  nextInvoices,
  overdueInvoices,
  payableInvoices,
  undismissedItems,
} from './attentionRules.js'

const expense = (fields) => ({ status: 'OPEN', card_id: 1, invoice_year: 2026, invoice_month: 10, amount: '100', ...fields })

test('fatura vencida: so a que passou do vencimento, somada por fatura', () => {
  const open = [
    expense({ invoice_due_date: '2026-10-10', credit_cards: { name: 'Nubank' } }),
    expense({ invoice_due_date: '2026-10-10', amount: '50' }),
    expense({ invoice_month: 11, invoice_due_date: '2026-11-10' }),
  ]
  const overdue = overdueInvoices(open, '2026-10-18')
  assert.equal(overdue.length, 1)
  assert.equal(overdue[0].total, 150)
  assert.equal(overdue[0].count, 2)
  assert.equal(overdue[0].card_name, 'Nubank')
})

test('fatura fechada: uma por cartao, so as fechadas', () => {
  const payable = payableInvoices([
    expense({ invoice_closed: true }),
    expense({ invoice_closed: true, amount: '20' }),
    expense({ card_id: 2, invoice_closed: false }),
  ])
  assert.deepEqual(payable.map((invoice) => [invoice.card_id, invoice.total]), [[1, 120]])
})

test('fatura fechada nao aparece junto da vencida', () => {
  const overdue = [{ card_id: 1, invoice_year: 2026, invoice_month: 9, due_date: '2026-09-10', card_name: 'X', total: 10, count: 1 }]
  const payable = [{ card_id: 1, invoice_year: 2026, invoice_month: 11, total: 30 }]
  assert.deepEqual(attentionItems({ overdue, payable }).map((item) => item.kind), ['INVOICE_OVERDUE'])
  assert.deepEqual(attentionItems({ payable }).map((item) => item.kind), ['INVOICE_PAYABLE'])
})

test('debito automatico: a conta que nao cobre a fatura dos proximos dias', () => {
  const cards = [{ id: 1, autopay_account_id: 7 }]
  const accounts = [{ id: 7, name: 'Itaú', type: 'CHECKING', currency: 'BRL', balance: 80 }]
  const openExpenses = [expense({ invoice_due_date: '2026-10-25' }), expense({ invoice_due_date: '2026-12-25' })]
  const result = autopayShortfalls({ cards, accounts, openExpenses, todayText: '2026-10-18', limitText: '2026-11-18' })
  assert.equal(result.length, 1)
  assert.equal(result[0].missing, 20)
  assert.equal(result[0].accountName, 'Itaú')
})

test('a chave identifica o caso: nova fatura, novo atraso ou novo mes de orcamento voltam', () => {
  const recurring = (last) => [{ id: 3, pending_count: 1, last_occurrence_date: last }]
  const before = attentionItems({ recurringItems: recurring('2026-09-01') })[0].key
  const after = attentionItems({ recurringItems: recurring('2026-10-01') })[0].key
  assert.notEqual(before, after)

  const budget = (month) => ({ month, items: [{ id: 9, category_id: 4, category_name: 'Mercado', status: 'OVER', spent: 120, available: 100 }] })
  const october = attentionItems({ budget: budget('2026-10') })
  assert.equal(october[0].categoryName, 'Mercado')
  assert.notEqual(october[0].key, attentionItems({ budget: budget('2026-11') })[0].key)
})

test('dispensar esconde so os casos dispensados', () => {
  const budget = {
    month: '2026-10',
    items: [
      { id: 1, category_id: 1, category_name: 'A', status: 'OVER', spent: 2, available: 1 },
      { id: 2, category_id: 2, category_name: 'B', status: 'OK', spent: 0, available: 1 },
    ],
  }
  const items = attentionItems({ budget, recurringItems: [{ id: 3, pending_count: 2 }] })
  assert.equal(items.length, 2)
  const dismissed = addDismissed([], [items[0].key])
  assert.deepEqual(items.map((item) => item.kind), ['RECURRING', 'OVER_BUDGET'])
  assert.deepEqual(undismissedItems(items, dismissed).map((item) => item.kind), ['OVER_BUDGET'])
})

test('a lista de dispensados nao cresce sem fim e nao repete', () => {
  const many = Array.from({ length: MAX_DISMISSED_KEYS + 5 }, (_, index) => `k${index}`)
  const kept = addDismissed([], many)
  assert.equal(kept.length, MAX_DISMISSED_KEYS)
  assert.equal(kept.at(-1), `k${MAX_DISMISSED_KEYS + 4}`)
  assert.deepEqual(addDismissed(['a', 'b'], ['a']), ['b', 'a'])
})

test('estorno abate a fatura: em credito nao e vencida nem pagavel', () => {
  const refund = (fields) => expense({ kind: 'REFUND', ...fields })
  const overdue = overdueInvoices([
    expense({ invoice_due_date: '2026-10-10', amount: '100' }),
    refund({ invoice_due_date: '2026-10-10', amount: '30' }),
    expense({ card_id: 2, invoice_due_date: '2026-10-10', amount: '10' }),
    refund({ card_id: 2, invoice_due_date: '2026-10-10', amount: '50' }),
  ], '2026-10-18')
  assert.deepEqual(overdue.map((invoice) => [invoice.card_id, invoice.total]), [[1, 70]])
  const payable = payableInvoices([
    expense({ invoice_closed: true, amount: '10' }),
    refund({ invoice_closed: true, amount: '40' }),
  ])
  assert.deepEqual(payable, [])
})

// Fecha 3, vence 10 (o Nubank do seed): a fatura de novembro fecha em 03/11 e
// vence em 10/11. Fecha 25, vence 5: a de dezembro fecha em 25/11.
const nubank = (month, fields) => expense({
  card_id: 'nubank',
  invoice_month: month,
  invoice_due_date: `2026-${String(month).padStart(2, '0')}-10`,
  invoice_closing_date: `2026-${String(month).padStart(2, '0')}-03`,
  ...fields,
})
const late = (month, year, fields) => expense({
  card_id: 'late',
  invoice_month: month,
  invoice_year: year,
  invoice_due_date: `${year}-${String(month).padStart(2, '0')}-05`,
  ...fields,
})

test('proxima fatura: quem fecha antes de vencer paga a do proprio mes', () => {
  // 5 de novembro: a de novembro (R$ 1.200) fechou no dia 3 e vence no 10.
  const open = [
    nubank(11, { amount: '1000', invoice_closed: true }),
    nubank(11, { amount: '200', invoice_closed: true }),
    nubank(12, { amount: '80', invoice_closed: false }),
  ]
  const [invoice, ...others] = nextInvoices(open, '2026-11-05')
  assert.equal(others.length, 0)
  assert.equal(invoice.invoice_month, 11)
  assert.equal(invoice.total, 1200)
  assert.equal(invoice.closed, true)
  assert.equal(invoice.items.length, 2)
  assert.deepEqual(payableInvoices(invoice.items).map((entry) => [entry.invoice_month, entry.total]), [[11, 1200]])
})

test('proxima fatura: no dia do vencimento ainda e ela; no dia seguinte e a vencida', () => {
  const open = [nubank(11, { amount: '1200', invoice_closed: true }), nubank(12, { amount: '80' })]
  assert.equal(nextInvoices(open, '2026-11-10')[0].invoice_month, 11)
  assert.deepEqual(overdueInvoices(open, '2026-11-10'), [])
  assert.equal(nextInvoices(open, '2026-11-11')[0].invoice_month, 12)
  assert.equal(overdueInvoices(open, '2026-11-11')[0].invoice_month, 11)
  assert.equal(isPastDue('2026-11-10', '2026-11-10'), false)
  assert.equal(isPastDue('2026-11-10', '2026-11-11'), true)
  assert.equal(isPastDue(undefined, '2026-11-11'), false)
})

test('proxima fatura: quem fecha depois de vencer ja tem fechada a do mes seguinte', () => {
  // 26 de novembro: a de dezembro fechou no dia 25 e vence em 05/12.
  const open = [
    late(12, 2026, { amount: '300', invoice_closed: true }),
    late(1, 2027, { amount: '40', invoice_closed: false }),
  ]
  const [invoice] = nextInvoices(open, '2026-11-26')
  assert.deepEqual([invoice.invoice_month, invoice.total, invoice.closed], [12, 300, true])
})

test('proxima fatura: uma por cartao, pela ordem do vencimento; paga nao conta', () => {
  const open = [
    late(12, 2026, { amount: '300' }),
    nubank(12, { amount: '80' }),
    nubank(1, { invoice_year: 2027, invoice_due_date: '2027-01-10', amount: '50' }),
  ]
  // A de novembro do Nubank foi paga (saiu das abertas): a proxima e a de dezembro.
  const invoices = nextInvoices(open, '2026-11-12')
  assert.deepEqual(invoices.map((invoice) => [invoice.card_id, invoice.invoice_month, invoice.total]), [
    ['late', 12, 300],
    ['nubank', 12, 80],
  ])
})

test('fatura mais proxima (tela Cartoes): a vencida antes, senao a primeira das proximas', () => {
  const open = [nubank(11, { amount: '1200', invoice_closed: true }), late(12, 2026, { amount: '300' })]
  assert.equal(nearestOpenInvoice(open, '2026-11-05').card_id, 'nubank')
  const overdue = nearestOpenInvoice(open, '2026-11-20')
  assert.deepEqual([overdue.card_id, overdue.invoice_month], ['nubank', 11])
  assert.equal(nearestOpenInvoice([], '2026-11-20'), null)
})
