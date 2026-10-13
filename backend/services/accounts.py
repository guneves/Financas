"""Contas bancarias e categorias: a parte que outros modulos usam.

Todo lancamento precisa de uma conta (`resolve_account_id` cai na conta padrao)
e grava a categoria pelo *nome* em `transactions.category` (`resolve_category`).
"""

from db import serialize_metadata_row
from money import rounded_money
from validators import ValidationError, optional_string, require_string


DEFAULT_ACCOUNT_NAME = "Conta Principal"
DEFAULT_CATEGORY_SEEDS = (
    ("receita", "Receita", "INCOME"),
    ("investimento", "Investimento", "BOTH"),
    ("alimentacao", "Alimentação", "EXPENSE"),
    ("moradia", "Moradia", "EXPENSE"),
    ("transporte", "Transporte", "EXPENSE"),
    ("saude", "Saúde", "EXPENSE"),
    ("educacao", "Educação", "EXPENSE"),
    ("lazer", "Lazer", "EXPENSE"),
    ("servicos", "Serviços", "EXPENSE"),
    ("outros", "Outros", "EXPENSE"),
)


def serialize_account(row):
    item = serialize_metadata_row(row)
    if item:
        item["is_default"] = bool(item.get("is_default"))
        for key in ("balance", "initial_balance"):
            if key in item and item[key] is not None:
                item[key] = rounded_money(item[key])
    return item


def default_account_id(current_user_id):
    return f"acct:{current_user_id}"


def ensure_default_account(conn, current_user_id):
    """Garante que o usuario tenha ao menos uma conta e devolve o id dela.

    Contas nasceram na migration 007, mas usuarios criados depois dela e
    lancamentos vindos de outros fluxos (caixa de investimento, por exemplo)
    ainda precisam de um destino. A conta padrao e sempre criada com o mesmo id
    deterministico usado no backfill, para que nao existam duas "Conta
    Principal" para o mesmo usuario.
    """
    existing = conn.execute(
        """
        SELECT id FROM accounts
        WHERE user_id = ? AND archived_at IS NULL
        ORDER BY is_default DESC, created_at ASC
        LIMIT 1
        """,
        (current_user_id,),
    ).fetchone()
    if existing:
        return existing["id"]

    account_id = default_account_id(current_user_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO accounts (id, user_id, name, type, is_default)
        VALUES (?, ?, ?, 'CHECKING', 1)
        """,
        (account_id, current_user_id, DEFAULT_ACCOUNT_NAME),
    )
    return account_id


def seed_default_categories(conn, current_user_id):
    """Cria as 10 categorias iniciais para um usuario novo."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO categories (id, user_id, name, kind)
        VALUES (?, ?, ?, ?)
        """,
        [
            (f"cat:{current_user_id}:{slug}", current_user_id, name, kind)
            for slug, name, kind in DEFAULT_CATEGORY_SEEDS
        ],
    )


def fetch_account(conn, current_user_id, account_id):
    if not account_id:
        return None
    return conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, current_user_id),
    ).fetchone()


def require_account(conn, current_user_id, account_id, label="Conta"):
    account = fetch_account(conn, current_user_id, account_id)
    if not account:
        raise ValidationError(f"{label} nao encontrada.")
    if account["archived_at"]:
        raise ValidationError(f"{label} esta arquivada.")
    return account


def resolve_account_id(conn, current_user_id, payload, key="account_id", label="Conta"):
    """Conta informada no payload, ou a conta padrao quando omitida."""
    raw = payload.get(key)
    if raw in (None, ""):
        return ensure_default_account(conn, current_user_id)
    return require_account(conn, current_user_id, str(raw), label)["id"]


# Despesa/receita e transferencia dividem o indice do client_id: o mesmo id
# reenviado para a outra rota nao pode devolver, como se fosse sucesso, um
# lancamento de outro tipo.
CLIENT_ID_OTHER_KIND_MESSAGE = (
    "Este envio ja foi gravado como outro tipo de lancamento. Confira o extrato."
)


def fetch_transaction_by_client_id(conn, current_user_id, client_id):
    """O lancamento que um envio com este client_id ja criou (024), ou None.

    Despesa, receita e transferencia dividem a tabela e o indice unico, entao
    a consulta e a mesma para as duas rotas que criam.
    """
    if not client_id:
        return None
    return conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? AND client_id = ?",
        (current_user_id, client_id),
    ).fetchone()


def fetch_category(conn, current_user_id, category_id):
    if not category_id:
        return None
    return conn.execute(
        "SELECT * FROM categories WHERE id = ? AND user_id = ?",
        (category_id, current_user_id),
    ).fetchone()


def resolve_category(conn, current_user_id, payload, required=True):
    """Resolve (nome, id) da categoria de um lancamento.

    Aceita `category_id` (novo) ou `category` em texto (o que o app sempre
    mandou). O nome continua sendo gravado em transactions.category: e ele que
    o Dashboard agrupa e e o fallback caso a categoria seja apagada depois.
    """
    category_id = payload.get("category_id")
    if category_id not in (None, ""):
        row = fetch_category(conn, current_user_id, str(category_id))
        if not row:
            raise ValidationError("Categoria nao encontrada.")
        if row["archived_at"]:
            raise ValidationError("Categoria esta arquivada.")
        return row["name"], row["id"]

    if required:
        name = require_string(payload, "category", "Categoria")
    else:
        name = optional_string(payload, "category", max_length=255)
        if not name:
            return None, None

    row = conn.execute(
        "SELECT id FROM categories WHERE user_id = ? AND name = ? LIMIT 1",
        (current_user_id, name),
    ).fetchone()
    return name, row["id"] if row else None


def account_balance_rows(conn, current_user_id):
    """Saldo por conta: inicial + receitas - despesas -/+ transferencias.

    TRANSFER sai de account_id e entra em transfer_account_id, por isso aparece
    duas vezes aqui com sinais opostos e some do consolidado.
    """
    return conn.execute(
        """
        SELECT
            a.*,
            a.initial_balance
              + COALESCE((
                    SELECT SUM(
                        CASE t.type
                            WHEN 'INCOME' THEN t.amount
                            WHEN 'EXPENSE' THEN -t.amount
                            WHEN 'TRANSFER' THEN -t.amount
                            ELSE 0
                        END
                    )
                    FROM transactions t
                    WHERE t.user_id = a.user_id AND t.account_id = a.id
                ), 0)
              + COALESCE((
                    SELECT SUM(t.amount)
                    FROM transactions t
                    WHERE t.user_id = a.user_id
                      AND t.type = 'TRANSFER'
                      AND t.transfer_account_id = a.id
                ), 0) AS balance
        FROM accounts a
        WHERE a.user_id = ?
        ORDER BY a.archived_at IS NOT NULL, a.is_default DESC, a.name COLLATE NOCASE
        """,
        (current_user_id,),
    ).fetchall()
