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

// "1.234,56", "1234,56", "1234.56", "1,234.56" -> 1234.56; "3.000" -> 3000.
// Com virgula e ponto, o ultimo dos dois e o decimal e o outro separa milhar
// (em grupos de tres). So ponto: grupos de tres depois de um digito que nao e
// zero sao milhar, como se escreve em reais ("1.500"); senao e decimal
// ("0.500" -> 0,5). So virgula: decimal; mais de uma, milhar ("1,234,567").
// Vazio -> null; invalido (milhar fora do lugar, "1.2.3") -> NaN. O teclado
// decimal do Android em pt-BR digita virgula; o do desktop, ponto.
export function parseMoneyInput(value) {
  const text = String(value ?? '').trim().replace(/\s|R\$/g, '')
  if (!text) return null
  const lastComma = text.lastIndexOf(',')
  const lastDot = text.lastIndexOf('.')
  let integer = text
  let fraction = ''
  let groupSeparator = ''
  const splitAt = (index) => {
    integer = text.slice(0, index)
    fraction = text.slice(index + 1)
  }
  if (lastComma >= 0 && lastDot >= 0) {
    splitAt(Math.max(lastComma, lastDot))
    groupSeparator = lastComma > lastDot ? '.' : ','
  } else if (lastComma >= 0) {
    if (text.indexOf(',') === lastComma) splitAt(lastComma)
    else groupSeparator = ','
  } else if (lastDot >= 0) {
    if (/^[1-9]\d{0,2}(\.\d{3})+$/.test(text)) groupSeparator = '.'
    else if (text.indexOf('.') === lastDot) splitAt(lastDot)
    else return Number.NaN
  }
  if (groupSeparator) {
    const grouped = groupSeparator === '.' ? /^\d{1,3}(\.\d{3})*$/ : /^\d{1,3}(,\d{3})*$/
    if (!grouped.test(integer)) return Number.NaN
    integer = integer.split(groupSeparator).join('')
  }
  if (!/^\d*$/.test(integer) || !/^\d*$/.test(fraction) || !(integer || fraction)) return Number.NaN
  return Number(`${integer || '0'}.${fraction || '0'}`)
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
      return `Investir e gastar passam da renda do mês em ${amount}. Reduza um dos dois para o plano caber.`
    case 'CATEGORIES_OVER_SPEND':
      return `As categorias somam ${String(flag.percent).replace('.', ',')}% do Gastar: passam dele em ${amount}. Reduza alguma.`
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
