// Paginas do extrato filtrado (GET /api/transactions?limit=N, servidor em
// services/transaction_pages.py). Os totais e a contagem sao do filtro
// inteiro e vem na primeira pagina; o total de cada dia vem do servidor, que
// soma o dia todo mesmo quando ele cai partido entre duas paginas.

export const STATEMENT_PAGE_LIMIT = 200

export function mergeTransactionPages(pages) {
  const list = Array.isArray(pages) ? pages.filter(Boolean) : []
  const items = list.flatMap((page) => page.items || [])
  const dayTotals = {}
  list.forEach((page) => Object.assign(dayTotals, page.day_totals || {}))
  const first = list[0]
  const last = list[list.length - 1]
  return {
    items,
    count: first ? Number(first.count ?? items.length) : 0,
    totals: first?.totals || { income: 0, expense: 0, investment: 0 },
    dayTotals,
    hasMore: Boolean(last?.next_cursor),
  }
}

export const nextPageCursor = (lastPage) => lastPage?.next_cursor || undefined

// Muda as linhas de uma leitura guardada do extrato, nos dois formatos: a carga
// inteira (`transactions`) e as paginas do filtrado (`pages[].items`). `change`
// recebe a lista e devolve a nova. Outro formato passa como esta.
export function changeCachedRows(data, change) {
  if (Array.isArray(data?.transactions)) return { ...data, transactions: change(data.transactions) }
  if (Array.isArray(data?.pages)) {
    return { ...data, pages: data.pages.map((page) => (page?.items ? { ...page, items: change(page.items) } : page)) }
  }
  return data
}

export const withoutRow = (id) => (rows) => rows.filter((row) => row.id !== id)
export const withRow = (updated) => (rows) => rows.map((row) => (row.id === updated.id ? { ...row, ...updated } : row))
