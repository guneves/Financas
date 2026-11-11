import { test } from 'node:test'
import assert from 'node:assert/strict'
import { quoteFailureCount, quoteFailureGroups } from './quoteUpdate.js'

test('sem falha não há aviso, mesmo com cotações atualizadas, em cache ou desatualizadas', () => {
  const result = {
    updated_assets: [{ ticker: 'PETR4' }],
    cached_assets: [{ ticker: 'VALE3' }],
    stale_assets: [{ ticker: 'IVVB11' }],
    failed_assets: [],
  }
  assert.equal(quoteFailureCount(result), 0)
  assert.deepEqual(quoteFailureGroups(result), [])
  assert.deepEqual(quoteFailureGroups(null), [])
})

test('as falhas se agrupam por motivo, na ordem em que chegaram', () => {
  const result = {
    updated_assets: [{ ticker: 'PETR4' }],
    failed_assets: [
      { ticker: 'AAPL34', error: 'Tempo limite' },
      { ticker: 'XPML11', error: 'Cotacao nao encontrada' },
      { ticker: 'BOVA11', error: 'Tempo limite' },
      { name: 'CDB Banco X' },
    ],
  }
  assert.equal(quoteFailureCount(result), 4)
  assert.deepEqual(quoteFailureGroups(result), [
    { error: 'Tempo limite', names: ['AAPL34', 'BOVA11'] },
    { error: 'Cotacao nao encontrada', names: ['XPML11'] },
    { error: 'sem detalhe', names: ['CDB Banco X'] },
  ])
})
