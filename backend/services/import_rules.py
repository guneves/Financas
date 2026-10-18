"""Regras de categorizacao do extrato: a leitura que mais de um fluxo usa.

A importacao de arquivo (routes/imports.py) e Aprovar (services/inbox.py)
categorizam do mesmo jeito: a primeira regra ativa que casa
(statement_import.first_matching_rule), senao a categoria padrao do tipo. Uma
regra so, num lugar so.
"""

from db import row_to_dict
from services.accounts import CATEGORY_NAME_ORDER


# Categoria sugerida quando nenhuma regra casa. E so um palpite: a previa
# sempre deixa o dono trocar antes de gravar.
DEFAULT_IMPORT_CATEGORIES = {"EXPENSE": "Outros", "INCOME": "Receita"}


def import_rules_for_matching(conn, current_user_id):
    """Regras ativas na ordem de avaliacao: prioridade desc, depois idade.

    Empate resolvido pela mais antiga de proposito — a regra que o dono criou
    primeiro continua ganhando quando ele acrescenta outra parecida.
    """
    rows = conn.execute(
        """
        SELECT * FROM import_rules
        WHERE user_id = ? AND active = 1
        ORDER BY priority DESC, created_at ASC
        """,
        (current_user_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def import_default_category(conn, current_user_id, transaction_type):
    """(nome, id) da categoria padrao: "Outros" e o da raiz, nao o de uma
    subcategoria com o mesmo nome."""
    name = DEFAULT_IMPORT_CATEGORIES.get(transaction_type)
    if not name:
        return None, None
    row = conn.execute(
        f"""
        SELECT id, name FROM categories
        WHERE user_id = ? AND name = ? AND archived_at IS NULL
        ORDER BY {CATEGORY_NAME_ORDER}
        LIMIT 1
        """,
        (current_user_id, name),
    ).fetchone()
    if not row:
        return None, None
    return row["name"], row["id"]


def count_rule_hits(conn, current_user_id, rule_hits):
    """Soma em `hits` quantos lancamentos cada regra categorizou de verdade."""
    for rule_id, count in rule_hits.items():
        conn.execute(
            "UPDATE import_rules SET hits = hits + ? WHERE id = ? AND user_id = ?",
            (count, rule_id, current_user_id),
        )
