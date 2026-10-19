// Renda fixa: tipo do titulo e forma de remuneracao.
//
// O metadata do lancamento guarda:
//   fixed_income_type  'CDB', 'LCI', ...
//   rate_type          'POS' | 'PRE'
//   indexer            'CDI' | 'CDI_PLUS' | 'IPCA' (so pos-fixado)
//   cdi_percentage     fracao do CDI, 1.10 = 110% (indexador CDI)
//   annual_rate        taxa anual em fracao, 0.065 = 6,5% a.a. (CDI+, IPCA+ e pre)
// Lancamentos antigos so tem cdi_percentage e sao lidos como pos-fixado em CDI.

export const TREASURY_TYPE = 'TESOURO'

export const FIXED_INCOME_TYPES = [
  { value: 'CDB', label: 'CDB' },
  { value: 'LCI', label: 'LCI' },
  { value: 'LCA', label: 'LCA' },
  { value: 'LIG', label: 'LIG' },
  { value: 'LC', label: 'LC' },
  { value: 'LF', label: 'LF' },
  { value: 'RDB', label: 'RDB' },
  { value: 'DEBENTURE', label: 'Debênture' },
  { value: 'DEBENTURE_INCENTIVADA', label: 'Debênture incentivada' },
  { value: 'CRI', label: 'CRI' },
  { value: 'CRA', label: 'CRA' },
  { value: 'CCB', label: 'CCB' },
  // Tesouro Direto: titulo publico, tabela regressiva. Na tela e uma categoria
  // propria ("Tesouro Direto" no tipo de ativo, aba em Posicao), separada da
  // renda fixa; no banco continua FIXED_INCOME com este tipo.
  { value: TREASURY_TYPE, label: 'Tesouro Direto' },
]

// Os titulos vendidos hoje no Tesouro Direto: sugestoes do nome, e a
// rentabilidade que cada um pede (Selic acompanha o CDI no app).
export const TREASURY_TITLES = [
  'Tesouro Selic',
  'Tesouro Prefixado',
  'Tesouro Prefixado com Juros Semestrais',
  'Tesouro IPCA+',
  'Tesouro IPCA+ com Juros Semestrais',
  'Tesouro Renda+ Aposentadoria Extra',
  'Tesouro Educa+',
]

// Rentabilidade (RATE_MODES) pelo nome do titulo do Tesouro, ou null.
export function treasuryRateMode(name) {
  const text = String(name || '').toUpperCase()
  if (text.includes('SELIC')) return 'POS'
  if (/IPCA|RENDA ?\+|EDUCA ?\+/.test(text)) return 'IPCA'
  if (text.includes('PREFIXADO')) return 'PRE'
  return null
}

// Isentos de IR para pessoa fisica pela especie do titulo. A isencao nao e
// escolhida no formulario: segue o tipo (mesma lista de services/fixed_income.py).
export const TAX_FREE_FIXED_INCOME_TYPES = ['LCI', 'LCA', 'LIG', 'CRI', 'CRA', 'DEBENTURE_INCENTIVADA']

export const isTaxFreeFixedIncomeType = (type) => TAX_FREE_FIXED_INCOME_TYPES.includes(type)

// "Rentabilidade" no formulario: IPCA+ aparece ao lado de pos e pre, mas no
// metadata continua sendo rate_type POS com indexer IPCA.
export const RATE_MODES = [
  { value: 'POS', label: 'Pós-fixado (CDI)' },
  { value: 'IPCA', label: 'IPCA+' },
  { value: 'PRE', label: 'Pré-fixado' },
]

// Indexadores do pos-fixado em CDI.
export const INDEXERS = [
  { value: 'CDI', label: '% do CDI' },
  { value: 'CDI_PLUS', label: 'CDI+' },
]

export function rateModeOf(fields) {
  if (fields.rate_type === 'PRE') return 'PRE'
  return fields.indexer === 'IPCA' ? 'IPCA' : 'POS'
}

export function rateFieldsForMode(mode) {
  if (mode === 'PRE') return { rate_type: 'PRE', indexer: 'CDI' }
  if (mode === 'IPCA') return { rate_type: 'POS', indexer: 'IPCA' }
  return { rate_type: 'POS', indexer: 'CDI' }
}

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
})

function formatRateInput(fraction) {
  const value = Number(fraction)
  if (!Number.isFinite(value)) return ''
  return String(Number((value * 100).toFixed(4)))
}

// metadata salvo -> campos do formulario (edicao).
export function fixedIncomeFormFromMetadata(metadata = {}) {
  // Debenture marcada isenta antes do tipo "incentivada" existir.
  const fixedIncomeType = metadata.fixed_income_type === 'DEBENTURE' && metadata.is_tax_free
    ? 'DEBENTURE_INCENTIVADA'
    : (metadata.fixed_income_type || '')
  const rateType = metadata.rate_type === 'PRE' ? 'PRE' : 'POS'
  const indexer = rateType === 'PRE' ? 'CDI' : (metadata.indexer || 'CDI')
  const rate = rateType === 'POS' && indexer === 'CDI' ? metadata.cdi_percentage : metadata.annual_rate
  return {
    fixed_income_type: fixedIncomeType,
    rate_type: rateType,
    indexer,
    rate: rate != null && rate !== '' ? formatRateInput(rate) : '',
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
    is_tax_free: isTaxFreeFixedIncomeType(fields.fixed_income_type),
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
