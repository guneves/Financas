// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { flagText, moneyInputValue, parseMoneyInput, sortFlags, spendStatus } from './monthlyPlan.js'

test('parseMoneyInput aceita virgula do teclado do celular e ponto do desktop', () => {
  assert.equal(parseMoneyInput('1.234,56'), 1234.56)
  assert.equal(parseMoneyInput('1234,5'), 1234.5)
  assert.equal(parseMoneyInput('1234.56'), 1234.56)
  assert.equal(parseMoneyInput('R$ 3.000'), 3000)
  assert.equal(parseMoneyInput('1.234.567'), 1234567)
  assert.equal(parseMoneyInput('1.5'), 1.5)
  assert.equal(parseMoneyInput('  '), null)
  assert.ok(Number.isNaN(parseMoneyInput('12a')))
})

test('parseMoneyInput: o ultimo separador e o decimal, e milhar so em grupos de tres', () => {
  assert.equal(parseMoneyInput('1,234.56'), 1234.56)
  assert.equal(parseMoneyInput('1,234,567.8'), 1234567.8)
  assert.equal(parseMoneyInput('1,234,567'), 1234567)
  assert.equal(parseMoneyInput('0.500'), 0.5)
  assert.equal(parseMoneyInput('0,50'), 0.5)
  assert.equal(parseMoneyInput('1.500'), 1500)
  assert.equal(parseMoneyInput('1.500,00'), 1500)
  assert.equal(parseMoneyInput('42,9'), 42.9)
  assert.equal(parseMoneyInput('5,'), 5)
  assert.equal(parseMoneyInput(',5'), 0.5)
  assert.ok(Number.isNaN(parseMoneyInput('1.2.3')))
  assert.ok(Number.isNaN(parseMoneyInput('12.34,5.6')))
  assert.ok(Number.isNaN(parseMoneyInput('1,23.4,5')))
  assert.ok(Number.isNaN(parseMoneyInput('12,34.56')))
  assert.ok(Number.isNaN(parseMoneyInput(',')))
  assert.ok(Number.isNaN(parseMoneyInput('-5')))
})

test('moneyInputValue devolve o valor com virgula', () => {
  assert.equal(moneyInputValue(1500.5), '1500,5')
  assert.equal(moneyInputValue(null), '')
})

test('cada codigo de alerta tem texto', () => {
  const codes = [
    'PLAN_OVER_INCOME', 'SPEND_OVER', 'SPEND_PACE', 'SPEND_NEAR', 'SPEND_KEPT',
    'INVEST_DONE', 'INVEST_PENDING', 'INVEST_MISSED', 'GOAL_SHORT', 'GOAL_COVERED',
  ]
  for (const code of codes) {
    const text = flagText({ code, amount: 100, over: 10, missing: 5, days_left: 3, goal_name: 'Reserva', target_month: '2026-12' })
    assert.ok(text.length > 10, code)
  }
  assert.match(flagText({ code: 'GOAL_SHORT', amount: 1000, missing: 400, goal_name: 'Reserva', target_month: '2026-12' }), /Reserva/)
})

test('alertas que pedem acao vem primeiro', () => {
  const sorted = sortFlags([{ code: 'A', tone: 'gain' }, { code: 'B', tone: 'loss' }, { code: 'C', tone: 'warning' }])
  assert.deepEqual(sorted.map((flag) => flag.code), ['B', 'C', 'A'])
})

test('spendStatus segue o alerta de gasto', () => {
  assert.equal(spendStatus([{ code: 'SPEND_OVER' }]), 'OVER')
  assert.equal(spendStatus([{ code: 'SPEND_PACE' }]), 'WARNING')
  assert.equal(spendStatus([{ code: 'INVEST_DONE' }]), 'OK')
})
