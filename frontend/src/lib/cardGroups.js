// Os cartoes da tela Cartoes: as faturas em aberto (credito) e as compras no
// debito (049) de cada cartao, juntas. Puro: testado em cardGroups.test.js.
import { shareSummary } from './sharing.js'

// Uma compra no debito de GET /api/cc-invoices (`debit_cards`): uma despesa da
// conta do cartao, sem fatura.
export function debitRow(purchase) {
  return {
    purchaseKey: `debit:${purchase.id}`,
    id: purchase.id,
    description: purchase.description || purchase.category || 'Compra no débito',
    category: purchase.category || 'Outros',
    category_id: purchase.category_id || null,
    purchase_date: purchase.date,
    amount: purchase.amount,
    attachmentCount: Number(purchase.attachment_count || 0),
    shareText: shareSummary(purchase),
  }
}

// `creditGroups`: os cartoes com fatura em aberto (cardGroupOf de Cartoes.jsx),
// na ordem do servidor. `debitCards`: `debit_cards` do servidor. Cada grupo
// ganha `debit` ({...cartao, rows}) quando o cartao tem a funcao debito; um
// cartao sem fatura em aberto entra so se tem compra no debito, depois dos
// outros (`withoutInvoices`).
export function mergeCardGroups(creditGroups, debitCards) {
  const withRows = (card) => (card ? { ...card, rows: (card.purchases || []).map(debitRow) } : null)
  const debitById = new Map((debitCards || []).map((card) => [card.card_id, card]))
  const merged = (creditGroups || []).map((group) => ({ ...group, debit: withRows(debitById.get(group.cardId)) }))
  const seen = new Set(merged.map((group) => group.cardId))
  for (const card of debitCards || []) {
    if (seen.has(card.card_id) || (card.purchases || []).length === 0) continue
    merged.push({ cardId: card.card_id, cardName: card.card_name, invoices: [], total: 0, debit: withRows(card), withoutInvoices: true })
  }
  return merged
}
