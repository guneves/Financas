// Port: mudou um, muda o outro, com um teste de cada lado. Copia nativa em
// frontend/android/app/src/main/java/br/financas/app/rules/Goals.kt (GoalsTest.kt).
//
// Metas: os textos da previsao e o selo de cada cartao. Puro, testado em
// goals.test.js. Todo valor (atual, falta, previsao, aporte necessario) vem do
// servidor (services/goals.py); aqui so o texto.

// 'AAAA-MM' -> 'out/2028': cabe no quadro mesmo no celular.
export function shortMonthYear(key) {
  const [year, month] = String(key).split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
  return `${name}/${year}`
}

function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many}`
}

// O quadro "Previsão": o mes em que chega no ritmo atual.
export function forecastText(goal) {
  if (goal.reached) return 'Alcançada'
  if (goal.kind === 'MONTHLY_INCOME') return '—'
  if (!goal.estimated_month) return 'Sem previsão'
  return shortMonthYear(goal.estimated_month)
}

// A linha embaixo da previsao: "em 2 anos e 3 meses".
export function forecastHint(goal) {
  if (goal.reached || goal.kind === 'MONTHLY_INCOME') return ''
  if (!goal.estimated_month) return 'Informe um aporte mensal'
  const years = Math.floor(goal.estimated_months / 12)
  const months = goal.estimated_months % 12
  const parts = [years ? plural(years, 'ano', 'anos') : '', months ? plural(months, 'mês', 'meses') : ''].filter(Boolean)
  return parts.length ? `em ${parts.join(' e ')}` : ''
}

// O selo do cartao: alcancada vence o prazo; sem data (on_track null), nenhum.
export function goalBadge(goal) {
  if (goal.reached) return { label: 'Alcançada', tone: 'success' }
  if (goal.on_track === false) return { label: 'Fora do prazo', tone: 'warning' }
  if (goal.on_track === true) return { label: 'No prazo', tone: 'neutral' }
  return null
}
