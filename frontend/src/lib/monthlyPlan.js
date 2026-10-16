// Plano do mes (Orcamento): o texto de cada alerta e a leitura dos valores
// digitados. Funcoes puras — testadas com node --test (monthlyPlan.test.js).
//
// O backend (services/monthly_plan.py) devolve cada alerta como codigo, tom
// e valores; o texto em portugues sai daqui.
import { formatCurrency, monthLabel } from './format.js'

// Tom do backend -> tom do AlertMessage/Badge.
export const FLAG_TONES = {
  loss: 'danger',
  warning: 'warning',
  gain: 'success',
  info: 'info',
}

// "1.234,56", "1234,56", "1234.56" -> 1234.56; "3.000" -> 3000 (sem virgula,
// ponto seguido de grupos de tres digitos e milhar, como se escreve em reais).
// Vazio -> null; invalido -> NaN. O teclado decimal do Android em pt-BR
// digita virgula; o do desktop, ponto.
export function parseMoneyInput(value) {
  const text = String(value ?? '').trim().replace(/\s|R\$/g, '')
  if (!text) return null
  const thousandsOnly = !text.includes(',') && /^\d{1,3}(\.\d{3})+$/.test(text)
  const normalized = text.includes(',') || thousandsOnly ? text.replace(/\./g, '').replace(',', '.') : text
  if (!/^\d+(\.\d+)?$/.test(normalized)) return Number.NaN
  return Number(normalized)
}

// Valor guardado -> texto do campo, no formato que o teclado do celular digita.
export function moneyInputValue(value) {
  if (value === null || value === undefined || value === '') return ''
  return String(value).replace('.', ',')
}

const days = (count) => (count === 1 ? '1 dia' : `${count} dias`)

export function flagText(flag) {
  const amount = formatCurrency(flag.amount)
  switch (flag.code) {
    case 'PLAN_OVER_INCOME':
      return `Gastar e investir o planejado passa da renda esperada em ${amount}. Reduza um dos dois para o plano caber.`
    case 'SPEND_OVER':
      return `Os gastos passaram do plano em ${amount}.`
    case 'SPEND_PACE':
      return `No ritmo atual, o mês fecha com ${amount} de gastos — ${formatCurrency(flag.over)} acima do plano.`
    case 'SPEND_NEAR':
      return `Quase no limite: restam ${amount} para gastar no mês.`
    case 'SPEND_KEPT':
      return `Gastos dentro do plano: sobraram ${amount}.`
    case 'INVEST_DONE':
      return `Aporte do mês feito: ${amount} investidos.`
    case 'INVEST_PENDING':
      return flag.days_left > 0
        ? `Faltam ${amount} para o aporte do mês (${days(flag.days_left)} até o fim do mês).`
        : `Faltam ${amount} para o aporte do mês, e o mês termina hoje.`
    case 'INVEST_MISSED':
      return `Faltaram ${amount} para o aporte planejado.`
    case 'GOAL_SHORT':
      return `Meta “${flag.goal_name}”: precisa de ${amount} por mês até ${monthLabel(flag.target_month)}. O plano aporta ${formatCurrency(flag.missing)} a menos que isso.`
    case 'GOAL_COVERED':
      return `Meta “${flag.goal_name}”: o aporte planejado cobre os ${amount} por mês até ${monthLabel(flag.target_month)}.`
    default:
      return ''
  }
}

// Alertas que pedem acao primeiro; as boas noticias por ultimo.
const TONE_ORDER = { loss: 0, warning: 1, info: 2, gain: 3 }

export function sortFlags(flags = []) {
  return [...flags].sort((a, b) => (TONE_ORDER[a.tone] ?? 9) - (TONE_ORDER[b.tone] ?? 9))
}

// Estado da barra (mesmas cores do orcamento por categoria).
export function spendStatus(flags = []) {
  if (flags.some((flag) => flag.code === 'SPEND_OVER')) return 'OVER'
  if (flags.some((flag) => flag.code === 'SPEND_PACE' || flag.code === 'SPEND_NEAR')) return 'WARNING'
  return 'OK'
}
