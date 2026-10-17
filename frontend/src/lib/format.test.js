// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatQuantity, maskEmail } from './format.js'

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

test('formatQuantity usa os separadores do pt-BR', () => {
  assert.equal(formatQuantity(1022), '1.022')
  assert.equal(formatQuantity(62.7), '62,7')
  assert.equal(formatQuantity(0.3333333), '0,333333')
  assert.equal(formatQuantity(-5), '−5')
  assert.equal(formatQuantity(null), '0')
})
