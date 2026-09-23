// Formatadores e leituras de uma movimentacao de investimento, compartilhados
// entre Posicao e Operacoes. Movidos de Investments.jsx sem mudanca de regra.

export function readStoredJson(key, fallback) {
  try {
    const saved = localStorage.getItem(key)
    return saved ? JSON.parse(saved) : fallback
  } catch {
    localStorage.removeItem(key)
    return fallback
  }
}

export { formatPercent } from '../../lib/format'

export function formatDateTime(value) {
  if (!value) return 'Sem atualização'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Data inválida'
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function quoteSourceLabel(source) {
  const labels = {
    market: 'Mercado',
    manual: 'Manual',
    cdi: 'Taxa do título',
    legacy: 'Legado',
    cache: 'Cache',
    cache_stale: 'Cache antigo',
    fallback: 'Sem fonte',
  }
  return labels[source] || source || 'Sem fonte'
}

export function quoteStatusLabel(status) {
  const labels = {
    fresh: 'Atual',
    stale: 'Desatualizada',
    missing: 'Sem cotação',
  }
  return labels[status] || 'Sem cotação'
}

export function parseNumberInput(value) {
  const rawValue = String(value || '').trim()
  const normalized = rawValue.includes(',')
    ? rawValue.replace(/\./g, '').replace(',', '.')
    : rawValue
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : NaN
}

export function movementDateValue(movement) {
  return movement.metadata?.redemption_date
    || movement.metadata?.sale_date
    || movement.metadata?.purchase_date
    || movement.created_at
}

export function movementUnitPrice(movement) {
  if (movement.metadata?.is_redemption) return Number(movement.current_price || 0)
  if (movement.quantity < 0 && movement.metadata?.sale_price) return Number(movement.metadata.sale_price || 0)
  return Number(movement.average_price || 0)
}

export function movementTotalValue(movement) {
  return Math.abs(Number(movement.quantity || 0) * movementUnitPrice(movement))
}

export function movementFees(movement) {
  return Number(
    movement.realized_fee_amount
    ?? movement.fee_amount
    ?? movement.metadata?.other_costs
    ?? 0
  )
}

export function hasRealizedResult(movement) {
  return movement.realized_profit !== null
    && movement.realized_profit !== undefined
    && Number.isFinite(Number(movement.realized_profit))
}

export function getClassLabel(assetClass) {
  const labels = {
    'STOCKS': 'Ações',
    'FIXED_INCOME': 'Renda Fixa',
    'REIT': 'Fundos Imobiliários',
    'CATTLE': 'Gado',
    'OTHER': 'Outros'
  }
  return labels[assetClass] || assetClass
}
