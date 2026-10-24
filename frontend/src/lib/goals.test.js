// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { forecastHint, forecastText, goalBadge, shortMonthYear } from './goals.js'

test('shortMonthYear: mes curto sem ponto e o ano inteiro', () => {
  assert.equal(shortMonthYear('2028-10'), 'out/2028')
  assert.equal(shortMonthYear('2027-05'), 'mai/2027')
  assert.equal(shortMonthYear('2030-01'), 'jan/2030')
})

test('forecastText: alcancada, renda, sem previsao ou o mes', () => {
  assert.equal(forecastText({ reached: true, kind: 'NET_WORTH', estimated_month: '2028-10' }), 'Alcançada')
  assert.equal(forecastText({ reached: false, kind: 'MONTHLY_INCOME', estimated_month: null }), '—')
  assert.equal(forecastText({ reached: false, kind: 'PORTFOLIO', estimated_month: null }), 'Sem previsão')
  assert.equal(forecastText({ reached: false, kind: 'PORTFOLIO', estimated_month: '2028-12' }), 'dez/2028')
})

test('forecastHint: anos e meses, no singular quando e um', () => {
  const goal = (months) => ({ reached: false, kind: 'NET_WORTH', estimated_month: '2030-01', estimated_months: months })
  assert.equal(forecastHint(goal(27)), 'em 2 anos e 3 meses')
  assert.equal(forecastHint(goal(13)), 'em 1 ano e 1 mês')
  assert.equal(forecastHint(goal(24)), 'em 2 anos')
  assert.equal(forecastHint(goal(5)), 'em 5 meses')
  assert.equal(forecastHint(goal(0)), '')
  assert.equal(forecastHint({ reached: false, kind: 'NET_WORTH', estimated_month: null }), 'Informe um aporte mensal')
  assert.equal(forecastHint({ reached: true, kind: 'NET_WORTH', estimated_month: '2030-01', estimated_months: 3 }), '')
  assert.equal(forecastHint({ reached: false, kind: 'MONTHLY_INCOME', estimated_month: null }), '')
})

test('goalBadge: alcancada vence o prazo; sem data, nenhum selo', () => {
  assert.deepEqual(goalBadge({ reached: true, on_track: false }), { label: 'Alcançada', tone: 'success' })
  assert.deepEqual(goalBadge({ reached: false, on_track: false }), { label: 'Fora do prazo', tone: 'warning' })
  assert.deepEqual(goalBadge({ reached: false, on_track: true }), { label: 'No prazo', tone: 'neutral' })
  assert.equal(goalBadge({ reached: false, on_track: null }), null)
})
