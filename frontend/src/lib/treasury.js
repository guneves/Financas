// Porte: mudou um, muda o outro, com um teste de cada lado. Par nativo (so os textos):
// android/.../rules/TreasuryLabels.kt (TreasuryLabelsTest.kt), os mesmos casos de treasury.test.js.
// Tesouro Direto na Posicao: a posicao agrupada por titulo (services/treasury.py)
// traz `lots` (as compras) e `treasury` (vencimento, titulos, taxa media, PU).

// O resgate (a divisao PEPS pelas compras) e do servidor:
// POST /api/investments/redemptions (services/treasury.py, redemption_parts()).

function percentNumber(fraction) {
  return (Number(fraction) * 100).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// "IPCA + 6,23% a.a.", "Pré 12,10% a.a.", "100,00% do CDI" a partir de uma taxa
// (fracao) e do metadata do titulo.
export function treasuryRateText(rate, metadata = {}) {
  if (rate == null || !Number.isFinite(Number(rate))) return ''
  if (metadata.rate_type === 'PRE') return `Pré ${percentNumber(rate)}% a.a.`
  if (metadata.indexer === 'IPCA') return `IPCA + ${percentNumber(rate)}% a.a.`
  if (metadata.indexer === 'CDI_PLUS') return `CDI + ${percentNumber(rate)}% a.a.`
  return `${percentNumber(rate)}% do CDI`
}

// A taxa da linha: "Taxa média" quando a posicao junta mais de uma compra.
export function treasuryRateLabel(asset) {
  const treasury = asset?.treasury || {}
  const metadata = asset?.metadata || {}
  const rate = treasury.average_rate ?? (metadata.indexer === 'CDI' || (!metadata.indexer && metadata.rate_type !== 'PRE')
    ? metadata.cdi_percentage
    : metadata.annual_rate)
  const text = treasuryRateText(rate, metadata)
  if (!text) return ''
  return (treasury.lot_count || 0) > 1 ? `Taxa média ${text}` : `Taxa ${text}`
}

// A taxa de mercado do dia (a de venda, do arquivo do Tesouro) no mesmo formato.
// No Selic a taxa do arquivo e o agio/desagio sobre a Selic, nao uma taxa a.a.
export function treasuryMarketRateText(asset) {
  const treasury = asset?.treasury || {}
  if (treasury.market_rate == null || String(treasury.title_type || '').includes('SELIC')) return ''
  const metadata = asset?.metadata || {}
  if (metadata.rate_type === 'PRE') return `Pré ${percentNumber(treasury.market_rate)}% a.a.`
  return `IPCA + ${percentNumber(treasury.market_rate)}% a.a.`
}

export const isMarketValued = (asset) => asset?.treasury?.valuation === 'MARKET'

// "0,85" (ou "0.85") -> 0.85; vazio -> null. Um numero invalido ou <= 0 e NaN.
// A quantidade de titulos que o extrato da corretora mostra, na compra e na edicao.
export function parseTreasuryUnits(raw) {
  const text = String(raw ?? '').trim()
  if (!text) return null
  const units = Number(text.includes(',') ? text.replace(/\./g, '').replace(',', '.') : text)
  return Number.isFinite(units) && units > 0 ? units : NaN
}
