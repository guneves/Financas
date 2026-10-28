"""Contas bancarias e categorias: a parte que outros modulos usam.

Todo lancamento precisa de uma conta (`resolve_account_id` cai na conta padrao)
e grava a categoria pelo *nome* em `transactions.category` (`resolve_category`).
"""

from db import serialize_metadata_row
from money import parse_money, rounded_money
from services.fx import normalize_currency
from validators import ValidationError, optional_string, require_string


DEFAULT_ACCOUNT_NAME = "Conta Principal"
DEFAULT_CATEGORY_SEEDS = (
    ("receita", "Receita", "INCOME"),
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


# A conta padrao, quando nenhuma ativa esta marcada: a primeira que nao e da
# carteira (Corretora, cujo saldo so aparece em Investimentos), pelo nome — a
# ordem da lista de contas, que e a que as telas mostram. A marcada e gravada,
# para servidor e telas lerem a mesma (is_default).
# A padrao recebe o lancamento sem conta, em reais: nunca a Corretora nem a
# conta global (outra moeda), se houver outra.
DEFAULT_ACCOUNT_ORDER = (
    "is_default DESC, type = 'BROKERAGE', COALESCE(currency, 'BRL') <> 'BRL', name COLLATE NOCASE, created_at, id"
)


def ensure_default_account(conn, current_user_id):
    """Garante que o usuario tenha uma conta padrao ativa e devolve o id dela.

    Contas nasceram na migration 007, mas usuarios criados depois dela e
    lancamentos vindos de outros fluxos (caixa de investimento, por exemplo)
    ainda precisam de um destino. Sem conta ativa, cria "Conta Principal" com o
    id deterministico do backfill, para que nao existam duas. Com contas mas
    nenhuma padrao (a padrao foi arquivada, ou virou Corretora), a escolhida
    por DEFAULT_ACCOUNT_ORDER passa a ser a padrao.
    """
    existing = conn.execute(
        f"""
        SELECT id, is_default FROM accounts
        WHERE user_id = ? AND archived_at IS NULL
        ORDER BY {DEFAULT_ACCOUNT_ORDER}
        LIMIT 1
        """,
        (current_user_id,),
    ).fetchone()
    if existing:
        if not existing["is_default"]:
            conn.execute(
                "UPDATE accounts SET is_default = 1 WHERE id = ? AND user_id = ?",
                (existing["id"], current_user_id),
            )
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


def keep_or_require_account(conn, current_user_id, raw, current_id, label="Conta"):
    """Conta de uma edicao: a que a linha ja tem fica (arquivada ou nao); outra
    tem que ser ativa. Vazio e recusado — nao cai na conta padrao."""
    if raw in (None, ""):
        raise ValidationError(f"Informe a {label.lower()}.")
    raw = str(raw)
    if current_id and raw == current_id:
        return current_id
    return require_account(conn, current_user_id, raw, label)["id"]


# Uma transferencia e uma linha; entre moedas (047) o valor que entra no
# destino, na moeda dele, vai em transfer_amount.
TRANSFER_CURRENCY_MESSAGE = "Contas em moedas diferentes: informe o valor que entrou no destino."
SAME_CURRENCY_MESSAGE = "O valor no destino so existe entre contas de moedas diferentes."


def transfer_amount_for(origin, destination, payload, current=None):
    """O `transfer_amount` de uma transferencia de origin para destination.

    Mesma moeda: None (entra o mesmo valor que sai); mandar um e recusado.
    Moedas diferentes: o do payload, senao o que a linha ja tinha (`current`);
    sem nenhum, recusado — nunca dolar contado como real.
    """
    cross = normalize_currency(origin["currency"]) != normalize_currency(destination["currency"])
    sent = payload.get("transfer_amount") not in (None, "")
    if not cross:
        if sent:
            raise ValidationError(SAME_CURRENCY_MESSAGE)
        return None
    if sent:
        return parse_money(payload, "transfer_amount", "Valor no destino")
    if current is not None and current["transfer_amount"]:
        return current["transfer_amount"]
    raise ValidationError(TRANSFER_CURRENCY_MESSAGE)


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


# Um nome so nao diz qual categoria e: "Outros" pode ser a raiz e tambem
# "Alimentação › Outros" e "Lazer › Outros". Quando so o nome chega (cliente
# antigo, item da fila de antes do id, texto livre), vale esta ordem: a raiz,
# que e unica, e depois a subcategoria mais antiga. As telas mandam o id.
CATEGORY_NAME_ORDER = "parent_id IS NOT NULL, created_at, id"


def category_id_for_name(conn, current_user_id, name):
    """O id da categoria com este nome, pela ordem de CATEGORY_NAME_ORDER."""
    if not name:
        return None
    row = conn.execute(
        f"SELECT id FROM categories WHERE user_id = ? AND name = ? ORDER BY {CATEGORY_NAME_ORDER} LIMIT 1",
        (current_user_id, name),
    ).fetchone()
    return row["id"] if row else None


def category_ids_by_name(conn, current_user_id):
    """{nome: id} de todas as categorias, com a mesma escolha de
    category_id_for_name() — para quem resolve muitas linhas de uma vez."""
    ids = {}
    for row in conn.execute(
        f"SELECT id, name FROM categories WHERE user_id = ? ORDER BY {CATEGORY_NAME_ORDER}",
        (current_user_id,),
    ).fetchall():
        ids.setdefault(row["name"], row["id"])
    return ids


# Tabelas que guardam o nome da categoria ao lado do id: o Dashboard agrupa
# pelo nome, e a recorrencia, a regra e o rascunho de Aprovar gravam o nome
# deles nos lancamentos que criam.
CATEGORY_NAME_TABLES = ("transactions", "cc_expenses", "recurring_transactions", "import_rules", "inbox_items")


def rename_category_rows(conn, current_user_id, category_id, old_name, new_name, *, owned_old_name):
    """Renomear a categoria arrasta o nome gravado em toda linha dela, pelo id.

    `owned_old_name`: o nome antigo era desta categoria (category_id_for_name,
    lido antes de renomear). Entao uma linha so com esse texto, sem id, contava
    aqui pelo nome; ela ganha o id e o nome novo para continuar contando onde
    contava. Sem isso a compra no cartao saia do orcamento depois de renomear.
    """
    for table in CATEGORY_NAME_TABLES:
        conn.execute(
            f"UPDATE {table} SET category = ? WHERE user_id = ? AND category_id = ?",
            (new_name, current_user_id, category_id),
        )
        if owned_old_name:
            conn.execute(
                f"UPDATE {table} SET category = ?, category_id = ?"
                " WHERE user_id = ? AND category_id IS NULL AND category = ?",
                (new_name, category_id, current_user_id, old_name),
            )


def resolve_category(conn, current_user_id, payload, required=True, current=None, allow_archived=False):
    """Resolve (nome, id) da categoria de um lancamento.

    Aceita `category_id` (o que as telas mandam) ou `category` em texto. O nome
    continua sendo gravado em transactions.category: e ele que o Dashboard
    agrupa e e o fallback caso a categoria seja apagada depois.

    `current`: a linha que esta sendo editada. Um nome igual ao que ela ja tem
    nao a tira da categoria dela — "Alimentação › Outros" nao vira o "Outros"
    da raiz so porque a edicao mandou o nome de volta.

    `allow_archived`: a importacao grava a categoria que a regra escolheu, mesmo
    arquivada (pelo nome ja era assim); uma escolha nova do dono nao pode.
    """
    category_id = payload.get("category_id")
    if category_id not in (None, ""):
        row = fetch_category(conn, current_user_id, str(category_id))
        if not row:
            raise ValidationError("Categoria nao encontrada.")
        if row["archived_at"] and not allow_archived:
            raise ValidationError("Categoria esta arquivada.")
        return row["name"], row["id"]

    if required:
        name = require_string(payload, "category", "Categoria")
    else:
        name = optional_string(payload, "category", max_length=255)
        if not name:
            return None, None

    if current is not None and name == current["category"]:
        return name, current["category_id"]
    return name, category_id_for_name(conn, current_user_id, name)


def account_balance_rows(conn, current_user_id):
    """Saldo por conta: inicial + receitas - despesas -/+ transferencias.

    TRANSFER sai de account_id e entra em transfer_account_id, por isso aparece
    duas vezes aqui com sinais opostos e some do consolidado. Entre moedas
    (047) entra `transfer_amount`, na moeda do destino; sem ele (a conta virou
    global depois), nada entra ate a Pluggy ou o dono dizer quanto.
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
                    SELECT SUM(COALESCE(
                        t.transfer_amount,
                        CASE WHEN COALESCE(o.currency, 'BRL') = COALESCE(a.currency, 'BRL') THEN t.amount ELSE 0 END
                    ))
                    FROM transactions t
                    LEFT JOIN accounts o ON o.id = t.account_id AND o.user_id = t.user_id
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
