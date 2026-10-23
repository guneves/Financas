"""Cartoes de credito, compras parceladas e pagamento de fatura.

`/api/credit-cards` e `/api/cc-expenses/*`. As regras (mes da fatura,
fechamento, debito automatico) estao em `services/invoices.py`; o pagamento
real e `POST /api/cc-expenses/pay-invoice`, e o desfazer e
`DELETE /api/cc-expenses/payments/<lancamento>`. Um estorno (033) e uma linha
`kind = 'REFUND'` da mesma tabela, criada por `POST /api/cc-expenses/refunds`.
Um cartao com historico e arquivado, nunca apagado (037).
"""

import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db, new_id, row_to_dict, serialize_transaction, utc_timestamp
from money import parse_money, rounded_money
from services.accounts import (
    category_id_for_name,
    fetch_account,
    require_account,
    resolve_account_id,
    resolve_category,
)
from services.attachments import (
    cc_expense_attachment_names,
    cc_purchase_expense_ids,
    remove_attachment_files,
    same_purchase_sql,
)
from services.inbox_decisions import absorb_created
from services.sharing import update_purchase_share
from services.invoices import (
    InvoiceConflictError,
    InvoiceStillOpenError,
    apply_due_autopay,
    autopay_source_id,
    build_installment_rows,
    ensure_invoice_closed,
    invoice_label,
    invoice_open_lines,
    local_today,
    purchase_invoice_start,
    refund_invoice,
    require_active_card,
    serialize_cc_expense,
    settle_invoice,
    signed_amount_sql,
    undo_invoice_payment,
)
from source_types import CC_INVOICE_PAYMENT_SOURCE_TYPE, INVOICE_PAYMENT_SOURCE_TYPES
from validators import (
    MAX_YEAR,
    ValidationError,
    optional_client_id,
    optional_date,
    parse_int_number,
    parse_json_body,
    require_date,
    require_id_list,
    require_string,
    validation_error,
)

bp = Blueprint("cards", __name__)


def fetch_purchase_by_client_id(conn, current_user_id, client_id):
    """As parcelas que um envio com este client_id ja criou (024), na ordem das faturas."""
    if not client_id:
        return []
    return conn.execute(
        """
        SELECT * FROM cc_expenses
        WHERE user_id = ? AND client_id = ?
        ORDER BY invoice_year ASC, invoice_month ASC
        """,
        (current_user_id, client_id),
    ).fetchall()


ALLOWED_CC_STATUS = {"OPEN", "PAID"}


@bp.route("/api/credit-cards", methods=["GET", "POST"])
@token_required
def credit_cards(current_user_id):
    if request.method == "GET":
        # Os arquivados (037) so com include_archived: nenhuma tela lanca neles.
        include_archived = str(request.args.get("include_archived", "")).lower() in ("1", "true", "yes")
        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            rows = conn.execute(
                f"""
                SELECT * FROM credit_cards WHERE user_id = ?
                {"" if include_archived else "AND archived_at IS NULL"}
                ORDER BY name ASC
                """,
                (current_user_id,),
            ).fetchall()
        return jsonify([row_to_dict(row) for row in rows]), 200

    payload = parse_json_body()
    try:
        name = require_string(payload, "name", "Nome do cartao")
        credit_enabled = parse_card_flag(payload, "credit_enabled", "Funcao credito", default=True)
        if credit_enabled:
            due_day = parse_int_number(payload, "due_day", "Dia de vencimento", minimum=1, maximum=31)
            closing_day = parse_int_number(payload, "closing_day", "Dia de fechamento", minimum=1, maximum=31)
        else:
            # So debito (041): sem fatura; as colunas NOT NULL guardam 1 e nunca sao lidas.
            due_day, closing_day = DEBIT_ONLY_DAY, DEBIT_ONLY_DAY
    except ValidationError as exc:
        return validation_error(str(exc))

    item_id = new_id()
    try:
        with get_db() as conn:
            try:
                autopay_account_id = resolve_autopay_account(conn, current_user_id, payload)
                debit_account_id = resolve_debit_account(conn, current_user_id, payload)
                check_card_functions(credit_enabled, debit_account_id, autopay_account_id)
            except ValidationError as exc:
                return validation_error(str(exc))
            conn.execute(
                """
                INSERT INTO credit_cards
                (id, user_id, name, due_day, closing_day, autopay_account_id, autopay_start_date,
                 credit_enabled, debit_account_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    current_user_id,
                    name,
                    due_day,
                    closing_day,
                    autopay_account_id,
                    local_today().strftime("%Y-%m-%d") if autopay_account_id else None,
                    1 if credit_enabled else 0,
                    debit_account_id,
                ),
            )
            item = conn.execute("SELECT * FROM credit_cards WHERE id = ?", (item_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            with get_db() as conn:
                return jsonify({"error": card_name_conflict_message(conn, current_user_id, name)}), 409
        return jsonify({"error": "Nao foi possivel criar o cartao."}), 400
    return jsonify(row_to_dict(item)), 201


# As funcoes do cartao (041). Um cartao so debito nao tem fatura: vencimento e
# fechamento guardam este dia e nada os le.
DEBIT_ONLY_DAY = 1
NO_FUNCTION_MESSAGE = "Escolha ao menos uma funcao do cartao: credito ou debito."
DEBIT_ONLY_AUTOPAY_MESSAGE = "Um cartao so de debito nao tem fatura nem debito automatico."
CREDIT_OFF_OPEN_MESSAGE = "O cartao ainda tem fatura em aberto: pague ou exclua essas compras antes de tirar a funcao credito."
DEBIT_BROKERAGE_MESSAGE = "A conta da corretora fica em Investimentos: escolha uma conta do banco para o debito."
FLAG_VALUES = {True: True, False: False, 1: True, 0: False, "1": True, "0": False, "true": True, "false": False}


def parse_card_flag(payload, key, label, default):
    raw = payload.get(key)
    if raw is None:
        return default
    if isinstance(raw, str):
        raw = raw.strip().lower()
    # Lista ou objeto nao e flag (e nem entra num dict: era um 500).
    value = FLAG_VALUES.get(raw) if isinstance(raw, (str, int, float)) else None
    if value is None:
        raise ValidationError(f"{label} invalida.")
    return value


def resolve_debit_account(conn, current_user_id, payload, current_id=None):
    """A conta da funcao debito; vazio/None tira o debito. Numa edicao, a conta
    que o cartao ja tem fica mesmo arquivada; outra tem que ser ativa."""
    raw = payload.get("debit_account_id")
    if raw in (None, ""):
        return None
    if current_id and str(raw) == current_id:
        return current_id
    account = require_account(conn, current_user_id, str(raw), "Conta do debito")
    if account["type"] == "BROKERAGE":
        # A Corretora e da carteira (Investimentos): nenhuma compra sai dela.
        raise ValidationError(DEBIT_BROKERAGE_MESSAGE)
    return account["id"]


def check_card_functions(credit_enabled, debit_account_id, autopay_account_id):
    if not credit_enabled and not debit_account_id:
        raise ValidationError(NO_FUNCTION_MESSAGE)
    if not credit_enabled and autopay_account_id:
        raise ValidationError(DEBIT_ONLY_AUTOPAY_MESSAGE)


def resolve_autopay_account(conn, current_user_id, payload):
    """Conta do debito automatico no payload; vazio/None desliga o debito."""
    raw = payload.get("autopay_account_id")
    if raw in (None, ""):
        return None
    return require_account(conn, current_user_id, str(raw), "Conta do debito automatico")["id"]


CARD_NAME_TAKEN_MESSAGE = "Ja existe um cartao com este nome."
# O excluido continua com o nome: as compras antigas dele o mostram.
ARCHIVED_CARD_NAME_MESSAGE = "Um cartao excluido ainda usa este nome no historico. Escolha outro nome."


def card_name_conflict_message(conn, current_user_id, name):
    archived = conn.execute(
        "SELECT 1 FROM credit_cards WHERE user_id = ? AND name = ? AND archived_at IS NOT NULL",
        (current_user_id, name),
    ).fetchone()
    return ARCHIVED_CARD_NAME_MESSAGE if archived else CARD_NAME_TAKEN_MESSAGE


@bp.route("/api/credit-cards/<card_id>", methods=["PATCH"])
@token_required
def update_credit_card(current_user_id, card_id):
    """Corrige o cartao: nome, vencimento, fechamento, debito automatico e as
    funcoes (041: credit_enabled, debit_account_id).

    Cada campo e opcional. Tirar o credito de um cartao com item em aberto e
    recusado (409) e desliga o debito automatico; dar credito a um cartao so
    debito pede vencimento e fechamento no mesmo pedido. Vencimento e fechamento valem para as compras novas
    e para quando cada fatura fecha; as parcelas ja lancadas ficam na fatura em
    que estao. Ligar (ou trocar de conta) o debito automatico grava hoje em
    autopay_start_date: faturas que venceram antes disso continuam para
    pagamento manual.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe os dados do cartao.")
    updates = {}
    try:
        if "name" in payload:
            updates["name"] = require_string(payload, "name", "Nome do cartao")
        if "due_day" in payload:
            updates["due_day"] = parse_int_number(payload, "due_day", "Dia de vencimento", minimum=1, maximum=31)
        if "closing_day" in payload:
            updates["closing_day"] = parse_int_number(
                payload, "closing_day", "Dia de fechamento", minimum=1, maximum=31
            )
        if "credit_enabled" in payload:
            updates["credit_enabled"] = 1 if parse_card_flag(payload, "credit_enabled", "Funcao credito", True) else 0
    except ValidationError as exc:
        return validation_error(str(exc))
    if not updates and "autopay_account_id" not in payload and "debit_account_id" not in payload:
        return validation_error("Informe ao menos um campo para atualizar.")

    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
        if not card or card["archived_at"]:
            return jsonify({"error": "Cartao nao encontrado."}), 404
        credit_enabled = bool(updates.get("credit_enabled", card["credit_enabled"]))
        if credit_enabled and not card["credit_enabled"] and not ("due_day" in updates and "closing_day" in updates):
            # O cartao so debito ganha a funcao credito: as datas guardadas (1) nao valem.
            return validation_error("Informe o vencimento e o fechamento para ligar a funcao credito.")
        if not credit_enabled and card["credit_enabled"]:
            open_items = conn.execute(
                "SELECT 1 FROM cc_expenses WHERE user_id = ? AND card_id = ? AND status = 'OPEN' LIMIT 1",
                (current_user_id, card_id),
            ).fetchone()
            if open_items:
                return jsonify({"error": CREDIT_OFF_OPEN_MESSAGE}), 409
            # Sem credito nao ha fatura: o debito automatico desliga junto.
            if "autopay_account_id" not in payload:
                updates["autopay_account_id"] = None
                updates["autopay_start_date"] = None
        try:
            if "debit_account_id" in payload:
                updates["debit_account_id"] = resolve_debit_account(
                    conn, current_user_id, payload, current_id=card["debit_account_id"],
                )
            debit_account_id = updates.get("debit_account_id", card["debit_account_id"])
            if "autopay_account_id" in payload:
                autopay_account_id = resolve_autopay_account(conn, current_user_id, payload)
            else:
                autopay_account_id = updates.get("autopay_account_id", card["autopay_account_id"])
            check_card_functions(credit_enabled, debit_account_id, autopay_account_id)
        except ValidationError as exc:
            return validation_error(str(exc))
        if "autopay_account_id" in payload:
            if autopay_account_id is None:
                start_date = None
            elif autopay_account_id == card["autopay_account_id"]:
                start_date = card["autopay_start_date"]
            else:
                start_date = local_today().strftime("%Y-%m-%d")
            updates["autopay_account_id"] = autopay_account_id
            updates["autopay_start_date"] = start_date

        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE credit_cards SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), card_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return jsonify({"error": card_name_conflict_message(conn, current_user_id, updates.get("name"))}), 409
        # Uma fatura que vence hoje ja e paga agora, sem esperar a proxima leitura.
        apply_due_autopay(conn, current_user_id)
        item = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
    return jsonify(row_to_dict(item)), 200


def card_payment_count(conn, current_user_id, card_id):
    """Pagamentos de fatura deste cartao no Extrato (source_id '<cartao>:...')."""
    placeholders = ",".join("?" for _ in INVOICE_PAYMENT_SOURCE_TYPES)
    prefix = f"{card_id}:"
    return conn.execute(
        f"""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND source_type IN ({placeholders})
          AND substr(source_id, 1, ?) = ?
        """,
        (current_user_id, *sorted(INVOICE_PAYMENT_SOURCE_TYPES), len(prefix), prefix),
    ).fetchone()[0]


@bp.route("/api/credit-cards/<card_id>", methods=["DELETE"])
@token_required
def delete_credit_card(current_user_id, card_id):
    """Exclui um cartao sem perder historico (037).

    Com item em aberto, recusa (409): essas parcelas ainda vao ser cobradas.
    Com compras pagas ou pagamentos de fatura, arquiva: o DELETE real levava
    pelo CASCADE todas as compras (orcamentos passados mudavam) e deixava os
    pagamentos presos no Extrato. Sem nada, apaga de verdade.
    """
    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
        if not card or card["archived_at"]:
            return jsonify({"deleted": False}), 404
        open_items = conn.execute(
            f"""
            SELECT COUNT(*) AS count, COALESCE(SUM(amount * {signed_amount_sql()}), 0) AS total
            FROM cc_expenses WHERE user_id = ? AND card_id = ? AND status = 'OPEN'
            """,
            (current_user_id, card_id),
        ).fetchone()
        if open_items["count"]:
            total_text = f"{rounded_money(open_items['total']):.2f}".replace(".", ",")
            return validation_error(
                f"O cartao {card['name']} ainda tem {open_items['count']} item(ns) em aberto nas faturas "
                f"(R$ {total_text}). Pague as faturas ou exclua as compras em aberto "
                "em Lancamentos > Cartoes antes de excluir o cartao.",
                409,
            )
        history = conn.execute(
            "SELECT COUNT(*) FROM cc_expenses WHERE user_id = ? AND card_id = ?",
            (current_user_id, card_id),
        ).fetchone()[0] + card_payment_count(conn, current_user_id, card_id)
        if history:
            conn.execute(
                """
                UPDATE credit_cards
                SET archived_at = ?, autopay_account_id = NULL, autopay_start_date = NULL
                WHERE id = ? AND user_id = ?
                """,
                (utc_timestamp(), card_id, current_user_id),
            )
            return jsonify({"deleted": True, "archived": True}), 200
        stored_names = cc_expense_attachment_names(conn, current_user_id, card_id=card_id)
        cursor = conn.execute(
            "DELETE FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    remove_attachment_files(current_user_id, stored_names)
    return jsonify({"deleted": True, "archived": False}), 200


@bp.route("/api/cc-expenses", methods=["GET", "POST", "DELETE"])
@token_required
def cc_expenses(current_user_id):
    if request.method == "GET":
        status = request.args.get("status")
        params = [current_user_id]
        status_filter = ""
        if status:
            status = str(status).strip().upper()
            if status not in ALLOWED_CC_STATUS:
                return validation_error("Status invalido.")
            status_filter = "AND cce.status = ?"
            params.append(status)

        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            rows = conn.execute(
                f"""
                SELECT
                    cce.*,
                    cc.name AS card_name,
                    cc.due_day AS card_due_day,
                    cc.closing_day AS card_closing_day,
                    (
                        -- Comprovantes da compra inteira (todas as parcelas), 016.
                        SELECT COUNT(*) FROM cc_expense_attachments a
                        JOIN cc_expenses sib ON sib.id = a.cc_expense_id AND sib.user_id = a.user_id
                        WHERE a.user_id = cce.user_id
                          AND {same_purchase_sql("sib.", "cce.")}
                    ) AS attachment_count
                FROM cc_expenses cce
                LEFT JOIN credit_cards cc ON cc.id = cce.card_id
                WHERE cce.user_id = ?
                {status_filter}
                ORDER BY cce.invoice_year ASC, cce.invoice_month ASC, cce.created_at ASC
                """,
                params,
            ).fetchall()
        return jsonify([serialize_cc_expense(row) for row in rows]), 200

    if request.method == "DELETE":
        payload = parse_json_body()
        try:
            ids = require_id_list(payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        placeholders = ",".join("?" for _ in ids)
        with get_db() as conn:
            # Item de fatura paga fica: o pagamento saiu com ele, e apaga-lo
            # deixava o lancamento com o valor antigo e a compra fora dos
            # orcamentos passados. Desfaz-se o pagamento antes (Extrato).
            paid = conn.execute(
                f"SELECT COUNT(*) FROM cc_expenses WHERE user_id = ? AND status = 'PAID' AND id IN ({placeholders})",
                [current_user_id, *ids],
            ).fetchone()[0]
            if paid:
                return validation_error(
                    f"{paid} item(ns) ja foram pagos com a fatura e nao se excluem. "
                    "Para tira-los, desfaca o pagamento da fatura no Extrato.",
                    409,
                )
            # Os comprovantes saem pelo CASCADE; os arquivos, depois do commit.
            stored_names = cc_expense_attachment_names(conn, current_user_id, expense_ids=ids)
            cursor = conn.execute(
                f"DELETE FROM cc_expenses WHERE user_id = ? AND id IN ({placeholders})",
                [current_user_id, *ids],
            )
        remove_attachment_files(current_user_id, stored_names)
        return jsonify({"deleted": cursor.rowcount}), 200

    payload = parse_json_body(allow_list=True)
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos uma fatura.")

    inserted = []
    # Cada compra ganha o client_id dela (035): as parcelas da mesma compra
    # neste envio dividem um, e uma segunda compra igual (a mesma parcela de
    # novo) abre outro — sem id, duas corridas iguais viravam uma compra so.
    purchase_groups = {}
    try:
        with get_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError("Cada fatura deve ser um objeto valido.")

                card_id = require_string(item, "card_id", "Cartao")
                require_active_card(conn, current_user_id, card_id)
                category, category_id = resolve_category(conn, current_user_id, item)
                description = require_string(item, "description", "Descricao", max_length=500)
                amount = parse_money(item, "amount", "Valor")
                purchase_date = require_date(item, "purchase_date", "Data da compra")
                invoice_month = parse_int_number(item, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
                invoice_year = parse_int_number(item, "invoice_year", "Ano da fatura", minimum=2000, maximum=MAX_YEAR)
                installment_info = require_string(item, "installment_info", "Parcela", max_length=20)
                status_value = str(item.get("status", "OPEN") or "OPEN").strip().upper()
                if status_value not in ALLOWED_CC_STATUS:
                    raise ValidationError("Status invalido.")
                if status_value != "OPEN":
                    # Pago so pelo pagamento da fatura, que lanca o debito na conta.
                    raise ValidationError(
                        "Uma compra entra em aberto; a fatura e paga por POST /api/cc-expenses/pay-invoice."
                    )
                client_id = optional_client_id(item)
                if not client_id:
                    groups = purchase_groups.setdefault((card_id, description, purchase_date, category_id or category), [])
                    group = next((g for g in groups if installment_info not in g["installments"]), None)
                    if group is None:
                        group = {"client_id": new_id(), "installments": set()}
                        groups.append(group)
                    group["installments"].add(installment_info)
                    client_id = group["client_id"]

                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, category_id, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status, client_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        card_id,
                        category,
                        category_id,
                        description,
                        amount,
                        purchase_date,
                        invoice_month,
                        invoice_year,
                        installment_info,
                        client_id,
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            rows = conn.execute(
                f"SELECT * FROM cc_expenses WHERE id IN ({placeholders})",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar a fatura."}), 400

    return jsonify([row_to_dict(row) for row in rows]), 201


@bp.route("/api/cc-expenses/purchases", methods=["POST"])
@token_required
def create_cc_purchase(current_user_id):
    """Registra uma compra no cartao, parcelando e escolhendo a fatura no servidor.

    O cliente manda a compra (valor total e numero de parcelas); a regra de qual
    fatura cada parcela ocupa fica aqui, junto do cartao que a define.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe uma compra valida.")

    client_id = None
    try:
        client_id = optional_client_id(payload)
        # Segunda entrega do mesmo envio: devolve as parcelas que a primeira
        # criou, antes de validar — o cartao pode ter sido alterado nesse meio.
        with get_db() as conn:
            existing = fetch_purchase_by_client_id(conn, current_user_id, client_id)
        if existing:
            return jsonify([row_to_dict(row) for row in existing]), 200

        card_id = require_string(payload, "card_id", "Cartao")
        purchase = {
            "card_id": card_id,
            "description": require_string(payload, "description", "Descricao", max_length=500),
            "total_amount": parse_money(payload, "total_amount", "Valor total"),
            "purchase_date": require_date(payload, "purchase_date", "Data da compra"),
            "installments": parse_int_number(payload, "installments", "Parcelas", minimum=1, maximum=72),
        }

        with get_db() as conn:
            # A categoria pelo id (035): pelo nome, "Lazer › Outros" virava o
            # "Outros" da raiz e contava no orcamento dele.
            purchase["category"], purchase["category_id"] = resolve_category(conn, current_user_id, payload)
            card = require_active_card(conn, current_user_id, card_id)

            # O client_id e a compra (035): sem um do cliente, ela ganha o seu,
            # e duas compras iguais nunca viram uma.
            purchase_id = client_id or new_id()
            # Numa fatura ja paga a compra ficaria em aberto para sempre (o
            # debito nao roda de novo): ela comeca na primeira nao paga.
            start = purchase_invoice_start(conn, current_user_id, card, purchase["purchase_date"])
            rows = build_installment_rows(purchase, card, start)
            inserted = []
            for row in rows:
                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, category_id, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status, client_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        row["card_id"],
                        row["category"],
                        row["category_id"],
                        row["description"],
                        row["amount"],
                        row["purchase_date"],
                        row["invoice_month"],
                        row["invoice_year"],
                        row["installment_info"],
                        row["status"],
                        purchase_id,
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            created = conn.execute(
                f"SELECT * FROM cc_expenses WHERE user_id = ? AND id IN ({placeholders})"
                " ORDER BY invoice_year ASC, invoice_month ASC",
                (current_user_id, *inserted),
            ).fetchall()
            # A mesma compra esperava em Aprovar (notificacao): vira esta.
            absorbed = absorb_created(conn, current_user_id, "cc_expenses", created[0], installments=created)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        # Com client_id, a recusa do indice unico quer dizer que outra entrega
        # do mesmo envio gravou primeiro (esta foi desfeita inteira).
        with get_db() as conn:
            existing = fetch_purchase_by_client_id(conn, current_user_id, client_id)
        if existing:
            return jsonify([row_to_dict(row) for row in existing]), 200
        return jsonify({"error": "Nao foi possivel criar a compra no cartao."}), 400

    if absorbed:
        return jsonify([{**row_to_dict(row), "matched_inbox": True} for row in created]), 201
    return jsonify([row_to_dict(row) for row in created]), 201


@bp.route("/api/cc-expenses/purchases/<item_id>", methods=["DELETE"])
@token_required
def delete_cc_purchase(current_user_id, item_id):
    """Exclui as parcelas em aberto da compra a que `item_id` pertence (qualquer
    parcela dela, ou um estorno 1/1), numa transacao so.

    A compra e o client_id (same_purchase_sql): uma corrida igual no mesmo dia
    e outra compra e fica. A parcela paga fica com a fatura dela (037); sem
    nenhuma em aberto, 409 e nada sai.
    """
    with get_db() as conn:
        ids = cc_purchase_expense_ids(conn, current_user_id, item_id)
        if not ids:
            return jsonify({"error": "Compra nao encontrada."}), 404
        placeholders = ",".join("?" for _ in ids)
        open_ids = [
            row["id"] for row in conn.execute(
                f"""
                SELECT id FROM cc_expenses
                WHERE user_id = ? AND status = 'OPEN' AND id IN ({placeholders})
                ORDER BY invoice_year, invoice_month, created_at, id
                """,
                [current_user_id, *ids],
            ).fetchall()
        ]
        if not open_ids:
            return validation_error("Nenhuma parcela em aberto foi encontrada para essa compra.", 409)
        # Os comprovantes saem pelo CASCADE; os arquivos, depois do commit.
        stored_names = cc_expense_attachment_names(conn, current_user_id, expense_ids=open_ids)
        open_placeholders = ",".join("?" for _ in open_ids)
        conn.execute(
            f"DELETE FROM cc_expenses WHERE user_id = ? AND status = 'OPEN' AND id IN ({open_placeholders})",
            [current_user_id, *open_ids],
        )
    remove_attachment_files(current_user_id, stored_names)
    return jsonify({"deleted": len(open_ids), "kept_paid": len(ids) - len(open_ids), "ids": open_ids}), 200


@bp.route("/api/cc-expenses/refunds", methods=["POST"])
@token_required
def create_cc_refund(current_user_id):
    """Registra um estorno no cartao: um credito que abate a fatura (033).

    Cai na fatura da data do estorno (a mesma regra da compra) ou, se essa ja
    foi paga, na primeira seguinte em aberto. `refund_of` (opcional) e a compra
    estornada, so para referencia. Idempotente por `client_id`, como a compra.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe um estorno valido.")

    client_id = None
    try:
        client_id = optional_client_id(payload)
        with get_db() as conn:
            existing = fetch_purchase_by_client_id(conn, current_user_id, client_id)
        if existing:
            return jsonify(row_to_dict(existing[0])), 200

        card_id = require_string(payload, "card_id", "Cartao")
        amount = parse_money(payload, "amount", "Valor do estorno")
        refund_date = require_date(payload, "purchase_date", "Data do estorno")
        description = require_string(payload, "description", "Descricao", max_length=500)
        refund_of = str(payload.get("refund_of") or "").strip() or None

        with get_db() as conn:
            card = require_active_card(conn, current_user_id, card_id)
            original = None
            if refund_of:
                original = conn.execute(
                    "SELECT id, category, category_id FROM cc_expenses"
                    " WHERE id = ? AND user_id = ? AND card_id = ? AND kind = 'PURCHASE'",
                    (refund_of, current_user_id, card_id),
                ).fetchone()
                if not original:
                    raise ValidationError("Compra estornada nao encontrada neste cartao.")
            # O estorno abate a categoria da compra estornada: o nome dela
            # volta com o id dela, nao com o de outra categoria de mesmo nome.
            category, category_id = resolve_category(
                conn, current_user_id, payload, required=False, current=original,
            )
            if not category:
                if original is not None:
                    category, category_id = original["category"], original["category_id"]
                else:
                    category, category_id = "Estorno", category_id_for_name(conn, current_user_id, "Estorno")

            invoice = refund_invoice(conn, current_user_id, card, refund_date)
            item_id = new_id()
            conn.execute(
                """
                INSERT INTO cc_expenses
                (id, user_id, card_id, category, category_id, description, amount, purchase_date,
                 invoice_month, invoice_year, installment_info, status, client_id,
                 kind, refund_of)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '1/1', 'OPEN', ?, 'REFUND', ?)
                """,
                (
                    item_id,
                    current_user_id,
                    card_id,
                    category,
                    category_id,
                    description,
                    amount,
                    refund_date,
                    invoice["invoice_month"],
                    invoice["invoice_year"],
                    client_id or new_id(),
                    refund_of,
                ),
            )
            created = conn.execute(
                "SELECT * FROM cc_expenses WHERE id = ? AND user_id = ?",
                (item_id, current_user_id),
            ).fetchone()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        with get_db() as conn:
            existing = fetch_purchase_by_client_id(conn, current_user_id, client_id)
        if existing:
            return jsonify(row_to_dict(existing[0])), 200
        return jsonify({"error": "Nao foi possivel registrar o estorno."}), 400
    return jsonify(row_to_dict(created)), 201


CANDIDATE_COLUMNS = (
    "id, amount, installment_info, status, share_mode, share_others_amount, share_person, share_settled_at"
)


@bp.route("/api/cc-expenses/candidates", methods=["GET"])
@token_required
def cc_expense_candidates(current_user_id):
    """As parcelas de uma compra (excluir a compra, dividir a compra).

    `id`: qualquer parcela dela. A compra e o client_id (035), entao duas
    compras iguais (mesmo cartao, descricao, data e categoria) nao se misturam.
    Sem `id`, a busca antiga por esses quatro campos, para uma tela antiga.
    """
    expense_id = str(request.args.get("id") or "").strip()
    with get_db() as conn:
        if expense_id:
            ids = cc_purchase_expense_ids(conn, current_user_id, expense_id)
            placeholders = ", ".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT {CANDIDATE_COLUMNS} FROM cc_expenses
                WHERE user_id = ? AND kind = 'PURCHASE' AND id IN ({placeholders})
                ORDER BY invoice_year, invoice_month, created_at, id
                """,
                (current_user_id, *ids),
            ).fetchall() if ids else []
            return jsonify([row_to_dict(row) for row in rows]), 200
        rows = conn.execute(
            f"""
            SELECT {CANDIDATE_COLUMNS}
            FROM cc_expenses
            WHERE user_id = ?
              AND kind = 'PURCHASE'
              AND card_id = ?
              AND description = ?
              AND purchase_date = ?
              AND category = ?
            """,
            (
                current_user_id,
                request.args.get("card_id"),
                request.args.get("description"),
                request.args.get("purchase_date"),
                request.args.get("category"),
            ),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows]), 200


@bp.route("/api/cc-expenses/<item_id>/share", methods=["PATCH"])
@token_required
def update_cc_purchase_share(current_user_id, item_id):
    """De quem e a compra (032): a unica coisa que se edita numa compra no cartao.

    Vale para a compra inteira — todas as parcelas, cada uma com a sua fatia
    da parte dos outros (services/sharing.py).
    """
    payload = parse_json_body()
    try:
        with get_db() as conn:
            rows = update_purchase_share(conn, current_user_id, item_id, payload)
    except ValidationError as exc:
        return validation_error(str(exc))
    if rows is None:
        return jsonify({"error": "Compra nao encontrada."}), 404
    return jsonify(rows), 200


def invoice_payment_account_id(conn, current_user_id, card, payload):
    """Conta do pagamento manual: a informada, a do debito automatico ou a padrao."""
    if payload.get("account_id") in (None, "") and card["autopay_account_id"]:
        autopay_account = fetch_account(conn, current_user_id, card["autopay_account_id"])
        if autopay_account and not autopay_account["archived_at"]:
            return autopay_account["id"]
    return resolve_account_id(conn, current_user_id, payload)


@bp.route("/api/cc-expenses/pay-invoice", methods=["POST"])
@token_required
def pay_invoice(current_user_id):
    """Paga uma fatura fechada: debita a conta e baixa os itens, de uma vez.

    Fatura ainda aberta (antes do dia do fechamento) e recusada com 409 — o
    valor dela ainda pode mudar. `account_id` omitido usa a conta do debito
    automatico do cartao, se houver e nao estiver arquivada, senao a conta
    padrao; `date` omitido e hoje.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe uma fatura valida.")

    try:
        card_id = require_string(payload, "card_id", "Cartao")
        invoice_month = parse_int_number(payload, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
        invoice_year = parse_int_number(payload, "invoice_year", "Ano da fatura", minimum=2000, maximum=MAX_YEAR)
        payment_date = optional_date(payload, "date", "Data do pagamento") or local_today().strftime("%Y-%m-%d")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
        if not card:
            return jsonify({"error": "Cartao nao encontrado."}), 404
        try:
            ensure_invoice_closed(card, invoice_month, invoice_year)
            account_id = invoice_payment_account_id(conn, current_user_id, card, payload)
        except InvoiceStillOpenError as exc:
            return validation_error(str(exc), 409)
        except ValidationError as exc:
            return validation_error(str(exc))

        lines, total = invoice_open_lines(conn, current_user_id, card_id, invoice_month, invoice_year)
        if lines and total < 0:
            return validation_error(
                f"A fatura {invoice_label(invoice_month, invoice_year)} ficou com credito de estorno; "
                "ele abate a proxima fatura.",
                409,
            )

        row = settle_invoice(
            conn,
            current_user_id,
            card,
            invoice_month,
            invoice_year,
            account_id=account_id,
            payment_date=payment_date,
            source_type=CC_INVOICE_PAYMENT_SOURCE_TYPE,
            source_id=f"{autopay_source_id(card_id, invoice_month, invoice_year)}:{new_id()}",
        )
        if not row:
            if lines and total == 0:
                # Zerada por estorno: baixada sem lancamento na conta.
                return jsonify({"transaction": None}), 200
            return jsonify({"error": "Nao ha itens em aberto nesta fatura."}), 409
    return jsonify({"transaction": serialize_transaction(row)}), 201


@bp.route("/api/cc-expenses/payments/<item_id>", methods=["DELETE"])
@token_required
def undo_invoice_payment_route(current_user_id, item_id):
    """Desfaz o pagamento de uma fatura (037): o lancamento sai do Extrato, o
    valor volta para o saldo da conta e os itens pagos por ele reabrem.

    A fatura volta para o botao Pagar; o debito automatico nao a paga de novo.
    """
    with get_db() as conn:
        try:
            result = undo_invoice_payment(conn, current_user_id, item_id)
        except InvoiceConflictError as exc:
            return validation_error(str(exc), 409)
    if not result:
        return jsonify({"error": "Pagamento de fatura nao encontrado."}), 404
    return jsonify({
        "undone": True,
        "reopened": result["reopened"],
        "transaction": serialize_transaction(result["transaction"]),
    }), 200
