// O "Lançar" de uma operacao da corretora que espera (Fase 3): o `prefill` que o
// servidor manda em GET /api/open-finance (investments.held[].prefill, kind
// `operation`) vira o formulario do InvestmentLaunchModal. O `op_key` vai de
// volta no metadata (`open_finance_op_key`): e o que deixa a operacao passar pela
// Corretora da Pluggy e marca a linha como gravada. Modulo puro (node --test).
// Par nativo: android/.../rules/InvestmentPrefill.kt (InvestmentPrefillTest.kt).

import { fixedIncomeFormFromMetadata } from './fixedIncome.js'

export const OP_KEY_METADATA = 'open_finance_op_key'

const numberText = (value) => (value === null || value === undefined || value === '' ? '' : String(value))

// {mode, assetType, ticker, quantity, price, otherCosts, date, fixedIncome,
// treasuryUnits, cash: {enabled, accountId}, opKey} ou null.
export function launchFormFromPrefill(prefill) {
  if (!prefill || prefill.kind !== 'operation') return null
  const metadata = prefill.metadata || {}
  const quantity = Number(prefill.quantity || 0)
  const sell = quantity < 0
  const fixedIncome = prefill.asset_class === 'FIXED_INCOME'
  const otherCosts = Number(metadata.other_costs || 0)
  const price = fixedIncome
    ? Number(prefill.average_price || 0) - otherCosts
    : Number(sell ? metadata.sale_price || prefill.average_price : prefill.average_price || 0)
  const accountId = typeof prefill.cash_account_id === 'string' ? prefill.cash_account_id : ''
  return {
    mode: sell ? 'SELL' : 'BUY',
    assetType: prefill.treasury ? 'TESOURO' : (prefill.asset_class || 'STOCKS'),
    ticker: prefill.ticker_or_name || '',
    quantity: fixedIncome ? '1' : numberText(Math.abs(quantity)),
    price: price > 0 ? numberText(price) : '',
    otherCosts: otherCosts > 0 ? numberText(otherCosts) : '',
    date: metadata.purchase_date || metadata.sale_date || '',
    fixedIncome: fixedIncome ? fixedIncomeFormFromMetadata(metadata) : null,
    treasuryUnits: numberText(metadata.treasury_units),
    cash: { enabled: Boolean(accountId), accountId, missing: false, fresh: false },
    opKey: metadata[OP_KEY_METADATA] || '',
  }
}

// O pedaco do metadata que leva o op_key (nada sem ele).
export function opKeyMetadata(opKey) {
  return opKey ? { [OP_KEY_METADATA]: opKey } : {}
}
