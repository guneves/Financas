// node --test src/lib   (npm test em frontend/)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  ACCOUNT_KINDS,
  NEEDS_ATTENTION,
  PENDING,
  applyPendingToAccounts,
  applyPendingToHome,
  buildItem,
  countByStatus,
  deliveredDiffers,
  editedItem,
  endpointFor,
  isEditableKind,
  itemAmount,
  itemDate,
  itemTitle,
  newClientId,
  outcomeOf,
  pendingAccountDeltas,
  pendingAsTransactions,
  sendOrder,
} from './outboxRules.js'

const item = (kind, payload, extra = {}) => ({
  client_id: `id-${Math.random()}`,
  kind,
  payload,
  status: PENDING,
  created_at: '2026-10-12T10:00:00.000Z',
  ...extra,
})

test('cada formulario tem a sua rota; transferencia nao vai para /api/transactions', () => {
  assert.equal(endpointFor('EXPENSE'), '/api/transactions')
  assert.equal(endpointFor('INCOME'), '/api/transactions')
  assert.equal(endpointFor('TRANSFER'), '/api/transfers')
  assert.equal(endpointFor('CARD'), '/api/cc-expenses/purchases')
  assert.equal(endpointFor('INVESTMENT'), '/api/investments')
  assert.equal(endpointFor('PROCEED'), '/api/investment-proceeds')
  assert.throws(() => endpointFor('BUY'))
})

test('operacao e provento pendentes: nao mexem em conta, nem no extrato, nem no Inicio', () => {
  const buy = item('INVESTMENT', { asset_class: 'STOCKS', ticker_or_name: 'PETR4', quantity: 10, average_price: 30.5, metadata: { purchase_date: '2026-10-12', cash_account_id: 'corretora' } })
  const proceed = item('PROCEED', { asset_id: 'a1', gross_amount: 80, payment_date: '2026-11-03' }, { title: 'CDB X' })
  assert.equal(pendingAccountDeltas([buy, proceed], { defaultAccountId: 'main' }).size, 0)
  assert.deepEqual(pendingAsTransactions([buy, proceed], { defaultAccountId: 'main' }), [])
  const home = { accounts: [{ id: 'main', balance: 100, balance_brl: 100, is_default: true }], consolidated_balance: 100, flow: [{ month: '2026-10', income: 0, expense: 0, invested: 0, redeemed: 0, others_paid: 0, others_received: 0, balance: 100 }] }
  assert.equal(applyPendingToHome(home, [buy, proceed]), home)
  // O aviso "Saldo estimado" conta so os que mexem em conta.
  assert.deepEqual(ACCOUNT_KINDS, ['EXPENSE', 'INCOME', 'TRANSFER'])
  assert.equal([buy, proceed].filter((entry) => ACCOUNT_KINDS.includes(entry.kind)).length, 0)
})

test('operacao e provento pendentes em Pendentes: titulo, valor e data; so se descartam', () => {
  const buy = item('INVESTMENT', { ticker_or_name: 'PETR4', quantity: 10, average_price: 30.5, metadata: { purchase_date: '2026-10-12' } })
  const sale = item('INVESTMENT', { ticker_or_name: 'BOVA11', quantity: -2, average_price: 100, metadata: { sale_date: '2026-10-13', sale_price: 120 } })
  const proceed = item('PROCEED', { asset_id: 'a1', gross_amount: 80, payment_date: '2026-11-03' }, { title: 'CDB X' })
  assert.deepEqual([buy, sale, proceed].map(itemTitle), ['PETR4', 'BOVA11', 'CDB X'])
  assert.deepEqual([buy, sale, proceed].map(itemAmount), [305, 240, 80])
  assert.deepEqual([buy, sale, proceed].map(itemDate), ['2026-10-12', '2026-10-13', '2026-11-03'])
  assert.equal(itemTitle(item('PROCEED', { gross_amount: 1 })), 'Provento')
  assert.equal(itemTitle(item('EXPENSE', { description: 'Pao' })), 'Pao')
  assert.deepEqual(['EXPENSE', 'INCOME', 'TRANSFER', 'CARD', 'INVESTMENT', 'PROCEED'].map(isEditableKind), [true, true, true, true, false, false])
  // Nunca editados na fila: o reenvio nao tem versao antiga para comparar.
  assert.equal(deliveredDiffers({ ...buy, edited: true }, [{ quantity: 1 }]), false)
})

test('o client_id tem o formato que o servidor aceita', () => {
  const pattern = /^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$/
  for (let i = 0; i < 50; i += 1) assert.match(newClientId(), pattern)
  assert.notEqual(newClientId(), newClientId())
})

test('o item leva o client_id dentro do payload, e mantem o que ja veio', () => {
  const built = buildItem({ kind: 'EXPENSE', payload: { amount: 10 }, userId: 'u1' })
  assert.equal(built.payload.client_id, built.client_id)
  assert.equal(built.status, PENDING)
  assert.equal(built.user_id, 'u1')

  const kept = buildItem({ kind: 'EXPENSE', payload: { amount: 10, client_id: 'ja-existia-123' } })
  assert.equal(kept.client_id, 'ja-existia-123')
})

test('item corrigido: mesmo client_id, de volta a pendente, marcado como editado', () => {
  const current = { ...item('EXPENSE', { amount: 10, client_id: 'abc12345' }), client_id: 'abc12345', user_id: 'u1', status: NEEDS_ATTENTION, last_error: 'Categoria nao encontrada.' }
  const next = editedItem(current, { kind: 'INCOME', payload: { amount: 12.5, client_id: 'outro-id-99' } })
  assert.equal(next.client_id, 'abc12345')
  assert.equal(next.payload.client_id, 'abc12345')
  assert.equal(next.payload.amount, 12.5)
  assert.equal(next.kind, 'INCOME')
  assert.equal(next.status, PENDING)
  assert.equal(next.last_error, '')
  assert.equal(next.edited, true)
  assert.equal(next.user_id, 'u1')
  assert.equal(next.created_at, current.created_at)
  assert.equal(editedItem(current, { payload: { amount: 1 } }).kind, 'EXPENSE')
  assert.throws(() => editedItem(current, { kind: 'BUY', payload: {} }))
})

test('resposta do envio: gravou sai, sem rede e 5xx esperam, 401 para, recusa pede atencao', () => {
  assert.equal(outcomeOf({ ok: true }), 'done')
  assert.equal(outcomeOf({ network: true }), 'retry')
  assert.equal(outcomeOf({ status: 500 }), 'retry')
  assert.equal(outcomeOf({ status: 503 }), 'retry')
  assert.equal(outcomeOf({ status: 401 }), 'stop')
  assert.equal(outcomeOf({ status: 400 }), 'attention')
  assert.equal(outcomeOf({ status: 409 }), 'attention')
  assert.equal(outcomeOf({ status: 404 }), 'attention')
  // Sem nada que diga que o servidor recebeu, o item nunca e descartado.
  assert.equal(outcomeOf({}), 'retry')
  assert.equal(outcomeOf(undefined), 'retry')
})

test('a fila sai na ordem em que foi lancada', () => {
  const late = item('EXPENSE', { amount: 1 }, { created_at: '2026-10-12T12:00:00.000Z', client_id: 'b' })
  const early = item('EXPENSE', { amount: 2 }, { created_at: '2026-10-12T09:00:00.000Z', client_id: 'a' })
  assert.deepEqual(sendOrder([late, early]).map((entry) => entry.client_id), ['a', 'b'])
})

test('despesa tira da conta, receita poe', () => {
  const deltas = pendingAccountDeltas([
    item('EXPENSE', { amount: 25.9, account_id: 'main' }),
    item('INCOME', { amount: 100, account_id: 'main' }),
    item('EXPENSE', { amount: 10, account_id: 'other' }),
  ])
  assert.equal(deltas.get('main'), 7410)
  assert.equal(deltas.get('other'), -1000)
})

test('transferencia mexe nas duas contas e deixa o consolidado onde estava', () => {
  const accounts = [
    { id: 'main', balance: 1000, is_default: true },
    { id: 'savings', balance: 50 },
  ]
  const result = applyPendingToAccounts(accounts, [
    item('TRANSFER', { amount: 300, account_id: 'main', transfer_account_id: 'savings' }),
  ])
  assert.equal(result[0].balance, 700)
  assert.equal(result[1].balance, 350)
  const total = (list) => list.reduce((acc, account) => acc + account.balance, 0)
  assert.equal(total(result), total(accounts))
})

test('compra no cartao pendente nao toca em nenhuma conta', () => {
  const accounts = [{ id: 'main', balance: 1000, is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('CARD', { total_amount: 900, installments: 3, card_id: 'c1' }),
  ])
  assert.equal(result, accounts)
})

test('lancamento sem conta cai na conta padrao, como no servidor', () => {
  const accounts = [{ id: 'a', balance: 10 }, { id: 'main', balance: 100, is_default: true }]
  const result = applyPendingToAccounts(accounts, [item('EXPENSE', { amount: 30 })])
  assert.equal(result[0].balance, 10)
  assert.equal(result[1].balance, 70)
  assert.equal(result[1].balance_estimated, true)
})

test('item recusado pelo servidor nao entra no saldo estimado', () => {
  const accounts = [{ id: 'main', balance: 100, is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('EXPENSE', { amount: 30, account_id: 'main' }, { status: NEEDS_ATTENTION }),
  ])
  assert.equal(result, accounts)
})

test('centavos nao se perdem na soma', () => {
  const accounts = [{ id: 'main', balance: 0.3, balance_brl: 0.3, currency: 'BRL', is_default: true }]
  const result = applyPendingToAccounts(accounts, [
    item('EXPENSE', { amount: 0.1, account_id: 'main' }),
    item('EXPENSE', { amount: 0.2, account_id: 'main' }),
  ])
  assert.equal(result[0].balance, 0)
  assert.equal(result[0].balance_brl, 0)
})

test('conta em moeda estrangeira: o saldo convertido nao e estimado sem cotacao', () => {
  const accounts = [{ id: 'usd', balance: 100, balance_brl: 550, currency: 'USD' }]
  const result = applyPendingToAccounts(accounts, [item('EXPENSE', { amount: 10, account_id: 'usd' })])
  assert.equal(result[0].balance, 90)
  assert.equal(result[0].balance_brl, 550)
})

test('sem pendentes a lista de contas volta a mesma (nada a recalcular)', () => {
  const accounts = [{ id: 'main', balance: 1 }]
  assert.equal(applyPendingToAccounts(accounts, []), accounts)
})

test('linhas do extrato: mais recente primeiro, sem a compra no cartao', () => {
  const rows = pendingAsTransactions([
    item('EXPENSE', { amount: 5, date: '2026-10-12', category: 'Mercado', description: 'Pao' }, { client_id: 'a', created_at: '2026-10-12T09:00:00.000Z' }),
    item('CARD', { total_amount: 90, purchase_date: '2026-10-12' }, { client_id: 'b', created_at: '2026-10-12T09:30:00.000Z' }),
    item('TRANSFER', { amount: 7, date: '2026-10-12', account_id: 'x', transfer_account_id: 'y' }, { client_id: 'c', created_at: '2026-10-12T10:00:00.000Z' }),
  ], { defaultAccountId: 'main' })
  assert.deepEqual(rows.map((row) => row.id), ['pending:c', 'pending:a'])
  assert.equal(rows[1].account_id, 'main')
  assert.equal(rows[0].type, 'TRANSFER')
  assert.equal(rows[0].transfer_account_id, 'y')
  assert.ok(rows.every((row) => row.pending))
})

test('item corrigido: o servidor devolver a versao antiga nao passa por entregue', () => {
  const edited = item('EXPENSE', { amount: 5, date: '2026-10-12', account_id: 'main' })
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), false)
  assert.equal(deliveredDiffers(edited, { amount: 50, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-11', type: 'EXPENSE', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'INCOME', account_id: 'main' }), true)
  assert.equal(deliveredDiffers(edited, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'other' }), true)
  // Sem conta no envio, o servidor escolheu a padrao: nao e diferenca.
  const noAccount = item('EXPENSE', { amount: 5, date: '2026-10-12' })
  assert.equal(deliveredDiffers(noAccount, { amount: 5, date: '2026-10-12', type: 'EXPENSE', account_id: 'main' }), false)

  const transfer = item('TRANSFER', { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'b' })
  assert.equal(deliveredDiffers(transfer, { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'b' }), false)
  assert.equal(deliveredDiffers(transfer, { amount: 7, date: '2026-10-12', account_id: 'a', transfer_account_id: 'c' }), true)

  const card = item('CARD', { total_amount: 100, installments: 3, purchase_date: '2026-10-12', card_id: 'c1' })
  const rows = [33.34, 33.33, 33.33].map((amount) => ({ amount, purchase_date: '2026-10-12', card_id: 'c1' }))
  assert.equal(deliveredDiffers(card, rows), false)
  assert.equal(deliveredDiffers(card, rows.slice(0, 2)), true)
  assert.equal(deliveredDiffers({ ...card, payload: { ...card.payload, total_amount: 90 } }, rows), true)
})

test('contagem por estado', () => {
  assert.deepEqual(
    countByStatus([item('EXPENSE', {}), item('EXPENSE', {}), item('EXPENSE', {}, { status: NEEDS_ATTENTION })]),
    { [PENDING]: 2, [NEEDS_ATTENTION]: 1 }
  )
})

// /api/home com os pendentes por cima (proposta home-attention-invoices.md, B1).
const homeAccounts = [
  { id: 'banco', type: 'CHECKING', currency: 'BRL', is_default: true, balance: 1000, balance_brl: 1000 },
  { id: 'poupanca', type: 'SAVINGS', currency: 'BRL', balance: 500, balance_brl: 500 },
  { id: 'corretora', type: 'BROKERAGE', currency: 'BRL', balance: 7000, balance_brl: 7000 },
  { id: 'dolar', type: 'CHECKING', currency: 'USD', balance: 10, balance_brl: 50 },
]
const flowMonth = (month, balance, extra = {}) => ({
  month, income: 0, expense: 0, invested: 0, redeemed: 0, others_paid: 0, others_received: 0, net: 0, balance, ...extra,
})
const home = () => ({
  today: '2026-10-20',
  month: '2026-10',
  consolidated_balance: 1550,
  accounts: homeAccounts,
  summary: { income: 100, expense: 40, result: 60, invested: 0, redeemed: 0, investment_net: 0, others_paid: 0, others_received: 0, others_net: 0 },
  flow: [flowMonth('2026-09', 1490), flowMonth('2026-10', 1550, { income: 100, expense: 40, net: 60 })],
})

test('home: sem pendentes volta o mesmo objeto', () => {
  const base = home()
  assert.equal(applyPendingToHome(base, []), base)
  assert.equal(applyPendingToHome(base, [item('CARD', { total_amount: 90, purchase_date: '2026-10-12' })]), base)
  assert.equal(applyPendingToHome(base, [item('EXPENSE', { amount: 5, date: '2026-10-12' }, { status: NEEDS_ATTENTION })]), base)
})

test('home: despesa pendente baixa a conta, o saldo em contas e entra no Saiu do mes', () => {
  const result = applyPendingToHome(home(), [item('EXPENSE', { amount: 0.1, date: '2026-10-12' }), item('EXPENSE', { amount: 0.2, date: '2026-10-13' })])
  assert.equal(result.consolidated_balance, 1549.7)
  assert.equal(result.accounts.find((account) => account.id === 'banco').balance, 999.7)
  assert.equal(result.summary.expense, 40.3)
  assert.equal(result.summary.result, 59.7)
  assert.equal(result.flow[1].net, 59.7)
  assert.equal(result.flow[1].balance, 1549.7)
  assert.equal(result.flow[0].balance, 1490)
  assert.equal(result.balance_estimated, true)
})

test('home: receita entra inteira; "Pagamento Fatura" mexe no saldo, nao no Saiu', () => {
  const result = applyPendingToHome(home(), [
    item('INCOME', { amount: 30, date: '2026-10-12', account_id: 'poupanca' }),
    item('EXPENSE', { amount: 20, date: '2026-10-12', category: 'Pagamento Fatura Nubank' }),
  ])
  assert.equal(result.summary.income, 130)
  assert.equal(result.summary.expense, 40)
  assert.equal(result.consolidated_balance, 1560)
  assert.equal(result.flow[1].balance, 1560)
})

test('home: transferencia para a Corretora e aporte, de volta resgate, entre bancos nada', () => {
  const result = applyPendingToHome(home(), [
    item('TRANSFER', { amount: 300, date: '2026-10-12', account_id: 'banco', transfer_account_id: 'corretora' }),
    item('TRANSFER', { amount: 100, date: '2026-10-13', account_id: 'corretora', transfer_account_id: 'poupanca' }),
    item('TRANSFER', { amount: 50, date: '2026-10-14', account_id: 'banco', transfer_account_id: 'poupanca' }),
  ])
  assert.deepEqual([result.summary.invested, result.summary.redeemed, result.summary.investment_net], [300, 100, 200])
  assert.equal(result.summary.expense, 40)
  assert.equal(result.consolidated_balance, 1350)
  assert.equal(result.flow[1].balance, 1350)
})

test('home: linha numa Corretora fica de fora; conta em dolar nao muda o saldo em contas', () => {
  const result = applyPendingToHome(home(), [
    item('EXPENSE', { amount: 70, date: '2026-10-12', account_id: 'corretora' }),
    item('EXPENSE', { amount: 3, date: '2026-10-12', account_id: 'dolar' }),
  ])
  assert.equal(result.summary.expense, 43)
  assert.equal(result.consolidated_balance, 1550)
  assert.equal(result.accounts.find((account) => account.id === 'corretora').balance, 6930)
})

test('home: pendente de um mes anterior muda aquele mes e o saldo dali em diante', () => {
  const result = applyPendingToHome(home(), [
    item('EXPENSE', { amount: 10, date: '2026-09-30' }),
    item('INCOME', { amount: 1, date: '2026-08-01' }),
    item('EXPENSE', { amount: 99, date: '2026-11-01' }),
  ])
  assert.equal(result.flow[0].expense, 10)
  assert.equal(result.flow[0].balance, 1481)
  assert.equal(result.flow[1].expense, 40)
  assert.equal(result.flow[1].balance, 1541)
  assert.equal(result.consolidated_balance, 1442)
})
