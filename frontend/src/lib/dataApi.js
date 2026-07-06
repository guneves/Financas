import { apiFetch } from './api'

const queryString = (params) => {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.set(key, value)
    }
  })
  const value = searchParams.toString()
  return value ? `?${value}` : ''
}

export const transactionsApi = {
  list: () => apiFetch('/api/transactions'),
  create: (payload) => apiFetch('/api/transactions', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/transactions/${id}`, { method: 'DELETE' })
}

export const creditCardsApi = {
  list: () => apiFetch('/api/credit-cards'),
  create: (payload) => apiFetch('/api/credit-cards', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/credit-cards/${id}`, { method: 'DELETE' })
}

export const ccExpensesApi = {
  list: (params = {}) => apiFetch(`/api/cc-expenses${queryString(params)}`),
  create: (payload) => apiFetch('/api/cc-expenses', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  candidates: (params) => apiFetch(`/api/cc-expenses/candidates${queryString(params)}`),
  removeMany: (ids) => apiFetch('/api/cc-expenses', {
    method: 'DELETE',
    body: JSON.stringify({ ids })
  }),
  updateStatus: (ids, status = 'PAID') => apiFetch('/api/cc-expenses/status', {
    method: 'PATCH',
    body: JSON.stringify({ ids, status })
  }),
  updateInvoiceStatus: (payload) => apiFetch('/api/cc-expenses/invoice-status', {
    method: 'PATCH',
    body: JSON.stringify(payload)
  })
}

export const investmentsApi = {
  list: (params = {}) => apiFetch(`/api/investments${queryString(params)}`),
  assets: () => apiFetch('/api/assets'),
  transactions: () => apiFetch('/api/investment-transactions'),
  positions: () => apiFetch('/api/investment-positions'),
  realizedResults: () => apiFetch('/api/investment-realized-results'),
  create: (payload) => apiFetch('/api/investments', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/investments/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/investments/${id}`, { method: 'DELETE' }),
  removeByAsset: (assetId, assetClass) => apiFetch(`/api/investments/by-asset/${encodeURIComponent(assetId)}${queryString({ asset_class: assetClass })}`, { method: 'DELETE' }),
  updatePriceByAsset: (assetId, assetClass, currentPrice) => apiFetch(`/api/investments/price-by-asset/${encodeURIComponent(assetId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ asset_class: assetClass, current_price: currentPrice })
  })
}

export const investmentProceedsApi = {
  list: (params = {}) => apiFetch(`/api/investment-proceeds${queryString(params)}`),
  summary: (params = {}) => apiFetch(`/api/investment-proceeds/summary${queryString(params)}`),
  calendar: (params = {}) => apiFetch(`/api/investment-proceeds/calendar${queryString(params)}`),
  create: (payload) => apiFetch('/api/investment-proceeds', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/investment-proceeds/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/investment-proceeds/${id}`, { method: 'DELETE' })
}
