// Porte: mudou um, muda o outro, com um teste de cada lado (par nativo:
// android/app/src/main/java/br/financas/app/rules/InvestmentStatement.kt e
// InvestmentStatementTest.kt, os mesmos casos).
//
// Extrato de investimentos: operacoes e proventos numa lista so, do mais novo
// para o mais antigo, agrupada por dia — o mesmo formato do extrato das contas.
// Funcoes puras (testadas em investmentStatement.test.js): nada de navegador,
// React ou lib/api.js aqui.
//
// O sinal e o do dinheiro do investidor: compra/aporte sai (−), venda,
// resgate e provento entram (+). Bonificacao nao mexe em dinheiro (0).
// Nada disto e lancamento bancario: o saldo das contas nao muda por aqui.

const PROCEED_LABELS = { DIVIDEND: 'Dividendo', JCP: 'JCP', AMORTIZATION: 'Amortização', INTEREST: 'Juros' }

function day(value) {
  return String(value || '').slice(0, 10)
}

function movementDate(movement) {
  const meta = movement.metadata || {}
  return day(meta.redemption_date || meta.sale_date || meta.purchase_date || movement.created_at)
}

function unitPrice(movement) {
  const meta = movement.metadata || {}
  if (meta.is_redemption) return Number(movement.current_price || 0)
  if (Number(movement.quantity) < 0 && meta.sale_price) return Number(meta.sale_price || 0)
  return Number(movement.average_price || 0)
}

function fees(movement) {
  return Number(movement.realized_fee_amount ?? movement.fee_amount ?? movement.metadata?.other_costs ?? 0) || 0
}

export function movementEntry(movement) {
  const meta = movement.metadata || {}
  const isFixed = movement.asset_class === 'FIXED_INCOME'
  const isSale = Number(movement.quantity) < 0
  const isBonus = Boolean(meta.corporate_action_id)
  const quantity = Math.abs(Number(movement.quantity || 0))
  const gross = quantity * unitPrice(movement)
  const cost = fees(movement)
  let amount
  if (isBonus) amount = 0
  else if (isSale) {
    const net = movement.realized_net_proceeds
    amount = net !== null && net !== undefined ? Number(net) : Math.max(gross - cost, 0)
  } else amount = -(gross + cost)

  const kind = isBonus ? 'Bonificação' : isFixed ? (isSale ? 'Resgate' : 'Aporte') : (isSale ? 'Venda' : 'Compra')
  return {
    id: `mov:${movement.id}`,
    source: 'movement',
    movementId: movement.id,
    // Bonificacao so sai desfazendo o evento (o servidor recusa, 409).
    deletable: !isBonus,
    date: movementDate(movement),
    title: movement.ticker_or_name || '',
    kind,
    quantity: isFixed ? null : quantity,
    unitPrice: isFixed ? null : unitPrice(movement),
    amount,
    scheduled: false,
    inStatement: Boolean(meta.cash_account_id),
  }
}

export function proceedEntry(proceed, today) {
  const date = day(proceed.payment_date)
  return {
    id: `prov:${proceed.id}`,
    source: 'proceed',
    date,
    title: proceed.asset?.ticker || proceed.asset?.name || '',
    kind: PROCEED_LABELS[proceed.proceeds_type] || proceed.proceeds_type,
    quantity: Number(proceed.eligible_quantity || 0) || null,
    unitPrice: proceed.amount_per_unit === null || proceed.amount_per_unit === undefined ? null : Number(proceed.amount_per_unit),
    amount: Number(proceed.net_amount || 0),
    tax: Number(proceed.tax_amount || 0),
    scheduled: Boolean(today) && date > today,
    automatic: Boolean(proceed.sync_key),
  }
}

export const STATEMENT_KINDS = ['ALL', 'MOVEMENTS', 'PROCEEDS']

export function buildInvestmentStatement(movements = [], proceeds = [], { today = '', kind = 'ALL', query = '' } = {}) {
  const entries = []
  if (kind !== 'PROCEEDS') movements.forEach((movement) => entries.push(movementEntry(movement)))
  if (kind !== 'MOVEMENTS') proceeds.forEach((proceed) => entries.push(proceedEntry(proceed, today)))
  const needle = String(query || '').trim().toLowerCase()
  const visible = needle
    ? entries.filter((entry) => `${entry.title} ${entry.kind}`.toLowerCase().includes(needle))
    : entries
  // Mais novo primeiro; no mesmo dia, operacoes antes de proventos.
  return visible.sort((a, b) => (
    a.date === b.date ? a.source.localeCompare(b.source) : (a.date < b.date ? 1 : -1)
  ))
}

export function statementTotals(entries) {
  return entries.reduce((acc, entry) => {
    if (entry.scheduled) acc.scheduled += entry.amount
    else if (entry.source === 'proceed') acc.proceeds += entry.amount
    else if (entry.amount < 0) acc.invested += -entry.amount
    else acc.withdrawn += entry.amount
    return acc
  }, { invested: 0, withdrawn: 0, proceeds: 0, scheduled: 0 })
}

// Dias em ordem; o total do dia ignora o agendado (ainda nao entrou).
export function groupEntriesByDay(entries) {
  const groups = []
  entries.forEach((entry) => {
    let group = groups[groups.length - 1]
    if (!group || group.date !== entry.date) {
      group = { date: entry.date, items: [], total: 0 }
      groups.push(group)
    }
    group.items.push(entry)
    if (!entry.scheduled) group.total += entry.amount
  })
  return groups
}
