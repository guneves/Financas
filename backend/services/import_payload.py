"""Importacao de extrato e regras de importacao: ler o pedido, a chave de cada linha, os candidatos de uma regra.

Saiu de routes/imports.py (2026-11-13): nada aqui usa o Flask. A rota continua importando
todos estes nomes.
"""

import sqlite3


import statement_import
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import parse_money, rounded_money
from services import manual_entries
from services.accounts import require_account, resolve_account_id, resolve_category
from services.import_rules import (
    count_rule_hits,
    import_default_category,
    import_rules_for_matching,
)
from source_types import (
    INVESTMENT_SOURCE_TYPES,
    MONTH_SUMMARY_SOURCE_TYPE,
    INVOICE_PAYMENT_SOURCE_TYPES,
    STATEMENT_IMPORT_SOURCE_TYPE,
)
from validators import (
    ValidationError,
    optional_string,
    parse_json_body,
    parse_number,
    parse_optional_number,
    require_choice,
    require_date,
    require_string,
    validation_error,
)


ALLOWED_IMPORT_MATCH_TYPES = {"CONTAINS", "STARTS_WITH", "EQUALS"}


ALLOWED_IMPORT_APPLIES_TO = {"INCOME", "EXPENSE", "BOTH"}


# Um extrato de um ano cabe folgado; acima disso o arquivo provavelmente nao e
# um extrato, e o payload passa a pesar na memoria do processo.
MAX_IMPORT_CONTENT_CHARS = 4_000_000


def serialize_import_rule(row):
    item = row_to_dict(row)
    item["active"] = bool(item.get("active"))
    return item


def fetch_import_rule(conn, current_user_id, rule_id):
    return conn.execute(
        "SELECT * FROM import_rules WHERE id = ? AND user_id = ?",
        (rule_id, current_user_id),
    ).fetchone()


RULE_CONDITION_FIELDS = ("amount_min", "amount_max", "account_id")


def ensure_unique_import_rule(conn, current_user_id, fields, existing=None):
    """Recusa uma regra que ja existe *do jeito que a comparacao enxerga*.

    O indice unico de 013/015 compara o texto cru, mas a avaliacao normaliza
    (sem acento, sem caixa): sem esta checagem, "Uber" e "uber" entrariam como
    duas regras que casam sempre juntas, e so a prioridade decidiria qual vence.
    Duas regras com o mesmo texto e condicoes diferentes (015) convivem.
    """
    def current(key, default):
        if key in fields:
            return fields[key]
        return existing[key] if existing else default

    pattern = current("pattern", "")
    match_type = current("match_type", "CONTAINS")
    applies_to = current("applies_to", "BOTH")
    conditions = tuple(current(key, None) for key in RULE_CONDITION_FIELDS)
    normalized = statement_import.normalize_text(pattern)

    rows = conn.execute(
        """
        SELECT id, pattern, amount_min, amount_max, account_id FROM import_rules
        WHERE user_id = ? AND match_type = ? AND applies_to = ?
        """,
        (current_user_id, match_type, applies_to),
    ).fetchall()
    for row in rows:
        if existing is not None and row["id"] == existing["id"]:
            continue
        if tuple(row[key] for key in RULE_CONDITION_FIELDS) != conditions:
            continue
        if statement_import.normalize_text(row["pattern"]) == normalized:
            raise ValidationError(f"Ja existe uma regra para \"{row['pattern']}\".")


def read_import_rule_payload(conn, current_user_id, payload, existing=None):
    """Campos validados de uma regra. Em PATCH, so o que veio no payload."""
    fields = {}
    is_create = existing is None

    if is_create or "pattern" in payload:
        pattern = require_string(payload, "pattern", "Texto da regra", max_length=255)
        if len(statement_import.normalize_text(pattern)) < 2:
            raise ValidationError("O texto da regra precisa de ao menos 2 caracteres.")
        fields["pattern"] = pattern

    if is_create or "match_type" in payload:
        fields["match_type"] = require_choice(
            payload, "match_type", "Tipo de comparacao", ALLOWED_IMPORT_MATCH_TYPES
        ) if payload.get("match_type") else "CONTAINS"

    if is_create or "applies_to" in payload:
        fields["applies_to"] = require_choice(
            payload, "applies_to", "Aplica-se a", ALLOWED_IMPORT_APPLIES_TO
        ) if payload.get("applies_to") else "BOTH"

    if is_create or "category" in payload or "category_id" in payload:
        category, category_id = resolve_category(conn, current_user_id, payload, current=existing)
        fields["category"] = category
        fields["category_id"] = category_id

    if "priority" in payload:
        fields["priority"] = int(
            parse_number(payload, "priority", "Prioridade", minimum=-999, maximum=999)
        )

    if "active" in payload:
        fields["active"] = 1 if payload.get("active") else 0

    if "note" in payload:
        fields["note"] = optional_string(payload, "note")

    # Condicoes de 015: faixa de valor (absoluto) e conta. Vazio limpa.
    for key, label in (("amount_min", "Valor minimo"), ("amount_max", "Valor maximo")):
        if key in payload:
            value = parse_optional_number(payload, key, label, minimum=0)
            fields[key] = None if value is None else rounded_money(value)
    amount_min = fields.get("amount_min", existing["amount_min"] if existing else None)
    amount_max = fields.get("amount_max", existing["amount_max"] if existing else None)
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise ValidationError("O valor minimo nao pode passar do maximo.")

    if "account_id" in payload:
        raw_account = payload.get("account_id")
        fields["account_id"] = None if raw_account in (None, "") else require_account(
            conn, current_user_id, str(raw_account)
        )["id"]

    return fields


# Lancamentos que as regras nunca recategorizam: o dinheiro de um investimento,
# o provento pago na conta da carteira e o pagamento de uma fatura sao gerados
# pelo sistema e levam um rotulo, nao uma categoria escolhida (039: "Aporte",
# "Resgate", "Provento").
RULE_APPLY_SKIPPED_SOURCE_TYPES = (
    *INVESTMENT_SOURCE_TYPES,
    MONTH_SUMMARY_SOURCE_TYPE,
    *sorted(INVOICE_PAYMENT_SOURCE_TYPES),
)


MAX_RULE_APPLY_ROWS = 2000


def same_category(rule, row):
    """A regra deixaria a linha onde ela esta? Pelo id quando os dois tem um:
    "Lazer › Outros" e o "Outros" da raiz tem o mesmo nome e nao sao a mesma."""
    if rule["category_id"] and row["category_id"]:
        return rule["category_id"] == row["category_id"]
    return rule["category"] == row["category"]


def rule_apply_candidates(conn, current_user_id, rule_id=None, transaction_ids=None):
    """Lancamentos ja gravados cuja categoria mudaria se a regra rodasse agora.

    Com `rule_id`, so aquela regra (ativa ou nao — o dono escolheu ela); sem,
    todas as ativas na ordem da importacao, e a primeira que casa decide. Uma
    linha que a regra deixaria na mesma categoria nao e candidata.

    Returns (candidatos, total) — `total` antes do corte de MAX_RULE_APPLY_ROWS.
    """
    if rule_id is not None:
        row = fetch_import_rule(conn, current_user_id, rule_id)
        if not row:
            raise LookupError("Regra nao encontrada.")
        rules = [row_to_dict(row)]
    else:
        rules = import_rules_for_matching(conn, current_user_id)
    if not rules:
        return [], 0

    skipped = ", ".join("?" for _ in RULE_APPLY_SKIPPED_SOURCE_TYPES)
    sql = f"""
        SELECT t.id, t.date, t.amount, t.type, t.description, t.category,
               t.category_id, t.account_id, a.name AS account_name
        FROM transactions t
        LEFT JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
        WHERE t.user_id = ?
          AND t.type IN ('INCOME', 'EXPENSE')
          AND COALESCE(t.source_type, '') NOT IN ({skipped})
          AND TRIM(COALESCE(t.description, '')) <> ''
    """
    params = [current_user_id, *RULE_APPLY_SKIPPED_SOURCE_TYPES]
    if transaction_ids is not None:
        placeholders = ", ".join("?" for _ in transaction_ids)
        sql += f" AND t.id IN ({placeholders})"
        params.extend(transaction_ids)
    sql += " ORDER BY t.date DESC, t.created_at DESC"

    candidates = []
    for row in conn.execute(sql, params).fetchall():
        rule = statement_import.first_matching_rule(
            rules, row["description"], row["type"], row["amount"], row["account_id"]
        )
        if not rule or same_category(rule, row):
            continue
        candidates.append({
            "id": row["id"],
            "date": row["date"],
            "amount": row["amount"],
            "type": row["type"],
            "description": row["description"],
            "account_name": row["account_name"],
            "category": row["category"],
            "new_category": rule["category"],
            "new_category_id": rule["category_id"],
            "rule_id": rule["id"],
            "rule_pattern": rule["pattern"],
        })
    return candidates[:MAX_RULE_APPLY_ROWS], len(candidates)


def read_rule_apply_scope(payload):
    rule_id = payload.get("rule_id")
    if rule_id in (None, ""):
        return None
    if not isinstance(rule_id, str):
        raise ValidationError("Regra invalida.")
    return rule_id


def import_content_from_payload(payload):
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Envie o conteudo do arquivo em 'content'.")
    if len(content) > MAX_IMPORT_CONTENT_CHARS:
        raise ValidationError("Arquivo grande demais para importar de uma vez.")
    return content


def import_source_id(account_id, row, seen):
    """Chave de dedupe da linha, ja separando repetidas dentro do arquivo.

    Vale tambem para o FITID: ha banco que repete o mesmo FITID em dois
    lancamentos do arquivo, e o segundo era descartado como duplicado. A
    ordem no arquivo e estavel, entao reimportar da as mesmas chaves.
    """
    if row.get("fitid"):
        base = statement_import.ofx_source_id(account_id, row["fitid"])
    else:
        base = statement_import.row_hash(
            account_id, row["date"], row["amount"], row.get("description")
        )
    occurrence = seen.get(base, 0)
    seen[base] = occurrence + 1
    if occurrence == 0:
        return base
    return f"{base}:{occurrence}"


def existing_import_source_ids(conn, current_user_id, source_ids):
    """Quais desses source_id ja estao gravados — uma consulta, nao N."""
    found = set()
    ids = [sid for sid in source_ids if sid]
    for start in range(0, len(ids), 400):
        chunk = ids[start:start + 400]
        placeholders = ", ".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT source_id FROM transactions
            WHERE user_id = ? AND source_type = ? AND source_id IN ({placeholders})
            """,
            (current_user_id, STATEMENT_IMPORT_SOURCE_TYPE, *chunk),
        ).fetchall()
        found.update(row["source_id"] for row in rows)
    return found
