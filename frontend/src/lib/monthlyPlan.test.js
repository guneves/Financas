// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  categoryAmountPreview,
  flagText,
  formatPlanPercent,
  incomeReceivedText,
  livePlanText,
  livePlanTotals,
  moneyInputValue,
  parseMoneyInput,
  planFlagKey,
  visibleFlags,
  percentOf,
  sortFlags,
  spendStatus,
  unallocatedText,
} from './monthlyPlan.js'

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
    'CATEGORIES_OVER_SPEND',
  ]
  for (const code of codes) {
    const text = flagText({ code, amount: 100, over: 10, missing: 5, days_left: 3, goal_name: 'Reserva', target_month: '2026-12' })
    assert.ok(text.length > 10, code)
  }
  assert.match(flagText({ code: 'GOAL_SHORT', amount: 1000, missing: 400, goal_name: 'Reserva', target_month: '2026-12' }), /Reserva/)
  assert.match(flagText({ code: 'CATEGORIES_OVER_SPEND', amount: 180, percent: 120.5 }), /120,5% do Gastar/)
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

// Os testes de texto comparam sem o espaco de R$ (o Intl usa NBSP).
const plain = (text) => text.replace(/\u00a0/g, ' ')

test('percentOf arredonda meio-para-cima nos centavos, como percent_of() do servidor', () => {
  assert.equal(percentOf(5000, 20), 1000)
  assert.equal(percentOf(5000, 33.333333), 1666.67)
  assert.equal(percentOf(100.05, 50), 50.03) // 50,025 -> 50,03 (round() de banqueiro daria 50,02)
  assert.equal(percentOf(0.1, 50), 0.05)
  assert.equal(percentOf(1234.56, 0), 0)
  assert.equal(percentOf(3000, 12.5), 375)
  assert.equal(percentOf(null, 10), null)
  assert.equal(percentOf(1000, Number.NaN), null)
})

test('formatPlanPercent mostra ate duas casas, com virgula', () => {
  assert.equal(formatPlanPercent(20), '20%')
  assert.equal(formatPlanPercent(33.333333), '33,33%')
  assert.equal(formatPlanPercent(12.5), '12,5%')
  assert.equal(formatPlanPercent(null), '0%')
})

test('unallocatedText: sobra da renda, ou quanto passa de 100%', () => {
  assert.equal(unallocatedText(15), 'Sem destino 15%')
  assert.equal(unallocatedText(0), 'Sem destino 0%')
  assert.equal(unallocatedText(-5.5), 'Passa de 100% da renda em 5,5%')
  assert.equal(unallocatedText(null), '')
})

test('incomeReceivedText compara o recebido com a renda planejada', () => {
  assert.equal(plain(incomeReceivedText(3200, 5000)), 'Recebido R$ 3.200,00 de R$ 5.000,00 esperados')
})

test('livePlanTotals: R$ e Sem destino a cada tecla, e salvar so com renda e ate 100%', () => {
  const totals = livePlanTotals({ income: 5000, invest: 20, spend: 70 })
  assert.equal(totals.investAmount, 1000)
  assert.equal(totals.spendAmount, 3500)
  assert.equal(totals.unallocatedPercent, 10)
  assert.equal(totals.over, false)
  assert.equal(totals.blocked, null)
  assert.equal(plain(livePlanText(totals)), 'Investir R$ 1.000,00 · Gastar R$ 3.500,00 · Sem destino 10%')

  // Somas em float que nao fecham (33,33 + 66,67) ainda dao 100% exatos.
  const full = livePlanTotals({ income: 4000, invest: 33.33, spend: 66.67 })
  assert.equal(full.unallocatedPercent, 0)
  assert.equal(full.blocked, null)

  const over = livePlanTotals({ income: 5000, invest: 40, spend: 70 })
  assert.equal(over.over, true)
  assert.equal(over.unallocatedPercent, -10)
  assert.match(over.blocked, /100%/)
  assert.match(livePlanText(over), /Passa de 100% da renda em 10%/)

  const noIncome = livePlanTotals({ income: null, invest: 20, spend: 70 })
  assert.equal(noIncome.investAmount, null)
  assert.equal(noIncome.unallocatedPercent, 10)
  assert.match(noIncome.blocked, /renda/)
  assert.equal(livePlanText(noIncome), 'Investir — · Gastar — · Sem destino 10%')

  assert.match(livePlanTotals({ income: 0, invest: 20, spend: 70 }).blocked, /renda/)

  const partial = livePlanTotals({ income: 5000, invest: 20, spend: null })
  assert.equal(partial.investAmount, 1000)
  assert.equal(partial.spendAmount, null)
  assert.equal(partial.unallocatedPercent, null)
  assert.match(partial.blocked, /investir e gastar/)
  assert.ok(livePlanTotals({ income: 5000, invest: Number.NaN, spend: 70 }).blocked)
})

test('livePlanTotals: plano antigo sem renda, % em branco converte os reais de antes', () => {
  const legacy = { invest_amount: 1000, spend_amount: 3000 }
  const totals = livePlanTotals({ income: 5000, invest: null, spend: null, legacy })
  assert.equal(totals.convert, true)
  assert.equal(totals.investAmount, 1000)
  assert.equal(totals.spendAmount, 3000)
  assert.equal(totals.unallocatedPercent, 20)
  assert.equal(totals.blocked, null)

  // Acima da renda a conversao e aceita (vira alerta no plano), nao bloqueada.
  const over = livePlanTotals({ income: 3000, invest: null, spend: null, legacy })
  assert.equal(over.over, true)
  assert.equal(over.blocked, null)

  assert.match(livePlanTotals({ income: null, invest: null, spend: null, legacy }).blocked, /renda/)
  // Digitar um % sai da conversao: vale a regra normal.
  assert.match(livePlanTotals({ income: 5000, invest: 20, spend: null, legacy }).blocked, /investir e gastar/)
})

test('categoryAmountPreview: o % do Gastar em reais', () => {
  assert.equal(categoryAmountPreview(3500, 10), 350)
  assert.equal(categoryAmountPreview(3500, null), null)
  assert.equal(categoryAmountPreview(3500, Number.NaN), null)
  assert.equal(categoryAmountPreview(null, 10), null)
})

test('planFlagKey: codigo + mes, e a meta nos alertas de meta', () => {
  assert.equal(planFlagKey({ code: 'SPEND_PACE', tone: 'warning' }, '2026-10'), 'plan:2026-10:SPEND_PACE')
  assert.equal(planFlagKey({ code: 'GOAL_SHORT', goal_id: 7 }, '2026-10'), 'plan:2026-10:GOAL_SHORT:7')
  // O valor do alerta muda todo dia; a chave nao.
  assert.equal(planFlagKey({ code: 'SPEND_PACE', amount: 10 }, '2026-10'), planFlagKey({ code: 'SPEND_PACE', amount: 99 }, '2026-10'))
})

test('visibleFlags: o dispensado nao volta no mes; um novo, outra meta ou o mes seguinte voltam', () => {
  const flags = [
    { code: 'SPEND_PACE', tone: 'warning', amount: 120 },
    { code: 'GOAL_SHORT', tone: 'loss', goal_id: 1 },
    { code: 'GOAL_SHORT', tone: 'loss', goal_id: 2 },
  ]
  const dismissed = ['plan:2026-10:SPEND_PACE', 'plan:2026-10:GOAL_SHORT:1']
  assert.deepEqual(visibleFlags(flags, '2026-10', dismissed).map((flag) => flag.goal_id ?? flag.code), [2])
  // O ritmo virou estouro: outro codigo, outro alerta.
  assert.equal(visibleFlags([{ code: 'SPEND_OVER', tone: 'loss' }], '2026-10', dismissed).length, 1)
  // Mes seguinte: tudo de novo.
  assert.equal(visibleFlags(flags, '2026-11', dismissed).length, 3)
  assert.deepEqual(visibleFlags(undefined, '2026-10', dismissed), [])
})
