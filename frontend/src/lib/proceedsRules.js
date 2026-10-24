// Porte: mudou um, muda o outro, com um teste de cada lado. Par nativo:
// android/.../rules/ProceedsRules.kt (ProceedsRulesTest.kt), os mesmos casos de proceedsRules.test.js.
// Registrar provento: que tipo cada ativo recebe e que campos cada tipo pede.
// Puro (sem React nem api.js): testado por node --test.
//
// A categoria vem do servidor (`category` de /api/assets,
// services/asset_categories.py): ACAO, ETF, BDR, FII, RENDA_FIXA, TESOURO,
// CRIPTO, OTHER. O servidor recusa so o que a classe nunca recebe (cupom fora
// da renda fixa, dividendo/JCP em renda fixa, JCP em FII); aqui o filtro e
// mais fino:
// - JCP e de sociedade anonima (Lei 9.249/1995, art. 9o): so acoes (units
//   incluidas), nunca ETF, BDR ou FII;
// - dividendos: acoes, ETFs que distribuem, BDRs e os rendimentos de FII;
// - amortizacao: FII, acao (restituicao de capital), renda fixa e, no Tesouro,
//   so os titulos que devolvem o capital em parcelas (Renda+, Educa+);
// - juros (cupom): renda fixa e, no Tesouro, so os com juros semestrais (NTN-B,
//   NTN-F). Um titulo do Tesouro cujo nome nao diz o produto fica nos dois.

import { normalizeSearchText } from './assetSearch.js'

export const PROCEEDS_TYPES = [
  { value: 'DIVIDEND', label: 'Dividendos' },
  { value: 'JCP', label: 'JCP' },
  { value: 'AMORTIZATION', label: 'Amortização' },
  { value: 'INTEREST', label: 'Juros (cupom)' },
]

export const CATEGORY_LABELS = {
  ACAO: 'Ações',
  ETF: 'ETFs',
  BDR: 'BDRs',
  FII: 'FIIs',
  RENDA_FIXA: 'Renda fixa',
  TESOURO: 'Tesouro Direto',
  CRIPTO: 'Cripto',
  OTHER: 'Outros',
}

// Abaixo do tipo, no formulario: quem pode ter este provento.
export const TYPE_HINTS = {
  DIVIDEND: 'Ações, ETFs, BDRs e FIIs (rendimentos).',
  JCP: 'Só ações: ETF, BDR e FII não pagam JCP.',
  AMORTIZATION: 'FIIs, ações, renda fixa e Tesouro Renda+/Educa+.',
  INTEREST: 'Renda fixa e Tesouro com juros semestrais.',
}

const TYPE_CATEGORIES = {
  DIVIDEND: ['ACAO', 'ETF', 'BDR', 'FII'],
  JCP: ['ACAO'],
  AMORTIZATION: ['ACAO', 'FII', 'RENDA_FIXA', 'TESOURO'],
  INTEREST: ['RENDA_FIXA', 'TESOURO'],
}

const FIXED_INCOME_CATEGORIES = ['RENDA_FIXA', 'TESOURO']

const CLASS_CATEGORY = { STOCKS: 'ACAO', REIT: 'FII', FIXED_INCOME: 'RENDA_FIXA', OTHER: 'OTHER' }

// A categoria do ativo; sem ela (resposta antiga), a da classe.
export function assetCategory(asset) {
  if (!asset) return null
  return asset.category || CLASS_CATEGORY[asset.asset_class || asset.class] || 'OTHER'
}

export const categoryLabel = (asset) => CATEGORY_LABELS[assetCategory(asset)] || ''

export const isFixedIncomeCategory = (category) => FIXED_INCOME_CATEGORIES.includes(category)

// O produto do Tesouro pelo nome: COUPON (juros semestrais), INSTALLMENTS
// (Renda+, Educa+), BULLET (Selic, Prefixado, IPCA+ sem juros: tudo no
// vencimento) ou null quando o nome nao diz.
export function treasuryProduct(name) {
  const text = normalizeSearchText(name)
  if (!text) return null
  if (/RENDA ?\+|EDUCA ?\+/.test(text)) return 'INSTALLMENTS'
  if (text.includes('JUROS SEMESTRAIS') || /\bNTN-?F\b/.test(text)) return 'COUPON'
  if (/\bNTN-?B\b/.test(text)) return text.includes('PRINCIPAL') ? 'BULLET' : 'COUPON'
  if (/SELIC|PREFIXADO|PRE-FIXADO|IPCA|\bLFT\b|\bLTN\b/.test(text)) return 'BULLET'
  return null
}

const assetName = (asset) => asset?.ticker || asset?.name || ''

export function proceedsTypeFitsAsset(type, asset) {
  const category = assetCategory(asset)
  if (!(TYPE_CATEGORIES[type] || []).includes(category)) return false
  if (category !== 'TESOURO') return true
  const product = treasuryProduct(assetName(asset))
  if (type === 'INTEREST') return product === 'COUPON' || product === null
  if (type === 'AMORTIZATION') return product === 'INSTALLMENTS' || product === null
  return true
}

// Os ativos que podem ter este tipo de provento; `keepId` (o da edicao) fica
// mesmo que nao caiba, para um provento antigo continuar editavel.
export function assetsForProceedsType(assets, type, keepId = '') {
  return (assets || []).filter((asset) => (
    proceedsTypeFitsAsset(type, asset) || (keepId && String(asset.id) === String(keepId))
  ))
}

// FIXED: renda fixa e Tesouro — so pagamento e valor bruto, com "repetir".
// MARKET: acao, ETF, BDR, FII — data com, valor por cota, quantidade na data com.
export function proceedsLayout(type, asset) {
  return isFixedIncomeCategory(assetCategory(asset)) && ['INTEREST', 'AMORTIZATION'].includes(type)
    ? 'FIXED'
    : 'MARKET'
}

// O campo de IR: null quando o tipo nao tem IR (a amortizacao devolve capital).
export function proceedsTaxField(type) {
  if (type === 'AMORTIZATION') return null
  if (type === 'INTEREST') {
    return {
      label: 'IR retido (R$)',
      hint: 'Em branco: tabela regressiva desde a aplicação (22,5% a 15%), zero em título isento.',
    }
  }
  if (type === 'JCP') {
    return { label: 'IR retido (R$)', hint: 'Em branco: 15% retido na fonte (17,5% com data com desde 2026).' }
  }
  return {
    label: 'IR retido (R$)',
    hint: 'Em branco: sem IR (dividendos e rendimentos de FII). Preencha só se houve retenção na fonte.',
  }
}

// O tipo atual se vale para o ativo; senao o primeiro que vale (ou o atual,
// quando nenhum vale: o servidor diz o porque).
export function typeForAsset(asset, current) {
  if (!asset || proceedsTypeFitsAsset(current, asset)) return current
  return PROCEEDS_TYPES.find((item) => proceedsTypeFitsAsset(item.value, asset))?.value || current
}

export const typeLabel = (value) => PROCEEDS_TYPES.find((item) => item.value === value)?.label || value

// Escritas que mudam a posicao de um ativo em alguma data, e com ela os
// proventos automaticos (lib/proceedsSync.js sincroniza logo depois). Uma
// cotacao (atualizar precos, preco manual) nao muda posicao nenhuma.
const QUOTE_ONLY_WRITE = /^\/api\/investments\/(update-prices|price-by-asset)(\/|\?|$)/

export function changesPositions(path) {
  const value = path || ''
  return /^\/api\/(investments|corporate-actions)(\/|\?|$)/.test(value) && !QUOTE_ONLY_WRITE.test(value)
}
