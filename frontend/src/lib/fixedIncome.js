// Renda fixa: tipo do titulo e forma de remuneracao.
//
// O metadata do lancamento guarda:
//   fixed_income_type  'CDB', 'LCI', ...
//   rate_type          'POS' | 'PRE'
//   indexer            'CDI' | 'CDI_PLUS' | 'IPCA' (so pos-fixado)
//   cdi_percentage     fracao do CDI, 1.10 = 110% (indexador CDI)
//   annual_rate        taxa anual em fracao, 0.065 = 6,5% a.a. (CDI+, IPCA+ e pre)
// Lancamentos antigos so tem cdi_percentage e sao lidos como pos-fixado em CDI.

export const FIXED_INCOME_TYPES = [
  { value: 'CDB', label: 'CDB' },
  { value: 'LCI', label: 'LCI' },
  { value: 'LCA', label: 'LCA' },
  { value: 'LC', label: 'LC' },
  { value: 'LF', label: 'LF' },
  { value: 'RDB', label: 'RDB' },
  { value: 'DEBENTURE', label: 'Debênture' },
  { value: 'CRI', label: 'CRI' },
  { value: 'CRA', label: 'CRA' },
  { value: 'CCB', label: 'CCB' },
]

// Isentos de IR para pessoa fisica. Debenture incentivada tambem e, mas nem
// toda debenture e incentivada: para ela o checkbox fica a cargo do usuario.
export const TAX_FREE_FIXED_INCOME_TYPES = ['LCI', 'LCA', 'CRI', 'CRA']

export const RATE_TYPES = [
  { value: 'POS', label: 'Pós-fixado' },
  { value: 'PRE', label: 'Pré-fixado' },
]

export const INDEXERS = [
  { value: 'CDI', label: 'CDI' },
  { value: 'CDI_PLUS', label: 'CDI+' },
  { value: 'IPCA', label: 'IPCA+' },
]

export function rateFieldLabel(rateType, indexer) {
  if (rateType === 'PRE') return 'Taxa (% a.a.)'
  if (indexer === 'CDI_PLUS') return 'CDI + (% a.a.)'
  if (indexer === 'IPCA') return 'IPCA + (% a.a.)'
  return '% do CDI'
}

export function ratePlaceholder(rateType, indexer) {
  if (rateType === 'PRE') return 'Ex: 12,5'
  if (indexer === 'CDI_PLUS') return 'Ex: 1,5'
  if (indexer === 'IPCA') return 'Ex: 6,5'
  return 'Ex: 110'
}

export const emptyFixedIncomeForm = () => ({
  fixed_income_type: 'CDB',
  rate_type: 'POS',
  indexer: 'CDI',
  rate: '',
  is_tax_free: false,
})

function formatRateInput(fraction) {
  const value = Number(fraction)
  if (!Number.isFinite(value)) return ''
  return String(Number((value * 100).toFixed(4)))
}

// metadata salvo -> campos do formulario (edicao).
export function fixedIncomeFormFromMetadata(metadata = {}) {
  const rateType = metadata.rate_type === 'PRE' ? 'PRE' : 'POS'
  const indexer = rateType === 'PRE' ? 'CDI' : (metadata.indexer || 'CDI')
  const rate = rateType === 'POS' && indexer === 'CDI' ? metadata.cdi_percentage : metadata.annual_rate
  return {
    fixed_income_type: metadata.fixed_income_type || '',
    rate_type: rateType,
    indexer,
    rate: rate != null && rate !== '' ? formatRateInput(rate) : '',
    is_tax_free: Boolean(metadata.is_tax_free),
  }
}

function parseRate(value) {
  const raw = String(value ?? '').trim()
  const normalized = raw.includes(',') ? raw.replace(/\./g, '').replace(',', '.') : raw
  return Number(normalized)
}

// Campos do formulario -> chaves de metadata. Lanca erro se a taxa for invalida.
export function fixedIncomeMetadataFromForm(fields) {
  const rate = parseRate(fields.rate)
  const isCdi = fields.rate_type === 'POS' && fields.indexer === 'CDI'
  if (!Number.isFinite(rate) || rate < 0 || (isCdi && rate === 0) || String(fields.rate ?? '').trim() === '') {
    throw new Error(isCdi ? 'Informe um percentual do CDI válido.' : 'Informe uma taxa válida.')
  }

  const metadata = {
    fixed_income_type: fields.fixed_income_type || undefined,
    rate_type: fields.rate_type,
    indexer: fields.rate_type === 'POS' ? fields.indexer : undefined,
    cdi_percentage: isCdi ? rate / 100 : undefined,
    annual_rate: isCdi ? undefined : rate / 100,
    is_tax_free: Boolean(fields.is_tax_free),
  }
  return metadata
}

// Chaves que fixedIncomeMetadataFromForm controla; limpas antes de regravar
// para que trocar de CDI para pre nao deixe um cdi_percentage antigo para tras.
export const FIXED_INCOME_METADATA_KEYS = [
  'fixed_income_type', 'rate_type', 'indexer', 'cdi_percentage', 'annual_rate', 'is_tax_free',
]

function formatPercentNumber(fraction) {
  return (Number(fraction) * 100).toLocaleString('pt-BR', { maximumFractionDigits: 2 })
}

// "CDB · 110% do CDI", "IPCA+ 6,5% a.a.", "Pré 12,5% a.a."
export function describeFixedIncome(metadata = {}) {
  const typeLabel = FIXED_INCOME_TYPES.find((type) => type.value === metadata.fixed_income_type)?.label
  let rateLabel = ''
  if (metadata.rate_type === 'PRE') {
    if (metadata.annual_rate != null) rateLabel = `Pré ${formatPercentNumber(metadata.annual_rate)}% a.a.`
  } else if (metadata.indexer === 'CDI_PLUS') {
    if (metadata.annual_rate != null) rateLabel = `CDI + ${formatPercentNumber(metadata.annual_rate)}% a.a.`
  } else if (metadata.indexer === 'IPCA') {
    if (metadata.annual_rate != null) rateLabel = `IPCA + ${formatPercentNumber(metadata.annual_rate)}% a.a.`
  } else if (metadata.cdi_percentage != null) {
    rateLabel = `${formatPercentNumber(metadata.cdi_percentage)}% do CDI`
  }
  return [typeLabel, rateLabel].filter(Boolean).join(' · ')
}
