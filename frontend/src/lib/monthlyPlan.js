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

// Dispensar um alerta e por aparelho (lib/planFlags.js), como o "Precisa de
// atencao" do Inicio. A chave e o caso: codigo + mes (+ meta). O mesmo alerta
// nao volta neste mes; um alerta novo (outro codigo — o ritmo que vira
// estouro), outra meta ou o mesmo no mes seguinte voltam.
export function planFlagKey(flag, month) {
  const key = `plan:${month}:${flag.code}`
  return flag.goal_id === undefined || flag.goal_id === null ? key : `${key}:${flag.goal_id}`
}

export function visibleFlags(flags = [], month, dismissedKeys = []) {
  const dismissed = new Set(dismissedKeys)
  return flags.filter((flag) => !dismissed.has(planFlagKey(flag, month)))
}

// Estado da barra (mesmas cores do orcamento por categoria).
export function spendStatus(flags = []) {
  if (flags.some((flag) => flag.code === 'SPEND_OVER')) return 'OVER'
  if (flags.some((flag) => flag.code === 'SPEND_PACE' || flag.code === 'SPEND_NEAR')) return 'WARNING'
  return 'OK'
}

// --- O plano em %, na tela -------------------------------------------------
//
// O servidor calcula todo R$ do plano (services/budgets.py, percent_of()). Aqui
// so a previa enquanto se digita: o Gastar do formulario e o R$ ao lado do %
// de uma categoria. Mesma conta do servidor: centavos x percentual (seis
// casas) em inteiros, arredondado meio-para-cima (ROUND_HALF_UP), sem float.

const MICRO = 1000000 // seis casas do percentual, como o servidor guarda
const HUNDRED_MICRO = 100 * MICRO

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)

// 12,5 -> 12500000 (milionesimos de ponto percentual); null se nao for numero.
function toMicro(percent) {
  return isNumber(percent) ? Math.round(percent * MICRO) : null
}

// `percent`% de `amount`, em reais. null quando falta um dos dois.
export function percentOf(amount, percent) {
  const micro = toMicro(percent)
  if (!isNumber(amount) || micro === null) return null
  const cents = BigInt(Math.round(amount * 100))
  const product = cents * BigInt(micro)
  const divisor = BigInt(HUNDRED_MICRO)
  const negative = product < 0n
  const absolute = negative ? -product : product
  let quotient = absolute / divisor
  if ((absolute % divisor) * 2n >= divisor) quotient += 1n
  const result = Number(negative ? -quotient : quotient) / 100
  return result === 0 ? 0 : result
}

// "20%", "33,33%", "12,5%": ate duas casas, sem zeros sobrando.
export function formatPlanPercent(value) {
  const number = isNumber(Number(value)) ? Number(value) : 0
  return `${number.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`
}

// "Sem destino" do plano: o que sobra de 100% depois de Investir e Gastar.
// Acima de 100% (so um plano antigo convertido chega aqui) o texto diz quanto passa.
export function unallocatedText(percent) {
  if (!isNumber(percent)) return ''
  if (percent < 0) return `Passa de 100% da renda em ${formatPlanPercent(-percent)}`
  return `Sem destino ${formatPlanPercent(percent)}`
}

// "Recebido R$ 3.200,00 de R$ 5.000,00 esperados".
export function incomeReceivedText(received, planned) {
  return `Recebido ${formatCurrency(received)} de ${formatCurrency(planned)} esperados`
}

// A previa do formulario "Plano do mes", a cada tecla. Recebe os valores ja
// lidos por parseMoneyInput() (null = vazio, NaN = invalido) e, num plano antigo
// sem renda, os reais de antes (`legacy`): com os dois % em branco o servidor
// converte esses reais sobre a renda (038), e a previa mostra o mesmo.
//
// Devolve os R$ e o "Sem destino" para a linha ao vivo e, em `blocked`, o motivo
// que impede salvar (null = pode salvar).
export function livePlanTotals({ income, invest, spend, legacy = null }) {
  const hasIncome = isNumber(income) && income > 0
  const convert = Boolean(legacy) && invest === null && spend === null
  const result = {
    convert,
    investAmount: null,
    spendAmount: null,
    unallocatedPercent: null,
    over: false,
    blocked: null,
  }

  if (convert) {
    if (!hasIncome) {
      result.blocked = 'Informe a renda do mês.'
      return result
    }
    result.investAmount = Number(legacy.invest_amount || 0)
    result.spendAmount = Number(legacy.spend_amount || 0)
    const committed = Math.round((result.investAmount + result.spendAmount) * 100)
    const unallocatedMicro = HUNDRED_MICRO - Math.round((committed * MICRO) / Math.round(income * 100) * 100)
    result.unallocatedPercent = unallocatedMicro / MICRO
    // A conversao acima de 100% e aceita e vira alerta no plano (038).
    result.over = unallocatedMicro < 0
    return result
  }

  const investValid = isNumber(invest) && invest >= 0
  const spendValid = isNumber(spend) && spend >= 0
  if (hasIncome) {
    if (investValid) result.investAmount = percentOf(income, invest)
    if (spendValid) result.spendAmount = percentOf(income, spend)
  }
  if (investValid && spendValid) {
    const unallocatedMicro = HUNDRED_MICRO - toMicro(invest) - toMicro(spend)
    result.unallocatedPercent = unallocatedMicro / MICRO
    result.over = unallocatedMicro < 0
  }

  if (!hasIncome) result.blocked = 'Informe a renda do mês.'
  else if (!investValid || !spendValid) result.blocked = 'Informe quanto da renda investir e gastar, em %.'
  else if (result.over) result.blocked = 'Investir e Gastar passam de 100% da renda.'
  return result
}

// "Investir R$ 1.000,00 · Gastar R$ 3.500,00 · Sem destino 10%". Uma parte que
// ainda nao da para calcular aparece como "—".
export function livePlanText(totals) {
  const money = (value) => (isNumber(value) ? formatCurrency(value) : '—')
  const rest = isNumber(totals.unallocatedPercent) ? unallocatedText(totals.unallocatedPercent) : 'Sem destino —'
  return `Investir ${money(totals.investAmount)} · Gastar ${money(totals.spendAmount)} · ${rest}`
}

// O R$ ao lado do % de uma categoria, enquanto se digita: % do Gastar em reais.
// null quando o % ainda nao e um numero valido ou o plano nao tem Gastar.
export function categoryAmountPreview(spendAmount, percent) {
  if (!isNumber(percent) || percent < 0) return null
  return percentOf(spendAmount, percent)
}
