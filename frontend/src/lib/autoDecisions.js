// Tudo automatico (dono, 2026-11-18): o que o app antes perguntava, agora
// decide sozinho por uma regra escrita, e cada decisao fica visivel com
// "Desfazer" (GET /api/review/auto, POST /api/review/auto/<id>/undo).
// Puro: o texto de cada decisao.

// A Conferencia (Ajustes > Open Finance) mostra o que ela antes apontava e o app
// resolveu sozinho (o conflito com o banco, a linha da carteira) nestes dias.
export const CONFERENCE_DAYS = 30

// GET /api/review/auto com os filtros do servidor: `kinds` (lista ou 'conference')
// e `days` (1 a 365). Sem filtro, tudo.
export function autoDecisionsPath({ kinds, days } = {}) {
  const params = new URLSearchParams()
  const list = Array.isArray(kinds) ? kinds.filter(Boolean) : kinds ? [kinds] : []
  if (list.length) params.set('kinds', list.join(','))
  if (Number.isInteger(days) && days >= 1 && days <= 365) params.set('days', String(days))
  const query = params.toString()
  return query ? `/api/review/auto?${query}` : '/api/review/auto'
}

// A confirmacao e automatica e nao aparece na tela (dono 2026-11-22: sem
// Revisar): a lista "Decidido sozinho" nao mostra `auto_confirm`, cujo
// "Desfazer" so devolveria a linha a uma fila que ninguem ve.
export const HIDDEN_KINDS = ['auto_confirm']

export function shownDecisions(items) {
  return (items || []).filter((decision) => !HIDDEN_KINDS.includes(decision?.kind))
}

const TITLES = {
  pluggy_category: 'Categoria da Pluggy',
  auto_confirm: 'Confirmado sozinho',
  transfer_guess: 'Aporte/resgate com o banco adivinhado',
  fx_fallback: 'Câmbio do último dia útil disponível',
  conflict_changed: 'Valor do banco aplicado',
  conflict_vanished: 'Removido: sumiu do banco e o saldo confirma',
  investment_custody: 'Custódia da corretora: o app já tinha',
  investment_proceed_link: 'Provento da corretora ligado ao calculado',
  investment_closed_fund: 'Fundo do banco já encerrado',
  investment_custody_in: 'Título vindo de outra corretora, pelo custo',
  investment_rate_deduced: 'Título sem indexador: pré-fixado',
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
    case 'investment_custody':
    case 'investment_proceed_link':
      return detail.code || ''
    case 'investment_closed_fund':
      return detail.name || ''
    case 'investment_custody_in':
      return [detail.name, Number.isFinite(detail.cost) ? cents(Math.round(detail.cost * 100)) : ''].filter(Boolean).join(' · ')
    case 'investment_rate_deduced':
      return [detail.name, Number.isFinite(detail.fixedAnnualRate) ? `${String(detail.fixedAnnualRate).replace('.', ',')}% a.a.` : '']
        .filter(Boolean).join(' · ')
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
    case 'investment_custody':
    case 'investment_proceed_link':
    case 'investment_closed_fund':
      return 'Voltou a esperar você na Conferência.'
    default:
      return 'Desfeito.'
  }
}

// O servidor diz o que se desfaz aqui (`undoable`); um antigo nao manda: vale sim.
export function canUndo(decision) {
  return Boolean(decision?.id) && !decision?.undone_at && decision?.undoable !== false
}

// O que aparece no lugar do "Desfazer".
export function noUndoLabel(decision) {
  return decision?.undone_at ? 'Desfeito' : 'Apague no Extrato para desfazer'
}
