// A conta da carteira (dono, 2026-10-17): uma conta do tipo Corretora em reais
// e a conta de onde as operacoes saem (e para onde a venda e o resgate voltam).
// Toda operacao nova vai para o Extrato nessa conta, a nao ser que o dono marque
// "Não descontar de nenhuma conta". O backend tem a mesma regra
// (`portfolio_cash_account_id()` em services/investments.py) para quem nao manda
// a chave; a tela manda sempre. Modulo puro: testado com node --test.

export const PORTFOLIO_ACCOUNT_TYPE = 'BROKERAGE'

export const NO_PORTFOLIO_ACCOUNT_MESSAGE = 'Vincule uma conta à carteira antes: cadastre uma conta do tipo Corretora em Ajustes › Contas.'
export const PICK_ACCOUNT_MESSAGE = 'Escolha a conta da carteira, ou marque “Não descontar de nenhuma conta”.'

// O lancamento ligado e sempre em reais.
export const isBrlAccount = (account) => !account.currency || String(account.currency).toUpperCase() === 'BRL'

// As contas da carteira, na ordem da lista de contas (a padrao primeiro, depois
// o nome — a mesma do backend), so as ativas em reais.
export function portfolioAccounts(accounts) {
  return (accounts || []).filter((account) => (
    account.type === PORTFOLIO_ACCOUNT_TYPE && !account.archived_at && isBrlAccount(account)
  ))
}

export function pickPortfolioAccountId(accounts) {
  return portfolioAccounts(accounts)[0]?.id || ''
}

// O valor do campo e { enabled, accountId, missing }: `enabled` falso e a marca
// "não descontar de nenhuma conta"; `missing` diz que o dono ainda nao tem conta
// da carteira (a tela preenche quando a lista de contas chega).
export const emptyCashLink = () => ({ enabled: true, accountId: '', missing: false })

export function cashLinkFromMetadata(metadata) {
  const accountId = typeof metadata?.cash_account_id === 'string' ? metadata.cash_account_id.trim() : ''
  return { enabled: Boolean(accountId), accountId, missing: false }
}

// O pedaco do metadata, sempre explicito: a conta, ou `null` para nao descontar
// de lugar nenhum (sem a chave o backend usaria a conta da carteira). Uma
// operacao nova sem conta da carteira cadastrada e recusada aqui, com a
// mensagem que leva a Ajustes; a edicao (`editing`) de uma operacao antiga nao.
export function cashLinkMetadata(value, { editing = false } = {}) {
  if (!editing && value?.missing) throw new Error(NO_PORTFOLIO_ACCOUNT_MESSAGE)
  if (!value?.enabled) return { cash_account_id: null }
  const accountId = String(value.accountId || '')
  if (!accountId) throw new Error(PICK_ACCOUNT_MESSAGE)
  return { cash_account_id: accountId }
}
