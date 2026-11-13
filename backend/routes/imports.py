"""Importacao de extrato CSV/OFX e regras de categorizacao (Fase 4).

A leitura do arquivo e pura e mora em `statement_import.py`; aqui ficam conta,
categoria, regras e gravacao. `POST /api/import/preview` nunca grava;
`POST /api/import/commit` grava com `source_type = 'STATEMENT_IMPORT'`, e o
indice unico de source faz a reimportacao do mesmo arquivo nao criar nada.
Regras so tocam lancamentos ja gravados com confirmacao
(`/api/import-rules/apply`), e nunca TRANSFER, caixa de investimento ou
pagamento de fatura.
"""

import sqlite3

from flask import Blueprint, jsonify, request

import statement_import
from auth import token_required
from db import get_db, new_id, utc_timestamp
from money import parse_money, rounded_money
from services import manual_entries
from services.accounts import resolve_account_id, resolve_category
from services.import_payload import (  # noqa: F401  (as regras desta rota; os nomes continuam valendo aqui)
    ALLOWED_IMPORT_APPLIES_TO,
    ALLOWED_IMPORT_MATCH_TYPES,
    MAX_IMPORT_CONTENT_CHARS,
    MAX_RULE_APPLY_ROWS,
    RULE_APPLY_SKIPPED_SOURCE_TYPES,
    RULE_CONDITION_FIELDS,
    ensure_unique_import_rule,
    existing_import_source_ids,
    fetch_import_rule,
    import_content_from_payload,
    import_source_id,
    read_import_rule_payload,
    read_rule_apply_scope,
    rule_apply_candidates,
    same_category,
    serialize_import_rule,
)
from services.import_rules import (
    count_rule_hits,
    import_default_category,
    import_rules_for_matching,
)
from source_types import (
    STATEMENT_IMPORT_SOURCE_TYPE,
)
from validators import (
    ValidationError,
    optional_string,
    parse_json_body,
    require_choice,
    require_date,
    validation_error,
)

bp = Blueprint("imports", __name__)


ALLOWED_IMPORT_TYPES = {"INCOME", "EXPENSE"}
@bp.route("/api/import-rules", methods=["GET", "POST"])
@token_required
def import_rules(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM import_rules
                WHERE user_id = ?
                ORDER BY priority DESC, created_at ASC
                """,
                (current_user_id,),
            ).fetchall()
        return jsonify({"items": [serialize_import_rule(row) for row in rows]}), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            fields = read_import_rule_payload(conn, current_user_id, payload)
            ensure_unique_import_rule(conn, current_user_id, fields)
        except ValidationError as exc:
            return validation_error(str(exc))

        rule_id = new_id()
        columns = ["id", "user_id", *fields.keys()]
        placeholders = ", ".join("?" for _ in columns)
        try:
            conn.execute(
                f"INSERT INTO import_rules ({', '.join(columns)}) VALUES ({placeholders})",
                (rule_id, current_user_id, *fields.values()),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma regra igual a essa.")
        row = fetch_import_rule(conn, current_user_id, rule_id)
    return jsonify(serialize_import_rule(row)), 201


@bp.route("/api/import-rules/<rule_id>", methods=["PATCH", "DELETE"])
@token_required
def import_rule_detail(current_user_id, rule_id):
    with get_db() as conn:
        row = fetch_import_rule(conn, current_user_id, rule_id)
        if not row:
            return jsonify({"error": "Regra nao encontrada."}), 404

        if request.method == "DELETE":
            # Regra e configuracao, nao dinheiro: apagar nao desfaz nenhuma
            # categorizacao ja gravada, entao nao ha guarda de confirmacao.
            conn.execute(
                "DELETE FROM import_rules WHERE id = ? AND user_id = ?",
                (rule_id, current_user_id),
            )
            return jsonify({"deleted": True}), 200

        payload = parse_json_body()
        try:
            fields = read_import_rule_payload(conn, current_user_id, payload, existing=row)
            if fields:
                ensure_unique_import_rule(conn, current_user_id, fields, existing=row)
        except ValidationError as exc:
            return validation_error(str(exc))
        if not fields:
            return validation_error("Informe ao menos um campo para atualizar.")

        fields["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in fields)
        try:
            conn.execute(
                f"UPDATE import_rules SET {assignments} WHERE id = ? AND user_id = ?",
                (*fields.values(), rule_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma regra igual a essa.")
        updated = fetch_import_rule(conn, current_user_id, rule_id)
    return jsonify(serialize_import_rule(updated)), 200


@bp.route("/api/import-rules/apply/preview", methods=["POST"])
@token_required
def import_rules_apply_preview(current_user_id):
    """O que as regras mudariam nos lancamentos ja gravados — sem gravar nada.

    As regras nascem para a importacao; rodar sobre o passado reescreve
    categorias que o dono pode ter escolhido a mao, entao ele ve a lista antes
    e confirma linha por linha no /apply.
    """
    payload = parse_json_body()
    try:
        rule_id = read_rule_apply_scope(payload)
    except ValidationError as exc:
        return validation_error(str(exc))
    with get_db() as conn:
        try:
            items, total = rule_apply_candidates(conn, current_user_id, rule_id=rule_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
    return jsonify({"items": items, "total": total, "truncated": total > len(items)}), 200


@bp.route("/api/import-rules/apply", methods=["POST"])
@token_required
def import_rules_apply(current_user_id):
    """Recategoriza os lancamentos confirmados na previa.

    Guarda de confirmacao: so mexe nos `transaction_ids` enviados, e cada um e
    conferido de novo contra a regra — um id que a regra ja nao muda (editado
    depois da previa, de outro usuario, de investimento) e pulado, nao forcado.
    """
    payload = parse_json_body()
    raw_ids = payload.get("transaction_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return validation_error("Escolha ao menos um lancamento em 'transaction_ids'.")
    if len(raw_ids) > MAX_RULE_APPLY_ROWS:
        return validation_error("Lancamentos demais de uma vez.")
    if not all(isinstance(value, str) and value for value in raw_ids):
        return validation_error("Lista de lancamentos invalida.")
    transaction_ids = list(dict.fromkeys(raw_ids))
    try:
        rule_id = read_rule_apply_scope(payload)
    except ValidationError as exc:
        return validation_error(str(exc))

    rule_hits = {}
    with get_db() as conn:
        try:
            candidates, _ = rule_apply_candidates(
                conn, current_user_id, rule_id=rule_id, transaction_ids=transaction_ids
            )
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        for item in candidates:
            conn.execute(
                "UPDATE transactions SET category = ?, category_id = ? WHERE id = ? AND user_id = ?",
                (item["new_category"], item["new_category_id"], item["id"], current_user_id),
            )
            rule_hits[item["rule_id"]] = rule_hits.get(item["rule_id"], 0) + 1
        for hit_rule_id, count in rule_hits.items():
            conn.execute(
                "UPDATE import_rules SET hits = hits + ? WHERE id = ? AND user_id = ?",
                (count, hit_rule_id, current_user_id),
            )

    updated = sum(rule_hits.values())
    return jsonify({"updated": updated, "skipped": len(transaction_ids) - updated}), 200


@bp.route("/api/import/preview", methods=["POST"])
@token_required
def import_preview(current_user_id):
    """Le o arquivo, aplica as regras e diz o que entraria — sem gravar nada.

    Toda a gravacao acontece no /commit, com as linhas que o dono confirmou:
    importar e uma operacao que mexe no extrato inteiro, e ver antes e o que
    torna isso seguro.
    """
    payload = parse_json_body()
    with get_db() as conn:
        try:
            content = import_content_from_payload(payload)
            account_id = resolve_account_id(conn, current_user_id, payload)
            rows, meta = statement_import.parse_statement(
                content,
                file_format=payload.get("format"),
                filename=payload.get("filename"),
                mapping=payload.get("mapping"),
                delimiter=payload.get("delimiter"),
                has_header=payload.get("has_header"),
                decimal_separator=payload.get("decimal_separator", "auto"),
                invert_sign=payload.get("invert_sign"),
                skip_rows=payload.get("skip_rows", 0),
            )
        except statement_import.ImportError_ as exc:
            return validation_error(str(exc))
        except ValidationError as exc:
            return validation_error(str(exc))

        rules = import_rules_for_matching(conn, current_user_id)
        seen = {}
        items = []
        for row in rows:
            item = dict(row)
            if row.get("error"):
                item["status"] = "ERROR"
                item["source_id"] = None
                items.append(item)
                continue

            item["source_id"] = import_source_id(account_id, row, seen)
            rule = statement_import.first_matching_rule(
                rules, row.get("description"), row["type"], row.get("amount"), account_id
            )
            if rule:
                item["category"] = rule["category"]
                item["category_id"] = rule["category_id"]
                item["rule_id"] = rule["id"]
                item["rule_pattern"] = rule["pattern"]
                item["category_source"] = "RULE"
            else:
                name, category_id = import_default_category(conn, current_user_id, row["type"])
                item["category"] = name
                item["category_id"] = category_id
                item["rule_id"] = None
                item["rule_pattern"] = None
                item["category_source"] = "DEFAULT" if name else None
            items.append(item)

        already = existing_import_source_ids(
            conn, current_user_id, [item.get("source_id") for item in items]
        )
        for item in items:
            if item.get("status") == "ERROR":
                continue
            item["status"] = "DUPLICATE" if item["source_id"] in already else "NEW"

    summary = {
        "total": len(items),
        "new": sum(1 for item in items if item.get("status") == "NEW"),
        "duplicates": sum(1 for item in items if item.get("status") == "DUPLICATE"),
        "errors": sum(1 for item in items if item.get("status") == "ERROR"),
        "categorized": sum(1 for item in items if item.get("category_source") == "RULE"),
    }
    return jsonify({**meta, "account_id": account_id, "rows": items, "summary": summary}), 200


@bp.route("/api/import/commit", methods=["POST"])
@token_required
def import_commit(current_user_id):
    """Grava as linhas confirmadas na previa.

    INSERT OR IGNORE contra idx_transactions_user_source: uma linha que ja
    entrou (mesmo arquivo importado duas vezes, ou duas abas abertas) e
    ignorada em vez de duplicada, e o retorno conta quantas foram puladas.
    """
    payload = parse_json_body()
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return validation_error("Envie as linhas a importar em 'rows'.")
    if len(raw_rows) > statement_import.MAX_IMPORT_ROWS:
        return validation_error("Linhas demais em uma unica importacao.")

    created = 0
    skipped = 0
    rule_hits = {}
    with get_db() as conn:
        seen = {}
        prepared = []
        for index, raw in enumerate(raw_rows):
            if not isinstance(raw, dict):
                return validation_error(f"Linha {index + 1}: formato invalido.")
            try:
                amount = parse_money(raw, "amount", "Valor")
                date_value = require_date(raw, "date", "Data")
                transaction_type = require_choice(raw, "type", "Tipo", ALLOWED_IMPORT_TYPES)
                description = optional_string(raw, "description")
                category, category_id = resolve_category(conn, current_user_id, raw, allow_archived=True)
                account_id = resolve_account_id(conn, current_user_id, raw) if raw.get("account_id") \
                    else resolve_account_id(conn, current_user_id, payload)
                manual_entries.require_manual_account(conn, current_user_id, account_id)
                # Normalmente o source_id vem da previa; sem ele, e recalculado
                # aqui com a mesma regra, para o dedupe valer de qualquer jeito.
                source_id = optional_string(raw, "source_id", max_length=255) or import_source_id(
                    account_id,
                    {"date": date_value, "amount": amount, "description": description},
                    seen,
                )
            except ValidationError as exc:
                return validation_error(f"Linha {index + 1}: {exc}")
            prepared.append((raw.get("rule_id"), (
                new_id(),
                current_user_id,
                account_id,
                rounded_money(amount),
                date_value,
                category,
                category_id,
                description,
                transaction_type,
                STATEMENT_IMPORT_SOURCE_TYPE,
                source_id,
            )))

        for rule_id, values in prepared:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO transactions
                (id, user_id, account_id, amount, date, category, category_id,
                 description, type, source_type, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            if cursor.rowcount:
                created += 1
                if rule_id:
                    rule_hits[str(rule_id)] = rule_hits.get(str(rule_id), 0) + 1
            else:
                skipped += 1

        # hits so conta o que virou lancamento de verdade; e o numero que diz
        # se a regra esta puxando o peso dela.
        count_rule_hits(conn, current_user_id, rule_hits)

    return jsonify({"created": created, "skipped": skipped}), 201
