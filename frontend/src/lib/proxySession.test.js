// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PROXY_RELOAD_MIN_MS, isProxyAuthResponse, shouldReload } from './proxySession.js'

const response = (status, headers = {}, type = 'basic') => ({
  status,
  type,
  headers: { get: (name) => headers[Object.keys(headers).find((key) => key.toLowerCase() === name.toLowerCase())] ?? null },
})

test('o 401 do proxy leva X-Proxy-Auth: required', () => {
  assert.equal(isProxyAuthResponse(response(401, { 'x-proxy-auth': 'required' })), true)
  assert.equal(isProxyAuthResponse(response(401, { 'X-Proxy-Auth': 'required' })), true)
})

test('o 401 do app (JWT vencido) nao e do proxy', () => {
  assert.equal(isProxyAuthResponse(response(401)), false)
  assert.equal(isProxyAuthResponse(response(401, { 'X-Proxy-Auth': 'other' })), false)
})

test('um redirecionamento para o login do Google e do proxy', () => {
  assert.equal(isProxyAuthResponse(response(0, {}, 'opaqueredirect')), true)
})

test('outras respostas nao sao do proxy', () => {
  assert.equal(isProxyAuthResponse(response(200)), false)
  assert.equal(isProxyAuthResponse(response(403, { 'X-Proxy-Auth': 'required' })), false)
  assert.equal(isProxyAuthResponse(response(502)), false)
  assert.equal(isProxyAuthResponse(null), false)
})

test('recarrega no maximo uma vez a cada 30 s', () => {
  const now = 1_000_000
  assert.equal(shouldReload(null, now), true)
  assert.equal(shouldReload(undefined, now), true)
  assert.equal(shouldReload('', now), true)
  assert.equal(shouldReload(now - 1_000, now), false)
  assert.equal(shouldReload(now - PROXY_RELOAD_MIN_MS + 1, now), false)
  assert.equal(shouldReload(now - PROXY_RELOAD_MIN_MS, now), true)
  assert.equal(shouldReload(String(now - 60_000), now), true)
})

test('um relogio que voltou nao trava a recarga', () => {
  assert.equal(shouldReload(2_000_000, 1_000_000), true)
})
