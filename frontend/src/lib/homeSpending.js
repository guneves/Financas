// O gasto de consumo de um mes, como o Inicio o mostra (categorias e ritmo).
// Puro: so listas e numeros. Saiu de pages/Dashboard.jsx (2026-11-13); o servidor
// tem a mesma conta em services/home_panels.py (GET /api/home/panels, que o APK le).
import { cardPurchaseKey, cardSignedAmount, isCardRefund, isInvestmentOutflow, isInvoicePayment } from './transactions.js'
import { ownAmount } from './sharing.js'

// Gasto de consumo de um mes, por dia e por categoria: saidas da conta (menos
// o pagamento de fatura, que ja e a soma das compras, e os aportes em
// investimento) + compras no cartao pelo valor total da compra, na data da compra.
// So a parte do dono (lib/sharing.js): o que era de outra pessoa nao e gasto dele.
export function buildSpending(transactions, ccExpenses, key) {
  const byDay = {}
  const byCategory = {}
  const add = (day, category, channel, amount) => {
    byDay[day] = (byDay[day] || 0) + amount
    const name = category || 'Outros'
    if (!byCategory[name]) byCategory[name] = { cash: 0, credit: 0 }
    byCategory[name][channel] += amount
  }

  transactions.forEach((transaction) => {
    if (transaction.type !== 'EXPENSE' || isInvoicePayment(transaction) || isInvestmentOutflow(transaction)) return
    // O gasto de um mes numa linha so nao tem dia (Inter): fora do ritmo.
    if (transaction.source_type === 'MONTH_SUMMARY') return
    if (String(transaction.date).slice(0, 7) !== key) return
    const own = ownAmount(transaction)
    if (own > 0) add(Number(transaction.date.slice(8, 10)), transaction.category, 'cash', own)
  })

  const purchases = {}
  ccExpenses.forEach((expense) => {
    if (String(expense.purchase_date || '').slice(0, 7) !== key) return
    const groupKey = cardPurchaseKey(expense)
    if (!purchases[groupKey]) {
      purchases[groupKey] = { day: Number(expense.purchase_date.slice(8, 10)), category: expense.category, amount: 0 }
    }
    // O estorno (033) abate a categoria no dia dele.
    purchases[groupKey].amount += isCardRefund(expense) ? cardSignedAmount(expense) : ownAmount(expense)
  })
  Object.values(purchases).forEach((purchase) => {
    if (purchase.amount !== 0) add(purchase.day, purchase.category, 'credit', purchase.amount)
  })

  const total = Object.values(byDay).reduce((acc, value) => acc + value, 0)
  return { byDay, byCategory, total }
}
