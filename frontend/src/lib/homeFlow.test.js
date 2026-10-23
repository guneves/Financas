// node --test src/lib   (npm test em frontend/)
// Os mesmos casos estao em android/.../rules/HomeFlowTest.kt.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { flowPoint, flowSummary, savingsRateText } from './homeFlow.js'

const month = (key, values = {}) => ({
  month: key,
  income: 0,
  expense: 0,
  invested: 0,
  redeemed: 0,
  others_paid: 0,
  others_received: 0,
  net: 0,
  balance: 0,
  ...values,
})

test('o ponto do grafico: saidas abaixo do zero, investimento e outras pessoas liquidos', () => {
  const point = flowPoint(month('2026-10', {
    income: 1000, expense: 250.5, invested: 300, redeemed: 100, others_paid: 40, others_received: 10, net: 519.5, balance: 5000,
  }))
  assert.equal(point.key, '2026-10')
  assert.equal(point.label, 'out/26')
  assert.equal(point.income, 1000)
  assert.equal(point.expense, -250.5)
  assert.equal(point.investment, -200)
  assert.equal(point.others, -30)
  assert.equal(point.net, 519.5)
  assert.equal(point.balance, 5000)
})

test('mes vazio nao vira -0; resgate maior que aporte fica acima do zero', () => {
  const empty = flowPoint(month('2026-01'))
  assert.ok(Object.is(empty.expense, 0))
  assert.ok(Object.is(empty.investment, 0))
  assert.ok(Object.is(empty.others, 0))
  assert.equal(flowPoint(month('2026-02', { invested: 100, redeemed: 350.25 })).investment, 250.25)
  assert.equal(flowPoint(month('2026-02', { others_received: 80.1 })).others, 80.1)
})

test('as medias contam so os meses com movimento', () => {
  const summary = flowSummary([
    flowPoint(month('2026-08')),
    flowPoint(month('2026-09', { income: 1000, expense: 400 })),
    flowPoint(month('2026-10', { income: 2000, expense: 600, invested: 500 })),
  ])
  assert.equal(summary.avgIncome, 1500)
  assert.equal(summary.avgExpense, 500)
  assert.equal(summary.avgInvestment, 250)
  assert.equal(Math.round(summary.savingsRate * 1000) / 1000, 66.667)
  assert.equal(summary.hasData, true)
  assert.equal(summary.hasInvestment, true)
  assert.equal(summary.hasOthers, false)
})

test('so outras pessoas ja e um mes com movimento; resgate deixa a media negativa', () => {
  const summary = flowSummary([
    flowPoint(month('2026-09', { others_paid: 30 })),
    flowPoint(month('2026-10', { redeemed: 200 })),
  ])
  assert.equal(summary.hasData, true)
  assert.equal(summary.hasOthers, true)
  assert.equal(summary.avgInvestment, -100)
  assert.equal(summary.avgIncome, 0)
  assert.equal(summary.savingsRate, null)
})

test('sem nenhum movimento: nada a mostrar, e a divisao e por um mes', () => {
  const summary = flowSummary([flowPoint(month('2026-10'))])
  assert.equal(summary.hasData, false)
  assert.equal(summary.avgIncome, 0)
  assert.equal(summary.savingsRate, null)
  assert.deepEqual(flowSummary([]).hasData, false)
})

test('despesa maior que a receita: taxa negativa', () => {
  const summary = flowSummary([flowPoint(month('2026-10', { income: 1000, expense: 1500 }))])
  assert.equal(summary.savingsRate, -50)
})

test('a taxa de poupanca com uma casa no maximo', () => {
  assert.equal(savingsRateText(null), '—')
  assert.equal(savingsRateText(200 / 3), '66,7%')
  assert.equal(savingsRateText(-50), '-50%')
  assert.equal(savingsRateText(12.25), '12,3%')
  assert.equal(savingsRateText(1234.56), '1.234,6%')
  assert.equal(savingsRateText(0), '0%')
})
