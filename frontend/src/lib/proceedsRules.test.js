import { test } from 'node:test'
import assert from 'node:assert/strict'
import { filterAssetOptions, normalizeSearchText } from './assetSearch.js'
import {
  assetCategory,
  assetsForProceedsType,
  categoryLabel,
  proceedsLayout,
  proceedsTaxField,
  proceedsTypeFitsAsset,
  treasuryProduct,
  typeForAsset,
} from './proceedsRules.js'

const asset = (id, ticker, category, extra = {}) => ({ id, ticker, name: ticker, category, ...extra })

const ASSETS = [
  asset('petr', 'PETR4', 'ACAO'),
  asset('bova', 'BOVA11', 'ETF'),
  asset('xpbr', 'XPBR31', 'BDR'),
  asset('mxrf', 'MXRF11', 'FII'),
  asset('cdb', 'CDB BANCO X', 'RENDA_FIXA'),
  asset('selic', 'TESOURO SELIC 2029', 'TESOURO'),
  asset('ntnb', 'TESOURO IPCA+ COM JUROS SEMESTRAIS 2035', 'TESOURO'),
  asset('renda', 'TESOURO RENDA+ APOSENTADORIA EXTRA 2065', 'TESOURO'),
  asset('tit', 'TITULO PUBLICO X', 'TESOURO'),
  asset('btc', 'BTC', 'CRIPTO'),
]

const ids = (list) => list.map((item) => item.id)

test('each proceeds type lists only the assets that can pay it', () => {
  assert.deepEqual(ids(assetsForProceedsType(ASSETS, 'JCP')), ['petr'])
  assert.deepEqual(ids(assetsForProceedsType(ASSETS, 'DIVIDEND')), ['petr', 'bova', 'xpbr', 'mxrf'])
  assert.deepEqual(ids(assetsForProceedsType(ASSETS, 'INTEREST')), ['cdb', 'ntnb', 'tit'])
  assert.deepEqual(ids(assetsForProceedsType(ASSETS, 'AMORTIZATION')), ['petr', 'mxrf', 'cdb', 'renda', 'tit'])
})

test('an edit keeps its own asset even when it no longer fits', () => {
  assert.deepEqual(ids(assetsForProceedsType(ASSETS, 'JCP', 'mxrf')), ['petr', 'mxrf'])
})

test('the treasury product comes from the title name', () => {
  assert.equal(treasuryProduct('Tesouro Selic 2029'), 'BULLET')
  assert.equal(treasuryProduct('Tesouro Prefixado 2031'), 'BULLET')
  assert.equal(treasuryProduct('Tesouro IPCA+ 2045'), 'BULLET')
  assert.equal(treasuryProduct('Tesouro Prefixado com Juros Semestrais 2035'), 'COUPON')
  assert.equal(treasuryProduct('NTN-B 2035'), 'COUPON')
  assert.equal(treasuryProduct('NTN-B Principal 2035'), 'BULLET')
  assert.equal(treasuryProduct('NTN-F 2031'), 'COUPON')
  assert.equal(treasuryProduct('Tesouro Educa+ 2030'), 'INSTALLMENTS')
  assert.equal(treasuryProduct('Título do governo'), null)
})

test('a category falls back to the class for an old response', () => {
  assert.equal(assetCategory({ asset_class: 'STOCKS' }), 'ACAO')
  assert.equal(assetCategory({ class: 'FIXED_INCOME' }), 'RENDA_FIXA')
  assert.equal(assetCategory({ asset_class: 'STOCKS', category: 'ETF' }), 'ETF')
  assert.equal(categoryLabel({ category: 'TESOURO' }), 'Tesouro Direto')
  assert.equal(proceedsTypeFitsAsset('JCP', { asset_class: 'REIT' }), false)
})

test('the form layout and the tax field follow the type and the asset', () => {
  assert.equal(proceedsLayout('INTEREST', ASSETS[4]), 'FIXED')
  assert.equal(proceedsLayout('AMORTIZATION', ASSETS[7]), 'FIXED')
  assert.equal(proceedsLayout('AMORTIZATION', ASSETS[3]), 'MARKET')
  assert.equal(proceedsLayout('DIVIDEND', ASSETS[0]), 'MARKET')
  assert.equal(proceedsTaxField('AMORTIZATION'), null)
  assert.match(proceedsTaxField('JCP').hint, /15%/)
  assert.match(proceedsTaxField('INTEREST').hint, /regressiva/)
  assert.match(proceedsTaxField('DIVIDEND').hint, /sem IR/)
})

test('changing asset keeps the type when it fits, else picks the first that does', () => {
  assert.equal(typeForAsset(ASSETS[0], 'JCP'), 'JCP')
  assert.equal(typeForAsset(ASSETS[3], 'JCP'), 'DIVIDEND')
  assert.equal(typeForAsset(ASSETS[4], 'DIVIDEND'), 'AMORTIZATION')
  assert.equal(typeForAsset(ASSETS[6], 'DIVIDEND'), 'INTEREST')
  assert.equal(typeForAsset(null, 'JCP'), 'JCP')
})

test('the search matches ticker or name, without accents, ticker first', () => {
  const options = [
    { value: '1', label: 'ITSA4', name: 'Itaúsa' },
    { value: '2', label: 'ITUB4', name: 'Itaú Unibanco' },
    { value: '3', label: 'BBAS3', name: 'Banco do Brasil' },
    { value: '4', label: 'XPBR31', name: 'Petrobras BDR' },
    { value: '5', label: 'PETR4', name: 'Petrobras PN' },
  ]
  assert.deepEqual(filterAssetOptions(options, 'itau').map((o) => o.value), ['1', '2'])
  assert.deepEqual(filterAssetOptions(options, 'petr').map((o) => o.value), ['5', '4'])
  assert.deepEqual(filterAssetOptions(options, ' banco ').map((o) => o.value), ['3', '2'])
  assert.deepEqual(filterAssetOptions(options, '').map((o) => o.value), ['1', '2', '3', '4', '5'])
  assert.deepEqual(filterAssetOptions(options, 'zzz'), [])
  assert.equal(normalizeSearchText('  Tesouro   IPCA+ '), 'TESOURO IPCA+')
})
