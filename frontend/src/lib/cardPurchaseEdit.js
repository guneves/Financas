// O corpo da edicao de uma compra no cartao (CardPurchaseEditSheet): so o que
// mudou. Puro: testado em cardPurchaseEdit.test.js.
//
// `target`: a compra como a tela a tem ({ description, category_id }).
// `form`: { description, category_id }. Devolve { payload } (null = nada mudou)
// ou { error }.
export function purchaseEditPayload(target, form) {
  const description = String(form?.description || '').trim()
  if (!description) return { error: 'Informe a descrição da compra.' }
  if (description.length > 500) return { error: 'A descrição pode ter até 500 caracteres.' }
  const payload = {}
  if (description !== String(target?.description || '').trim()) payload.description = description
  const categoryId = form?.category_id || ''
  if (categoryId && categoryId !== (target?.category_id || '')) payload.category_id = categoryId
  return { payload: Object.keys(payload).length ? payload : null }
}
