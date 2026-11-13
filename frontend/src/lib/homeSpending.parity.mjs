// Usado por backend/tests/test_home_panels_parity.py: le {transactions, ccExpenses,
// accounts, month} do stdin e devolve o gasto do mes como o Inicio web o calcula.
import { buildSpending } from './homeSpending.js'
import { bankingTransactions, withoutForeignEntries } from './transactions.js'

let input = ''
process.stdin.on('data', (chunk) => { input += chunk })
process.stdin.on('end', () => {
  const { transactions, ccExpenses, accounts, month } = JSON.parse(input)
  const banking = withoutForeignEntries(bankingTransactions(transactions, accounts), accounts)
  const spending = buildSpending(banking, ccExpenses, month)
  const cents = (value) => Math.round(value * 100)
  const categories = {}
  for (const [name, totals] of Object.entries(spending.byCategory)) {
    const value = cents(totals.cash + totals.credit)
    if (value > 0) categories[name] = { value, cash: cents(totals.cash), credit: cents(totals.credit) }
  }
  process.stdout.write(JSON.stringify({ total: cents(spending.total), categories }))
})
