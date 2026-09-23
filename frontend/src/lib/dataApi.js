import { apiBlob, apiDownload, apiFetch } from './api'

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
  list: (params = {}) => apiFetch(`/api/transactions${queryString(params)}`),
  create: (payload) => apiFetch('/api/transactions', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/transactions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/transactions/${id}`, { method: 'DELETE' }),
  // Baixa o extrato filtrado; aceita os mesmos filtros do list, mais
  // `format` ('csv' | 'xlsx') e `columns` ('data,valor').
  exportFile: (params = {}) => apiDownload(`/api/transactions/export${queryString(params)}`, `extrato.${params.format || 'csv'}`)
}

// Comprovantes (PDF/imagem) de um lancamento. As rotas sao aninhadas no
// lancamento: o backend confere que o comprovante e mesmo daquele lancamento.
function attachmentsApiFor(base) {
  return {
    list: (ownerId) => apiFetch(`${base}/${ownerId}/attachments`),
    upload: (ownerId, file) => {
      const body = new FormData()
      body.append('file', file)
      return apiFetch(`${base}/${ownerId}/attachments`, { method: 'POST', body })
    },
    remove: (ownerId, attachmentId) => apiFetch(
      `${base}/${ownerId}/attachments/${attachmentId}`,
      { method: 'DELETE' }
    ),
    // Blob do arquivo; quem chama decide entre abrir numa aba ou salvar.
    file: async (ownerId, attachmentId) => {
      const { blob } = await apiBlob(`${base}/${ownerId}/attachments/${attachmentId}/file`)
      return blob
    }
  }
}

export const attachmentsApi = attachmentsApiFor('/api/transactions')

// Comprovantes de compra no cartao: anexados numa parcela, listados pela
// compra inteira (todas as parcelas).
export const ccExpenseAttachmentsApi = attachmentsApiFor('/api/cc-expenses')

export const accountsApi = {
  list: (params = {}) => apiFetch(`/api/accounts${queryString(params)}`),
  create: (payload) => apiFetch('/api/accounts', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/accounts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  archive: (id) => apiFetch(`/api/accounts/${id}`, { method: 'DELETE' })
}

export const categoriesApi = {
  list: (params = {}) => apiFetch(`/api/categories${queryString(params)}`),
  create: (payload) => apiFetch('/api/categories', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/categories/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  archive: (id) => apiFetch(`/api/categories/${id}`, { method: 'DELETE' })
}

export const budgetsApi = {
  month: (month) => apiFetch(`/api/budgets${queryString({ month })}`),
  create: (payload) => apiFetch('/api/budgets', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/budgets/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/budgets/${id}`, { method: 'DELETE' }),
  copy: (payload) => apiFetch('/api/budgets/copy', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export const recurringApi = {
  list: (params = {}) => apiFetch(`/api/recurring${queryString(params)}`),
  create: (payload) => apiFetch('/api/recurring', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/recurring/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/recurring/${id}`, { method: 'DELETE' }),
  run: (payload = {}) => apiFetch('/api/recurring/run', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  forecast: (params = {}) => apiFetch(`/api/recurring/forecast${queryString(params)}`)
}

// Importacao de extrato (Fase 4). A previa nao grava nada: ela le o arquivo,
// aplica as regras e devolve o que entraria; o commit grava o que foi conferido.
export const importApi = {
  preview: (payload) => apiFetch('/api/import/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  commit: (payload) => apiFetch('/api/import/commit', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export const importRulesApi = {
  list: () => apiFetch('/api/import-rules'),
  create: (payload) => apiFetch('/api/import-rules', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  update: (id, payload) => apiFetch(`/api/import-rules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  }),
  remove: (id) => apiFetch(`/api/import-rules/${id}`, { method: 'DELETE' }),
  // Regras sobre lancamentos ja gravados: previa (nao grava) e aplicacao dos
  // ids confirmados. `rule_id` opcional restringe a uma regra.
  applyPreview: (payload = {}) => apiFetch('/api/import-rules/apply/preview', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  apply: (payload) => apiFetch('/api/import-rules/apply', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export const transfersApi = {
  create: (payload) => apiFetch('/api/transfers', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export const creditCardsApi = {
  list: () => apiFetch('/api/credit-cards'),
  create: (payload) => apiFetch('/api/credit-cards', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  // Debito automatico: conta que paga a fatura no vencimento; null desliga.
  setAutopay: (id, accountId) => apiFetch(`/api/credit-cards/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ autopay_account_id: accountId || null })
  }),
  remove: (id) => apiFetch(`/api/credit-cards/${id}`, { method: 'DELETE' })
}

export const ccExpensesApi = {
  list: (params = {}) => apiFetch(`/api/cc-expenses${queryString(params)}`),
  create: (payload) => apiFetch('/api/cc-expenses', {
    method: 'POST',
    body: JSON.stringify(payload)
  }),
  createPurchase: (payload) => apiFetch('/api/cc-expenses/purchases', {
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
  }),
  // Paga uma fatura fechada: debita a conta e baixa os itens de uma vez.
  // O servidor recusa (409) uma fatura que ainda nao fechou.
  payInvoice: (payload) => apiFetch('/api/cc-expenses/pay-invoice', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export const investmentsApi = {
  list: (params = {}) => apiFetch(`/api/investments${queryString(params)}`),
  assets: () => apiFetch('/api/assets'),
  transactions: () => apiFetch('/api/investment-transactions'),
  positions: () => apiFetch('/api/investment-positions'),
  realizedResults: () => apiFetch('/api/investment-realized-results'),
  history: (params = {}) => apiFetch(`/api/investments/history${queryString(params)}`),
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
  }),
  exportPortfolio: (params = {}) => apiDownload(`/api/investments/portfolio/export${queryString(params)}`, `carteira.${params.format || 'csv'}`),
  exportMovements: (params = {}) => apiDownload(`/api/investments/export${queryString(params)}`, `operacoes.${params.format || 'csv'}`)
}

export const marketApi = {
  searchTickers: (params = {}) => apiFetch(`/api/market/tickers${queryString(params)}`),
  ticker: (ticker) => apiFetch(`/api/market/tickers/${encodeURIComponent(ticker)}`)
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
  remove: (id) => apiFetch(`/api/investment-proceeds/${id}`, { method: 'DELETE' }),
  exportFile: (params = {}) => apiDownload(`/api/investment-proceeds/export${queryString(params)}`, `proventos.${params.format || 'csv'}`)
}

// Colunas de cada exportacao (extrato, carteira, operacoes, proventos).
export const exportsApi = {
  columns: () => apiFetch('/api/exports/columns')
}

// Saude das integracoes (yfinance, brapi, BCB). `refresh: 1` ignora o cache do backend.
export const systemApi = {
  integrations: (params = {}) => apiFetch(`/api/health/integrations${queryString(params)}`)
}
