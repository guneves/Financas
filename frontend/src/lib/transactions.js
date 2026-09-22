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
