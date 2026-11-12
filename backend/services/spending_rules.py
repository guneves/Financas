"""O que uma linha de `transactions` e para as somas do mes, em SQL.

Quatro consultas somam o mes: o resumo e os paineis do Inicio
(services/home.py, home_panels.py), o plano do mes (monthly_plan.py) e o
orcamento (budgets.py). Cada uma escrevia de novo as mesmas condicoes ("e
pagamento de fatura", "e caixa da carteira", "e da conta global"...); aqui cada
condicao tem uma definicao so, e cada tela diz quais usa.

As telas ainda NAO somam igual, e isso esta fixado em
tests/test_month_spending_rules.py ate o dono decidir:

- o Inicio ignora a despesa/receita de uma conta Corretora (`brokerage_account_sql`);
  o plano e o orcamento contam (decisao "B2" de docs/next-steps.md);
- o pagamento de fatura antigo, reconhecido pelo nome da categoria: o Inicio
  compara o prefixo exato (`exact_case=True`), o plano e o orcamento usam LIKE,
  que ignora a caixa;
- o Inicio so tira o pagamento de fatura das despesas; o plano e o orcamento
  tiram a linha inteira (uma receita com esse nome de categoria tambem).

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


def invoice_payment_by_name_sql(row="t.", *, exact_case):
    """Pagamento de fatura de antes do pagamento pelo servidor: a categoria
    "Pagamento Fatura...". `exact_case`: o prefixo exato; senao LIKE (sem caixa)."""
    if exact_case:
        return (
            f"substr(COALESCE({row}category, ''), 1, {len(INVOICE_PAYMENT_CATEGORY_PREFIX)})"
            f" = '{INVOICE_PAYMENT_CATEGORY_PREFIX}'"
        )
    return f"COALESCE({row}category, '') LIKE '{INVOICE_PAYMENT_CATEGORY_PREFIX}%'"


def invoice_payment_sql(row="t.", *, exact_case):
    return f"({invoice_payment_by_origin_sql(row)} OR {invoice_payment_by_name_sql(row, exact_case=exact_case)})"


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
    linha do Inter, e a conta e em reais. A Corretora conta (ver o topo)."""
    return (
        f"{row}type <> 'TRANSFER'"
        f" AND NOT {invoice_payment_sql(row, exact_case=False)}"
        f" AND NOT {investment_cash_sql(row)}"
        f" AND NOT {month_summary_sql(row)}"
        f" AND {reais_account_sql(account)}"
    )
