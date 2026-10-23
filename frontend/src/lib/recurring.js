// Edicao de uma recorrencia em Recorrentes: valor e conta. Puro, testado em
// recurring.test.js. Uma recorrencia numa conta arquivada nao lanca (/run a
// devolve em `blocked`) ate o dono escolher outra conta aqui.
import { parseMoneyInput } from './monthlyPlan.js'

// As contas ativas (a lista de /api/accounts nao traz as arquivadas) e, quando
// a da recorrencia nao esta entre elas, ela mesma no topo, so para mostrar a
// atual: nao se escolhe de volta uma conta arquivada.
export function recurringAccountOptions(item, accounts = []) {
  const options = accounts.map((account) => ({ id: account.id, label: account.name, disabled: false }))
  if (item?.account_id && !accounts.some((account) => account.id === item.account_id)) {
    options.unshift({ id: item.account_id, label: 'Conta arquivada', disabled: true })
  }
  return options
}

// O PATCH leva so o que mudou; a conta, so quando outra foi escolhida (nunca
// "" — o servidor nao troca a conta de uma recorrencia por "a padrao" sozinho).
export function recurringEditPatch(item, draft) {
  const patch = {}
  const amount = parseMoneyInput(draft.amount)
  if (amount !== null && Number(amount) !== Number(item.amount)) patch.amount = amount
  if (draft.account_id && draft.account_id !== (item.account_id || '')) patch.account_id = draft.account_id
  return patch
}
