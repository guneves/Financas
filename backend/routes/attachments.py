"""Comprovantes por lancamento (`/api/transactions/<id>/attachments`).

As rotas ficam aninhadas no lancamento e conferem os dois ids — e essa a
guarda do delete. O arquivo e gravado antes da linha e so e apagado depois do
commit; `prune_orphan_attachment_files()` varre as sobras no boot.
"""

import hashlib
import os
import uuid

from flask import Blueprint, jsonify, request, send_file

from auth import token_required
from config import ATTACHMENT_MAX_BYTES
from db import get_db, new_id
from services.attachments import (
    ATTACHMENT_TYPES,
    ATTACHMENT_TYPES_MESSAGE,
    attachment_path,
    attachment_user_dir,
    clean_attachment_name,
    remove_attachment_files,
    serialize_attachment,
    sniff_attachment_type,
)
from validators import validation_error

bp = Blueprint("attachments", __name__)


# Um lancamento com mais que isso nao e um lancamento, e uma pasta.
ATTACHMENT_MAX_PER_TRANSACTION = 20


def require_owned_transaction(conn, current_user_id, transaction_id):
    return conn.execute(
        "SELECT id FROM transactions WHERE id = ? AND user_id = ?",
        (transaction_id, current_user_id),
    ).fetchone()


def fetch_owned_attachment(conn, current_user_id, transaction_id, attachment_id):
    return conn.execute(
        """
        SELECT * FROM transaction_attachments
        WHERE id = ? AND transaction_id = ? AND user_id = ?
        """,
        (attachment_id, transaction_id, current_user_id),
    ).fetchone()


@bp.route("/api/transactions/<item_id>/attachments", methods=["GET", "POST"])
@token_required
def transaction_attachments(current_user_id, item_id):
    if request.method == "GET":
        with get_db() as conn:
            if not require_owned_transaction(conn, current_user_id, item_id):
                return jsonify({"error": "Lancamento nao encontrado."}), 404
            rows = conn.execute(
                """
                SELECT * FROM transaction_attachments
                WHERE user_id = ? AND transaction_id = ?
                ORDER BY created_at, id
                """,
                (current_user_id, item_id),
            ).fetchall()
        return jsonify([serialize_attachment(row) for row in rows]), 200

    # Recusa pelo cabecalho antes de ler o corpo: um video de 2 GB escolhido
    # por engano nao chega a ocupar a memoria do processo.
    limit_mb = ATTACHMENT_MAX_BYTES / (1024 * 1024)
    too_big = f"O arquivo passa do limite de {limit_mb:.0f} MB."
    if request.content_length and request.content_length > ATTACHMENT_MAX_BYTES + 64 * 1024:
        return validation_error(too_big, 413)

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return validation_error("Envie o arquivo no campo 'file'.")
    data = upload.read(ATTACHMENT_MAX_BYTES + 1)
    if not data:
        return validation_error("O arquivo esta vazio.")
    if len(data) > ATTACHMENT_MAX_BYTES:
        return validation_error(too_big, 413)
    content_type = sniff_attachment_type(data[:16])
    if not content_type:
        return validation_error(ATTACHMENT_TYPES_MESSAGE, 415)

    extension = ATTACHMENT_TYPES[content_type]
    attachment_id = new_id()
    stored_name = f"{uuid.uuid4().hex}{extension}"
    original_name = clean_attachment_name(upload.filename, extension)

    with get_db() as conn:
        if not require_owned_transaction(conn, current_user_id, item_id):
            return jsonify({"error": "Lancamento nao encontrado."}), 404
        count = conn.execute(
            """
            SELECT COUNT(*) FROM transaction_attachments
            WHERE user_id = ? AND transaction_id = ?
            """,
            (current_user_id, item_id),
        ).fetchone()[0]
        if count >= ATTACHMENT_MAX_PER_TRANSACTION:
            return validation_error(
                f"Este lancamento ja tem {ATTACHMENT_MAX_PER_TRANSACTION} comprovantes."
            )

        # Arquivo primeiro, linha depois: se a gravacao da linha falhar, o
        # arquivo sai; se o processo cair no meio, a varredura de boot o leva.
        user_dir = attachment_user_dir(current_user_id)
        os.makedirs(user_dir, exist_ok=True)
        path = attachment_path(current_user_id, stored_name)
        with open(path, "wb") as file:
            file.write(data)
        try:
            conn.execute(
                """
                INSERT INTO transaction_attachments
                (id, user_id, transaction_id, original_name, stored_name,
                 content_type, size_bytes, sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attachment_id,
                    current_user_id,
                    item_id,
                    original_name,
                    stored_name,
                    content_type,
                    len(data),
                    hashlib.sha256(data).hexdigest(),
                ),
            )
            row = fetch_owned_attachment(conn, current_user_id, item_id, attachment_id)
        except Exception:
            remove_attachment_files(current_user_id, [stored_name])
            raise
    return jsonify(serialize_attachment(row)), 201


@bp.route("/api/transactions/<item_id>/attachments/<attachment_id>/file", methods=["GET"])
@token_required
def transaction_attachment_file(current_user_id, item_id, attachment_id):
    with get_db() as conn:
        row = fetch_owned_attachment(conn, current_user_id, item_id, attachment_id)
    if not row:
        return jsonify({"error": "Comprovante nao encontrado."}), 404
    path = attachment_path(current_user_id, row["stored_name"])
    if not os.path.isfile(path):
        return jsonify({"error": "O arquivo deste comprovante sumiu da pasta de comprovantes."}), 410

    as_download = str(request.args.get("download", "")).lower() in ("1", "true", "yes")
    response = send_file(
        path,
        mimetype=row["content_type"],
        as_attachment=as_download,
        download_name=row["original_name"],
        max_age=0,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return response


@bp.route("/api/transactions/<item_id>/attachments/<attachment_id>", methods=["DELETE"])
@token_required
def delete_transaction_attachment(current_user_id, item_id, attachment_id):
    """Remove um comprovante.

    A rota aninhada e a guarda: o id do lancamento tem que bater com o do
    comprovante, entao um id trocado no cliente nao apaga o recibo de outro
    lancamento. O arquivo sai do disco depois do commit.
    """
    with get_db() as conn:
        row = fetch_owned_attachment(conn, current_user_id, item_id, attachment_id)
        if not row:
            return jsonify({"deleted": False, "error": "Comprovante nao encontrado."}), 404
        conn.execute(
            "DELETE FROM transaction_attachments WHERE id = ? AND user_id = ?",
            (attachment_id, current_user_id),
        )
    remove_attachment_files(current_user_id, [row["stored_name"]])
    return jsonify({"deleted": True}), 200
