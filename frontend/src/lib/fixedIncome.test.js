import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  FIXED_INCOME_TYPES,
  TREASURY_TITLES,
  TREASURY_TYPE,
  describeFixedIncome,
  fixedIncomeFormFromMetadata,
  fixedIncomeMetadataFromForm,
  isTaxFreeFixedIncomeType,
  rateFieldLabel,
  rateFieldsForMode,
  rateModeOf,
  ratePlaceholder,
  treasuryRateMode,
} from './fixedIncome.js'

// Par nativo: android/.../rules/FixedIncome.kt (FixedIncomeTest.kt), os mesmos casos na mesma ordem.

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

const CDI_ERROR = 'Informe um percentual do CDI válido.'
const RATE_ERROR = 'Informe uma taxa válida.'

test('the form refuses an empty, negative or unreadable rate, and a zero % of CDI', () => {
  const cdi = { fixed_income_type: 'CDB', rate_type: 'POS', indexer: 'CDI' }
  for (const rate of ['', '  ', '-1', 'abc', '0', '0,0']) {
    assert.throws(() => fixedIncomeMetadataFromForm({ ...cdi, rate }), { message: CDI_ERROR }, rate)
  }
  const pre = { fixed_income_type: 'CDB', rate_type: 'PRE', indexer: 'CDI' }
  for (const rate of ['', '-0,5', '1,2,3']) {
    assert.throws(() => fixedIncomeMetadataFromForm({ ...pre, rate }), { message: RATE_ERROR }, rate)
  }
  // Zero e aceito fora do CDI (um pre de 0% e um titulo sem juros).
  assert.equal(fixedIncomeMetadataFromForm({ ...pre, rate: '0' }).annual_rate, 0)
})

test('the form writes the rate in the key its mode reads, and the tax-free flag by type', () => {
  assert.deepEqual(
    fixedIncomeMetadataFromForm({ fixed_income_type: 'LCI', rate_type: 'POS', indexer: 'CDI', rate: '1.234,5' }),
    { fixed_income_type: 'LCI', rate_type: 'POS', indexer: 'CDI', cdi_percentage: 12.345, annual_rate: undefined, is_tax_free: true },
  )
  assert.deepEqual(
    fixedIncomeMetadataFromForm({ fixed_income_type: '', rate_type: 'PRE', indexer: 'CDI', rate: '12.5' }),
    { fixed_income_type: undefined, rate_type: 'PRE', indexer: undefined, cdi_percentage: undefined, annual_rate: 0.125, is_tax_free: false },
  )
  assert.equal(fixedIncomeMetadataFromForm({ fixed_income_type: 'CDB', rate_type: 'POS', indexer: 'CDI_PLUS', rate: '1,5' }).annual_rate, 0.015)
})

test('the saved metadata comes back as the form', () => {
  assert.deepEqual(
    fixedIncomeFormFromMetadata({ fixed_income_type: 'CDB', rate_type: 'POS', indexer: 'CDI', cdi_percentage: 1.1 }),
    { fixed_income_type: 'CDB', rate_type: 'POS', indexer: 'CDI', rate: '110' },
  )
  assert.deepEqual(
    fixedIncomeFormFromMetadata({ fixed_income_type: 'DEBENTURE', is_tax_free: true, rate_type: 'PRE', indexer: 'IPCA', annual_rate: 0.123456 }),
    { fixed_income_type: 'DEBENTURE_INCENTIVADA', rate_type: 'PRE', indexer: 'CDI', rate: '12.3456' },
  )
  // Lancamento antigo: so cdi_percentage, lido como pos em CDI.
  assert.deepEqual(fixedIncomeFormFromMetadata({ cdi_percentage: 0.95 }), { fixed_income_type: '', rate_type: 'POS', indexer: 'CDI', rate: '95' })
  assert.equal(fixedIncomeFormFromMetadata({ rate_type: 'POS', indexer: 'IPCA' }).rate, '')
  assert.equal(fixedIncomeFormFromMetadata().rate, '')
})

test('rate modes, labels and placeholders', () => {
  assert.equal(rateModeOf({ rate_type: 'PRE', indexer: 'IPCA' }), 'PRE')
  assert.equal(rateModeOf({ rate_type: 'POS', indexer: 'IPCA' }), 'IPCA')
  assert.equal(rateModeOf({ rate_type: 'POS', indexer: 'CDI_PLUS' }), 'POS')
  assert.deepEqual(rateFieldsForMode('PRE'), { rate_type: 'PRE', indexer: 'CDI' })
  assert.deepEqual(rateFieldsForMode('POS'), { rate_type: 'POS', indexer: 'CDI' })
  assert.equal(rateFieldLabel('PRE', 'CDI'), 'Taxa (% a.a.)')
  assert.equal(rateFieldLabel('POS', 'CDI_PLUS'), 'CDI + (% a.a.)')
  assert.equal(rateFieldLabel('POS', 'IPCA'), 'IPCA + (% a.a.)')
  assert.equal(rateFieldLabel('POS', 'CDI'), '% do CDI')
  assert.equal(ratePlaceholder('PRE', 'CDI'), 'Ex: 12,5')
  assert.equal(ratePlaceholder('POS', 'CDI'), 'Ex: 110')
})

test('the one-line description of a title', () => {
  assert.equal(describeFixedIncome({ fixed_income_type: 'CDB', rate_type: 'POS', indexer: 'CDI', cdi_percentage: 1.1 }), 'CDB · 110% do CDI')
  assert.equal(describeFixedIncome({ fixed_income_type: 'TESOURO', rate_type: 'POS', indexer: 'IPCA', annual_rate: 0.065 }), 'Tesouro Direto · IPCA + 6,5% a.a.')
  assert.equal(describeFixedIncome({ rate_type: 'PRE', annual_rate: 0.12345 }), 'Pré 12,35% a.a.')
  assert.equal(describeFixedIncome({ fixed_income_type: 'LCA', rate_type: 'POS', indexer: 'CDI_PLUS', annual_rate: 0.015 }), 'LCA · CDI + 1,5% a.a.')
  assert.equal(describeFixedIncome({ fixed_income_type: 'CDB', rate_type: 'PRE' }), 'CDB')
  assert.equal(describeFixedIncome({ fixed_income_type: 'XYZ', cdi_percentage: 12 }), '1.200% do CDI')
  assert.equal(describeFixedIncome(), '')
})
