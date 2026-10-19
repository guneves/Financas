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
INVESTMENT_SOURCE_TYPES = (INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE)

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
