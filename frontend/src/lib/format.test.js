// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { formatQuantity, localDateOfTimestamp, maskEmail } from './format.js'

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
  assert.equal(formatQuantity(1 / 3), '0,33333333')
  assert.equal(formatQuantity(0.00012345), '0,00012345')
  assert.equal(formatQuantity(-5), '−5')
  assert.equal(formatQuantity(null), '0')
})

test('localDateOfTimestamp le um instante UTC no dia local', () => {
  const previous = process.env.TZ
  process.env.TZ = 'America/Sao_Paulo'
  try {
    // 22h30 de 22/10 em Brasilia e 01h30 de 23/10 em UTC: o dia e 22.
    assert.equal(localDateOfTimestamp('2026-10-23T01:30:00.123456Z'), '2026-10-22')
    assert.equal(localDateOfTimestamp('2026-10-23T15:00:00Z'), '2026-10-23')
    assert.equal(localDateOfTimestamp(''), '')
    assert.equal(localDateOfTimestamp('lixo'), '')
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
})
