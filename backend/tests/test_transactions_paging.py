"""Paginas do extrato: `GET /api/transactions?limit=N&cursor=...`.

Sem `limit` nada muda (lista inteira). Com ele, keyset por
`date DESC, created_at DESC, id DESC`, `totals` do filtro todo e `day_totals`
dos dias da pagina — services/transaction_pages.py.
"""

import base64


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 10,
        "date": "2026-03-01",
        "category": "Lazer",
        "description": "Cinema",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def get(client, headers, **params):
    response = client.get("/api/transactions", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def all_pages(client, headers, limit, **params):
    pages, cursor = [], None
    while True:
        query = {"limit": limit, **params}
        if cursor:
            query["cursor"] = cursor
        page = get(client, headers, **query)
        pages.append(page)
        cursor = page["next_cursor"]
        if not cursor:
            return pages


def set_columns(db_module, item_id, **values):
    assignments = ", ".join(f"{key} = ?" for key in values)
    with db_module.get_db() as conn:
        conn.execute(f"UPDATE transactions SET {assignments} WHERE id = ?", [*values.values(), item_id])


def test_without_limit_unchanged(client, auth):
    for day in ("2026-03-01", "2026-03-03", "2026-03-02"):
        create_transaction(client, auth, date=day, description=day)
    rows = get(client, auth)
    assert isinstance(rows, list)
    assert [row["description"] for row in rows] == ["2026-03-03", "2026-03-02", "2026-03-01"]


def test_pages_cover_everything_once(client, auth):
    for index in range(7):
        create_transaction(client, auth, date=f"2026-03-0{index + 1}", description=f"t{index}")
    pages = all_pages(client, auth, 3)
    assert [len(page["items"]) for page in pages] == [3, 3, 1]
    assert pages[-1]["next_cursor"] is None
    assert all(page["count"] == 7 for page in pages)
    paged = [row["id"] for page in pages for row in page["items"]]
    assert len(paged) == len(set(paged))
    assert paged == [row["id"] for row in get(client, auth)]


def test_ties_on_date_and_created_at_are_ordered_by_id(client, auth, db_module):
    ids = [create_transaction(client, auth, description=f"t{i}")["id"] for i in range(5)]
    for item_id in ids:
        set_columns(db_module, item_id, created_at="2026-03-01T12:00:00Z")
    pages = all_pages(client, auth, 2)
    paged = [row["id"] for page in pages for row in page["items"]]
    assert paged == sorted(ids, reverse=True)


def test_filters_apply_to_pages_and_totals(client, auth):
    for index in range(4):
        create_transaction(client, auth, description=f"Mercado {index}", amount=10 + index)
    create_transaction(client, auth, description="Cinema", amount=99)
    create_transaction(client, auth, description="Salario", type="INCOME", category="Salario", amount=1000)
    page = get(client, auth, limit=2, q="Mercado")
    assert len(page["items"]) == 2
    assert all("Mercado" in row["description"] for row in page["items"])
    # Os totais sao do filtro inteiro (10 + 11 + 12 + 13), nao da pagina.
    assert page["totals"] == {"income": 0, "expense": 46, "investment": 0}
    income = get(client, auth, limit=1, type="INCOME")
    assert income["totals"]["income"] == 1000
    assert income["next_cursor"] is None


def test_totals_keep_investment_apart(client, auth, db_module):
    create_transaction(client, auth, description="Mercado", amount=50)
    aporte = create_transaction(client, auth, description="Aporte", amount=200)
    resgate = create_transaction(client, auth, description="Resgate", type="INCOME", category="Outros", amount=30)
    create_transaction(client, auth, description="Salario", type="INCOME", category="Salario", amount=100)
    set_columns(db_module, aporte["id"], source_type="INVESTMENT_TRANSACTION", source_id="mov-1")
    set_columns(db_module, resgate["id"], source_type="INVESTMENT_TRANSACTION", source_id="mov-2")
    page = get(client, auth, limit=50)
    assert page["totals"] == {"income": 100, "expense": 50, "investment": 170}
    # O total do dia conta o caixa de investimento, como o Extrato: 100 + 30 - 50 - 200.
    assert page["day_totals"] == {"2026-03-01": -120}


def test_transfers_stay_out_of_totals(client, auth):
    source = client.post("/api/accounts", json={"name": "Origem", "type": "CHECKING"}, headers=auth).get_json()
    target = client.post("/api/accounts", json={"name": "Destino", "type": "CHECKING"}, headers=auth).get_json()
    response = client.post(
        "/api/transfers",
        json={"amount": 500, "date": "2026-03-01", "account_id": source["id"], "transfer_account_id": target["id"]},
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    page = get(client, auth, limit=10)
    assert len(page["items"]) == 1
    assert page["totals"] == {"income": 0, "expense": 0, "investment": 0}
    assert page["day_totals"] == {"2026-03-01": 0}


def test_day_totals_cover_a_split_day(client, auth):
    for amount in (10, 20, 30):
        create_transaction(client, auth, date="2026-03-02", amount=amount)
    create_transaction(client, auth, date="2026-03-01", amount=5)
    first, second = all_pages(client, auth, 2)
    assert first["day_totals"] == {"2026-03-02": -60}
    assert second["day_totals"] == {"2026-03-02": -60, "2026-03-01": -5}


def test_totals_round_in_cents(client, auth):
    for _ in range(3):
        create_transaction(client, auth, amount="0.10")
    page = get(client, auth, limit=1)
    assert page["totals"]["expense"] == 0.3
    assert page["day_totals"] == {"2026-03-01": -0.3}


def test_bad_limit_and_cursor_are_400(client, auth):
    create_transaction(client, auth)
    for limit in ("0", "501", "x"):
        response = client.get("/api/transactions", headers=auth, query_string={"limit": limit})
        assert response.status_code == 400, limit
    tampered = base64.urlsafe_b64encode(b"nao-e-cursor").decode("ascii")
    for cursor in ("%%%", tampered):
        response = client.get("/api/transactions", headers=auth, query_string={"limit": 5, "cursor": cursor})
        assert response.status_code == 400, cursor
    response = client.get("/api/transactions", headers=auth, query_string={"cursor": tampered})
    assert response.status_code == 400


def test_user_isolation(client, auth, other_user):
    create_transaction(client, auth, description="minha", amount=10)
    create_transaction(client, other_user["headers"], description="dele", amount=77)
    page = get(client, auth, limit=10)
    assert [row["description"] for row in page["items"]] == ["minha"]
    assert page["totals"]["expense"] == 10
