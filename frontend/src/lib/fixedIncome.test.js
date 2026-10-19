import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  FIXED_INCOME_TYPES,
  TREASURY_TITLES,
  TREASURY_TYPE,
  fixedIncomeMetadataFromForm,
  isTaxFreeFixedIncomeType,
  rateFieldsForMode,
  treasuryRateMode,
} from './fixedIncome.js'

test('Tesouro Direto is a fixed-income type, taxed by the regressive table', () => {
  assert.ok(FIXED_INCOME_TYPES.some((type) => type.value === TREASURY_TYPE && type.label === 'Tesouro Direto'))
  assert.equal(isTaxFreeFixedIncomeType(TREASURY_TYPE), false)
  const metadata = fixedIncomeMetadataFromForm({ fixed_income_type: TREASURY_TYPE, ...rateFieldsForMode('IPCA'), rate: '6,5' })
  assert.deepEqual(
    [metadata.fixed_income_type, metadata.rate_type, metadata.indexer, metadata.annual_rate, metadata.is_tax_free],
    ['TESOURO', 'POS', 'IPCA', 0.065, false],
  )
})

test('the treasury title name gives its rate mode', () => {
  assert.equal(treasuryRateMode('Tesouro Selic 2029'), 'POS')
  assert.equal(treasuryRateMode('Tesouro Prefixado com Juros Semestrais 2035'), 'PRE')
  assert.equal(treasuryRateMode('Tesouro IPCA+ 2045'), 'IPCA')
  assert.equal(treasuryRateMode('Tesouro Renda+ Aposentadoria Extra 2065'), 'IPCA')
  assert.equal(treasuryRateMode('Tesouro Educa+ 2030'), 'IPCA')
  assert.equal(treasuryRateMode('Título X'), null)
  // Todo titulo sugerido tem a rentabilidade que o nome diz.
  TREASURY_TITLES.forEach((title) => assert.ok(treasuryRateMode(title), title))
})
