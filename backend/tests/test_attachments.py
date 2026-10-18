"""Comprovantes por lancamento (migration 014).

O que estes testes fixam:

- o tipo vem dos bytes, nao do nome: um .pdf que nao e PDF e recusado, e o que
  volta no download e o tipo detectado;
- o nome enviado nunca vira caminho no disco (so e exibido);
- limite de tamanho e de quantidade por lancamento;
- as rotas sao aninhadas no lancamento: o id do lancamento tem que bater com o
  do comprovante, inclusive para excluir;
- excluir o lancamento leva linha e arquivo; o que sobra de outros caminhos
  (movimentacao de investimento excluida) sai na varredura de orfaos;
- nada de outro usuario e listado, baixado ou apagado;
- o extrato traz `attachment_count` por linha.
"""

import importlib
import io
import os

import pytest


def attachment_files():
    """`services/attachments.py`: caminhos no disco e a varredura de orfaos."""
    return importlib.import_module("services.attachments")


def attachment_routes():
    """`routes/attachments.py`: onde os limites de upload sao lidos (patch aqui)."""
    return importlib.import_module("routes.attachments")

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 89.9,
        "date": "2026-09-10",
        "category": "Saúde",
        "description": "Farmacia",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def default_account_id(client, headers):
    """A conta que recebe o lancamento de uma operacao de investimento: ele so
    existe quando a operacao pede (`metadata.cash_account_id`)."""
    accounts = client.get("/api/accounts", headers=headers).get_json()
    return next(item["id"] for item in accounts if item["is_default"])


def upload(client, headers, transaction_id, content=PDF, filename="nota.pdf"):
    return client.post(
        f"/api/transactions/{transaction_id}/attachments",
        data={"file": (io.BytesIO(content), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


def stored_path(app_module, user_id, attachment_id):
    with importlib.import_module("db").get_db() as conn:
        row = conn.execute(
            "SELECT stored_name FROM transaction_attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
    assert row is not None
    return attachment_files().attachment_path(user_id, row["stored_name"])


def attachment_rows(app_module, transaction_id):
    with importlib.import_module("db").get_db() as conn:
        return conn.execute(
            "SELECT * FROM transaction_attachments WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchall()


class TestUpload:
    def test_a_pdf_is_stored_and_listed(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        response = upload(client, auth, transaction["id"])
        assert response.status_code == 201, response.get_data(as_text=True)
        body = response.get_json()
        assert body["original_name"] == "nota.pdf"
        assert body["content_type"] == "application/pdf"
        assert body["size_bytes"] == len(PDF)
        assert body["transaction_id"] == transaction["id"]
        assert "stored_name" not in body and "user_id" not in body

        path = stored_path(app_module, user["id"], body["id"])
        with open(path, "rb") as file:
            assert file.read() == PDF

        listed = client.get(f"/api/transactions/{transaction['id']}/attachments", headers=auth)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.get_json()] == [body["id"]]

    @pytest.mark.parametrize(
        "content, expected",
        [(PNG, "image/png"), (JPEG, "image/jpeg"), (b"GIF89a" + b"\x00" * 16, "image/gif"),
         (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
         (b"\x00\x00\x00\x18ftypheic\x00\x00", "image/heic")],
    )
    def test_the_type_comes_from_the_bytes(self, client, auth, content, expected):
        transaction = create_transaction(client, auth)
        # Nome enganoso de proposito: vale o conteudo.
        response = upload(client, auth, transaction["id"], content=content, filename="foto.txt")
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["content_type"] == expected

    def test_a_renamed_html_is_refused(self, client, auth, app_module):
        transaction = create_transaction(client, auth)
        response = upload(
            client, auth, transaction["id"],
            content=b"<html><script>alert(1)</script></html>", filename="recibo.pdf",
        )
        assert response.status_code == 415
        assert attachment_rows(app_module, transaction["id"]) == []

    def test_an_empty_file_is_refused(self, client, auth):
        transaction = create_transaction(client, auth)
        response = upload(client, auth, transaction["id"], content=b"")
        assert response.status_code == 400

    def test_a_missing_file_field_is_refused(self, client, auth):
        transaction = create_transaction(client, auth)
        response = client.post(
            f"/api/transactions/{transaction['id']}/attachments",
            data={"other": "x"},
            headers=auth,
            content_type="multipart/form-data",
        )
        assert response.status_code == 400

    def test_a_file_over_the_limit_is_refused(self, client, auth, app_module, monkeypatch):
        monkeypatch.setattr(attachment_routes(), "ATTACHMENT_MAX_BYTES", len(PDF) - 1)
        transaction = create_transaction(client, auth)
        response = upload(client, auth, transaction["id"])
        assert response.status_code == 413
        assert attachment_rows(app_module, transaction["id"]) == []

    def test_the_per_transaction_cap(self, client, auth, app_module, monkeypatch):
        monkeypatch.setattr(attachment_routes(), "ATTACHMENT_MAX_PER_TRANSACTION", 2)
        transaction = create_transaction(client, auth)
        assert upload(client, auth, transaction["id"]).status_code == 201
        assert upload(client, auth, transaction["id"]).status_code == 201
        response = upload(client, auth, transaction["id"])
        assert response.status_code == 400
        assert len(attachment_rows(app_module, transaction["id"])) == 2

    def test_the_uploaded_name_never_becomes_a_path(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        response = upload(client, auth, transaction["id"], filename="../../finance.db.pdf")
        assert response.status_code == 201
        body = response.get_json()
        assert body["original_name"] == "finance.db.pdf"
        path = stored_path(app_module, user["id"], body["id"])
        assert os.path.dirname(path) == attachment_files().attachment_user_dir(user["id"])
        assert "finance" not in os.path.basename(path)

    def test_an_unknown_transaction_is_404(self, client, auth):
        assert upload(client, auth, "nao-existe").status_code == 404

    def test_investment_cash_and_invoice_rows_accept_receipts(self, client, auth):
        # Nota de corretagem no lancamento de uma operacao que foi ao extrato:
        # o comprovante nao mexe no lancamento, entao nao ha motivo para bloquear.
        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "PETR4",
                "quantity": 10,
                "average_price": 30.0,
                "current_price": 30.0,
                "metadata": {
                    "purchase_date": "2026-02-10",
                    "cash_account_id": default_account_id(client, auth),
                },
            },
        )
        assert response.status_code in (200, 201)
        cash = [
            item for item in client.get("/api/transactions", headers=auth).get_json()
            if item.get("source_type") == "INVESTMENT_TRANSACTION"
        ][0]
        assert upload(client, auth, cash["id"]).status_code == 201


class TestDownload:
    def test_the_file_comes_back_with_the_detected_type(self, client, auth):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"], filename="Recibo farmácia.pdf").get_json()

        response = client.get(
            f"/api/transactions/{transaction['id']}/attachments/{attachment['id']}/file",
            headers=auth,
        )
        assert response.status_code == 200
        assert response.data == PDF
        assert response.mimetype == "application/pdf"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "attachment" not in response.headers.get("Content-Disposition", "")

        download = client.get(
            f"/api/transactions/{transaction['id']}/attachments/{attachment['id']}/file?download=1",
            headers=auth,
        )
        disposition = download.headers["Content-Disposition"]
        assert disposition.startswith("attachment")
        assert "Recibo%20farm%C3%A1cia.pdf" in disposition

    def test_the_transaction_id_must_match(self, client, auth):
        first = create_transaction(client, auth)
        second = create_transaction(client, auth)
        attachment = upload(client, auth, first["id"]).get_json()
        response = client.get(
            f"/api/transactions/{second['id']}/attachments/{attachment['id']}/file",
            headers=auth,
        )
        assert response.status_code == 404

    def test_a_file_missing_from_disk_is_410(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"]).get_json()
        os.remove(stored_path(app_module, user["id"], attachment["id"]))
        response = client.get(
            f"/api/transactions/{transaction['id']}/attachments/{attachment['id']}/file",
            headers=auth,
        )
        assert response.status_code == 410


class TestDelete:
    def test_deleting_an_attachment_removes_row_and_file(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])

        response = client.delete(
            f"/api/transactions/{transaction['id']}/attachments/{attachment['id']}",
            headers=auth,
        )
        assert response.status_code == 200
        assert attachment_rows(app_module, transaction["id"]) == []
        assert not os.path.exists(path)

    def test_deleting_with_the_wrong_transaction_is_refused(self, client, auth, user, app_module):
        first = create_transaction(client, auth)
        second = create_transaction(client, auth)
        attachment = upload(client, auth, first["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])

        response = client.delete(
            f"/api/transactions/{second['id']}/attachments/{attachment['id']}",
            headers=auth,
        )
        assert response.status_code == 404
        assert len(attachment_rows(app_module, first["id"])) == 1
        assert os.path.exists(path)

    def test_deleting_the_transaction_takes_its_attachments(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])

        response = client.delete(f"/api/transactions/{transaction['id']}", headers=auth)
        assert response.status_code == 200
        assert attachment_rows(app_module, transaction["id"]) == []
        assert not os.path.exists(path)

    def test_a_refused_transaction_delete_keeps_the_receipt(self, client, auth, user, app_module):
        client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "VALE3",
                "quantity": 5,
                "average_price": 60.0,
                "current_price": 60.0,
                "metadata": {
                    "purchase_date": "2026-03-10",
                    "cash_account_id": default_account_id(client, auth),
                },
            },
        )
        cash = [
            item for item in client.get("/api/transactions", headers=auth).get_json()
            if item.get("source_type") == "INVESTMENT_TRANSACTION"
        ][0]
        attachment = upload(client, auth, cash["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])

        response = client.delete(f"/api/transactions/{cash['id']}", headers=auth)
        assert response.status_code == 409
        assert os.path.exists(path)

    def test_orphans_from_other_paths_are_pruned(self, client, auth, user, app_module):
        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "ITUB4",
                "quantity": 10,
                "average_price": 30.0,
                "current_price": 30.0,
                "metadata": {
                    "purchase_date": "2026-04-10",
                    "cash_account_id": default_account_id(client, auth),
                },
            },
        )
        body = response.get_json()
        investment = body[0] if isinstance(body, list) else body
        cash = [
            item for item in client.get("/api/transactions", headers=auth).get_json()
            if item.get("source_id") == investment["id"]
        ][0]
        attachment = upload(client, auth, cash["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])

        # Excluir a movimentacao apaga o lancamento ligado a ela; a linha do
        # comprovante vai pelo CASCADE, o arquivo fica ate a varredura.
        assert client.delete(f"/api/investments/{investment['id']}", headers=auth).status_code == 200
        assert attachment_rows(app_module, cash["id"]) == []
        assert os.path.exists(path)

        # Recente demais: a varredura respeita a folga de um upload em andamento.
        assert attachment_files().prune_orphan_attachment_files() == []
        assert os.path.exists(path)

        removed = attachment_files().prune_orphan_attachment_files(min_age_seconds=-1)
        assert any(entry.endswith(os.path.basename(path)) for entry in removed)
        assert not os.path.exists(path)

    def test_the_sweep_keeps_referenced_files(self, client, auth, user, app_module):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])
        attachment_files().prune_orphan_attachment_files(min_age_seconds=-1)
        assert os.path.exists(path)


class TestStatementCount:
    def test_each_row_carries_its_attachment_count(self, client, auth):
        with_two = create_transaction(client, auth, description="Consulta")
        without = create_transaction(client, auth, description="Padaria")
        upload(client, auth, with_two["id"])
        upload(client, auth, with_two["id"], content=PNG, filename="foto.png")

        rows = {item["id"]: item for item in client.get("/api/transactions", headers=auth).get_json()}
        assert rows[with_two["id"]]["attachment_count"] == 2
        assert rows[without["id"]]["attachment_count"] == 0

        filtered = client.get("/api/transactions?q=Consulta", headers=auth).get_json()
        assert [item["attachment_count"] for item in filtered] == [2]


class TestIsolation:
    def test_another_user_cannot_list_download_upload_or_delete(
        self, client, auth, user, other_user, app_module
    ):
        transaction = create_transaction(client, auth)
        attachment = upload(client, auth, transaction["id"]).get_json()
        path = stored_path(app_module, user["id"], attachment["id"])
        intruder = other_user["headers"]
        base = f"/api/transactions/{transaction['id']}/attachments"

        assert client.get(base, headers=intruder).status_code == 404
        assert client.get(f"{base}/{attachment['id']}/file", headers=intruder).status_code == 404
        assert upload(client, intruder, transaction["id"]).status_code == 404
        assert client.delete(f"{base}/{attachment['id']}", headers=intruder).status_code == 404
        assert os.path.exists(path)
        assert len(attachment_rows(app_module, transaction["id"])) == 1

    def test_files_live_under_the_owner_directory(self, client, auth, user, other_user, app_module):
        mine = create_transaction(client, auth)
        theirs = create_transaction(client, other_user["headers"])
        a = upload(client, auth, mine["id"]).get_json()
        b = upload(client, other_user["headers"], theirs["id"]).get_json()
        assert os.path.dirname(stored_path(app_module, user["id"], a["id"])) != os.path.dirname(
            stored_path(app_module, other_user["id"], b["id"])
        )

    def test_requires_auth(self, client, auth):
        transaction = create_transaction(client, auth)
        response = client.get(f"/api/transactions/{transaction['id']}/attachments")
        assert response.status_code == 401


# --- comprovantes de compra no cartao (016) ---------------------------------

def create_card_purchase(client, headers, installments=3, description="Geladeira"):
    card = client.post(
        "/api/credit-cards", headers=headers,
        json={"name": f"Cartao {description}", "due_day": 10, "closing_day": 3},
    ).get_json()
    card = card[0] if isinstance(card, list) else card
    response = client.post(
        "/api/cc-expenses/purchases",
        headers=headers,
        json={
            "card_id": card["id"],
            "category": "Casa",
            "description": description,
            "total_amount": 3000,
            "purchase_date": "2026-09-05",
            "installments": installments,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return card, response.get_json()


def upload_to_expense(client, headers, expense_id, content=PDF, filename="nota.pdf"):
    return client.post(
        f"/api/cc-expenses/{expense_id}/attachments",
        data={"file": (io.BytesIO(content), filename)},
        headers=headers,
        content_type="multipart/form-data",
    )


def expense_stored_path(user_id, attachment_id):
    with importlib.import_module("db").get_db() as conn:
        row = conn.execute(
            "SELECT stored_name FROM cc_expense_attachments WHERE id = ?", (attachment_id,),
        ).fetchone()
    return attachment_files().attachment_path(user_id, row["stored_name"])


class TestCardPurchaseReceipts:
    def test_a_receipt_on_one_installment_shows_on_every_installment(self, client, auth):
        _card, installments = create_card_purchase(client, auth)
        first, last = installments[0]["id"], installments[-1]["id"]
        created = upload_to_expense(client, auth, first)
        assert created.status_code == 201, created.get_data(as_text=True)

        listed = client.get(f"/api/cc-expenses/{last}/attachments", headers=auth).get_json()
        assert [item["id"] for item in listed] == [created.get_json()["id"]]

        file = client.get(f"/api/cc-expenses/{last}/attachments/{listed[0]['id']}/file", headers=auth)
        assert file.status_code == 200
        assert file.data == PDF

    def test_cc_expenses_carry_the_purchase_attachment_count(self, client, auth):
        _card, installments = create_card_purchase(client, auth)
        create_card_purchase(client, auth, description="Outra compra")
        upload_to_expense(client, auth, installments[1]["id"])
        rows = client.get("/api/cc-expenses", headers=auth).get_json()
        counts = {row["description"]: set() for row in rows}
        for row in rows:
            counts[row["description"]].add(row["attachment_count"])
        assert counts == {"Geladeira": {1}, "Outra compra": {0}}

    def test_the_route_guard_refuses_another_purchase(self, client, auth):
        _card, installments = create_card_purchase(client, auth)
        _card2, other = create_card_purchase(client, auth, description="Outra compra")
        attachment = upload_to_expense(client, auth, installments[0]["id"]).get_json()
        response = client.delete(
            f"/api/cc-expenses/{other[0]['id']}/attachments/{attachment['id']}", headers=auth,
        )
        assert response.status_code == 404

    def test_deleting_the_purchase_removes_rows_and_files(self, client, auth, user):
        _card, installments = create_card_purchase(client, auth)
        attachment = upload_to_expense(client, auth, installments[0]["id"]).get_json()
        path = expense_stored_path(user["id"], attachment["id"])
        assert os.path.isfile(path)

        response = client.delete(
            "/api/cc-expenses", headers=auth, json={"ids": [item["id"] for item in installments]},
        )
        assert response.status_code == 200
        assert not os.path.exists(path)

    def test_a_card_with_an_open_purchase_is_not_deleted_and_keeps_the_files(self, client, auth, user):
        # 037: excluir o cartao nao leva mais as compras (nem os recibos) junto.
        card, installments = create_card_purchase(client, auth)
        attachment = upload_to_expense(client, auth, installments[0]["id"]).get_json()
        path = expense_stored_path(user["id"], attachment["id"])

        assert client.delete(f"/api/credit-cards/{card['id']}", headers=auth).status_code == 409
        assert os.path.exists(path)

    def test_orphan_sweep_keeps_card_receipts(self, client, auth, user):
        _card, installments = create_card_purchase(client, auth)
        attachment = upload_to_expense(client, auth, installments[0]["id"]).get_json()
        path = expense_stored_path(user["id"], attachment["id"])
        old = os.path.getmtime(path) - 3600
        os.utime(path, (old, old))

        attachment_files().prune_orphan_attachment_files(min_age_seconds=0)
        assert os.path.isfile(path)

    def test_another_user_cannot_see_or_attach(self, client, auth, other_user):
        _card, installments = create_card_purchase(client, auth)
        upload_to_expense(client, auth, installments[0]["id"])
        foreign = other_user["headers"]
        assert client.get(f"/api/cc-expenses/{installments[0]['id']}/attachments", headers=foreign).status_code == 404
        assert upload_to_expense(client, foreign, installments[0]["id"]).status_code == 404
