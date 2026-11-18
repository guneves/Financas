// Tudo automatico (dono, 2026-11-18): o que o app antes perguntava, agora
// decide sozinho por uma regra escrita, e cada decisao fica visivel com
// "Desfazer" (GET /api/review/auto, POST /api/review/auto/<id>/undo).
// Puro: o texto de cada decisao e o prazo do Revisar (review_auto_days).

export const REVIEW_DAY_CHOICES = [0, 3, 7, 14]

export const REVIEW_AUTO_HINT = 'Depois desse prazo, o que ainda está em Revisar sai sozinho com a categoria que tem. Numa conta da Pluggy, espera o banco confirmar primeiro.'

// O prazo do servidor; um servidor antigo que nao manda o campo vale 3.
export function reviewAutoDays(settings) {
  const value = settings?.review_auto_days
  return Number.isInteger(value) && value >= 0 ? value : 3
}

export function reviewDayItems(current) {
  const values = REVIEW_DAY_CHOICES.includes(current) ? REVIEW_DAY_CHOICES : [...REVIEW_DAY_CHOICES, current].sort((a, b) => a - b)
  return values.map((value) => ({ value, label: value === 0 ? 'Nunca' : `${value} dias` }))
}

export function reviewAutoToast(days) {
  return days === 0 ? 'O Revisar espera você.' : `O que ficar ${days} dias em Revisar sai sozinho.`
}

const TITLES = {
  pluggy_category: 'Categoria da Pluggy',
  auto_confirm: 'Saiu do Revisar sozinho',
  transfer_guess: 'Aporte/resgate com o banco adivinhado',
  fx_fallback: 'Câmbio do último dia útil disponível',
  conflict_changed: 'Valor do banco aplicado',
  conflict_vanished: 'Removido: sumiu do banco e o saldo confirma',
}

export function decisionTitle(decision) {
  return TITLES[decision?.kind] || 'Decisão automática'
}

function cents(value) {
  if (!Number.isFinite(value)) return ''
  return (value / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

// Uma linha do que mudou, sem nada que o servidor nao mandou.
export function decisionDetail(decision) {
  const detail = decision?.detail || {}
  switch (decision?.kind) {
    case 'pluggy_category':
      return detail.before?.[0] && detail.after?.[0] ? `${detail.before[0]} → ${detail.after[0]}` : ''
    case 'auto_confirm':
      return detail.category?.[0] ? `Ficou em ${detail.category[0]}` : ''
    case 'conflict_changed':
      return `${cents(detail.before_cents)} → ${cents(detail.after_cents)}`
    case 'conflict_vanished':
      return detail.row?.description || ''
    case 'fx_fallback':
      return detail.rate_date ? `PTAX de ${detail.rate_date.split('-').reverse().join('/')}` : ''
    default:
      return ''
  }
}

// O que o "Desfazer" faz, para o toast.
export function undoToast(decision) {
  switch (decision?.kind) {
    case 'pluggy_category':
      return 'A categoria voltou.'
    case 'conflict_changed':
      return 'O valor voltou; a Conferência aponta a diferença.'
    case 'conflict_vanished':
      return 'O lançamento voltou.'
    default:
      return 'Voltou para o Revisar.'
  }
}

export function canUndo(decision) {
  return Boolean(decision?.id) && !decision?.undone_at
}
