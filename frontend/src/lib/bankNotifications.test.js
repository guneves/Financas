import test from 'node:test'
import assert from 'node:assert/strict'
import { bankNotificationsOn, bankNotificationsToast } from './bankNotifications.js'

test('ligado por padrao, tambem quando o servidor antigo nao manda o campo', () => {
  assert.equal(bankNotificationsOn(undefined), true)
  assert.equal(bankNotificationsOn({}), true)
  assert.equal(bankNotificationsOn({ bank_notifications: null }), true)
  assert.equal(bankNotificationsOn({ bank_notifications: true }), true)
})

test('desligado so quando o servidor diz false', () => {
  assert.equal(bankNotificationsOn({ bank_notifications: false }), false)
  assert.equal(bankNotificationsOn({ bank_notifications: 'false' }), false)
})

test('o aviso de cada lado', () => {
  assert.match(bankNotificationsToast(true), /gravam na hora/)
  assert.match(bankNotificationsToast(false), /Só o Flash/)
})
