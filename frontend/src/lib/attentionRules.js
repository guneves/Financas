// "Precisa de atencao": as regras de cada aviso, sem React nem navegador, para
// o Inicio (os cartoes) e o sino do cabecalho (a lista) dizerem o mesmo.
//
// Cada aviso tem uma `key` que identifica o caso, nao o tipo: dispensar a
// "fatura vencida de outubro do Nubank" nao esconde a de novembro. O Inicio
// esconde os dispensados; o sino mostra todos enquanto valerem.
import { formatDateBR } from './format.js'
import { accountBalanceBrl, cardSignedAmount, isPortfolioAccount } from './transactions.js'

// Estorno (033) abate: toda soma de compras do cartao passa pelo sinal.
const amountOf = cardSignedAmount
const invoiceId = (invoice) => `${invoice.card_id}|${invoice.invoice_year}-${invoice.invoice_month}`

// O mes da fatura (AAAA-MM), que e o mes do vencimento.
export function invoiceMonthKey(invoice) {
  return `${invoice.invoice_year}-${String(invoice.invoice_month).padStart(2, '0')}`
}

export function openCardExpenses(ccExpenses = []) {
  return ccExpenses.filter((expense) => expense.status === 'OPEN')
}

// Mesma conta da tela Recorrentes: soma do pending_count de cada recorrencia.
export function pendingRecurringCount(recurringItems = []) {
  return recurringItems.reduce((total, item) => total + Number(item.pending_count || 0), 0)
}

// Vencida so depois do dia do vencimento: no proprio dia ainda se paga em dia.
export function isPastDue(dueDateText, todayText) {
  return Boolean(dueDateText) && dueDateText < todayText
}

// A proxima fatura de cada cartao: a em aberto que vence primeiro, de hoje em
// diante (a que ja venceu e o aviso de vencida). Nao e "a fatura do mes que
// vem": um cartao que fecha antes de vencer (fecha 3, vence 10) paga em
// novembro a fatura de novembro, e um que fecha depois (fecha 25, vence 5) ja
// tem fechada em novembro a de dezembro. As datas vem do servidor
// (invoice_due_date, invoice_closed), onde mora a regra.
export function nextInvoices(openExpenses, todayText) {
  const byCard = {}
  openExpenses.forEach((item) => {
    const due = item.invoice_due_date
    if (!due || isPastDue(due, todayText)) return
    const known = byCard[item.card_id]
    if (known && known.due_date < due) return
    if (!known || due < known.due_date) {
      byCard[item.card_id] = {
        card_id: item.card_id,
        card_name: item.card_name || item.credit_cards?.name || 'Cartão',
        invoice_month: item.invoice_month,
        invoice_year: item.invoice_year,
        due_date: due,
        closing_date: item.invoice_closing_date || null,
        closed: item.invoice_closed === true,
        total: 0,
        items: [],
      }
    }
    byCard[item.card_id].total += amountOf(item)
    byCard[item.card_id].items.push(item)
  })
  return Object.values(byCard).sort((a, b) => a.due_date.localeCompare(b.due_date))
}

// A fatura em aberto que vence primeiro, de qualquer cartao: a vencida mais
// antiga ou, sem vencida, a primeira das proximas. A tela Cartoes abre esta e
// o "Pagar fatura" do topo dela paga esta.
export function nearestOpenInvoice(openExpenses, todayText) {
  return overdueInvoices(openExpenses, todayText)[0] || nextInvoices(openExpenses, todayText)[0] || null
}

// So fatura fechada pode ser paga (o servidor recusa as outras). Uma por
// cartao: cada uma vira um pagamento proprio.
export function payableInvoices(invoiceItems) {
  const byCard = {}
  invoiceItems.forEach((item) => {
    if (item.invoice_closed !== true) return
    if (!byCard[item.card_id]) {
      byCard[item.card_id] = { card_id: item.card_id, invoice_month: item.invoice_month, invoice_year: item.invoice_year, total: 0 }
    }
    byCard[item.card_id].total += amountOf(item)
  })
  // Fatura com credito de estorno nao se paga (o servidor recusa).
  return Object.values(byCard).filter((invoice) => invoice.total >= 0)
}

// Fatura vencida: passou do dia do vencimento e continua em aberto. A data vem
// do servidor (invoice_due_date).
export function overdueInvoices(openExpenses, todayText) {
  const byInvoice = {}
  openExpenses.forEach((item) => {
    if (!isPastDue(item.invoice_due_date, todayText)) return
    const key = invoiceId(item)
    if (!byInvoice[key]) {
      byInvoice[key] = {
        card_id: item.card_id,
        card_name: item.credit_cards?.name || 'Cartão',
        invoice_month: item.invoice_month,
        invoice_year: item.invoice_year,
        due_date: item.invoice_due_date,
        total: 0,
        count: 0,
      }
    }
    byInvoice[key].total += amountOf(item)
    byInvoice[key].count += 1
  })
  return Object.values(byInvoice)
    .filter((invoice) => invoice.total > 0)
    .sort((a, b) => a.due_date.localeCompare(b.due_date))
}

// Debito automatico que a conta nao cobre: faturas de cartoes com debito
// automatico que vencem entre hoje e `limitText`, somadas por conta e
// comparadas ao saldo de hoje. O debito acontece mesmo assim (deixa a conta
// negativa), entao o aviso e para transferir antes. Fatura ainda aberta entra
// pelo total atual, que ainda pode crescer.
// "Nubank · venceu em 10/10/2026", ou a mais antiga quando sao varias.
export function overdueDetail(overdue) {
  return overdue.length === 1
    ? `${overdue[0].card_name} · venceu em ${formatDateBR(overdue[0].due_date)}`
    : `${overdue.length} faturas · a mais antiga venceu em ${formatDateBR(overdue[0]?.due_date)}`
}

export function autopayShortfalls({ cards = [], accounts = [], openExpenses = [], todayText, limitText }) {
  const autopayByCard = Object.fromEntries(
    cards.filter((card) => card.autopay_account_id).map((card) => [card.id, card.autopay_account_id])
  )
  const byAccount = {}
  openExpenses.forEach((item) => {
    const accountId = autopayByCard[item.card_id]
    const due = item.invoice_due_date
    if (!accountId || !due || due < todayText || due > limitText) return
    if (!byAccount[accountId]) byAccount[accountId] = { accountId, total: 0, firstDue: due }
    byAccount[accountId].total += amountOf(item)
    if (due < byAccount[accountId].firstDue) byAccount[accountId].firstDue = due
  })
  return Object.values(byAccount)
    .map((entry) => {
      const account = accounts.find((row) => row.id === entry.accountId)
      // A Corretora nao tem saldo no Inicio: o aviso nao o mostra.
      if (!account || account.archived_at || isPortfolioAccount(account)) return null
      // Em reais, como a fatura. Sem cambio hoje nao da para dizer se cobre.
      const balance = accountBalanceBrl(account)
      if (balance === null) return null
      return balance < entry.total
        ? { ...entry, accountName: account.name, balance, missing: entry.total - balance }
        : null
    })
    .filter(Boolean)
    .sort((a, b) => a.firstDue.localeCompare(b.firstDue))
}

export function overBudgetItems(budget) {
  return (budget?.items || [])
    .filter((item) => item.status === 'OVER')
    .sort((a, b) => (b.spent - b.available) - (a.spent - a.available))
}

// Os avisos, na ordem em que aparecem. Cada um leva os numeros; o texto fica
// com quem desenha (o valor da conta some no modo privado).
//   - fatura vencida (todas juntas, um pagamento por fatura);
//   - fatura fechada do mes, so quando nao ha vencida;
//   - debito automatico sem saldo, um por conta;
//   - recorrencias vencidas (todas juntas);
//   - categoria acima do orcamento, uma por categoria.
export function attentionItems({ overdue = [], payable = [], shortfalls = [], recurringItems = [], budget = null }) {
  const items = []
  const overdueTotal = overdue.reduce((acc, invoice) => acc + invoice.total, 0)
  const overdueCount = overdue.reduce((acc, invoice) => acc + invoice.count, 0)
  if (overdueCount > 0 && overdueTotal > 0) {
    items.push({
      key: `fatura-vencida:${overdue.map(invoiceId).sort().join(',')}`,
      kind: 'INVOICE_OVERDUE',
      tone: 'danger',
      total: overdueTotal,
      itemCount: overdueCount,
      detail: overdueDetail(overdue),
      invoices: overdue,
    })
  }
  const payableTotal = payable.reduce((acc, invoice) => acc + invoice.total, 0)
  if (items.length === 0 && payableTotal > 0) {
    items.push({
      key: `fatura-fechada:${payable.map(invoiceId).sort().join(',')}`,
      kind: 'INVOICE_PAYABLE',
      tone: 'warning',
      total: payableTotal,
      invoices: payable,
    })
  }
  shortfalls.forEach((entry) => {
    items.push({ key: `debito-sem-saldo:${entry.accountId}:${entry.firstDue}`, kind: 'AUTOPAY_SHORTFALL', tone: 'danger', ...entry })
  })
  const pendingRecurring = recurringItems.filter((item) => Number(item.pending_count || 0) > 0)
  const recurringCount = pendingRecurringCount(pendingRecurring)
  if (recurringCount > 0) {
    // A ultima ocorrencia lancada muda a cada "Lancar": o mesmo atraso
    // dispensado nao volta, um novo volta.
    const ids = pendingRecurring
      .map((item) => `${item.id}@${item.last_occurrence_date || ''}x${item.pending_count}`)
      .sort()
      .join(',')
    items.push({ key: `recorrencias:${ids}`, kind: 'RECURRING', tone: 'info', count: recurringCount })
  }
  overBudgetItems(budget).forEach((item) => {
    items.push({
      key: `orcamento:${budget?.month || ''}:${item.category_id ?? item.id}`,
      kind: 'OVER_BUDGET',
      tone: 'warning',
      categoryName: item.parent_name ? `${item.parent_name} › ${item.category_name}` : item.category_name,
      spent: item.spent,
      available: item.available,
    })
  })
  return items
}

export function undismissedItems(items, dismissedKeys = []) {
  const dismissed = new Set(dismissedKeys)
  return items.filter((item) => !dismissed.has(item.key))
}

// A lista guardada no aparelho nao cresce sem fim: fica com as mais recentes.
export const MAX_DISMISSED_KEYS = 200

export function addDismissed(dismissedKeys = [], keys = []) {
  const merged = [...dismissedKeys.filter((key) => !keys.includes(key)), ...keys]
  return merged.slice(-MAX_DISMISSED_KEYS)
}
