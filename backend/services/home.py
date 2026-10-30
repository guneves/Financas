"""Inicio: o saldo em contas, as contas e o fluxo do mes (GET /api/home).

O `buildMonthlyFlow()` + `bankingTransactions()` que o cliente rodava sobre
todo o historico, aqui, em centavos inteiros (proposta home-attention-invoices.md):

1. A visao bancaria. Linha que nao e transferencia numa conta Corretora fica
   de fora; transferencia entre dois bancos (ou entre duas Corretoras) nao e
   fluxo; banco -> Corretora e aporte do lado do banco, e a volta, resgate.
   O caixa da carteira (`INVESTMENT_SOURCE_TYPES`) numa conta de banco tambem
   e aporte (saida) ou resgate (entrada): investimento e a origem da linha,
   nunca a categoria (039).
2. Receita e despesa sao so a parte do dono (032); a dos outros vai para
   `others_received` / `others_paid`. O pagamento de fatura nunca e despesa
   (ele e a soma de compras ja contadas), mas mexe no saldo.
3. A compra no cartao conta inteira no mes da compra, paga ou em aberto; o
   estorno (033) abate inteiro no mes dele e nunca e dividido.
4. O saldo de fim de mes parte do saldo inicial das contas em reais que nao
   sao Corretora (arquivadas inclusive; a Conta global fica de fora) mais tudo antes da janela.

Cada linha vira centavos como no cliente (`Math.round(x * 100)`): a soma e de
inteiros, sem erro de ponto flutuante. `local_today()` e lido por nome aqui.
"""

from decimal import Decimal

from money import rounded_money
from services import auto_record, review
from services.accounts import account_balance_rows, ensure_default_account, serialize_account
from services.card_invoices import invoice_summary, next_invoices, open_invoices
from services.fx import with_balance_in_brl
from services.investments import PORTFOLIO_ACCOUNT_TYPE
from services.invoices import apply_due_autopay, local_today
from services.proceeds_cash import apply_paid_proceeds
from source_types import INVESTMENT_SOURCE_TYPES, INVOICE_PAYMENT_SOURCE_TYPES
from validators import ValidationError, shift_month

MAX_MONTHS = 24
INVOICE_PAYMENT_CATEGORY_PREFIX = "Pagamento Fatura"


def _quoted(values):
    return ", ".join(f"'{value}'" for value in sorted(values))


def investment_flow_sql(row="t.", origin="origin.", target="target."):
    """As condicoes SQL de aporte e de resgate vistos das contas.

    Uma regra so para o "Investido" do Inicio (aqui) e o do plano do mes
    (`month_investment_flow()`): os dois nunca discordam. `origin`/`target` sao
    as contas de `account_id` e `transfer_account_id` (LEFT JOIN).
    """
    from_bank = f"COALESCE({origin}type, '') != '{PORTFOLIO_ACCOUNT_TYPE}'"
    to_portfolio = f"COALESCE({target}type, '') = '{PORTFOLIO_ACCOUNT_TYPE}'"
    portfolio_cash = f"COALESCE({row}source_type, '') IN ({_quoted(INVESTMENT_SOURCE_TYPES)})"
    return {
        "aporte": (
            f"(({row}type = 'TRANSFER' AND {from_bank} AND {to_portfolio})"
            f" OR ({row}type = 'EXPENSE' AND {from_bank} AND {portfolio_cash}))"
        ),
        "resgate": (
            f"(({row}type = 'TRANSFER' AND NOT {from_bank} AND NOT {to_portfolio})"
            f" OR ({row}type = 'INCOME' AND {from_bank} AND {portfolio_cash}))"
        ),
        "from_bank": from_bank,
        "portfolio_cash": portfolio_cash,
    }


def _cents(expression):
    return f"CAST(ROUND(({expression}) * 100) AS INTEGER)"


def _others_cents(row=""):
    return _cents(
        f"CASE {row}share_mode WHEN 'OTHERS' THEN {row}amount"
        f" WHEN 'SPLIT' THEN COALESCE({row}share_others_amount, 0) ELSE 0 END"
    )


def banking_month_rows(conn, current_user_id):
    """Por mes (AAAA-MM), em centavos: cash, income, expense, invested,
    redeemed, others_paid e others_received das contas, na visao bancaria."""
    cases = investment_flow_sql()
    from_bank = cases["from_bank"]
    amount = _cents("t.amount")
    others = _others_cents("t.")
    invoice_payment = (
        f"(COALESCE(t.source_type, '') IN ({_quoted(INVOICE_PAYMENT_SOURCE_TYPES)})"
        f" OR substr(COALESCE(t.category, ''), 1, {len(INVOICE_PAYMENT_CATEGORY_PREFIX)})"
        f" = '{INVOICE_PAYMENT_CATEGORY_PREFIX}')"
    )
    plain = f"t.type != 'TRANSFER' AND {from_bank} AND NOT {cases['portfolio_cash']}"
    return conn.execute(
        f"""
        SELECT
          substr(t.date, 1, 7) AS month,
          SUM(CASE
                WHEN t.type = 'TRANSFER' AND {cases['aporte']} THEN -{amount}
                WHEN t.type = 'TRANSFER' AND {cases['resgate']} THEN {amount}
                WHEN t.type = 'TRANSFER' OR NOT {from_bank} THEN 0
                WHEN t.type = 'INCOME' THEN {amount}
                WHEN t.type = 'EXPENSE' THEN -{amount}
                ELSE 0 END) AS cash,
          SUM(CASE WHEN {cases['aporte']} THEN {amount} ELSE 0 END) AS invested,
          SUM(CASE WHEN {cases['resgate']} THEN {amount} ELSE 0 END) AS redeemed,
          SUM(CASE WHEN {plain} AND t.type = 'INCOME' THEN {amount} - {others} ELSE 0 END) AS income,
          SUM(CASE WHEN {plain} AND t.type = 'INCOME' THEN {others} ELSE 0 END) AS others_received,
          SUM(CASE WHEN {plain} AND t.type = 'EXPENSE' AND NOT {invoice_payment}
                   THEN {amount} - {others} ELSE 0 END) AS expense,
          SUM(CASE WHEN {plain} AND t.type = 'EXPENSE' AND NOT {invoice_payment}
                   THEN {others} ELSE 0 END) AS others_paid
        FROM transactions t
        LEFT JOIN accounts origin ON origin.id = t.account_id AND origin.user_id = t.user_id
        LEFT JOIN accounts target ON target.id = t.transfer_account_id AND target.user_id = t.user_id
        WHERE t.user_id = ?
          -- A conta global (outra moeda) fica fora dos totais em reais; a
          -- transferencia para ela e so transferencia.
          AND (t.type = 'TRANSFER' OR COALESCE(origin.currency, 'BRL') = 'BRL')
        GROUP BY substr(t.date, 1, 7)
        """,
        (current_user_id,),
    ).fetchall()


def card_month_rows(conn, current_user_id, first_month, last_month):
    """Compras no cartao por mes da compra, pagas e em aberto, em centavos."""
    amount = _cents("amount")
    others = _others_cents()
    return conn.execute(
        f"""
        SELECT
          substr(purchase_date, 1, 7) AS month,
          SUM(CASE WHEN kind = 'REFUND' THEN -{amount} ELSE {amount} - {others} END) AS expense,
          SUM(CASE WHEN kind = 'REFUND' THEN 0 ELSE {others} END) AS others_paid
        FROM cc_expenses
        WHERE user_id = ? AND substr(purchase_date, 1, 7) BETWEEN ? AND ?
        GROUP BY substr(purchase_date, 1, 7)
        """,
        (current_user_id, first_month, last_month),
    ).fetchall()


def is_portfolio(account):
    return account.get("type") == PORTFOLIO_ACCOUNT_TYPE


def is_foreign(account):
    """A Conta global (047): conta em outra moeda. Fica fora do saldo em contas
    (dono, 2026-10-30): so aparece na propria tela e em Ajustes > Contas."""
    return str(account.get("currency") or "BRL").upper() != "BRL"


def _reais(cents):
    return rounded_money(Decimal(int(cents or 0)) / 100)


FLOW_FIELDS = ("income", "expense", "invested", "redeemed", "others_paid", "others_received")


def monthly_flow(conn, current_user_id, accounts, keys):
    """`flow` de /api/home: um item por mes de `keys`, em reais."""
    by_month = {key: dict.fromkeys((*FLOW_FIELDS, "cash"), 0) for key in keys}
    opening = sum(
        int(Decimal(str(account.get("initial_balance") or 0)).scaleb(2).to_integral_value())
        for account in accounts
        if not is_portfolio(account) and not is_foreign(account)
    )
    for row in banking_month_rows(conn, current_user_id):
        month = row["month"] or ""
        if month < keys[0]:
            opening += int(row["cash"] or 0)
            continue
        target = by_month.get(month)
        if target is None:
            continue
        for field in (*FLOW_FIELDS, "cash"):
            target[field] += int(row[field] or 0)
    for row in card_month_rows(conn, current_user_id, keys[0], keys[-1]):
        target = by_month.get(row["month"])
        if target is not None:
            target["expense"] += int(row["expense"] or 0)
            target["others_paid"] += int(row["others_paid"] or 0)

    flow = []
    running = opening
    for key in keys:
        month = by_month[key]
        running += month["cash"]
        net = (
            month["income"] - month["expense"] - month["invested"] + month["redeemed"]
            + month["others_received"] - month["others_paid"]
        )
        flow.append({
            "month": key,
            **{field: _reais(month[field]) for field in FLOW_FIELDS},
            "net": _reais(net),
            "balance": _reais(running),
        })
    return flow


def parse_months(raw):
    if raw in (None, ""):
        return 1
    try:
        months = int(str(raw).strip())
    except ValueError:
        raise ValidationError("Meses deve ser um numero inteiro.") from None
    if not 1 <= months <= MAX_MONTHS:
        raise ValidationError(f"Meses deve ficar entre 1 e {MAX_MONTHS}.")
    return months


def prepare_reads(conn, current_user_id, today):
    """O que as leituras substituidas faziam antes de ler: a conta padrao, o
    debito automatico vencido, os proventos pagos e o que esperava o prazo
    para gravar sozinho (045: o Samsung sem o banco, a transferencia sem par)."""
    ensure_default_account(conn, current_user_id)
    auto_record.record_due(conn, current_user_id, today=today)
    apply_due_autopay(conn, current_user_id, today=today)
    apply_paid_proceeds(conn, current_user_id)


def account_list(conn, current_user_id):
    """Todas as contas, arquivadas e Corretora inclusive, com `balance_brl`:
    o que GET /api/accounts?include_archived=1 devolve."""
    return [
        with_balance_in_brl(conn, current_user_id, serialize_account(row))
        for row in account_balance_rows(conn, current_user_id)
    ]


def consolidated_balance(accounts):
    """Saldo em contas: a soma do `balance` de toda conta em reais que nao e
    Corretora, arquivadas inclusive. A Conta global (outra moeda) nao entra
    (dono, 2026-10-30): o total e a soma das contas listadas."""
    total = sum(
        (Decimal(str(account["balance_brl"])) for account in accounts
         if not is_portfolio(account) and not is_foreign(account)
         and account.get("balance_brl") is not None),
        Decimal("0"),
    )
    return rounded_money(total)


def balance_projections(balance, invoices, today):
    """O cabecalho de Extrato e Cartoes: o saldo em contas menos o cartao em
    aberto — ate a fatura do mes que vem (`next_month`) ou todo (`global`).
    Estorno abate (o total da fatura ja e com sinal)."""
    next_key = shift_month(today.strftime("%Y-%m"), 1)
    up_to_next = sum(
        (item["total"] for item in invoices if item["key"] <= next_key), Decimal("0")
    )
    everything = sum((item["total"] for item in invoices), Decimal("0"))
    base = Decimal(str(balance))
    return {
        "next_month": rounded_money(base - up_to_next),
        "global": rounded_money(base - everything),
    }


def build_home(conn, current_user_id, months=1):
    today = local_today()
    prepare_reads(conn, current_user_id, today)
    accounts = account_list(conn, current_user_id)
    current = today.strftime("%Y-%m")
    keys = [shift_month(current, offset) for offset in range(-(months - 1), 1)]
    flow = monthly_flow(conn, current_user_id, accounts, keys)
    last = flow[-1]

    invoices = open_invoices(conn, current_user_id, today)["invoices"]
    upcoming = next_invoices(invoices)
    closing_dates = sorted(item["closing_date"] for item in upcoming if not item["closed"])
    balance = consolidated_balance(accounts)
    return {
        "today": today.strftime("%Y-%m-%d"),
        "month": current,
        "consolidated_balance": balance,
        # Gravados sozinhos que esperam o dono dizer "e meu" e a categoria (045).
        "review_count": review.count(conn, current_user_id),
        "projections": balance_projections(balance, invoices, today),
        "accounts": accounts,
        "summary": {
            "income": last["income"],
            "expense": last["expense"],
            "result": rounded_money(Decimal(str(last["income"])) - Decimal(str(last["expense"]))),
            "invested": last["invested"],
            "redeemed": last["redeemed"],
            "investment_net": rounded_money(Decimal(str(last["invested"])) - Decimal(str(last["redeemed"]))),
            "others_paid": last["others_paid"],
            "others_received": last["others_received"],
            "others_net": rounded_money(Decimal(str(last["others_received"])) - Decimal(str(last["others_paid"]))),
        },
        "flow": flow,
        "next_invoices": [invoice_summary(item) for item in upcoming],
        "next_invoices_total": rounded_money(sum((item["total"] for item in upcoming), Decimal("0"))),
        "next_closing_date": closing_dates[0] if closing_dates else None,
    }
