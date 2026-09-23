"""Comprovantes (014): o arquivo no disco e as regras sobre ele.

A linha em `transaction_attachments` so referencia; os bytes ficam em
`ATTACHMENTS_DIR/<user_id>/<stored_name>`, com `stored_name` gerado — o nome
enviado e so exibido, nunca vira caminho. Fora do zip de backup; o backup
mantem um espelho da pasta (db.mirror_attachments).
"""

import os
import time

from config import ATTACHMENTS_DIR
from db import get_db, row_to_dict


# O tipo vem dos primeiros bytes, nao da extensao nem do Content-Type que o
# navegador manda: e o que e servido de volta, entao um .html renomeado para
# .pdf nao pode sair como PDF — ele e recusado.
ATTACHMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/heic": ".heic",
}
HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"}
ATTACHMENT_TYPES_MESSAGE = "Envie um PDF ou uma imagem (JPG, PNG, WEBP, GIF ou HEIC)."


def sniff_attachment_type(head):
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIC_BRANDS:
        return "image/heic"
    return None


def attachment_user_dir(current_user_id):
    return os.path.join(ATTACHMENTS_DIR, str(current_user_id))


def attachment_path(current_user_id, stored_name):
    return os.path.join(attachment_user_dir(current_user_id), os.path.basename(stored_name))


def remove_attachment_files(current_user_id, stored_names):
    for stored_name in stored_names:
        path = attachment_path(current_user_id, stored_name)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"Nao foi possivel remover o comprovante {path}: {exc}")


def cc_purchase_expense_ids(conn, current_user_id, expense_id):
    """Ids de todas as parcelas da compra de `expense_id` (016).

    cc_expenses nao tem id de compra: as parcelas sao as linhas do mesmo
    cartao com a mesma descricao, data e categoria — a chave que
    /api/cc-expenses/candidates e a tela Cartoes usam. Vazio se a linha nao e
    do usuario.
    """
    row = conn.execute(
        """
        SELECT card_id, description, purchase_date, category
        FROM cc_expenses WHERE id = ? AND user_id = ?
        """,
        (expense_id, current_user_id),
    ).fetchone()
    if not row:
        return []
    rows = conn.execute(
        """
        SELECT id FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND description = ?
          AND purchase_date = ? AND category = ?
        """,
        (current_user_id, row["card_id"], row["description"], row["purchase_date"], row["category"]),
    ).fetchall()
    return [item["id"] for item in rows]


def cc_expense_attachment_names(conn, current_user_id, expense_ids=None, card_id=None):
    """stored_name dos comprovantes presos a essas parcelas (ou a esse cartao),
    lidos antes de um DELETE que os leva por CASCADE — o arquivo sai depois."""
    if card_id is not None:
        rows = conn.execute(
            """
            SELECT a.stored_name FROM cc_expense_attachments a
            JOIN cc_expenses e ON e.id = a.cc_expense_id AND e.user_id = a.user_id
            WHERE a.user_id = ? AND e.card_id = ?
            """,
            (current_user_id, card_id),
        ).fetchall()
        return [row["stored_name"] for row in rows]
    if not expense_ids:
        return []
    placeholders = ", ".join("?" for _ in expense_ids)
    rows = conn.execute(
        f"""
        SELECT stored_name FROM cc_expense_attachments
        WHERE user_id = ? AND cc_expense_id IN ({placeholders})
        """,
        (current_user_id, *expense_ids),
    ).fetchall()
    return [row["stored_name"] for row in rows]


def clean_attachment_name(raw_name, extension):
    """Nome para exibir e baixar: sem pasta, sem caractere de controle, curto."""
    name = os.path.basename(str(raw_name or "").replace("\\", "/")).strip()
    name = "".join(char for char in name if char.isprintable()).strip(" .")
    if not name:
        name = f"comprovante{extension}"
    if len(name) > 120:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 120 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else name[:120]
    return name


def serialize_attachment(row):
    item = row_to_dict(row)
    item.pop("stored_name", None)
    item.pop("user_id", None)
    return item


def prune_orphan_attachment_files(min_age_seconds=600):
    """Remove do disco o comprovante cuja linha ja nao existe.

    O DELETE /api/transactions (e o de compras no cartao) apaga os arquivos na
    hora, mas um lancamento tambem sai por outros caminhos (movimentacao de investimento excluida leva
    o espelho de caixa pelo CASCADE). Roda no boot; arquivos recentes ficam,
    para nao disputar com um upload em andamento em outro processo.
    """
    if not os.path.isdir(ATTACHMENTS_DIR):
        return []
    cutoff = time.time() - min_age_seconds
    removed = []
    with get_db() as conn:
        for user_dir in os.listdir(ATTACHMENTS_DIR):
            full_dir = os.path.join(ATTACHMENTS_DIR, user_dir)
            if not os.path.isdir(full_dir):
                continue
            known = {
                row["stored_name"]
                for row in conn.execute(
                    """
                    SELECT stored_name FROM transaction_attachments WHERE user_id = ?
                    UNION ALL
                    SELECT stored_name FROM cc_expense_attachments WHERE user_id = ?
                    """,
                    (user_dir, user_dir),
                ).fetchall()
            }
            for filename in os.listdir(full_dir):
                path = os.path.join(full_dir, filename)
                if filename in known or not os.path.isfile(path):
                    continue
                try:
                    if os.path.getmtime(path) > cutoff:
                        continue
                    os.remove(path)
                    removed.append(os.path.join(user_dir, filename))
                except OSError as exc:
                    print(f"Nao foi possivel remover o comprovante orfao {path}: {exc}")
    return removed
