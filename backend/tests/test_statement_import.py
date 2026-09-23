"""Importacao de extrato e regras de categorizacao — Fase 4 de docs/next-steps.md.

O que estes testes fixam:

- CSV em pt-BR (ponto de milhar, virgula decimal, dd/mm/aaaa) e lido sem
  configuracao, e o mapeamento explicito por nome de coluna sobrescreve o
  palpite;
- as tres formas de sinal que os bancos exportam: coluna Valor com sinal,
  Debito/Credito separadas, e Valor + coluna Tipo;
- a previa nao grava nada; o /commit grava e reimportar o mesmo arquivo e um
  no-op (mesmo source_id, indice unico de 007);
- duas linhas identicas no mesmo arquivo continuam sendo dois lancamentos;
- as regras categorizam por prioridade e respeitam INCOME/EXPENSE;
- OFX usa o FITID do banco como chave de deduplicacao;
- nada de outro usuario aparece nas regras, nem na deduplicacao.
"""

import pytest

import statement_import


CSV_PT = """Data;Histórico;Valor
01/09/2026;PADARIA DO ZE;-1.234,56
02/09/2026;SALARIO SETEMBRO;4.000,00
03/09/2026;UBER * TRIP;-27,90
"""


def preview(client, headers, content, **options):
    payload = {"content": content}
    payload.update(options)
    return client.post("/api/import/preview", json=payload, headers=headers)


def commit(client, headers, rows, **options):
    payload = {"rows": rows}
    payload.update(options)
    return client.post("/api/import/commit", json=payload, headers=headers)


def new_rows(body):
    return [row for row in body["rows"] if row["status"] == "NEW"]


# --- parser puro ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("1.234,56", 1234.56),
    ("-1.234,56", -1234.56),
    ("R$ 27,90", 27.90),
    ("1,234.56", 1234.56),
    ("(50,00)", -50.0),
    ("100", 100.0),
    ("", None),
    ("abc", None),
])
def test_parse_amount_accepts_both_locales(raw, expected):
    assert statement_import.parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("01/09/2026", "2026-09-01"),
    ("2026-09-01", "2026-09-01"),
    ("01-09-2026", "2026-09-01"),
    ("20260901120000[-3:BRT]", "2026-09-01"),
    ("nao e data", None),
])
def test_parse_date_accepts_the_usual_shapes(raw, expected):
    assert statement_import.parse_date(raw) == expected


def test_row_hash_ignores_punctuation_and_case():
    first = statement_import.row_hash("acc", "2026-09-01", 10.0, "PADARIA  DO ZÉ")
    second = statement_import.row_hash("acc", "2026-09-01", 10.0, "padaria do ze!")
    assert first == second
    other_account = statement_import.row_hash("outra", "2026-09-01", 10.0, "padaria do ze")
    assert other_account != first


# --- previa --------------------------------------------------------------

def test_preview_reads_a_brazilian_csv_without_configuration(client, auth):
    response = preview(client, auth, CSV_PT)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()

    assert body["format"] == "CSV"
    assert body["delimiter"] == ";"
    assert body["summary"]["total"] == 3
    assert body["summary"]["new"] == 3

    rows = body["rows"]
    assert rows[0]["date"] == "2026-09-01"
    assert rows[0]["amount"] == 1234.56
    assert rows[0]["type"] == "EXPENSE"
    assert rows[0]["description"] == "PADARIA DO ZE"
    assert rows[1]["type"] == "INCOME"


def test_preview_does_not_write_anything(client, auth):
    preview(client, auth, CSV_PT)
    listed = client.get("/api/transactions", headers=auth).get_json()
    assert listed == []


def test_preview_accepts_debit_and_credit_columns(client, auth):
    content = "Data,Descricao,Debito,Credito\n01/09/2026,MERCADO,150.00,\n02/09/2026,ESTORNO,,80.00\n"
    body = preview(client, auth, content).get_json()
    rows = body["rows"]
    assert (rows[0]["type"], rows[0]["amount"]) == ("EXPENSE", 150.0)
    assert (rows[1]["type"], rows[1]["amount"]) == ("INCOME", 80.0)


def test_preview_uses_a_type_column_when_the_value_has_no_sign(client, auth):
    content = "Data;Descricao;Valor;Tipo\n01/09/2026;MERCADO;150,00;Debito\n02/09/2026;SALARIO;900,00;Credito\n"
    rows = preview(client, auth, content).get_json()["rows"]
    assert rows[0]["type"] == "EXPENSE"
    assert rows[1]["type"] == "INCOME"


def test_preview_maps_columns_explicitly_when_asked(client, auth):
    content = "quando;quanto;o que\n01/09/2026;-10,00;CAFE\n"
    body = preview(client, auth, content, mapping={
        "date": "quando", "amount": "quanto", "description": "o que",
    }).get_json()
    assert body["rows"][0]["description"] == "CAFE"
    assert body["rows"][0]["amount"] == 10.0


def test_preview_reports_an_unknown_column(client, auth):
    response = preview(client, auth, CSV_PT, mapping={"date": "Inexistente"})
    assert response.status_code == 400
    assert "Inexistente" in response.get_json()["error"]


def test_preview_marks_bad_lines_instead_of_failing(client, auth):
    content = "Data;Descricao;Valor\n01/09/2026;OK;-10,00\nsem data;RUIM;-10,00\n"
    body = preview(client, auth, content).get_json()
    assert body["summary"]["new"] == 1
    assert body["summary"]["errors"] == 1
    assert body["rows"][1]["status"] == "ERROR"


def test_preview_can_invert_the_sign(client, auth):
    body = preview(client, auth, CSV_PT, invert_sign=True).get_json()
    assert body["rows"][0]["type"] == "INCOME"


def test_preview_rejects_an_empty_file(client, auth):
    assert preview(client, auth, "   ").status_code == 400


# --- gravacao ------------------------------------------------------------

def test_commit_writes_the_rows_and_a_reimport_is_a_no_op(client, auth):
    body = preview(client, auth, CSV_PT).get_json()
    response = commit(client, auth, new_rows(body))
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json() == {"created": 3, "skipped": 0}

    listed = client.get("/api/transactions", headers=auth).get_json()
    assert len(listed) == 3
    assert {item["source_type"] for item in listed} == {"STATEMENT_IMPORT"}

    again = preview(client, auth, CSV_PT).get_json()
    assert again["summary"]["duplicates"] == 3
    assert again["summary"]["new"] == 0
    # Mesmo forcando as linhas ja gravadas, o indice unico segura.
    forced = commit(client, auth, [row for row in again["rows"]]).get_json()
    assert forced == {"created": 0, "skipped": 3}
    assert len(client.get("/api/transactions", headers=auth).get_json()) == 3


def test_two_identical_lines_in_one_file_are_two_transactions(client, auth):
    content = "Data;Descricao;Valor\n01/09/2026;CAFE;-7,00\n01/09/2026;CAFE;-7,00\n"
    body = preview(client, auth, content).get_json()
    assert body["summary"]["new"] == 2
    assert body["rows"][0]["source_id"] != body["rows"][1]["source_id"]
    assert commit(client, auth, new_rows(body)).get_json()["created"] == 2


def test_commit_rounds_money_half_up(client, auth):
    content = "Data;Descricao;Valor\n01/09/2026;CAFE;-10,005\n"
    body = preview(client, auth, content).get_json()
    commit(client, auth, new_rows(body))
    listed = client.get("/api/transactions", headers=auth).get_json()
    assert listed[0]["amount"] == 10.01


def test_commit_refuses_an_invalid_row(client, auth):
    response = commit(client, auth, [{
        "date": "2026-09-01", "amount": 0, "type": "EXPENSE", "category": "Outros",
    }])
    assert response.status_code == 400
    assert "Linha 1" in response.get_json()["error"]


def test_commit_refuses_an_empty_payload(client, auth):
    assert commit(client, auth, []).status_code == 400


def test_commit_honours_the_chosen_account(client, auth):
    account = client.post(
        "/api/accounts", json={"name": "Conta importada", "type": "CHECKING"}, headers=auth,
    ).get_json()
    body = preview(client, auth, CSV_PT, account_id=account["id"]).get_json()
    assert body["account_id"] == account["id"]
    commit(client, auth, new_rows(body), account_id=account["id"])
    listed = client.get("/api/transactions", headers=auth).get_json()
    assert {item["account_id"] for item in listed} == {account["id"]}


def test_the_same_file_in_two_accounts_is_not_a_duplicate(client, auth):
    account = client.post(
        "/api/accounts", json={"name": "Segunda conta", "type": "CHECKING"}, headers=auth,
    ).get_json()
    first = preview(client, auth, CSV_PT).get_json()
    commit(client, auth, new_rows(first))
    second = preview(client, auth, CSV_PT, account_id=account["id"]).get_json()
    assert second["summary"]["new"] == 3


# --- regras --------------------------------------------------------------

def create_rule(client, headers, **overrides):
    payload = {"pattern": "uber", "category": "Transporte"}
    payload.update(overrides)
    return client.post("/api/import-rules", json=payload, headers=headers)


def test_rule_categorizes_a_matching_row(client, auth):
    assert create_rule(client, auth).status_code == 201
    body = preview(client, auth, CSV_PT).get_json()
    uber = body["rows"][2]
    assert uber["category"] == "Transporte"
    assert uber["category_source"] == "RULE"
    assert body["summary"]["categorized"] == 1


def test_rows_without_a_rule_fall_back_to_a_default_category(client, auth):
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][0]["category"] == "Outros"
    assert body["rows"][0]["category_source"] == "DEFAULT"
    assert body["rows"][1]["category"] == "Receita"


def test_rule_ignores_accents_and_case(client, auth):
    create_rule(client, auth, pattern="PADARIA DO ZÉ", category="Alimentação")
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][0]["category"] == "Alimentação"


def test_rule_can_be_restricted_to_one_direction(client, auth):
    create_rule(client, auth, pattern="salario", category="Lazer", applies_to="EXPENSE")
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][1]["category"] != "Lazer"


def test_priority_decides_between_two_matching_rules(client, auth):
    create_rule(client, auth, pattern="uber", category="Transporte")
    create_rule(client, auth, pattern="uber * trip", category="Lazer", priority=10)
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][2]["category"] == "Lazer"


def test_starts_with_and_equals_are_stricter_than_contains(client, auth):
    create_rule(client, auth, pattern="trip", category="Lazer", match_type="STARTS_WITH")
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][2]["category"] != "Lazer"


def test_an_inactive_rule_does_not_match(client, auth):
    rule = create_rule(client, auth).get_json()
    client.patch(f"/api/import-rules/{rule['id']}", json={"active": False}, headers=auth)
    body = preview(client, auth, CSV_PT).get_json()
    assert body["rows"][2]["category_source"] == "DEFAULT"


def test_a_duplicated_rule_is_refused(client, auth):
    create_rule(client, auth)
    assert create_rule(client, auth).status_code == 400


def test_a_rule_needs_a_category_that_exists(client, auth):
    response = create_rule(client, auth, category_id="nao-existe")
    assert response.status_code == 400


# --- condicoes de valor e de conta (015) ----------------------------------

def create_account(client, headers, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def test_amount_range_splits_the_same_text(client, auth):
    content = """Data;Histórico;Valor
01/09/2026;UBER * TRIP;-27,90
02/09/2026;UBER * TRIP;-120,00
"""
    assert create_rule(client, auth, pattern="uber", category="Lazer", amount_min=80).status_code == 201
    assert create_rule(client, auth, pattern="uber", category="Transporte", amount_max=79.99).status_code == 201
    rows = preview(client, auth, content).get_json()["rows"]
    assert [row["category"] for row in rows] == ["Transporte", "Lazer"]


def test_amount_bounds_are_inclusive_and_compare_the_absolute_value(client, auth):
    create_rule(client, auth, pattern="uber", category="Lazer", amount_min=27.9, amount_max=27.9)
    assert preview(client, auth, CSV_PT).get_json()["rows"][2]["category"] == "Lazer"


def test_account_condition_only_matches_that_account(client, auth):
    business = create_account(client, auth, "Conta PJ")
    personal = create_account(client, auth, "Conta PF")
    create_rule(client, auth, pattern="uber", category="Lazer", account_id=business["id"])
    in_business = preview(client, auth, CSV_PT, account_id=business["id"]).get_json()["rows"][2]
    in_personal = preview(client, auth, CSV_PT, account_id=personal["id"]).get_json()["rows"][2]
    assert in_business["category"] == "Lazer"
    assert in_personal["category_source"] == "DEFAULT"


def test_same_text_with_different_conditions_is_not_a_duplicate(client, auth):
    assert create_rule(client, auth).status_code == 201
    assert create_rule(client, auth, amount_min=100).status_code == 201
    assert create_rule(client, auth, amount_min=100).status_code == 400
    assert create_rule(client, auth, pattern="UBER", amount_min=100).status_code == 400


def test_amount_range_is_validated(client, auth):
    assert create_rule(client, auth, amount_min=50, amount_max=10).status_code == 400
    assert create_rule(client, auth, amount_min=-1).status_code == 400
    rule = create_rule(client, auth, amount_max=10).get_json()
    response = client.patch(f"/api/import-rules/{rule['id']}", json={"amount_min": 20}, headers=auth)
    assert response.status_code == 400
    cleared = client.patch(
        f"/api/import-rules/{rule['id']}", json={"amount_max": "", "amount_min": 20}, headers=auth,
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["amount_max"] is None
    assert cleared.get_json()["amount_min"] == 20


def test_rule_amount_is_rounded_half_up(client, auth):
    rule = create_rule(client, auth, amount_min=10.005).get_json()
    assert rule["amount_min"] == 10.01


def test_rule_account_must_belong_to_the_user(client, auth, other_user):
    foreign = create_account(client, other_user["headers"], "Conta alheia")
    assert create_rule(client, auth, account_id=foreign["id"]).status_code == 400


def test_rule_hits_count_only_committed_rows(client, auth):
    rule = create_rule(client, auth).get_json()
    assert rule["hits"] == 0
    body = preview(client, auth, CSV_PT).get_json()
    commit(client, auth, new_rows(body))
    listed = client.get("/api/import-rules", headers=auth).get_json()["items"]
    assert listed[0]["hits"] == 1
    # Reimportar nao conta de novo: nada novo foi gravado.
    again = preview(client, auth, CSV_PT).get_json()
    commit(client, auth, again["rows"])
    listed = client.get("/api/import-rules", headers=auth).get_json()["items"]
    assert listed[0]["hits"] == 1


def test_deleting_a_rule_keeps_the_transactions_it_categorized(client, auth):
    rule = create_rule(client, auth).get_json()
    body = preview(client, auth, CSV_PT).get_json()
    commit(client, auth, new_rows(body))
    assert client.delete(f"/api/import-rules/{rule['id']}", headers=auth).status_code == 200
    listed = client.get("/api/transactions", headers=auth).get_json()
    assert any(item["category"] == "Transporte" for item in listed)


# --- OFX -----------------------------------------------------------------

OFX = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><ACCTID>12345-6</ACCTID></BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260901120000[-3:BRT]<TRNAMT>-1234.56<FITID>ABC1<MEMO>PADARIA DO ZE</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260902<TRNAMT>4000.00<FITID>ABC2<MEMO>SALARIO SETEMBRO</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_ofx_is_detected_and_read(client, auth):
    body = preview(client, auth, OFX).get_json()
    assert body["format"] == "OFX"
    assert body["bank_account"] == "12345-6"
    assert body["summary"]["new"] == 2
    assert body["rows"][0]["amount"] == 1234.56
    assert body["rows"][0]["type"] == "EXPENSE"
    assert body["rows"][0]["description"] == "PADARIA DO ZE"
    assert body["rows"][1]["type"] == "INCOME"


def test_ofx_deduplicates_by_fitid(client, auth):
    body = preview(client, auth, OFX).get_json()
    assert body["rows"][0]["source_id"].startswith("ofx:")
    assert body["rows"][0]["source_id"].endswith("ABC1")
    commit(client, auth, new_rows(body))
    # Mesmo lancamento reexportado com a descricao mudada: o FITID e o mesmo.
    changed = OFX.replace("PADARIA DO ZE", "PADARIA DO ZE LTDA")
    again = preview(client, auth, changed).get_json()
    assert again["summary"]["duplicates"] == 2


def test_an_ofx_without_transactions_is_refused(client, auth):
    response = preview(client, auth, "<OFX><SIGNONMSGSRSV1></SIGNONMSGSRSV1></OFX>", format="OFX")
    assert response.status_code == 400


# --- isolamento ----------------------------------------------------------

def test_rules_are_scoped_to_their_user(client, user, other_user):
    rule = create_rule(client, user["headers"]).get_json()
    assert client.get("/api/import-rules", headers=other_user["headers"]).get_json()["items"] == []
    assert client.patch(
        f"/api/import-rules/{rule['id']}", json={"category": "Lazer"},
        headers=other_user["headers"],
    ).status_code == 404
    assert client.delete(
        f"/api/import-rules/{rule['id']}", headers=other_user["headers"],
    ).status_code == 404

    body = preview(client, other_user["headers"], CSV_PT).get_json()
    assert body["summary"]["categorized"] == 0


def test_another_users_import_does_not_count_as_a_duplicate(client, user, other_user):
    body = preview(client, user["headers"], CSV_PT).get_json()
    commit(client, user["headers"], new_rows(body))
    mine = preview(client, other_user["headers"], CSV_PT).get_json()
    assert mine["summary"]["new"] == 3


def test_import_endpoints_need_a_token(client):
    assert client.post("/api/import/preview", json={"content": CSV_PT}).status_code == 401
    assert client.post("/api/import/commit", json={"rows": []}).status_code == 401
    assert client.get("/api/import-rules").status_code == 401


def test_commit_refuses_an_oversized_source_id(client, auth):
    response = commit(client, auth, [{
        "date": "2026-09-01", "amount": 10, "type": "EXPENSE", "category": "Outros",
        "source_id": "x" * 300,
    }])
    assert response.status_code == 400
    assert "Linha 1" in response.get_json()["error"]


@pytest.mark.parametrize("options", [
    {"skip_rows": "abc"},
    {"delimiter": ";;"},
    {"mapping": ["data"]},
])
def test_preview_refuses_broken_options_instead_of_failing(client, auth, options):
    assert preview(client, auth, CSV_PT, **options).status_code == 400


def test_preview_skips_a_report_header_before_the_table(client, auth):
    content = "Extrato de conta\nPeriodo: 09/2026\nData;Descricao;Valor\n01/09/2026;CAFE;-7,00\n"
    body = preview(client, auth, content, skip_rows=2).get_json()
    assert body["summary"]["new"] == 1
    assert body["rows"][0]["line"] == 4


def test_a_rule_that_only_differs_in_case_or_accent_is_refused(client, auth):
    create_rule(client, auth, pattern="Uber")
    # A avaliacao normaliza os dois para o mesmo texto: seriam duas regras que
    # casam sempre juntas.
    assert create_rule(client, auth, pattern="uber").status_code == 400
    assert create_rule(client, auth, pattern="ÜBER").status_code == 400
    # Outra comparacao ou outra direcao e uma regra de verdade diferente.
    assert create_rule(client, auth, pattern="uber", match_type="EQUALS").status_code == 201
    assert create_rule(client, auth, pattern="uber", applies_to="INCOME").status_code == 201


def test_renaming_a_rule_onto_an_existing_one_is_refused(client, auth):
    create_rule(client, auth, pattern="uber")
    other = create_rule(client, auth, pattern="padaria").get_json()
    response = client.patch(f"/api/import-rules/{other['id']}", json={"pattern": "UBER"}, headers=auth)
    assert response.status_code == 400
    # Salvar a propria regra sem mudar o texto continua valendo.
    assert client.patch(
        f"/api/import-rules/{other['id']}", json={"priority": 5}, headers=auth,
    ).status_code == 200
