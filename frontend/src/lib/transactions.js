// Aporte nao e despesa: o dinheiro sai da conta mas continua no patrimonio.
//
// No banco um aporte e uma linha EXPENSE comum (o saldo da conta precisa
// dela), entao a distincao e feita na leitura. Cobre o lancamento gerado por
// uma compra de investimento (source_type) e o lancado a mao na categoria
// Investimento.
export const INVESTMENT_CATEGORY = 'Investimento'

export const isInvestmentOutflow = (transaction) =>
  transaction?.type === 'EXPENSE' &&
  (transaction.source_type === 'INVESTMENT_TRANSACTION' || transaction.category === INVESTMENT_CATEGORY)

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
  accounts.reduce((acc, account) => {
    const value = account.balance_brl !== undefined ? account.balance_brl : account.balance
    return acc + (Number(value) || 0)
  }, 0)

export const openingBalanceTotal = (accounts = []) =>
  accounts.reduce((acc, account) => acc + (Number(account.initial_balance) || 0), 0)

export const activeAccounts = (accounts = []) => accounts.filter((account) => !account.archived_at)
