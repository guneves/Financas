// Gravar sozinho (045): a notificacao e a Pluggy viram lancamento na hora, e a
// confirmacao e automatica (dono 2026-11-22: sem "É meu" nem "É repasse" na
// tela). O Extrato mostra as compras no cartao na mesma linha do tempo das contas.
//
// Regras puras (testadas em review.test.js): nada aqui importa React, o
// navegador ou lib/api.js.

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

export function waitingNoticeText(count) {
  if (!count) return ''
  return count === 1
    ? '1 movimento a Pluggy atualizou e não identificou (outra moeda ainda sem a cotação do dia).'
    : `${count} movimentos a Pluggy atualizou e não identificou (outra moeda ainda sem a cotação do dia).`
}
