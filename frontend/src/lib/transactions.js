// Investimento no extrato: aporte nao e despesa e resgate nao e receita.
//
// Investimento nao e categoria (039): o que faz uma linha ser aporte, resgate
// ou provento e a origem dela — o caixa de uma operacao ou o provento pago na
// conta da carteira (source_type) — ou, vista da area bancaria, a
// transferencia entre um banco e a Corretora (bankingTransactions). O aporte
// digitado a mao e essa transferencia. No banco o caixa e o provento sao
// linhas EXPENSE / INCOME comuns (o saldo da conta precisa delas), entao a
// distincao e feita na leitura.
export const INVESTMENT_SOURCE_TYPES = ['INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED']

// Estorno no cartao (033): uma linha da fatura com kind = 'REFUND' e valor
// positivo, que abate a fatura em vez de somar. Toda soma de compras no
// cartao passa por cardSignedAmount().
export const isCardRefund = (expense) => expense?.kind === 'REFUND'

export const cardSignedAmount = (expense) => {
  const amount = Number(expense?.amount) || 0
  return isCardRefund(expense) ? -amount : amount
}

// A compra no cartao e o client_id dela (035): todas as parcelas o dividem, e
// duas compras iguais (mesmo cartao, descricao, data e valor) tem cada uma o
// seu — duas corridas de Uber no mesmo dia sao duas linhas, nao uma. Uma linha
// sem client_id (do caminho antigo) cai na chave antiga.
export function cardPurchaseKey(expense) {
  if (expense?.client_id) return `compra:${expense.client_id}`
  return [
    expense?.card_id || 'sem-cartao',
    expense?.description || 'sem-descricao',
    expense?.purchase_date || 'sem-data',
    expense?.category || 'sem-categoria',
    String(expense?.installment_info || '1/1').split('/').pop(),
    expense?.kind || 'PURCHASE',
  ].join('|')
}

const isInvestmentRow = (transaction) =>
  INVESTMENT_SOURCE_TYPES.includes(transaction?.source_type) || Boolean(transaction?.portfolio_transfer)

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
//
// Conta Corretora fica de fora (dono, 2026-10-17): o dinheiro parado na
// corretora e da carteira, nao "saldo em conta" (bankingAccounts).
export const consolidatedBalance = (accounts = []) =>
  bankingAccounts(accounts).reduce((acc, account) => acc + (accountBalanceBrl(account) || 0), 0)

// Saldo de uma conta em reais — o app e em reais, e o saldo de uma conta em
// moeda estrangeira so aparece convertido. Devolve null quando nao ha cambio
// hoje: quem mostra avisa, quem soma deixa de fora.
export function accountBalanceBrl(account) {
  const value = account?.balance_brl !== undefined ? account.balance_brl : account?.balance
  return value === null || value === undefined ? null : Number(value) || 0
}

export const openingBalanceTotal = (accounts = []) =>
  bankingAccounts(accounts).reduce((acc, account) => acc + (Number(account.initial_balance) || 0), 0)

export const activeAccounts = (accounts = []) => accounts.filter((account) => !account.archived_at)

// A conta da carteira (lib/portfolioAccount.js) e toda conta Corretora: o que
// esta nela e da area de investimentos. A area bancaria (Inicio, o "Saldo em
// contas" do Extrato) le so as outras.
export const isPortfolioAccount = (account) => account?.type === 'BROKERAGE'

export const bankingAccounts = (accounts = []) => accounts.filter((account) => !isPortfolioAccount(account))

// O saldo das contas Corretora, que so a area de investimentos mostra.
export const portfolioCashBalance = (accounts = []) =>
  accounts.filter(isPortfolioAccount).reduce((acc, account) => acc + (accountBalanceBrl(account) || 0), 0)

// Os lancamentos vistos da area bancaria: o que acontece dentro de uma conta
// Corretora (compra, venda, provento) sai, e a transferencia entre um banco e
// a corretora vira o que ela e para o banco — aporte (o dinheiro foi para a
// carteira) ou resgate (voltou dela). Assim a curva de saldo do Inicio termina
// no mesmo saldo do topo, que tambem nao conta a corretora.
export function bankingTransactions(transactions = [], accounts = []) {
  const portfolioIds = new Set(accounts.filter(isPortfolioAccount).map((account) => account.id))
  if (!portfolioIds.size) return transactions
  const result = []
  transactions.forEach((transaction) => {
    const fromPortfolio = portfolioIds.has(transaction.account_id)
    if (transaction.type !== 'TRANSFER') {
      if (!fromPortfolio) result.push(transaction)
      return
    }
    const toPortfolio = portfolioIds.has(transaction.transfer_account_id)
    if (fromPortfolio === toPortfolio) {
      if (!fromPortfolio) result.push(transaction)
      return
    }
    result.push({
      ...transaction,
      type: toPortfolio ? 'EXPENSE' : 'INCOME',
      account_id: toPortfolio ? transaction.account_id : transaction.transfer_account_id,
      transfer_account_id: null,
      category: toPortfolio ? 'Aporte' : 'Resgate',
      portfolio_transfer: true,
    })
  })
  return result
}

// POST /api/recurring/run devolve em `blocked` as recorrencias com ocorrencia
// vencida numa conta arquivada: elas nao lancam ate o dono trocar a conta.
export function blockedRecurringMessage(blocked = []) {
  if (!blocked.length) return ''
  const names = blocked.map((item) => `"${item.description || 'Sem descrição'}" (${item.account_name})`).join(', ')
  return blocked.length === 1
    ? `A recorrência ${names} está numa conta arquivada e não foi lançada. Edite a recorrência e escolha outra conta.`
    : `${blocked.length} recorrências estão em contas arquivadas e não foram lançadas: ${names}. Edite cada uma e escolha outra conta.`
}
