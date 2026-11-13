"""O que uma linha de `transactions` e para as somas do mes, em SQL.

Quatro consultas somam o mes: o resumo e os paineis do Inicio
(services/home.py, home_panels.py), o plano do mes (monthly_plan.py) e o
orcamento (budgets.py). Cada uma escrevia de novo as mesmas condicoes ("e
pagamento de fatura", "e caixa da carteira", "e da conta global"...); aqui cada
condicao tem uma definicao so, e cada tela diz quais usa.

As telas somam igual (dono 2026-11-13, tests/test_month_spending_rules.py):

- a despesa/receita de uma conta Corretora nao conta em nenhuma: o plano e o
  orcamento seguem o Inicio (`brokerage_account_sql`);
- o pagamento de fatura antigo, reconhecido pelo nome da categoria, e comparado
  pelo prefixo sem diferenca de caixa em todas;
- o pagamento de fatura sai das despesas e das receitas em todas (uma receita
  com esse nome de categoria tambem nao e receita).

Todas as expressoes recebem o alias com ponto (`"t."`, `"origin."`) e usam so
constantes do codigo: nada de valor do usuario entra no SQL.
"""

from source_types import INVESTMENT_SOURCE_TYPES, INVOICE_PAYMENT_SOURCE_TYPES, MONTH_SUMMARY_SOURCE_TYPE

# O texto de transactions.category de um pagamento de fatura (services/invoices.py).
INVOICE_PAYMENT_CATEGORY_PREFIX = "Pagamento Fatura"
# A conta da carteira (services/investments.PORTFOLIO_ACCOUNT_TYPE): aqui para
# este modulo nao depender de investimentos.
BROKERAGE_ACCOUNT_TYPE = "BROKERAGE"


def quoted(values):
    return ", ".join(f"'{value}'" for value in sorted(values))


def invoice_payment_by_origin_sql(row="t."):
    """Pagamento de fatura gravado pelo servidor (pay-invoice, debito automatico)."""
    return f"COALESCE({row}source_type, '') IN ({quoted(INVOICE_PAYMENT_SOURCE_TYPES)})"


def invoice_payment_by_name_sql(row="t."):
    """Pagamento de fatura de antes do pagamento pelo servidor: a categoria
    comeca com "Pagamento Fatura", em qualquer caixa (dono 2026-11-13). LOWER
    sobre o prefixo, e nao LIKE, para nao depender de `case_sensitive_like`."""
    return (
        f"LOWER(substr(COALESCE({row}category, ''), 1, {len(INVOICE_PAYMENT_CATEGORY_PREFIX)}))"
        f" = '{INVOICE_PAYMENT_CATEGORY_PREFIX.lower()}'"
    )


def invoice_payment_sql(row="t."):
    return f"({invoice_payment_by_origin_sql(row)} OR {invoice_payment_by_name_sql(row)})"


def investment_cash_sql(row="t."):
    """Caixa da carteira (039): aporte, resgate, provento, extrato da corretora,
    fundo do banco. Nunca despesa nem receita."""
    return f"COALESCE({row}source_type, '') IN ({quoted(INVESTMENT_SOURCE_TYPES)})"


def month_summary_sql(row="t."):
    """A linha do Inter (o liquido do mes): mexe no saldo, nunca e gasto."""
    return f"COALESCE({row}source_type, '') = '{MONTH_SUMMARY_SOURCE_TYPE}'"


def reais_account_sql(account="a."):
    """A conta e em reais (a conta global, em outra moeda, fica fora dos totais)."""
    return f"COALESCE({account}currency, 'BRL') = 'BRL'"


def brokerage_account_sql(account="a."):
    return f"COALESCE({account}type, '') = '{BROKERAGE_ACCOUNT_TYPE}'"


def plan_row_sql(row="t.", account="a."):
    """A linha que o plano do mes e o orcamento somam (despesa ou receita):
    nao e transferencia, nem pagamento de fatura, nem caixa da carteira, nem a
    linha do Inter, e a conta e em reais e nao e a Corretora (ver o topo)."""
    return (
        f"{row}type <> 'TRANSFER'"
        f" AND NOT {invoice_payment_sql(row)}"
        f" AND NOT {brokerage_account_sql(account)}"
        f" AND NOT {investment_cash_sql(row)}"
        f" AND NOT {month_summary_sql(row)}"
        f" AND {reais_account_sql(account)}"
    )
