// Fluxo de caixa do Inicio, mes a mes. Puro (testado com node --test).
//
// Cada gasto mexe no grafico no dia em que acontece (dono, 2026-10-18): a
// compra no cartao entra inteira no mes da compra, e o pagamento da fatura nao
// entra — ele e a soma de compras ja contadas. Aporte e resgate ficam a parte
// (lib/transactions.js), transferencia entre contas nao entra.
//
// O que era de outra pessoa (lib/sharing.js) tambem fica a parte: receitas e
// despesas sao so a parte do dono, e "others" e o liquido do que ele pagou
// pelos outros menos o que recebeu deles. O resultado do mes inclui tudo.
//
// O saldo de fim de mes (balance) e o das contas de verdade: saldo inicial +
// lancamentos, com o pagamento da fatura no dia em que saiu da conta.
import { isInvestmentInflow, isInvestmentOutflow } from './transactions.js'
import { othersAmount, ownAmount } from './sharing.js'

const INVOICE_SOURCE_TYPES = ['CC_INVOICE_PAYMENT', 'CC_AUTOPAY']

export const isInvoicePayment = (transaction) =>
  INVOICE_SOURCE_TYPES.includes(transaction?.source_type) || Boolean(transaction?.category?.startsWith('Pagamento Fatura'))

const cents = (value) => Math.round((Number(value) || 0) * 100)
// Centavos em reais com o sinal trocado, sem -0 num mes vazio.
const negated = (value) => (value ? -value / 100 : 0)

export function buildMonthlyFlow({ transactions = [], ccExpenses = [], keys = [], openingBalance = 0 }) {
  const firstKey = keys[0]
  const empty = () => ({ income: 0, expense: 0, invested: 0, redeemed: 0, othersPaid: 0, othersReceived: 0, cash: 0 })
  const byKey = Object.fromEntries(keys.map((key) => [key, empty()]))
  let opening = cents(openingBalance)

  transactions.forEach((transaction) => {
    if (transaction.type === 'TRANSFER') return
    const amount = cents(transaction.amount)
    const signed = transaction.type === 'INCOME' ? amount : -amount
    const key = String(transaction.date).slice(0, 7)
    if (firstKey && key < firstKey) {
      opening += signed
      return
    }
    const month = byKey[key]
    if (!month) return
    month.cash += signed
    if (isInvestmentInflow(transaction)) month.redeemed += amount
    else if (isInvestmentOutflow(transaction)) month.invested += amount
    else if (transaction.type === 'INCOME') {
      month.income += cents(ownAmount(transaction))
      month.othersReceived += cents(othersAmount(transaction))
    } else if (!isInvoicePayment(transaction)) {
      month.expense += cents(ownAmount(transaction))
      month.othersPaid += cents(othersAmount(transaction))
    }
  })

  ccExpenses.forEach((expense) => {
    const month = byKey[String(expense.purchase_date || '').slice(0, 7)]
    if (!month) return
    month.expense += cents(ownAmount(expense))
    month.othersPaid += cents(othersAmount(expense))
  })

  let running = opening
  return keys.map((key) => {
    const month = byKey[key]
    running += month.cash
    const net = month.income - month.expense - month.invested + month.redeemed + month.othersReceived - month.othersPaid
    return {
      key,
      income: month.income / 100,
      // Desenhadas abaixo do zero: a posicao diz "saida" sem depender da cor.
      expense: negated(month.expense),
      // Liquido (aportes menos resgates): abaixo do zero quando saiu mais do
      // que voltou, acima no mes em que o resgate foi maior.
      investment: negated(month.invested - month.redeemed),
      invested: month.invested / 100,
      redeemed: month.redeemed / 100,
      // Liquido de outras pessoas: abaixo do zero quando o dono pagou mais por
      // elas do que recebeu delas.
      others: (month.othersReceived - month.othersPaid) / 100,
      othersPaid: month.othersPaid / 100,
      othersReceived: month.othersReceived / 100,
      net: net / 100,
      balance: running / 100,
    }
  })
}
