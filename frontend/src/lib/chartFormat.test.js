// node --test src/lib   (npm test em frontend/)
// Os mesmos casos estao em android/.../rules/HomeFlowTest.kt (compactAxis).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { compactAxis } from './chartFormat.js'

test('eixo compacto: mil e milhao abreviados, sem o R$', () => {
  assert.equal(compactAxis(0), '0')
  assert.equal(compactAxis(null), '0')
  assert.equal(compactAxis(950), '950')
  assert.equal(compactAxis(999.6), '1.000')
  assert.equal(compactAxis(1500), '1,5 mil')
  assert.equal(compactAxis(2000), '2 mil')
  assert.equal(compactAxis(12500), '13 mil')
  assert.equal(compactAxis(1_250_000), '1,3 mi')
  assert.equal(compactAxis(-1500), '−1,5 mil')
  assert.equal(compactAxis(-300), '−300')
})
