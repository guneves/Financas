"""Gravar e ler operacoes sem trabalho a mais (2026-10-19, dono: "demorando
muito para salvar e editar operacoes em Investir").

O que estes testes fixam:

- o JSON grande da API vai com gzip quando o cliente aceita, e so ele
  (arquivos, respostas pequenas e erros ficam como estao);
- `investment_realized_results` so e regravada quando o resultado muda: as
  leituras que uma gravacao dispara nao pegam o lock de escrita a toa, e uma
  edicao continua refletindo no resultado;
- as gravacoes nao regravam `investment_positions`; a leitura dela continua
  igual a carteira.
"""

import gzip
import json

from compression import accepts_gzip


def post_movement(client, auth, *, quantity, price, date, sale_price=None):
    metadata = {"sale_date": date, "sale_price": sale_price} if quantity < 0 else {"purchase_date": date}
    response = client.post(
        "/api/investments",
        headers=auth,
        json=[{
            "asset_class": "STOCKS",
            "ticker_or_name": "PETR4",
            "quantity": quantity,
            "average_price": price,
            "current_price": price,
            "metadata": {**metadata, "cash_account_id": None},
        }],
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]


class TestGzip:
    def test_accept_encoding_parsing(self):
        assert accepts_gzip("gzip, deflate, br")
        assert accepts_gzip("br;q=1.0, gzip;q=0.8")
        assert accepts_gzip("*")
        assert not accepts_gzip("gzip;q=0")
        assert not accepts_gzip("br, deflate")
        assert not accepts_gzip("")
        assert not accepts_gzip(None)

    def test_large_json_is_compressed_when_accepted(self, client, auth):
        for day in range(1, 21):
            post_movement(client, auth, quantity=1, price=10 + day, date=f"2026-01-{day:02d}")

        plain = client.get("/api/investments", headers=auth)
        assert "Content-Encoding" not in plain.headers
        assert "Accept-Encoding" in plain.headers.get("Vary", "")

        packed = client.get("/api/investments", headers={**auth, "Accept-Encoding": "gzip"})
        assert packed.status_code == 200
        assert packed.headers["Content-Encoding"] == "gzip"
        body = packed.get_data()
        assert len(body) < len(plain.get_data())
        assert json.loads(gzip.decompress(body)) == plain.get_json()

    def test_small_and_error_responses_stay_plain(self, client, auth):
        small = client.get("/api/auth/me", headers={**auth, "Accept-Encoding": "gzip"})
        assert small.status_code == 200
        assert "Content-Encoding" not in small.headers

        missing = client.patch(
            "/api/investments/nao-existe",
            headers={**auth, "Accept-Encoding": "gzip"},
            json={"quantity": 1},
        )
        assert missing.status_code == 404
        assert "Content-Encoding" not in missing.headers


class TestRealizedResultsRewrite:
    def stored(self, db_module, user_id):
        with db_module.get_db() as conn:
            return {
                row["source_transaction_id"]: (row["realized_profit"], row["updated_at"])
                for row in conn.execute(
                    "SELECT source_transaction_id, realized_profit, updated_at"
                    " FROM investment_realized_results WHERE user_id = ?",
                    (user_id,),
                )
            }

    def test_reads_do_not_rewrite_unchanged_results(self, client, auth, user, db_module):
        post_movement(client, auth, quantity=10, price=10, date="2026-01-05")
        sale = post_movement(client, auth, quantity=-4, price=10, date="2026-02-05", sale_price=15)
        before = self.stored(db_module, user["id"])
        assert before[sale["id"]][0] == 20.0

        for path in ("/api/investments", "/api/investments/portfolio"):
            assert client.get(path, headers=auth).status_code == 200
        assert self.stored(db_module, user["id"]) == before

    def test_an_edit_still_changes_the_result(self, client, auth, user, db_module):
        buy = post_movement(client, auth, quantity=10, price=10, date="2026-01-05")
        sale = post_movement(client, auth, quantity=-4, price=10, date="2026-02-05", sale_price=15)

        response = client.patch(
            f"/api/investments/{buy['id']}",
            headers=auth,
            json={"quantity": 10, "average_price": 12, "metadata": {"purchase_date": "2026-01-05"}},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert self.stored(db_module, user["id"])[sale["id"]][0] == 12.0

        listed = client.get("/api/investments", headers=auth).get_json()
        [row] = [item for item in listed if item["id"] == sale["id"]]
        assert row["realized_profit"] == 12.0

    def test_deleting_the_sale_removes_its_result(self, client, auth, user, db_module):
        post_movement(client, auth, quantity=10, price=10, date="2026-01-05")
        sale = post_movement(client, auth, quantity=-4, price=10, date="2026-02-05", sale_price=15)
        assert client.delete(f"/api/investments/{sale['id']}", headers=auth).status_code == 200
        assert sale["id"] not in self.stored(db_module, user["id"])


def test_writes_leave_positions_to_the_read(client, auth, user, db_module):
    post_movement(client, auth, quantity=10, price=10, date="2026-01-05")
    with db_module.get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM investment_positions WHERE user_id = ?", (user["id"],)
        ).fetchone()[0]
    assert count == 0

    positions = client.get("/api/investment-positions", headers=auth).get_json()
    portfolio = client.get("/api/investments/portfolio", headers=auth).get_json()
    assert [p["quantity"] for p in positions] == [a["quantity"] for a in portfolio["assets"]]
    assert positions[0]["invested_amount"] == 100.0
