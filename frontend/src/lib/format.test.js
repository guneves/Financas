// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { maskEmail } from './format.js'

test('maskEmail mostra so algumas letras do e-mail', () => {
  assert.equal(maskEmail('fulano@gmail.com'), 'fu•••@g•••.com')
  assert.equal(maskEmail('ab@empresa.com.br'), 'a•••@e•••.com.br')
  assert.equal(maskEmail('x@host'), 'x•••@h•••')
})

test('maskEmail nunca devolve o e-mail inteiro, nem quebra sem um', () => {
  assert.equal(maskEmail(''), '')
  assert.equal(maskEmail(null), '')
  assert.equal(maskEmail('semarroba'), 'se•••')
})
