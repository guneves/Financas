import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  allocateTreasuryRedemption,
  parseTreasuryUnits,
  treasuryMarketRateText,
  treasuryRateLabel,
  treasuryRateText,
} from './treasury.js'

const lots = [
  { id: 'b', purchase_date: '2026-07-11', invested: 2200, gross: 2400 },
  { id: 'a', purchase_date: '2025-09-14', invested: 1000, gross: 1200 },
]

test('a redemption takes the oldest buy first (PEPS), cost in proportion', () => {
  assert.deepEqual(allocateTreasuryRedemption(lots, 600), [{ lotId: 'a', amount: 600, cost: 500 }])
  const parts = allocateTreasuryRedemption(lots, 1800)
  assert.deepEqual(parts.map((part) => [part.lotId, part.amount]), [['a', 1200], ['b', 600]])
  assert.equal(parts[0].cost, 1000)
  assert.equal(parts[1].cost, 550)
})

test('the whole position, and not a cent more', () => {
  assert.deepEqual(allocateTreasuryRedemption(lots, 3600).map((part) => part.amount), [1200, 2400])
  assert.throws(() => allocateTreasuryRedemption(lots, 3600.01), /saldo bruto/)
  assert.throws(() => allocateTreasuryRedemption(lots, 0), /valor/)
})

test('rate texts follow the indexer', () => {
  assert.equal(treasuryRateText(0.0623, { rate_type: 'POS', indexer: 'IPCA' }), 'IPCA + 6,23% a.a.')
  assert.equal(treasuryRateText(0.121, { rate_type: 'PRE' }), 'Pré 12,10% a.a.')
  assert.equal(treasuryRateText(1, { rate_type: 'POS', indexer: 'CDI' }), '100,00% do CDI')
  assert.equal(treasuryRateText(null, {}), '')
})

test('a grouped position says "Taxa média"', () => {
  const metadata = { rate_type: 'POS', indexer: 'IPCA', annual_rate: 0.0623 }
  assert.equal(
    treasuryRateLabel({ metadata, treasury: { average_rate: 0.0623, lot_count: 2 } }),
    'Taxa média IPCA + 6,23% a.a.',
  )
  assert.equal(treasuryRateLabel({ metadata, treasury: { average_rate: 0.065, lot_count: 1 } }), 'Taxa IPCA + 6,50% a.a.')
  assert.equal(treasuryRateLabel({ metadata }), 'Taxa IPCA + 6,23% a.a.')
})

test('the market rate of the day, never for Selic', () => {
  const metadata = { rate_type: 'POS', indexer: 'IPCA' }
  assert.equal(treasuryMarketRateText({ metadata, treasury: { market_rate: 0.062, title_type: 'TESOURO IPCA+' } }), 'IPCA + 6,20% a.a.')
  assert.equal(treasuryMarketRateText({ metadata, treasury: { market_rate: 0.0007, title_type: 'TESOURO SELIC' } }), '')
})

test('parseTreasuryUnits: virgula ou ponto, vazio e invalido', () => {
  assert.equal(parseTreasuryUnits('0,85'), 0.85)
  assert.equal(parseTreasuryUnits('42.79'), 42.79)
  assert.equal(parseTreasuryUnits('1.042,79'), 1042.79)
  assert.equal(parseTreasuryUnits('  '), null)
  assert.ok(Number.isNaN(parseTreasuryUnits('0')))
  assert.ok(Number.isNaN(parseTreasuryUnits('abc')))
})
