// Porte: mudou um, muda o outro, com um teste de cada lado. Par nativo:
// android/.../rules/CompoundInterest.kt (CompoundInterestTest.kt), os mesmos casos de compoundInterest.test.js.
// Calculadora de juros compostos (Investimentos › Calculadora). Funcoes puras,
// sem navegador nem React: testadas com node --test (compoundInterest.test.js).
//
// Regime de juros compostos com aportes mensais (serie uniforme):
//   VF = VP·(1+i)^n + PMT·((1+i)^n − 1)/i        aporte no fim do mes (postecipado)
//   VF = VP·(1+i)^n + PMT·((1+i)^n − 1)/i·(1+i)  aporte no inicio do mes (antecipado)
// A taxa anual vira mensal pela taxa equivalente, (1+ia) = (1+im)^12 — a mesma
// conversao de services/goals.py (monthly_rate) —, nunca pela proporcional ia/12.
// A inflacao entra pela relacao de Fisher: (1+real) = (1+nominal)/(1+inflacao).

export const MAX_MONTHS = 1200 // 100 anos
export const MAX_RATE_PERCENT = 1000

export const DEFAULT_FORM = {
  initial: '1000',
  monthly: '500',
  rate: '10',
  rateUnit: 'year', // 'year' | 'month'
  period: '10',
  periodUnit: 'year', // 'year' | 'month'
  timing: 'end', // 'end' | 'start'
  inflation: '',
}

// '1.234,56' do teclado brasileiro ou '1234.56' do input number. Vazio e null.
export function parseNumber(value) {
  if (value === null || value === undefined) return null
  const text = String(value).trim()
  if (!text) return null
  const normalized = text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text
  const number = Number(normalized)
  return Number.isFinite(number) ? number : null
}

export function monthlyFromAnnual(annualPercent) {
  return ((1 + annualPercent / 100) ** (1 / 12) - 1) * 100
}

export function annualFromMonthly(monthlyPercent) {
  return ((1 + monthlyPercent / 100) ** 12 - 1) * 100
}

// Taxa real anual (Fisher), em %.
export function realAnnualRate(annualPercent, inflationPercent) {
  return ((1 + annualPercent / 100) / (1 + inflationPercent / 100) - 1) * 100
}

// O formulario em numeros, ou { error } com o texto para a tela.
export function readForm(form) {
  const initial = parseNumber(form.initial) ?? 0
  const monthly = parseNumber(form.monthly) ?? 0
  const rate = parseNumber(form.rate) ?? 0
  const period = parseNumber(form.period)
  const inflation = parseNumber(form.inflation)

  if (initial < 0 || monthly < 0) return { error: 'Valor inicial e aporte não podem ser negativos.' }
  if (rate <= -100) return { error: 'A taxa precisa ser maior que −100%.' }
  if (rate > MAX_RATE_PERCENT) return { error: `A taxa pode ir até ${MAX_RATE_PERCENT}%.` }
  if (inflation !== null && (inflation <= -100 || inflation > MAX_RATE_PERCENT)) {
    return { error: 'Inflação fora do intervalo aceito.' }
  }
  if (period === null || period <= 0) return { error: 'Informe o período.' }
  const months = form.periodUnit === 'month' ? period : period * 12
  if (!Number.isInteger(months)) {
    return { error: form.periodUnit === 'month' ? 'O período em meses precisa ser inteiro.' : 'Esse período não fecha em meses inteiros: informe em meses.' }
  }
  if (months > MAX_MONTHS) return { error: 'O período pode ir até 100 anos.' }

  const monthlyRatePercent = form.rateUnit === 'month' ? rate : monthlyFromAnnual(rate)
  const annualRatePercent = form.rateUnit === 'month' ? annualFromMonthly(rate) : rate
  return {
    initial,
    monthly,
    months,
    monthlyRatePercent,
    annualRatePercent,
    timing: form.timing === 'start' ? 'start' : 'end',
    inflationPercent: inflation,
  }
}

// Mes a mes. Cada linha: saldo, total aportado e juros acumulados no fim do mes
// (e em reais de hoje, quando ha inflacao). A linha 0 e o valor inicial.
export function compoundSchedule({ initial, monthly, months, monthlyRatePercent, timing = 'end', inflationPercent = null }) {
  const rate = monthlyRatePercent / 100
  const deflator = inflationPercent === null || inflationPercent === undefined
    ? null
    : (1 + inflationPercent / 100) ** (1 / 12)
  const rows = [{ month: 0, balance: initial, invested: initial, interest: 0, interestInMonth: 0, real: deflator ? initial : null }]
  let balance = initial
  let invested = initial
  for (let month = 1; month <= months; month += 1) {
    if (timing === 'start') { balance += monthly; invested += monthly }
    const interestInMonth = balance * rate
    balance += interestInMonth
    if (timing !== 'start') { balance += monthly; invested += monthly }
    rows.push({
      month,
      balance,
      invested,
      interest: balance - invested,
      interestInMonth,
      real: deflator ? balance / deflator ** month : null,
    })
  }
  return rows
}

// Forma fechada do valor futuro, para conferir a serie.
export function futureValue({ initial, monthly, months, monthlyRatePercent, timing = 'end' }) {
  const rate = monthlyRatePercent / 100
  const growth = (1 + rate) ** months
  const annuity = rate === 0 ? months : (growth - 1) / rate
  return initial * growth + monthly * annuity * (timing === 'start' ? 1 + rate : 1)
}

// Um resumo por ano (o ultimo pode ser parcial): saldo no fim, aportes e juros do ano.
export function yearlyRows(schedule) {
  const years = []
  const last = schedule.length - 1
  for (let end = 12; end - 12 < last; end += 12) {
    const to = schedule[Math.min(end, last)]
    const from = schedule[end - 12]
    years.push({
      year: end / 12,
      months: to.month - from.month,
      balance: to.balance,
      invested: to.invested,
      interest: to.interest,
      investedInYear: to.invested - from.invested,
      interestInYear: to.interest - from.interest,
      real: to.real,
    })
  }
  return years
}

// Tudo o que a tela mostra, a partir do formulario.
export function calculate(form) {
  const input = readForm(form)
  if (input.error) return input
  const schedule = compoundSchedule(input)
  const final = schedule[schedule.length - 1]
  return {
    input,
    schedule,
    years: yearlyRows(schedule),
    final: final.balance,
    invested: final.invested,
    interest: final.interest,
    real: final.real,
    // Quanto o saldo final renderia no mes seguinte, a mesma taxa.
    monthlyIncomeAtEnd: final.balance * (input.monthlyRatePercent / 100),
    realAnnualRatePercent: input.inflationPercent === null ? null : realAnnualRate(input.annualRatePercent, input.inflationPercent),
  }
}

// "Ano 3" ou "Mês 7" para o eixo e a tabela.
export function periodLabel(month) {
  if (month === 0) return 'Hoje'
  return month % 12 === 0 ? `Ano ${month / 12}` : `Mês ${month}`
}

// "1 ano", "10 anos", "7 meses", "2 anos e 6 meses".
export function durationText(months) {
  const years = Math.floor(months / 12)
  const rest = months % 12
  const parts = []
  if (years) parts.push(`${years} ${years === 1 ? 'ano' : 'anos'}`)
  if (rest) parts.push(`${rest} ${rest === 1 ? 'mês' : 'meses'}`)
  return parts.join(' e ')
}
