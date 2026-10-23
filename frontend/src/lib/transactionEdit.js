// Editar um lancamento no Extrato: o formulario a partir da linha e o PATCH.
// Puro, testado em transactionEdit.test.js.
import { shareFormFrom, sharePayload } from './sharing.js'

export function transactionEditForm(transaction) {
  return {
    amount: String(transaction.amount ?? ''),
    date: transaction.date || '',
    category_id: transaction.category_id || '',
    description: transaction.description || '',
    type: transaction.type,
    account_id: transaction.account_id || '',
    transfer_account_id: transaction.type === 'TRANSFER' ? transaction.transfer_account_id || '' : '',
    share: shareFormFrom(transaction),
  }
}

// O PATCH e parcial; transferencias so aceitam os campos que fazem sentido
// para elas (o backend recusa converter um tipo no outro). `amount` ja vem lido.
export function transactionEditPayload(transaction, form, amount, { sharing = false } = {}) {
  const payload = {
    amount,
    date: form.date,
    description: form.description,
  }
  // As contas so quando mudaram: a de um lancamento antigo pode estar
  // arquivada, e o servidor recusa escolher uma conta arquivada.
  if (form.account_id && form.account_id !== (transaction.account_id || '')) payload.account_id = form.account_id
  if (transaction.type === 'TRANSFER') {
    if (form.transfer_account_id && form.transfer_account_id !== (transaction.transfer_account_id || '')) {
      payload.transfer_account_id = form.transfer_account_id
    }
  } else {
    payload.type = form.type
    // A categoria pelo id, e so quando mudou: mandar o nome de volta tirava
    // um lancamento de "Alimentação › Outros" e o punha no "Outros" da raiz.
    if (form.category_id !== (transaction.category_id || '')) payload.category_id = form.category_id
  }
  // Sem mudar a divisao, o PATCH nem leva os campos (o servidor so confere
  // que o valor novo ainda cabe nela).
  if (sharing && JSON.stringify(form.share) !== JSON.stringify(shareFormFrom(transaction))) {
    Object.assign(payload, sharePayload(form.share))
  }
  return payload
}
