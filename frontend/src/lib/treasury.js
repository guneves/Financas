// Tesouro Direto na Posicao: a posicao agrupada por titulo (services/treasury.py)
// traz `lots` (as compras) e `treasury` (vencimento, titulos, taxa media, PU).

const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100

// Resgate de um titulo agrupado: o Tesouro vende primeiro os titulos comprados
// antes (PEPS). Cada parte vira um resgate da compra dela (`related_id`), com o
// custo proporcional ao valor bruto tirado daquela compra -- a mesma regra do
// resgate parcial de um titulo so. Valor acima do bruto da posicao: erro.
export function allocateTreasuryRedemption(lots, amount) {
  const ordered = [...(lots || [])].sort((a, b) =>
    String(a.purchase_date).localeCompare(String(b.purchase_date)) || String(a.id).localeCompare(String(b.id)))
  let rest = round2(amount)
  if (!(rest > 0)) throw new Error('Informe um valor de resgate.')
  const parts = []
  for (const lot of ordered) {
    if (rest <= 0) break
    const gross = Number(lot.gross) || 0
    if (gross <= 0) continue
    const take = Math.min(rest, round2(gross))
    parts.push({ lotId: lot.id, amount: round2(take), cost: (Number(lot.invested) || 0) * (take / gross) })
    rest = round2(rest - take)
  }
  if (rest > 0) throw new Error('O valor passa do saldo bruto do título.')
  return parts
}

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
