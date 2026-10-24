// node --test src/lib   (npm test em frontend/)
// Par nativo: android/.../rules/AssetSearch.kt (AssetSearchTest.kt), os mesmos casos na mesma ordem.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { filterAssetOptions, normalizeSearchText } from './assetSearch.js'

const options = [
  { value: '1', label: 'ITSA4', name: 'Itaúsa' },
  { value: '2', label: 'ITUB4', name: 'Itaú Unibanco' },
  { value: '3', label: 'BBAS3', name: 'Banco do Brasil' },
  { value: '4', label: 'XPBR31', name: 'Petrobras BDR' },
  { value: '5', label: 'PETR4', name: 'Petrobras PN' },
]

const values = (list) => list.map((option) => option.value)

test('the search matches ticker or name, without accents, ticker first', () => {
  assert.deepEqual(values(filterAssetOptions(options, 'itau')), ['1', '2'])
  assert.deepEqual(values(filterAssetOptions(options, 'petr')), ['5', '4'])
  assert.deepEqual(values(filterAssetOptions(options, ' banco ')), ['3', '2'])
  assert.deepEqual(values(filterAssetOptions(options, '')), ['1', '2', '3', '4', '5'])
  assert.deepEqual(filterAssetOptions(options, 'zzz'), [])
})

test('the four ranks: ticker starts, ticker contains, name starts, name contains', () => {
  const ranked = [
    { value: 'name-contains', label: 'AAAA3', name: 'Grupo Vale' },
    { value: 'name-starts', label: 'BBBB3', name: 'Vale do Rio' },
    { value: 'ticker-contains', label: 'XVALE3', name: '' },
    { value: 'ticker-starts', label: 'VALE3', name: 'Mineradora' },
  ]
  assert.deepEqual(values(filterAssetOptions(ranked, 'vale')), ['ticker-starts', 'ticker-contains', 'name-starts', 'name-contains'])
})

test('a tie keeps the order given', () => {
  const tied = [
    { value: 'b', label: 'TAEE11' },
    { value: 'a', label: 'TAEE4' },
  ]
  assert.deepEqual(values(filterAssetOptions(tied, 'taee')), ['b', 'a'])
})

test('the limit cuts after ranking, with or without text', () => {
  assert.deepEqual(values(filterAssetOptions(options, '', 2)), ['1', '2'])
  assert.deepEqual(values(filterAssetOptions(options, 'petr', 1)), ['5'])
})

test('missing name, missing list and an accented query', () => {
  assert.deepEqual(values(filterAssetOptions([{ value: 'x', label: 'KNRI11' }], 'knri')), ['x'])
  assert.deepEqual(filterAssetOptions(undefined, 'a'), [])
  assert.deepEqual(values(filterAssetOptions(options, 'ITAÚ')), ['1', '2'])
})

test('normalizeSearchText: accents, case and spaces', () => {
  assert.equal(normalizeSearchText('  Tesouro   IPCA+ '), 'TESOURO IPCA+')
  assert.equal(normalizeSearchText('Ação Ômega'), 'ACAO OMEGA')
  assert.equal(normalizeSearchText(null), '')
  assert.equal(normalizeSearchText(undefined), '')
})
