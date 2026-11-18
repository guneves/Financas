import test from 'node:test'
import assert from 'node:assert/strict'
import {
  canUndo, decisionDetail, decisionTitle, reviewAutoDays, reviewAutoToast, reviewDayItems, undoToast,
} from './autoDecisions.js'

test('o prazo do Revisar: o do servidor, 3 quando um servidor antigo nao manda', () => {
  assert.equal(reviewAutoDays(undefined), 3)
  assert.equal(reviewAutoDays({}), 3)
  assert.equal(reviewAutoDays({ review_auto_days: 0 }), 0)
  assert.equal(reviewAutoDays({ review_auto_days: 7 }), 7)
  assert.equal(reviewAutoDays({ review_auto_days: '7' }), 3)
})

test('as escolhas incluem o prazo atual mesmo fora da lista', () => {
  assert.deepEqual(reviewDayItems(3).map((item) => item.value), [0, 3, 7, 14])
  assert.deepEqual(reviewDayItems(5).map((item) => item.value), [0, 3, 5, 7, 14])
  assert.equal(reviewDayItems(0)[0].label, 'Nunca')
  assert.match(reviewAutoToast(0), /espera/)
  assert.match(reviewAutoToast(3), /3 dias/)
})

test('o texto de cada decisao', () => {
  assert.equal(decisionTitle({ kind: 'pluggy_category' }), 'Categoria da Pluggy')
  assert.equal(decisionTitle({ kind: 'nova' }), 'Decisão automática')
  assert.equal(decisionDetail({ kind: 'pluggy_category', detail: { before: ['Outros', 'a'], after: ['Alimentação', 'b'] } }),
    'Outros → Alimentação')
  assert.equal(decisionDetail({ kind: 'auto_confirm', detail: { category: ['Lazer', 'x'] } }), 'Ficou em Lazer')
  assert.match(decisionDetail({ kind: 'conflict_changed', detail: { before_cents: 4590, after_cents: 4990 } }), /45,90.*49,90/)
  assert.equal(decisionDetail({ kind: 'fx_fallback', detail: { rate_date: '2026-10-09' } }), 'PTAX de 09/10/2026')
  assert.equal(decisionDetail({ kind: 'auto_confirm' }), '')
})

test('desfazer: so a que nao foi desfeita, e o aviso de cada uma', () => {
  assert.equal(canUndo({ id: 'a' }), true)
  assert.equal(canUndo({ id: 'a', undone_at: '2026-11-18' }), false)
  assert.match(undoToast({ kind: 'auto_confirm' }), /Revisar/)
  assert.match(undoToast({ kind: 'conflict_vanished' }), /voltou/)
})
