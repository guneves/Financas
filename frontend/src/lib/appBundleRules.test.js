import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  APPLY_AFTER_AWAY_MS,
  CHECK_EVERY_MS,
  checkStatusMessage,
  shortVersion,
  shouldApplyOnResume,
  shouldCheck,
} from './appBundleRules.js'

test('procura na primeira vez e depois no maximo a cada intervalo', () => {
  assert.equal(shouldCheck(1000, 0), true)
  assert.equal(shouldCheck(1000 + CHECK_EVERY_MS - 1, 1000), false)
  assert.equal(shouldCheck(1000 + CHECK_EVERY_MS, 1000), true)
})

test('troca ao voltar so com tela esperando, muito tempo fora e nada aberto', () => {
  const away = APPLY_AFTER_AWAY_MS
  assert.equal(shouldApplyOnResume({ awayMs: away, hasOpenLayer: false, staged: '1111111111111111' }), true)
  assert.equal(shouldApplyOnResume({ awayMs: away, hasOpenLayer: false, staged: 'builtin' }), true)
  assert.equal(shouldApplyOnResume({ awayMs: away - 1, hasOpenLayer: false, staged: '1111111111111111' }), false)
  assert.equal(shouldApplyOnResume({ awayMs: away, hasOpenLayer: true, staged: '1111111111111111' }), false)
  assert.equal(shouldApplyOnResume({ awayMs: away, hasOpenLayer: false, staged: '' }), false)
})

test('cada resposta do lado nativo tem um texto', () => {
  for (const status of ['up-to-date', 'staged', 'incompatible', 'other-server', 'failed-before', 'none', 'busy']) {
    const message = checkStatusMessage({ status })
    assert.ok(message.text && !message.text.startsWith('Resposta inesperada'), status)
  }
  assert.equal(checkStatusMessage({ status: 'error', message: 'sem rede' }).text, 'sem rede')
  assert.equal(checkStatusMessage({ status: 'error' }).tone, 'danger')
  assert.equal(checkStatusMessage(null), null)
})

test('versao curta', () => {
  assert.equal(shortVersion('0123456789abcdef'), '0123456')
  assert.equal(shortVersion(''), '—')
})
