// Investimento no extrato: aporte nao e despesa e resgate nao e receita.
//
// As areas sao separadas: uma operacao da carteira so chega ao extrato quando
// o dono pede, operacao por operacao (o lancamento ligado, source_type), ou
// quando ele lanca a mao na categoria Investimento. No banco sao linhas
// EXPENSE / INCOME comuns (o saldo da conta precisa delas), entao a distincao
// e feita na leitura: o aporte sai da conta sem ser gasto, e o resgate volta
// sem ser renda.
export const INVESTMENT_CATEGORY = 'Investimento'

const isInvestmentRow = (transaction) =>
  transaction?.source_type === 'INVESTMENT_TRANSACTION' || transaction?.category === INVESTMENT_CATEGORY

export const isInvestmentOutflow = (transaction) =>
  transaction?.type === 'EXPENSE' && isInvestmentRow(transaction)

export const isInvestmentInflow = (transaction) =>
  transaction?.type === 'INCOME' && isInvestmentRow(transaction)

// Saldo consolidado das contas: a soma dos saldos que /api/accounts devolve
// (saldo inicial + movimentacoes, calculado no servidor). Passe a lista COM
// as arquivadas (`include_archived`): o lancamento de uma conta arquivada
// continua existindo e continua no consolidado. Somar `transactions` direto
// deixava o saldo inicial das contas de fora.
//
// Conta em moeda estrangeira entra pelo `balance_brl` (PTAX de hoje, no
// servidor); sem cambio disponivel ela fica de fora em vez de somar dolar
// como real.
export const consolidatedBalance = (accounts = []) =>
  accounts.reduce((acc, account) => acc + (accountBalanceBrl(account) || 0), 0)

// Saldo de uma conta em reais — o app e em reais, e o saldo de uma conta em
// moeda estrangeira so aparece convertido. Devolve null quando nao ha cambio
// hoje: quem mostra avisa, quem soma deixa de fora.
export function accountBalanceBrl(account) {
  const value = account?.balance_brl !== undefined ? account.balance_brl : account?.balance
  return value === null || value === undefined ? null : Number(value) || 0
}

export const openingBalanceTotal = (accounts = []) =>
  accounts.reduce((acc, account) => acc + (Number(account.initial_balance) || 0), 0)

export const activeAccounts = (accounts = []) => accounts.filter((account) => !account.archived_at)
