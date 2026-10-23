// O fluxo de caixa do Inicio a partir de GET /api/home (`flow`, um item por
// mes, somado no servidor): os pontos do grafico e os numeros acima dele.
// Funcoes puras, testadas com `node --test` (homeFlow.test.js).
// Port: android/.../rules/HomeFlow.kt (HomeFlowTest.kt, os mesmos casos):
// mudou um, muda o outro.
import { shortMonthLabel } from './format.js'

// Um mes de /api/home como o grafico o desenha: as saidas abaixo do zero (a
// posicao diz "saida" sem depender da cor), o investimento e outras pessoas
// liquidos. Em centavos, sem -0 num mes vazio.
const cents = (value) => Math.round((Number(value) || 0) * 100)
const negated = (value) => (value ? -value / 100 : 0)

export function flowPoint(month) {
  return {
    key: month.month,
    label: shortMonthLabel(month.month),
    income: month.income,
    expense: negated(cents(month.expense)),
    investment: negated(cents(month.invested) - cents(month.redeemed)),
    invested: month.invested,
    redeemed: month.redeemed,
    others: (cents(month.others_received) - cents(month.others_paid)) / 100,
    othersPaid: month.others_paid,
    othersReceived: month.others_received,
    net: month.net,
    balance: month.balance,
  }
}

// As medias contam so os meses com algum movimento (receita, despesa,
// investimento ou outras pessoas): um mes antes de comecar a usar o app
// puxaria a media para baixo.
export function flowSummary(points) {
  const hasInvestment = (item) => item.invested !== 0 || item.redeemed !== 0
  const hasOthers = (item) => item.othersPaid !== 0 || item.othersReceived !== 0
  const active = points.filter((item) => item.income !== 0 || item.expense !== 0 || hasInvestment(item) || hasOthers(item))
  const income = points.reduce((acc, item) => acc + item.income, 0)
  const expense = points.reduce((acc, item) => acc - item.expense, 0)
  const investment = points.reduce((acc, item) => acc - item.investment, 0)
  const months = Math.max(active.length, 1)
  return {
    avgIncome: income / months,
    avgExpense: expense / months,
    avgInvestment: investment / months,
    // O que foi investido conta como poupado: so a despesa reduz a taxa. O
    // resgate ja ficou fora da receita.
    savingsRate: income > 0 ? ((income - expense) / income) * 100 : null,
    hasData: active.length > 0,
    // So existe investimento aqui se algum aporte ou resgate passou pelo
    // extrato; sem isso a media e a serie do grafico nem aparecem.
    hasInvestment: points.some(hasInvestment),
    // Algo pago por (ou recebido de) outra pessoa nos 12 meses: so entao a
    // serie aparece.
    hasOthers: points.some(hasOthers),
  }
}

// "Taxa de poupança": uma casa no maximo, "—" sem receita.
export function savingsRateText(rate) {
  return rate === null ? '—' : `${rate.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`
}
