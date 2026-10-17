import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  APPLY_AFTER_AWAY_MS,
  CHECK_EVERY_MS,
  apkPrompt,
  checkStatusMessage,
  installStatusMessage,
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

test('oferece o APK so quando o publicado e mais novo', () => {
  const latest = { versionCode: 10012, versionName: '2026.10.17-abc', nativeLevel: 1 }
  assert.equal(apkPrompt({ apk: null }), null)
  assert.equal(apkPrompt({ apk: { newer: false, latest, nativeLevel: 1 } }), null)
  assert.equal(apkPrompt({ apk: { newer: true, latest: null, nativeLevel: 1 } }), null)
  assert.deepEqual(apkPrompt({ apk: { newer: true, latest, nativeLevel: 1 } }), { versionName: '2026.10.17-abc', required: false })
})

test('o APK e necessario quando a tela do servidor pede um nivel acima do instalado', () => {
  const apk = { newer: true, latest: { versionCode: 10013, nativeLevel: 2 }, nativeLevel: 1 }
  assert.equal(apkPrompt({ apk }).required, true)
  const sameLevel = { ...apk, latest: { versionCode: 10013, nativeLevel: 1 } }
  assert.equal(apkPrompt({ apk: sameLevel, bundle: { status: 'up-to-date' } }).required, false)
  assert.equal(apkPrompt({ apk: sameLevel, bundle: { status: 'incompatible', nativeLevel: 2 } }).required, true)
})

test('cada resposta da instalacao tem um texto', () => {
  for (const status of ['installing', 'needs-permission', 'up-to-date', 'busy']) {
    const message = installStatusMessage({ status })
    assert.ok(message.text && !message.text.startsWith('Resposta inesperada'), status)
  }
  assert.equal(installStatusMessage({ status: 'error', message: 'falhou' }).text, 'falhou')
})
