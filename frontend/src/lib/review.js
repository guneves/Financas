// Gravar sozinho e revisar (045): a notificacao e a Pluggy viram lancamento na
// hora; o dono so diz "e meu" e a categoria. E o Extrato mostra as compras no
// cartao na mesma linha do tempo das contas.
//
// Regras puras (testadas em review.test.js): nada aqui importa React, o
// navegador ou lib/api.js.

export const REVIEW_PATH = '/lancamentos/extrato?review=1'

// Uma compra no cartao (GET /api/cc-expenses/statement) no formato de uma
// linha do extrato: `kind: 'card'`, a chave nao colide com a de um lancamento.
export function cardStatementRow(purchase) {
  return {
    ...purchase,
    kind: 'card',
    key: `card:${purchase.client_id || purchase.id}`,
  }
}

export const isCardRow = (row) => row?.kind === 'card'

// Chave de React e de "acabou de chegar": a do lancamento, ou a da compra.
export const statementKey = (row) => (isCardRow(row) ? row.key : row.id)

// O valor com sinal: a compra sai (−), o estorno volta (+). Nao mexe em saldo
// de conta: fica fora do total do dia e dos totais do filtro.
export function cardAmountSign(row) {
  return row.type === 'REFUND' ? 1 : -1
}

// Os lancamentos e as compras numa lista so, do mais novo para o mais antigo
// (a data; no mesmo dia, o gravado por ultimo primeiro). `until`: com o extrato
// paginado, so as compras ate a data mais antiga ja carregada — a pagina
// seguinte traz o resto, e uma compra antiga nao aparece antes da hora.
export function mergeStatement(transactions, purchases, { until = '' } = {}) {
  const cards = (purchases || [])
    .filter((purchase) => !until || (purchase.date || '') >= until)
    .map(cardStatementRow)
  if (!cards.length) return transactions || []
  return [...(transactions || []), ...cards].sort((a, b) => {
    const byDate = (b.date || '').localeCompare(a.date || '')
    if (byDate) return byDate
    return (b.created_at || '').localeCompare(a.created_at || '')
  })
}

// A data mais antiga de uma lista ja ordenada (a ultima), ou '' se vazia.
export function oldestDate(rows) {
  return rows?.length ? rows[rows.length - 1].date || '' : ''
}

// O item da fila de revisao (GET /api/review) mostra de onde veio.
export function reviewPlace(item) {
  if (item.table === 'cc_expenses') {
    const parts = Number(item.installments) > 1 ? ` · ${item.installments}x` : ''
    return `${item.card_name || 'Cartão'}${parts}`
  }
  if (item.type === 'TRANSFER') return `${item.account_name || 'Conta'} → ${item.transfer_account_name || 'Conta'}`
  return item.account_name || 'Conta'
}

// O sinal do valor na revisao: entrada +, saida −, transferencia sem sinal.
export function reviewSign(item) {
  if (item.type === 'TRANSFER') return 0
  if (item.type === 'INCOME' || item.type === 'REFUND') return 1
  return -1
}

// Uma transferencia nao tem categoria a escolher; o resto pode trocar.
export const reviewHasCategory = (item) => item.type !== 'TRANSFER'

// O pedido de POST /api/review: so manda category_id quando o dono mudou.
export function reviewPayload(items, chosen = {}) {
  return items.map((item) => {
    const entry = { table: item.table, id: item.id }
    const key = reviewKey(item)
    if (reviewHasCategory(item) && chosen[key] && chosen[key] !== (item.category_id || '')) {
      entry.category_id = chosen[key]
    }
    return entry
  })
}

export const reviewKey = (item) => `${item.table}:${item.id}`

// Que categorias a escolha oferece: despesa para saida e compra, receita para
// entrada e estorno.
export const reviewCategoryType = (item) => (reviewSign(item) > 0 ? 'INCOME' : 'EXPENSE')

export function reviewNoticeText(count) {
  if (!count) return ''
  return count === 1
    ? '1 lançamento gravado sozinho espera você confirmar.'
    : `${count} lançamentos gravados sozinhos esperam você confirmar.`
}

export function waitingNoticeText(count) {
  if (!count) return ''
  return count === 1
    ? '1 movimento não pôde ser gravado sozinho (uma transferência sem a outra ponta, outra moeda).'
    : `${count} movimentos não puderam ser gravados sozinhos (transferências sem a outra ponta, outra moeda).`
}
