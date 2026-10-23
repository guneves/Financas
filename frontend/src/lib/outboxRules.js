// Port: mudou um, muda o outro, com um teste de cada lado. O par nativo e
// frontend/android/.../outbox/OutboxRules.java (OutboxRulesTest): endpointFor,
// newClientId, buildItem, editedItem, outcomeOf, deliveredDiffers. O saldo com
// pendentes (pendingAccountDeltas, applyPendingToAccounts, pendingAsTransactions,
// applyPendingToHome, countByStatus e o sendOrder/toCents que usam) tem outro par:
// frontend/android/.../rules/OutboxPending.kt (OutboxPendingTest).
//
// As regras da fila de envio (lib/outbox.js), como funcoes puras: nada aqui
// toca em rede, IndexedDB ou React, entao os testes rodam com `node --test`
// (outboxRules.test.js) e o APK reaproveita as mesmas regras com a fila nativa.
//
// Um item da fila: { client_id, user_id, kind, payload, status, last_error,
// created_at }. O `payload` e exatamente o corpo que a rota recebe, ja com o
// client_id — e ele que faz a segunda entrega nao virar um segundo lancamento
// (migration 024).

export const PENDING = 'pending'
export const NEEDS_ATTENTION = 'needs_attention'

// Os quatro formularios do "+ Novo" e a rota de cada um.
const ENDPOINTS = {
  EXPENSE: '/api/transactions',
  INCOME: '/api/transactions',
  TRANSFER: '/api/transfers',
  CARD: '/api/cc-expenses/purchases',
}

export const ENTRY_KINDS = Object.keys(ENDPOINTS)

export function endpointFor(kind) {
  const endpoint = ENDPOINTS[kind]
  if (!endpoint) throw new Error(`Tipo de lancamento desconhecido: ${kind}`)
  return endpoint
}

export function newClientId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  // Origem sem contexto seguro (http fora do localhost): mesmo formato, a mao.
  const bytes = new Uint8Array(16)
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes)
  else bytes.forEach((_, index) => { bytes[index] = Math.floor(Math.random() * 256) })
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
}

export function buildItem({ kind, payload, userId, now = new Date() }) {
  endpointFor(kind)
  const clientId = payload?.client_id || newClientId()
  return {
    client_id: clientId,
    user_id: userId || '',
    kind,
    payload: { ...payload, client_id: clientId },
    status: PENDING,
    last_error: '',
    created_at: now.toISOString(),
  }
}

// Um item da fila corrigido (Pendentes › Corrigir): o mesmo client_id, de
// volta a pendente. O id continua o mesmo (trocar duplicaria um envio que ja
// chegou), entao o envio precisa conferir se o servidor ficou com esta versao:
// `edited` liga o deliveredDiffers().
export function editedItem(current, { kind, payload }) {
  const next = {
    ...current,
    kind: kind || current.kind,
    payload: { ...payload, client_id: current.client_id },
    status: PENDING,
    last_error: '',
    edited: true,
  }
  endpointFor(next.kind)
  return next
}

// O que uma tentativa de envio faz com o item.
//   done      — o servidor gravou (201) ou ja tinha gravado (200): sai da fila.
//   retry     — nao chegou, ou o servidor caiu (5xx): fica pendente, a rodada para.
//   stop      — 401: fica tudo como esta ate o dono entrar de novo.
//   attention — o servidor recusou (400, 409...): precisa do dono; os proximos seguem.
export function outcomeOf(result) {
  if (result?.ok) return 'done'
  if (result?.network) return 'retry'
  const status = Number(result?.status) || 0
  if (status === 401) return 'stop'
  if (status >= 500 || status === 408 || status === 429 || status === 0) return 'retry'
  return 'attention'
}

export const ALREADY_DELIVERED_MESSAGE =
  'Este lançamento já tinha chegado ao servidor antes da correção, com os valores antigos. Corrija-o na tela de lançamentos e descarte este pendente.'

// Um item corrigido na fila guarda o mesmo client_id. Se a primeira tentativa
// tinha chegado ao servidor (a resposta e que se perdeu), o reenvio devolve o
// lancamento antigo e ignora a correcao. Aqui se compara o que o servidor
// devolveu com o que o item pede: valor e data, em centavos.
export function deliveredDiffers(item, data) {
  if (!data) return false
  if (item.kind === 'CARD') {
    const rows = Array.isArray(data) ? data : []
    if (!rows.length) return false
    const total = rows.reduce((acc, row) => acc + toCents(row.amount), 0)
    return total !== toCents(item.payload.total_amount)
      || rows.length !== Number(item.payload.installments)
      || rows[0].purchase_date !== item.payload.purchase_date
      || rows[0].card_id !== item.payload.card_id
  }
  if (toCents(data.amount) !== toCents(item.payload.amount) || data.date !== item.payload.date) return true
  if (item.kind === 'TRANSFER') {
    return data.account_id !== item.payload.account_id || data.transfer_account_id !== item.payload.transfer_account_id
  }
  return data.type !== item.kind || (Boolean(item.payload.account_id) && data.account_id !== item.payload.account_id)
}

// Ordem de envio: a ordem em que foram lancados.
export function sendOrder(items) {
  return [...items].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
}

function toCents(value) {
  // Centavos inteiros: somar reais em ponto flutuante desalinha o saldo estimado.
  return Math.round(Number(value) * 100)
}

const amountOf = (item) => {
  const value = Number(item.kind === 'CARD' ? item.payload?.total_amount : item.payload?.amount)
  return Number.isFinite(value) ? value : 0
}

// Quanto cada conta muda quando os itens pendentes chegarem ao servidor, em
// centavos. Despesa sai, receita entra, transferencia sai de uma e entra na
// outra (o consolidado nao muda). Compra no cartao nao toca em conta: vira
// fatura. Item recusado (needs_attention) nao conta — do jeito que esta, ele
// nao vai ser gravado.
export function pendingAccountDeltas(items, { defaultAccountId = '' } = {}) {
  const deltas = new Map()
  const add = (accountId, cents) => {
    if (!accountId || !cents) return
    deltas.set(accountId, (deltas.get(accountId) || 0) + cents)
  }
  items.forEach((item) => {
    if (item.status !== PENDING) return
    const cents = toCents(amountOf(item))
    if (cents <= 0) return
    if (item.kind === 'EXPENSE') add(item.payload.account_id || defaultAccountId, -cents)
    else if (item.kind === 'INCOME') add(item.payload.account_id || defaultAccountId, cents)
    else if (item.kind === 'TRANSFER') {
      add(item.payload.account_id, -cents)
      add(item.payload.transfer_account_id, cents)
    }
  })
  return deltas
}

// As contas com o saldo ja contando os pendentes. `balance_brl` (o saldo
// convertido de uma conta em moeda estrangeira) so e ajustado quando a conta
// e em reais: sem a cotacao, o valor pendente nao tem como ser convertido aqui.
export function applyPendingToAccounts(accounts = [], items = []) {
  if (!items.length) return accounts
  const defaultAccountId = accounts.find((account) => account.is_default)?.id || ''
  const deltas = pendingAccountDeltas(items, { defaultAccountId })
  if (!deltas.size) return accounts
  return accounts.map((account) => {
    const cents = deltas.get(account.id)
    if (!cents) return account
    const next = { ...account, balance: (toCents(account.balance) + cents) / 100, balance_estimated: true }
    const inReais = !account.currency || account.currency === 'BRL'
    if (inReais && account.balance_brl !== undefined && account.balance_brl !== null) {
      next.balance_brl = (toCents(account.balance_brl) + cents) / 100
    }
    return next
  })
}

// Os pendentes como linhas do extrato (a compra no cartao nao e linha de
// extrato). Recusados aparecem tambem: o dono precisa ve-los para resolver.
export function pendingAsTransactions(items = [], { defaultAccountId = '' } = {}) {
  return sendOrder(items)
    .filter((item) => item.kind !== 'CARD')
    .map((item) => ({
      id: `pending:${item.client_id}`,
      client_id: item.client_id,
      pending: true,
      pending_status: item.status,
      amount: amountOf(item),
      date: item.payload.date,
      category: item.payload.category || (item.kind === 'TRANSFER' ? 'Transferência' : ''),
      description: item.payload.description || '',
      type: item.kind,
      account_id: item.payload.account_id || defaultAccountId || null,
      transfer_account_id: item.kind === 'TRANSFER' ? item.payload.transfer_account_id : null,
      source_type: null,
      created_at: item.created_at,
    }))
    .reverse()
}

// GET /api/home com os pendentes por cima. O servidor nao ve a fila do
// aparelho; sem isto uma despesa guardada offline baixaria a conta mas nao o
// "Saiu" do mes. E o bankingTransactions() + buildMonthlyFlow() de antes,
// restrito aos pendentes, em centavos:
//   - as contas: applyPendingToAccounts();
//   - o saldo em contas: + o que muda nas contas em reais que nao sao Corretora;
//   - cada mes do fluxo: despesa/receita inteira (um pendente nunca e
//     dividido; "Pagamento Fatura..." nao e despesa), transferencia banco ->
//     Corretora e aporte, Corretora -> banco resgate, banco -> banco nada;
//     linha numa Corretora fica de fora; compra no cartao nao entra;
//   - o saldo de fim de mes anda do mes do pendente em diante;
//   - `summary` e o ultimo mes de novo.
export function applyPendingToHome(home, items = []) {
  const waiting = items.filter((item) => item.status === PENDING && item.kind !== 'CARD')
  if (!home || !waiting.length) return home
  const accounts = home.accounts || []
  const defaultAccountId = accounts.find((account) => account.is_default)?.id || ''
  const isPortfolio = (id) => accounts.some((account) => account.id === id && account.type === 'BROKERAGE')

  const nextAccounts = applyPendingToAccounts(accounts, waiting)
  const deltas = pendingAccountDeltas(waiting, { defaultAccountId })
  let consolidated = toCents(home.consolidated_balance)
  accounts.forEach((account) => {
    const cents = deltas.get(account.id)
    const inReais = !account.currency || account.currency === 'BRL'
    if (cents && inReais && account.type !== 'BROKERAGE' && account.balance_brl !== null && account.balance_brl !== undefined) {
      consolidated += cents
    }
  })

  const months = (home.flow || []).map((month) => ({
    month: month.month,
    income: toCents(month.income),
    expense: toCents(month.expense),
    invested: toCents(month.invested),
    redeemed: toCents(month.redeemed),
    others_paid: toCents(month.others_paid),
    others_received: toCents(month.others_received),
    balance: toCents(month.balance),
  }))
  waiting.forEach((item) => {
    const cents = toCents(amountOf(item))
    if (cents <= 0) return
    const key = String(item.payload?.date || '').slice(0, 7)
    let field = null
    let cash = 0
    if (item.kind === 'TRANSFER') {
      const fromPortfolio = isPortfolio(item.payload.account_id)
      const toPortfolio = isPortfolio(item.payload.transfer_account_id)
      if (fromPortfolio === toPortfolio) return
      field = toPortfolio ? 'invested' : 'redeemed'
      cash = toPortfolio ? -cents : cents
    } else {
      if (isPortfolio(item.payload.account_id || defaultAccountId)) return
      cash = item.kind === 'INCOME' ? cents : -cents
      const invoicePayment = String(item.payload.category || '').startsWith('Pagamento Fatura')
      field = item.kind === 'INCOME' ? 'income' : invoicePayment ? null : 'expense'
    }
    months.forEach((month) => {
      if (month.month === key && field) month[field] += cents
      if (month.month >= key) month.balance += cash
    })
  })

  const flow = months.map((month) => ({
    month: month.month,
    income: month.income / 100,
    expense: month.expense / 100,
    invested: month.invested / 100,
    redeemed: month.redeemed / 100,
    others_paid: month.others_paid / 100,
    others_received: month.others_received / 100,
    net: (month.income - month.expense - month.invested + month.redeemed + month.others_received - month.others_paid) / 100,
    balance: month.balance / 100,
  }))
  const last = months[months.length - 1]
  const summary = last ? {
    income: last.income / 100,
    expense: last.expense / 100,
    result: (last.income - last.expense) / 100,
    invested: last.invested / 100,
    redeemed: last.redeemed / 100,
    investment_net: (last.invested - last.redeemed) / 100,
    others_paid: last.others_paid / 100,
    others_received: last.others_received / 100,
    others_net: (last.others_received - last.others_paid) / 100,
  } : home.summary
  return {
    ...home,
    accounts: nextAccounts,
    consolidated_balance: consolidated / 100,
    flow,
    summary,
    balance_estimated: nextAccounts !== accounts,
  }
}

export function countByStatus(items = []) {
  return items.reduce(
    (acc, item) => ({ ...acc, [item.status]: (acc[item.status] || 0) + 1 }),
    { [PENDING]: 0, [NEEDS_ATTENTION]: 0 }
  )
}

export const KIND_LABELS = {
  EXPENSE: 'Despesa',
  INCOME: 'Receita',
  TRANSFER: 'Transferência',
  CARD: 'Compra no cartão',
}

export function itemAmount(item) {
  return amountOf(item)
}

export function itemDate(item) {
  return item.kind === 'CARD' ? item.payload?.purchase_date : item.payload?.date
}
