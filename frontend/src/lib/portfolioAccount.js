// Porte: mudou um, muda o outro, com um teste de cada lado. Par nativo:
// android/.../rules/PortfolioAccount.kt (PortfolioAccountTest.kt), os mesmos casos de portfolioAccount.test.js.
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
// `fresh`: ainda nao passou pela lista de contas (cashLinkWithAccounts decide o padrao).
export const emptyCashLink = () => ({ enabled: true, accountId: '', missing: false, fresh: true })

// Investimentos so pela Pluggy (Fase 3): a Corretora alimentada pela Pluggy
// (`pluggy: true` em GET /api/accounts) recebe sozinha o que a corretora faz, e o
// servidor recusa uma operacao digitada com o caixa nela. Por isso o padrao, ali,
// e "Não descontar de nenhuma conta" (ou outra conta), nunca a Corretora.
export const PLUGGY_FED_NOTE = 'A Corretora é atualizada pela Pluggy: o que a corretora faz entra sozinho. '
  + 'Por isso o padrão é não descontar dela; escolha a Corretora se quiser lançar o caixa à mão.'

export function pluggyFedPortfolio(accounts) {
  return Boolean(portfolioAccounts(accounts)[0]?.pluggy)
}

// O valor do campo quando a lista de contas chega: a falta de conta da
// carteira, o padrao de uma operacao nova (desligado na Corretora da Pluggy) e a
// conta da carteira quando ligado. Puro, o mesmo do CashLinkField.
export function cashLinkWithAccounts(value, accounts) {
  const portfolio = portfolioAccounts(accounts)
  const next = { ...value, missing: portfolio.length === 0 }
  if (next.fresh) {
    next.fresh = false
    if (portfolio[0]?.pluggy) next.enabled = false
  }
  if (next.enabled && !next.accountId && portfolio[0]) next.accountId = portfolio[0].id
  return next
}

export function cashLinkFromMetadata(metadata) {
  const accountId = typeof metadata?.cash_account_id === 'string' ? metadata.cash_account_id.trim() : ''
  return { enabled: Boolean(accountId), accountId, missing: false }
}

// A escolhida (a operacao gravada, ou o que o "Lançar" da Pluggy pede) e a Corretora da Pluggy?
export function isPluggyFedAccount(accounts, accountId) {
  return Boolean(accountId) && Boolean((accounts || []).find((account) => account.id === accountId)?.pluggy)
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
