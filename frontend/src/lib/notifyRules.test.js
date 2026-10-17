import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  ADB_TEST_COMMAND,
  accessMessage,
  appRows,
  captureMessage,
  countLabel,
  formatStamp,
  installerLabel,
  listenerMessage,
  showsRestrictedHelp,
} from './notifyRules.js'

const at = (h, m, s = 0) => new Date(2026, 9, 17, h, m, s).getTime()

test('hora local, com segundos quando pedido', () => {
  assert.equal(formatStamp(at(8, 5, 9)), '17/10/2026 08:05')
  assert.equal(formatStamp(at(8, 5, 9), { seconds: true }), '17/10/2026 08:05:09')
  assert.equal(formatStamp(0), '')
})

test('contagem no singular e no plural', () => {
  assert.equal(countLabel(0), 'nenhuma')
  assert.equal(countLabel(1), '1 notificação')
  assert.equal(countLabel(12), '12 notificações')
})

test('acesso permitido ou nao', () => {
  assert.equal(accessMessage({ granted: true }).tone, 'success')
  assert.equal(accessMessage({ granted: false }).tone, 'warning')
  assert.equal(accessMessage(null), null)
})

test('o leitor: ligado, desligado depois de ligar, ou nunca ligado', () => {
  assert.equal(listenerMessage({ granted: false, connectedAt: at(8, 0) }), null)
  assert.match(listenerMessage({ granted: true, connectedAt: at(9, 0), disconnectedAt: at(8, 0) }), /ligado pelo Android em 17\/10\/2026 09:00/)
  assert.match(listenerMessage({ granted: true, connectedAt: at(8, 0), disconnectedAt: at(9, 0) }), /desligou o leitor em 17\/10\/2026 09:00/)
  assert.match(listenerMessage({ granted: true, connectedAt: 0, disconnectedAt: 0 }), /ainda não ligou/)
})

test('configuracoes restritas: so sem acesso e a partir do Android 13', () => {
  assert.equal(showsRestrictedHelp({ granted: false, sdk: 33 }), true)
  assert.equal(showsRestrictedHelp({ granted: false, sdk: 36 }), true)
  assert.equal(showsRestrictedHelp({ granted: false, sdk: 32 }), false)
  assert.equal(showsRestrictedHelp({ granted: true, sdk: 36 }), false)
  assert.equal(showsRestrictedHelp(null), false)
})

test('quem instalou o APK, em palavras', () => {
  assert.match(installerLabel('com.android.shell'), /adb/)
  assert.match(installerLabel('br.financas.app'), /próprio app/)
  assert.match(installerLabel('com.google.android.packageinstaller'), /arquivo APK/)
  assert.equal(installerLabel('com.outra.loja'), 'com.outra.loja')
  assert.equal(installerLabel(null), 'desconhecido')
})

test('o resumo da captura', () => {
  assert.equal(captureMessage({ captureOn: false, total: 0 }), 'Desligada: nenhuma notificação é guardada.')
  assert.match(captureMessage({ captureOn: false, total: 1 }), /^Desligada\. 1 notificação guardada continua aqui/)
  assert.match(captureMessage({ captureOn: false, total: 3 }), /3 notificações guardadas continuam aqui/)
  assert.equal(captureMessage({ captureOn: true, captureSince: at(8, 0), total: 0 }), 'Ligada desde 17/10/2026 08:00. Nada chegou ainda dos apps abaixo.')
  assert.equal(captureMessage({ captureOn: true, captureSince: at(8, 0), total: 2 }), 'Ligada desde 17/10/2026 08:00: 2 notificações guardadas.')
  assert.equal(captureMessage(null), '')
})

test('a lista de apps: o adb so quando guardou algo', () => {
  const rows = appRows({
    apps: [
      { package: 'com.samsung.android.spay', label: 'Samsung Wallet', installed: true, count: 2, lastPostedAt: at(14, 30) },
      { package: 'com.itaucard.activity', label: 'Itaú Cartões', installed: false, count: 0, lastPostedAt: 0 },
      { package: 'com.itau', label: 'Itaú', installed: true, count: 0, lastPostedAt: 0 },
      { package: 'com.android.shell', label: 'Teste (adb)', installed: true, count: 0, lastPostedAt: 0 },
    ],
  })
  assert.deepEqual(rows.map((row) => row.package), ['com.samsung.android.spay', 'com.itaucard.activity', 'com.itau'])
  assert.equal(rows[0].detail, '2 notificações · última 17/10/2026 14:30')
  assert.equal(rows[1].detail, 'não instalado')
  assert.equal(rows[2].detail, 'nada ainda')
  const withShell = appRows({ apps: [{ package: 'com.android.shell', label: 'Teste (adb)', installed: true, count: 1, lastPostedAt: at(9, 0) }] })
  assert.equal(withShell.length, 1)
  assert.deepEqual(appRows(null), [])
})

test('o comando de teste usa o caminho do plano (bigtext, titulo, tag, texto)', () => {
  assert.match(ADB_TEST_COMMAND, /^adb shell cmd notification post -S bigtext -t "[^"]+" \S+ "[^"]+"$/)
})
