"""Quem gravou uma linha de `transactions`: os valores de `source_type`.

Todo fluxo que materializa lancamentos sob demanda grava `source_type` e um
`source_id` deterministico; o indice unico `idx_transactions_user_source`
torna a segunda execucao um no-op. Um lancamento sem source_type foi digitado.
"""

# Ocorrencia de uma recorrencia (010): source_id = '<recorrencia>:<AAAA-MM-DD>'.
RECURRING_SOURCE_TYPE = "RECURRING_TRANSACTION"

# Importacao de extrato (013). O source_id e o hash da linha (ou o FITID do
# OFX), entao reimportar o mesmo arquivo nao duplica nada.
STATEMENT_IMPORT_SOURCE_TYPE = "STATEMENT_IMPORT"

# Caixa de uma compra/venda de investimento: source_id = id da movimentacao.
INVESTMENT_CASH_SOURCE_TYPE = "INVESTMENT_TRANSACTION"

# Provento pago na conta da carteira: source_id = id do provento
# (services/proceeds_cash.py, materializado na leitura).
INVESTMENT_PROCEED_SOURCE_TYPE = "INVESTMENT_PROCEED"

# Dinheiro da carteira (039): o que faz um lancamento ser aporte, resgate ou
# provento e a origem dele, nunca uma categoria. O aporte digitado e uma
# transferencia para a conta Corretora.
# Linha do extrato da corretora que nao e operacao nem provento (taxa, IR, renda
# fixa, services/broker_statement.py): source_id = o id da transacao na Pluggy.
BROKER_STATEMENT_SOURCE_TYPE = "BROKER_STATEMENT"
# Aplicacao ou resgate num fundo do proprio banco (RF High, Tesouro Reserva: Pluggy
# "Fixed income" numa conta corrente, 2026-10-31): sai do saldo, nunca e despesa nem
# receita. source_id = o id da transacao na Pluggy.
BANK_INVESTMENT_SOURCE_TYPE = "BANK_INVESTMENT"
INVESTMENT_SOURCE_TYPES = (
    INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE, BROKER_STATEMENT_SOURCE_TYPE,
    BANK_INVESTMENT_SOURCE_TYPE,
)

# O que saiu num mes de uma conta sem Pluggy (Inter), numa linha so: o liquido do
# que entrou nela (dono, 2026-10-31: nao e gasto). Tira o dinheiro do saldo e fica
# fora de todo total de despesa (Fluxo, Resumo, Orcamento, plano, Ritmo, Extrato).
# source_id = '<conta>:<AAAA-MM>'.
MONTH_SUMMARY_SOURCE_TYPE = "MONTH_SUMMARY"

# Pagamento de fatura: manual (pay-invoice) ou debito automatico (011,
# source_id = '<cartao>:<AAAA-MM>').
CC_INVOICE_PAYMENT_SOURCE_TYPE = "CC_INVOICE_PAYMENT"
CC_AUTOPAY_SOURCE_TYPE = "CC_AUTOPAY"
# O pagamento e o PAID dos itens nascem juntos em settle_invoice(); editar ou
# apagar so o lancamento deixaria a fatura quitada sem dinheiro saindo da conta.
INVOICE_PAYMENT_SOURCE_TYPES = {CC_INVOICE_PAYMENT_SOURCE_TYPE, CC_AUTOPAY_SOURCE_TYPE}
INVOICE_PAYMENT_LOCKED_MESSAGE = (
    "Este lancamento e o pagamento de uma fatura de cartao e fica vinculado a ela; "
    "nao pode ser editado nem excluido pelo extrato."
)

# Lancamento aprovado no Aprovar que veio do Open Finance (043): source_id = o
# id da transacao na Pluggy. O lancamento continua editavel como um digitado;
# a origem so impede que a mesma transacao vire dois lancamentos.
OPEN_FINANCE_SOURCE_TYPE = "OPEN_FINANCE"
