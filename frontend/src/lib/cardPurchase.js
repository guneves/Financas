// As parcelas de uma compra no cartao, a partir de GET /api/cc-expenses/candidates
// (o servidor ja as acha pelo client_id, 035). Puro, testado em cardPurchase.test.js.

const toCents = (value) => Math.round(Number(value || 0) * 100)

function installmentCount(info) {
  const total = Number(String(info || '').split('/')[1])
  return Number.isFinite(total) && total > 0 ? total : 1
}

// Uma linha sem client_id (do caminho antigo) cai na chave antiga no
// servidor; ai valor e parcelas ainda separam compras diferentes. As
// parcelas de uma compra diferem em ate 1 centavo (100/3 = 33,34 + 33,33...).
export function purchaseInstallments(candidates, purchase) {
  const purchaseCents = toCents(purchase.amount)
  const total = purchase.installmentTotal || 1
  return (candidates || []).filter((item) => (
    Math.abs(toCents(item.amount) - purchaseCents) <= 1 && installmentCount(item.installment_info) === total
  ))
}

// O estorno de uma compra comeca pelo total dela: a soma das parcelas, em
// centavos. Parcela x quantidade errava o centavo que a divisao poe na primeira.
// Sem as parcelas (falhou a busca), fica essa estimativa.
export function refundPrefillAmount(purchase, candidates) {
  const found = purchaseInstallments(candidates, purchase)
  const cents = found.length
    ? found.reduce((sum, item) => sum + toCents(item.amount), 0)
    : toCents(purchase.amount) * (purchase.installmentTotal || 1)
  return cents / 100
}
