import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULT_FORM,
  annualFromMonthly,
  calculate,
  compoundSchedule,
  durationText,
  futureValue,
  monthlyFromAnnual,
  parseNumber,
  periodLabel,
  readForm,
  realAnnualRate,
  yearlyRows,
} from './compoundInterest.js'

const close = (actual, expected, digits = 6) => {
  assert.ok(Math.abs(actual - expected) < 10 ** -digits, `${actual} != ${expected}`)
}

test('numbers from the Brazilian keyboard and from an input number', () => {
  assert.equal(parseNumber('1.234,56'), 1234.56)
  assert.equal(parseNumber('1234.56'), 1234.56)
  assert.equal(parseNumber('0,5'), 0.5)
  assert.equal(parseNumber(''), null)
  assert.equal(parseNumber('abc'), null)
})

test('annual and monthly rates are equivalent, never proportional', () => {
  close(monthlyFromAnnual(12), 0.948879293, 8)
  close(annualFromMonthly(1), 12.682503013, 8)
  close(annualFromMonthly(monthlyFromAnnual(10.65)), 10.65, 10)
})

test('Fisher real rate', () => {
  close(realAnnualRate(10, 4), 5.769230769, 8)
  close(realAnnualRate(4, 4), 0, 12)
})

test('a lump sum at 1% a month for 12 months', () => {
  const rows = compoundSchedule({ initial: 1000, monthly: 0, months: 12, monthlyRatePercent: 1 })
  assert.equal(rows.length, 13)
  close(rows[12].balance, 1126.825030132, 8)
  close(rows[12].interest, 126.825030132, 8)
  assert.equal(rows[12].invested, 1000)
})

test('contributions at the end and at the start of the month match the closed form', () => {
  const base = { initial: 0, monthly: 100, months: 12, monthlyRatePercent: 1 }
  const end = compoundSchedule(base)
  close(end[12].balance, 1268.250301, 6)
  close(end[1].balance, 100, 10) // o primeiro aporte ainda nao rendeu
  const start = compoundSchedule({ ...base, timing: 'start' })
  close(start[12].balance, 1280.932804, 6)
  close(start[1].balance, 101, 10)

  const long = { initial: 2500, monthly: 750, months: 360, monthlyRatePercent: monthlyFromAnnual(9) }
  close(compoundSchedule(long).at(-1).balance, futureValue(long), 4)
  close(compoundSchedule({ ...long, timing: 'start' }).at(-1).balance, futureValue({ ...long, timing: 'start' }), 4)
})

test('a zero rate only adds the contributions', () => {
  const rows = compoundSchedule({ initial: 100, monthly: 50, months: 24, monthlyRatePercent: 0 })
  assert.equal(rows.at(-1).balance, 1300)
  assert.equal(rows.at(-1).interest, 0)
  assert.equal(futureValue({ initial: 100, monthly: 50, months: 24, monthlyRatePercent: 0 }), 1300)
})

test('inflation deflates to today\'s money', () => {
  const rows = compoundSchedule({ initial: 1000, monthly: 0, months: 24, monthlyRatePercent: 0, inflationPercent: 10 })
  close(rows[12].real, 1000 / 1.1, 8)
  close(rows[24].real, 1000 / 1.21, 8)
  assert.equal(compoundSchedule({ initial: 1, monthly: 0, months: 1, monthlyRatePercent: 1 })[1].real, null)
})

test('yearly rows, the last one partial', () => {
  const schedule = compoundSchedule({ initial: 0, monthly: 100, months: 30, monthlyRatePercent: 1 })
  const years = yearlyRows(schedule)
  assert.deepEqual(years.map((row) => [row.year, row.months]), [[1, 12], [2, 12], [3, 6]])
  assert.equal(years[1].investedInYear, 1200)
  close(years[0].interestInYear, years[0].interest, 10)
  close(years[2].balance, schedule[30].balance, 10)
  close(years.reduce((sum, row) => sum + row.interestInYear, 0), schedule[30].interest, 8)
})

test('the form: units, defaults and errors', () => {
  const months = readForm({ ...DEFAULT_FORM, period: '18', periodUnit: 'month', rate: '1', rateUnit: 'month' })
  assert.equal(months.months, 18)
  close(months.annualRatePercent, 12.682503013, 8)
  assert.equal(readForm({ ...DEFAULT_FORM, period: '1,5' }).months, 18)
  assert.equal(readForm({ ...DEFAULT_FORM, initial: '', monthly: '' }).initial, 0)
  assert.equal(readForm({ ...DEFAULT_FORM, inflation: '' }).inflationPercent, null)

  assert.match(readForm({ ...DEFAULT_FORM, period: '' }).error, /período/)
  assert.match(readForm({ ...DEFAULT_FORM, period: '1,3' }).error, /meses inteiros/)
  assert.match(readForm({ ...DEFAULT_FORM, period: '7', periodUnit: 'month' }).error ?? '', /^$/)
  assert.match(readForm({ ...DEFAULT_FORM, period: '101' }).error, /100 anos/)
  assert.match(readForm({ ...DEFAULT_FORM, rate: '-100' }).error, /−100%/)
  assert.match(readForm({ ...DEFAULT_FORM, monthly: '-1' }).error, /negativos/)
})

test('calculate: totals, income at the end and the real rate', () => {
  const result = calculate({ initial: '10000', monthly: '1000', rate: '1', rateUnit: 'month', period: '1', periodUnit: 'year', timing: 'end', inflation: '4' })
  close(result.final, 10000 * 1.01 ** 12 + 1000 * (1.01 ** 12 - 1) / 0.01, 6)
  assert.equal(result.invested, 22000)
  close(result.interest, result.final - 22000, 8)
  close(result.monthlyIncomeAtEnd, result.final * 0.01, 8)
  close(result.real, result.final / 1.04, 6)
  close(result.realAnnualRatePercent, (1.01 ** 12 / 1.04 - 1) * 100, 8)
  assert.equal(calculate({ ...DEFAULT_FORM, inflation: '' }).realAnnualRatePercent, null)
  assert.ok(calculate({ ...DEFAULT_FORM, period: '0' }).error)
})

test('period labels', () => {
  assert.equal(periodLabel(0), 'Hoje')
  assert.equal(periodLabel(24), 'Ano 2')
  assert.equal(periodLabel(7), 'Mês 7')
})

test('duration text', () => {
  assert.equal(durationText(12), '1 ano')
  assert.equal(durationText(120), '10 anos')
  assert.equal(durationText(1), '1 mês')
  assert.equal(durationText(30), '2 anos e 6 meses')
})
