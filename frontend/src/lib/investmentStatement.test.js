import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  buildInvestmentStatement,
  groupEntriesByDay,
  movementEntry,
  proceedEntry,
  statementTotals,
} from './investmentStatement.js'

const buy = { id: 'm1', asset_class: 'STOCKS', ticker_or_name: 'BBAS3', quantity: 10, average_price: 20, fee_amount: 1, metadata: { purchase_date: '2026-03-01' } }
const sale = { id: 'm2', asset_class: 'STOCKS', ticker_or_name: 'BBAS3', quantity: -5, average_price: 20, realized_net_proceeds: 120, metadata: { sale_date: '2026-05-01', sale_price: 25 } }
const bonus = { id: 'm3', asset_class: 'STOCKS', ticker_or_name: 'ITSA4', quantity: 2, average_price: 0, metadata: { purchase_date: '2026-03-01', corporate_action_id: 'ca' } }
const redemption = { id: 'm4', asset_class: 'FIXED_INCOME', ticker_or_name: 'LCI', quantity: -1, current_price: 1000, metadata: { is_redemption: true, redemption_date: '2026-04-01' } }
const paid = { id: 'p1', proceeds_type: 'JCP', payment_date: '2026-06-11', net_amount: 8.25, tax_amount: 1.75, eligible_quantity: 10, amount_per_unit: 1, asset: { ticker: 'BBAS3' }, sync_key: 'k' }
const future = { id: 'p2', proceeds_type: 'DIVIDEND', payment_date: '2026-12-20', net_amount: 5, tax_amount: 0, asset: { ticker: 'KLBN4' } }

test('a compra sai com a taxa, a venda entra pelo liquido, bonificacao e zero', () => {
  assert.equal(movementEntry(buy).amount, -201)
  assert.equal(movementEntry(buy).kind, 'Compra')
  assert.equal(movementEntry(sale).amount, 120)
  assert.equal(movementEntry(sale).kind, 'Venda')
  assert.equal(movementEntry(bonus).amount, 0)
  assert.equal(movementEntry(bonus).kind, 'Bonificação')
})

test('renda fixa e aporte/resgate, sem quantidade', () => {
  const entry = movementEntry(redemption)
  assert.equal(entry.kind, 'Resgate')
  assert.equal(entry.amount, 1000)
  assert.equal(entry.quantity, null)
  assert.equal(entry.date, '2026-04-01')
})

test('provento entra pelo liquido e o futuro fica agendado', () => {
  assert.equal(proceedEntry(paid, '2026-10-16').amount, 8.25)
  assert.equal(proceedEntry(paid, '2026-10-16').scheduled, false)
  assert.equal(proceedEntry(paid, '2026-10-16').automatic, true)
  assert.equal(proceedEntry(future, '2026-10-16').scheduled, true)
})

test('lista do mais novo ao mais antigo, filtrada por tipo e busca', () => {
  const all = buildInvestmentStatement([buy, sale], [paid, future], { today: '2026-10-16' })
  assert.deepEqual(all.map((e) => e.id), ['prov:p2', 'prov:p1', 'mov:m2', 'mov:m1'])
  assert.deepEqual(buildInvestmentStatement([buy], [paid], { kind: 'PROCEEDS' }).map((e) => e.id), ['prov:p1'])
  assert.deepEqual(buildInvestmentStatement([buy], [paid], { kind: 'MOVEMENTS' }).map((e) => e.id), ['mov:m1'])
  assert.deepEqual(buildInvestmentStatement([buy, bonus], [], { query: 'itsa' }).map((e) => e.id), ['mov:m3'])
})

test('totais separam aporte, retirada, provento recebido e agendado', () => {
  const entries = buildInvestmentStatement([buy, sale], [paid, future], { today: '2026-10-16' })
  assert.deepEqual(statementTotals(entries), { invested: 201, withdrawn: 120, proceeds: 8.25, scheduled: 5 })
})

test('o total do dia ignora o agendado', () => {
  const groups = groupEntriesByDay([
    { date: '2026-12-20', amount: 5, scheduled: true },
    { date: '2026-03-01', amount: -201, scheduled: false },
    { date: '2026-03-01', amount: 0, scheduled: false },
  ])
  assert.deepEqual(groups.map((g) => [g.date, g.items.length, g.total]), [['2026-12-20', 1, 0], ['2026-03-01', 2, -201]])
})
