"""Open Finance gravado sozinho (044, services/open_finance_auto.py).

O que estes testes protegem:
- o interruptor `auto_record` so liga com cada conta da conexao mapeada (ou
  "nao usar") e um pull com sucesso nas ultimas 48 h; ligado, o que esperava
  no Aprovar vindo da Pluggy e gravado numa passada;
- ligado, o movimento vira lancamento sem aprovar: conta (source OPEN_FINANCE,
  source_id = id da Pluggy), cartao (client_id 'pluggy:<id>'), parcela 2..n
  coberta, estorno REFUND, pagamento de fatura ligado ao que o app ja tem,
  transferencia entre contas conectadas UMA so, banco <-> Corretora aporte;
- o que o dono ja digitou e ligado, nunca duplicado nem apagado;
- valor mudado / transacao sumida: corrigido ou apagado so se intocado;
- categoria: regra do dono, senao a da Pluggy traduzida, senao a padrao;
- avisos dos bancos conectados ignorados (com a preferencia), Flash nao;
- historico: previa sem gravar, aplicar so confirmado;
- o MeuPluggy: o banco vem do nome da conta (fonte, sugestao, Desconectar);
- outro usuario nao e tocado.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from open_finance_categories import pluggy_category_name
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_inbox import detection, ms, send

SETTINGS = "/api/open-finance/settings"
FLASH = "br.com.flashapp"
ITAU = "com.itau"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def run_sql(sql, params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute(sql, params)


def auto_on(world, expected=200):
    return world.call("patch", SETTINGS, expected=expected, json={"auto_record": True})


def of_tx(user_id, pluggy_id):
    [row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user_id, pluggy_id))
    return row


def meupluggy(world):
    """As tres conexoes do dono pelo MeuPluggy (o conector nao diz o banco):
    Itau (conta), BTG (conta, cartao, investimentos) e BB (conta, cartao e um
    segundo Ourocard sem uso). Mapeia tudo como o dono mapeou, menos o
    segundo Ourocard. Devolve {nome: (item, pluggy_account, app_target)}."""
    fake = world.fake
    made = {"items": {}}
    corretora = world.account("BTG Corretora", type_="BROKERAGE")
    plan = [
        ("itau", [("BANK", "Itaú Unibanco Conta", "0001/1-1", world.account("Itaú"))]),
        ("btg", [
            ("BANK", "BTG Banking", "0002/2-2", world.account("BTG conta corrente")),
            ("CREDIT", "Cartão BTG BLACK", "4321", world.card("BTG black")),
            ("BANK", "BTG Investimentos", "0002/2-2X", corretora),
        ]),
        ("bb", [
            ("BANK", "Conta Corrente BB", "0003/3-3", world.account("BB")),
            ("CREDIT", "OUROCARD FACIL VISA", "1111", world.card("BB ourocard")),
            ("CREDIT", "OUROCARD FACIL VISA", "2222", None),
        ]),
    ]
    for bank, accounts in plan:
        pluggy_item = fake.add_item("MeuPluggy")
        pluggy_ids = []
        for kind, name, number, _target in accounts:
            pluggy_ids.append(fake.add_account(pluggy_item, kind, name=name, number=number))
        body = world.connect(pluggy_item)
        item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
        by_number = {entry["number"]: entry for entry in item["accounts"]}
        made["items"][bank] = body["item_id"]
        for (kind, name, number, target), pluggy_account in zip(accounts, pluggy_ids):
            of_id = by_number[number]["id"]
            if target is None:
                world.map(of_id, ignore=True)
            elif kind == "BANK":
                world.map(of_id, account_id=target)
            else:
                world.map(of_id, card_id=target)
            made[f"{bank}:{number}"] = (pluggy_account, of_id, target)
    made["corretora"] = corretora
    return made


def sync_all(world, made):
    for item_id in made["items"].values():
        world.sync(item_id)


# ---------------------------------------------------------------------------
# O interruptor e a guarda
# ---------------------------------------------------------------------------

class TestSwitch:
    def test_off_by_default_keeps_aprovar(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        assert len(world.pending()) == 1
        assert world.transactions(made["bank"][2]) == []

    def test_refused_without_a_connection(self, world):
        body = auto_on(world, expected=400)
        assert "Conecte um banco" in body["error"]

    def test_refused_while_an_account_has_no_destination(self, world):
        fake = world.fake
        pluggy_item = fake.add_item("MeuPluggy")
        fake.add_account(pluggy_item, "BANK", name="Itaú Conta", number="1")
        fake.add_account(pluggy_item, "CREDIT", name="Itaú Visa", number="2")
        body = world.connect(pluggy_item)
        accounts = {entry["number"]: entry for entry in body["items"][0]["accounts"]}
        world.map(accounts["1"]["id"], account_id=world.account("Itaú"))
        error = auto_on(world, expected=400)["error"]
        assert "Itaú Visa" in error and "não usar" in error
        world.map(accounts["2"]["id"], ignore=True)
        assert auto_on(world)["auto_record"] is True

    def test_refused_without_a_recent_pull(self, world):
        item_id, _p, _made = connected(world)
        old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
        run_sql("UPDATE open_finance_items SET last_sync_at = ? WHERE id = ?", (old, item_id))
        assert "48 horas" in auto_on(world, expected=400)["error"]
        assert world.call("get", SETTINGS)["auto_record"] is False
        world.sync(item_id)
        assert auto_on(world)["auto_record"] is True

    def test_the_blockers_are_listed_in_settings(self, world):
        fake = world.fake
        pluggy_item = fake.add_item("MeuPluggy")
        fake.add_account(pluggy_item, "BANK", name="BB Conta", number="1")
        world.connect(pluggy_item)
        assert world.call("get", SETTINGS)["auto_record_blockers"] == [
            'Escolha o destino de BB Conta (ou marque "não usar").',
        ]

    def test_not_used_cannot_keep_a_destination(self, world):
        _item, _p, made = connected(world)
        body = world.map(made["bank"][1], expected=400, ignore=True)
        assert "Tire o destino" in body["error"]

    def test_turning_on_records_the_backlog_in_one_pass(self, world, user):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        ids = [
            world.fake.add_tx(pluggy_account, bank_tx(-10 - n, f"2026-10-{20 + n:02d}", f"LOJA {n}"))
            for n in range(5)
        ]
        world.sync(item_id)
        assert len(world.pending()) == 5
        body = auto_on(world)
        assert body["auto_recorded"] == {"recorded": 5, "linked": 0, "held": 0}
        assert world.pending() == []
        rows = world.transactions(mine)
        assert sorted(row["source_id"] for row in rows) == sorted(ids)
        assert {row["source_type"] for row in rows} == {"OPEN_FINANCE"}

    def test_turning_off_goes_back_to_aprovar(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.call("patch", SETTINGS, json={"auto_record": False})
        world.fake.add_tx(made["bank"][0], bank_tx(-12, "2026-10-20"))
        world.sync(item_id)
        assert len(world.pending()) == 1

    def test_per_user(self, world, client, other_user, fake_pluggy):
        connected(world)
        auto_on(world)
        other = World(client, other_user["headers"], fake_pluggy)
        assert other.call("get", SETTINGS)["auto_record"] is False


# ---------------------------------------------------------------------------
# Gravar sozinho
# ---------------------------------------------------------------------------

class TestAutoRecord:
    def test_a_bank_debit_becomes_an_expense(self, world):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        auto_on(world)
        tx_id = world.fake.add_tx(pluggy_account, bank_tx(-45.9, "2026-10-20", "PADARIA"))
        body = world.sync(item_id)
        assert body["result"]["auto_recorded"]["recorded"] == 1
        [row] = world.transactions(mine)
        assert (row["type"], row["amount"], row["date"]) == ("EXPENSE", 45.9, "2026-10-20")
        assert (row["source_type"], row["source_id"]) == ("OPEN_FINANCE", tx_id)
        assert world.pending() == []
        assert world.decided()[0]["state"] == "APPROVED"

    def test_a_repeat_pull_records_nothing_twice(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.sync(item_id)
        assert len(world.transactions(made["bank"][2])) == 1

    def test_a_card_purchase_in_installments(self, world, user):
        item_id, _p, made = connected(world, bank=False, card=True)
        pluggy_card, _of, card_id = made["card"]
        auto_on(world)
        tx_id = world.fake.add_tx(pluggy_card, card_tx(
            50, "2026-10-21", "LOJA X", installment=1, total_installments=3, purchase_date="2026-10-21T03:00:00.000Z",
            docs_sign=True,
        ))
        world.sync(item_id)
        rows = world.card_rows(card_id)
        assert len(rows) == 3 and sum(row["amount"] for row in rows) == 150.0
        assert {row["client_id"] for row in rows} == {f"pluggy:{tx_id}"}
        world.fake.add_tx(pluggy_card, card_tx(50, "2026-10-26", "LOJA X", installment=2, total_installments=3,
                                               docs_sign=True))
        assert world.sync(item_id)["result"]["counts"] == {"known": 1, "covered": 1}
        assert len(world.card_rows(card_id)) == 3

    def test_a_card_credit_is_a_refund(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        pluggy_card, _of, card_id = made["card"]
        auto_on(world)
        world.fake.add_tx(pluggy_card, card_tx(120, "2026-10-21", "LOJA"), card_tx(-30, "2026-10-22", "ESTORNO LOJA"),
                          card_tx(40, "2026-10-23", "LOJA 2"), card_tx(15, "2026-10-24", "LOJA 3"))
        world.sync(item_id)
        rows = world.card_rows(card_id)
        assert sorted((row["kind"], row["amount"]) for row in rows) == [
            ("PURCHASE", 15.0), ("PURCHASE", 40.0), ("PURCHASE", 120.0), ("REFUND", 30.0),
        ]

    def test_an_invoice_payment_links_to_the_apps_payment(self, world, user):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        auto_on(world)
        payment = world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 838.5, "date": "2026-10-21", "type": "EXPENSE", "category": "Outros",
            "description": "Fatura",
        })["id"]
        run_sql("UPDATE transactions SET source_type = 'CC_INVOICE_PAYMENT', source_id = 'x' WHERE id = ?", (payment,))
        tx_id = world.fake.add_tx(pluggy_account, bank_tx(-838.5, "2026-10-22", "PAGAMENTO FATURA",
                                                          category_id="05100000"))
        world.sync(item_id)
        assert [row["id"] for row in world.transactions(mine)] == [payment]
        row = of_tx(user["id"], tx_id)
        assert (row["role"], row["target_id"]) == ("INVOICE_PAYMENT", payment)

    def test_an_unpaid_invoice_payment_is_never_recorded(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-838.5, "2026-10-22", "PAGAMENTO FATURA", category_id="05100000"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2]) == []
        [account] = world.overview()["items"][0]["accounts"]
        assert account["check"]["bank_only"][0]["reason"] == "invoice_payment_missing"

    def test_a_typed_entry_is_linked_not_duplicated(self, world, user):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        typed = world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 45.9, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
            "description": "padaria",
        })["id"]
        auto_on(world)
        tx_id = world.fake.add_tx(pluggy_account, bank_tx(-45.9, "2026-10-21", "PADARIA"))
        assert world.sync(item_id)["result"]["auto_recorded"] == {"recorded": 0, "linked": 1, "held": 0}
        assert [row["id"] for row in world.transactions(mine)] == [typed]
        assert of_tx(user["id"], tx_id)["target_id"] == typed

    def test_two_equal_bank_rows_and_one_typed_entry(self, world):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 10, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
        })
        auto_on(world)
        world.fake.add_tx(pluggy_account, bank_tx(-10, "2026-10-20", "CAFE"), bank_tx(-10, "2026-10-20", "CAFE"))
        world.sync(item_id)
        assert len(world.transactions(mine)) == 2


class TestTransfers:
    def test_own_transfer_between_connected_banks_is_one_transfer(self, world, user):
        made = meupluggy(world)
        auto_on(world)
        itau, _of1, itau_id = made["itau:0001/1-1"]
        btg, _of2, btg_id = made["btg:0002/2-2"]
        world.fake.add_tx(itau, bank_tx(-500, "2026-10-20", "PIX ENVIADO", category_id="04000000"))
        world.fake.add_tx(btg, bank_tx(500, "2026-10-20", "PIX RECEBIDO", category_id="04000000"))
        sync_all(world, made)
        rows = [row for row in world.transactions() if row["amount"] == 500]
        assert [(row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            ("TRANSFER", itau_id, btg_id),
        ]
        assert world.pending() == []

    def test_one_side_waits_for_the_other(self, world):
        made = meupluggy(world)
        auto_on(world)
        itau, _of, _itau_id = made["itau:0001/1-1"]
        world.fake.add_tx(itau, bank_tx(-500, "2026-10-26", "PIX ENVIADO", category_id="04000000"))
        sync_all(world, made)
        assert [row for row in world.transactions() if row["amount"] == 500] == []
        assert len(world.pending()) == 1

    def test_a_pix_to_someone_else_is_held_two_days_then_recorded(self, world, invoices_module, monkeypatch):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        auto_on(world)
        world.fake.add_tx(pluggy_account, bank_tx(-80, "2026-10-26", "PIX FULANO", category_id="05070000",
                                                  counterparty="Fulano de Tal", doc="12345678901"))
        world.sync(item_id)
        assert world.transactions(mine) == []
        monkeypatch.setattr(invoices_module, "local_today", lambda: datetime(2026, 10, 29).date())
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert (row["type"], row["amount"]) == ("EXPENSE", 80.0)

    def test_bank_to_corretora_is_an_aporte(self, world):
        made = meupluggy(world)
        auto_on(world)
        btg, _of, btg_id = made["btg:0002/2-2"]
        broker, _of2, corretora = made["btg:0002/2-2X"]
        world.fake.add_tx(btg, bank_tx(-1000, "2026-10-20", "TED BTG INVEST", category_id="04000000"))
        world.fake.add_tx(broker, bank_tx(1000, "2026-10-20", "TED RECEBIDA", category_id="04000000"))
        world.sync(made["items"]["btg"])
        [row] = [row for row in world.transactions() if row["amount"] == 1000]
        assert (row["type"], row["account_id"], row["transfer_account_id"]) == ("TRANSFER", btg_id, corretora)

    def test_broker_cash_movements_are_covered(self, world, user):
        made = meupluggy(world)
        auto_on(world)
        broker, _of, corretora = made["btg:0002/2-2X"]
        dividend = world.fake.add_tx(broker, bank_tx(12.5, "2026-10-20", "DIVIDENDOS PETR4", category_id="03060000"))
        buy = world.fake.add_tx(broker, bank_tx(-300, "2026-10-21", "COMPRA ACOES", category_id="03040000"))
        world.sync(made["items"]["btg"])
        assert world.transactions(corretora) == []
        assert world.pending() == []
        assert {of_tx(user["id"], dividend)["role"], of_tx(user["id"], buy)["role"]} == {"COVERED"}

    def test_an_investment_on_a_bank_account_waits_for_the_owner(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-1000, "2026-10-20", "COMPRA TESOURO DIRETO",
                                                   category_id="03020000"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2]) == []
        assert len(world.pending()) == 1


class TestCategories:
    @pytest.mark.parametrize("category_id, name", [
        ("11010000", "Alimentação"), ("10000000", "Alimentação"), ("19050001", "Transporte"),
        ("17020002", "Moradia"), ("07020000", "Educação"), ("07030000", "Saúde"), ("01010000", "Receita"),
        ("03060000", "Receita"), ("03020000", None), ("05070000", None), ("04000000", None), ("99999999", None),
        (None, None), ("abc", None),
    ])
    def test_the_table(self, category_id, name):
        assert pluggy_category_name(category_id) == name

    def test_pluggy_category_when_no_rule(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-30, "2026-10-20", "RESTAURANTE X", category_id="11010000"))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["category"] == "Alimentação" and row["category_id"]

    def test_the_owners_rule_wins(self, world):
        item_id, _p, made = connected(world)
        world.call("post", "/api/import-rules", json={"pattern": "RESTAURANTE", "category": "Lazer",
                                                      "transaction_type": "EXPENSE"})
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-30, "2026-10-20", "RESTAURANTE X", category_id="11010000"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2])[0]["category"] == "Lazer"

    def test_without_either_it_is_the_default(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-30, "2026-10-20", "XPTO", category_id="99999999"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2])[0]["category"] == "Outros"

    def test_an_income_category_never_lands_on_an_expense(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-30, "2026-10-20", "XPTO", category_id="01010000"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2])[0]["category"] == "Outros"


# ---------------------------------------------------------------------------
# O banco mudou depois de gravado
# ---------------------------------------------------------------------------

class TestMutationGuard:
    def setup_recorded(self, world, amount=-45.9):
        item_id, _p, made = connected(world)
        auto_on(world)
        tx = bank_tx(amount, "2026-10-20", "PADARIA")
        world.fake.add_tx(made["bank"][0], tx)
        world.sync(item_id)
        return item_id, made, tx

    def test_an_untouched_entry_follows_the_new_amount(self, world):
        item_id, made, tx = self.setup_recorded(world)
        tx["amount"] = -49.9
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["amount"] == 49.9

    def test_an_edited_entry_is_kept_and_flagged(self, world, user):
        item_id, made, tx = self.setup_recorded(world)
        [row] = world.transactions(made["bank"][2])
        world.call("patch", f"/api/transactions/{row['id']}", json={**{k: row[k] for k in (
            "account_id", "amount", "date", "type", "category")}, "description": "padaria do bairro"})
        tx["amount"] = -49.9
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert (row["amount"], row["description"]) == (45.9, "padaria do bairro")
        assert of_tx(user["id"], tx["id"])["conflict"] == "changed"
        [account] = world.overview()["items"][0]["accounts"]
        assert account["check"]["conflicts"][0]["reason"] == "changed"

    def test_an_untouched_entry_that_vanished_is_removed(self, world):
        item_id, made, tx = self.setup_recorded(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-1, "2026-10-21", "OUTRA"))
        world.fake.drop_tx(made["bank"][0], tx["id"])
        world.sync(item_id)
        assert [row["amount"] for row in world.transactions(made["bank"][2])] == [1.0]

    def test_an_edited_entry_that_vanished_stays(self, world, user):
        item_id, made, tx = self.setup_recorded(world)
        [row] = world.transactions(made["bank"][2])
        world.call("patch", f"/api/transactions/{row['id']}", json={**{k: row[k] for k in (
            "account_id", "amount", "date", "type")}, "category": "Lazer"})
        world.fake.add_tx(made["bank"][0], bank_tx(-1, "2026-10-21", "OUTRA"))
        world.fake.drop_tx(made["bank"][0], tx["id"])
        world.sync(item_id)
        assert len(world.transactions(made["bank"][2])) == 2
        assert of_tx(user["id"], tx["id"])["conflict"] == "vanished"

    def test_a_typed_entry_is_never_deleted(self, world):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 45.9, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
        })
        auto_on(world)
        tx = bank_tx(-45.9, "2026-10-20")
        world.fake.add_tx(pluggy_account, tx, bank_tx(-1, "2026-10-21"))
        world.sync(item_id)
        world.fake.drop_tx(pluggy_account, tx["id"])
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [1.0, 45.9]

    def test_an_empty_pull_deletes_nothing(self, world):
        item_id, made, tx = self.setup_recorded(world)
        world.fake.drop_tx(made["bank"][0], tx["id"])
        world.sync(item_id)
        assert len(world.transactions(made["bank"][2])) == 1


# ---------------------------------------------------------------------------
# Avisos do celular
# ---------------------------------------------------------------------------

class TestNotifications:
    def test_a_connected_banks_notification_is_ignored(self, world):
        connected(world, connector_name="Itaú")
        world.call("patch", SETTINGS, json={"ignore_notifications": True})
        [result] = send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20), app=ITAU))
        assert result["status"] == "ignored"
        assert world.pending() == []

    def test_flash_still_reaches_aprovar(self, world):
        connected(world, connector_name="Itaú")
        world.call("patch", SETTINGS, json={"ignore_notifications": True})
        [result] = send(world.client, world.auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20), app=FLASH))
        assert result["status"] == "new"
        assert len(world.pending()) == 1

    def test_off_by_default(self, world):
        connected(world, connector_name="Itaú")
        [result] = send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20), app=ITAU))
        assert result["status"] == "new"

    def test_meupluggy_banks_are_known_by_account_name(self, world):
        meupluggy(world)
        world.call("patch", SETTINGS, json={"ignore_notifications": True})
        results = send(
            world.client, world.auth,
            detection("CREDIT_PURCHASE", 1000, at=ms(2026, 10, 20, 10), app="com.btg.pactual.banking"),
            detection("DEBIT_PURCHASE", 2000, at=ms(2026, 10, 20, 11), app="br.com.bb.android"),
        )
        assert [result["status"] for result in results] == ["ignored", "ignored"]

    def test_another_users_connection_does_not_count(self, world, client, other_user, fake_pluggy):
        connected(world, connector_name="Itaú")
        world.call("patch", SETTINGS, json={"ignore_notifications": True})
        other = World(client, other_user["headers"], fake_pluggy)
        other.call("patch", SETTINGS, json={"ignore_notifications": True})
        [result] = send(client, other_user["headers"], detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20),
                                                                 app=ITAU))
        assert result["status"] == "new"


# ---------------------------------------------------------------------------
# Historico
# ---------------------------------------------------------------------------

class TestHistory:
    def setup_history(self, world):
        item_id, _p, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        world.sync(item_id)
        typed = world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 200, "date": "2026-03-10", "type": "EXPENSE", "category": "Outros",
            "description": "aluguel",
        })["id"]
        only_app = world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 77, "date": "2026-04-01", "type": "EXPENSE", "category": "Outros",
            "description": "so no app",
        })["id"]
        world.fake.add_tx(
            pluggy_account,
            bank_tx(-200, "2026-03-10", "ALUGUEL"), bank_tx(-15, "2026-02-01", "CAFE"),
            bank_tx(3000, "2026-03-05", "SALARIO", category_id="01010000"),
        )
        return mine, typed, only_app

    def test_preview_counts_and_writes_nothing(self, world):
        mine, _typed, _only = self.setup_history(world)
        before = rows_of("open_finance_transactions")
        body = world.call("post", "/api/open-finance/history/preview", json={"days": 365})
        [account] = body["accounts"]
        assert (account["to_link"], account["to_record"], account["app_only"]) == (1, 2, 1)
        assert rows_of("open_finance_transactions") == before
        assert len(world.transactions(mine)) == 2

    def test_apply_needs_confirmation_and_the_switch(self, world):
        self.setup_history(world)
        world.call("post", "/api/open-finance/history/apply", expected=400, json={"days": 365})
        body = world.call("post", "/api/open-finance/history/apply", expected=400, json={"days": 365, "confirm": True})
        assert "Gravar sozinho" in body["error"]

    def test_apply_links_records_and_keeps_app_only(self, world):
        mine, typed, only_app = self.setup_history(world)
        auto_on(world)
        world.call("post", "/api/open-finance/history/apply", json={"days": 365, "confirm": True})
        rows = {row["description"]: row for row in world.transactions(mine)}
        assert rows["aluguel"]["id"] == typed
        assert rows["so no app"]["id"] == only_app
        assert {"CAFE", "SALARIO"} <= set(rows)
        assert rows["SALARIO"]["category"] == "Receita"
        assert len(rows) == 4
        body = world.call("post", "/api/open-finance/history/preview", json={"days": 365})
        assert (body["accounts"][0]["linked"], body["accounts"][0]["to_record"]) == (3, 0)

    def test_days_are_validated(self, world):
        connected(world)
        for days in (0, 400, "x", True):
            world.call("post", "/api/open-finance/history/preview", expected=400, json={"days": days})


# ---------------------------------------------------------------------------
# O MeuPluggy: o banco e o da conta
# ---------------------------------------------------------------------------

class TestBankNames:
    def test_items_are_named_by_their_accounts(self, world):
        made = meupluggy(world)
        names = {item["id"]: item["bank_name"] for item in world.overview()["items"]}
        assert names[made["items"]["itau"]] == "Itaú"
        assert names[made["items"]["btg"]] == "BTG Pactual"
        assert names[made["items"]["bb"]] == "Banco do Brasil"

    def test_suggestions_use_the_account_name(self, world):
        fake = world.fake
        mine = world.account("Itaú")
        card = world.card("BTG black")
        corretora = world.account("BTG Corretora", type_="BROKERAGE")
        item_itau = fake.add_item("MeuPluggy")
        fake.add_account(item_itau, "BANK", name="Itaú Unibanco Conta", number="1")
        item_btg = fake.add_item("MeuPluggy")
        fake.add_account(item_btg, "CREDIT", name="Cartão BTG BLACK", number="2")
        fake.add_account(item_btg, "BANK", name="BTG Investimentos", number="3")
        world.connect(item_itau)
        body = world.connect(item_btg)
        suggested = {account["number"]: account["suggested_id"] for item in body["items"] for account in item["accounts"]}
        assert suggested == {"1": mine, "2": card, "3": corretora}

    def test_the_corretora_takes_only_the_investments_account(self, world):
        fake = world.fake
        corretora = world.account("BTG Corretora", type_="BROKERAGE")
        pluggy_item = fake.add_item("MeuPluggy")
        fake.add_account(pluggy_item, "BANK", name="BTG Banking", number="1")
        body = world.connect(pluggy_item)
        of_id = body["items"][0]["accounts"][0]["id"]
        assert "Corretora" in world.map(of_id, expected=400, account_id=corretora)["error"]

    def test_disconnect_asks_for_the_bank(self, world):
        made = meupluggy(world)
        item_id = made["items"]["btg"]
        error = world.call("delete", f"/api/open-finance/items/{item_id}", expected=400,
                           json={"confirm": "MeuPluggy"})["error"]
        assert "BTG Pactual" in error
        world.call("delete", f"/api/open-finance/items/{item_id}", json={"confirm": "btg pactual"})

    def test_aprovar_names_the_bank(self, world):
        made = meupluggy(world)
        btg, _of, _mine = made["btg:0002/2-2"]
        world.fake.add_tx(btg, bank_tx(-10, "2026-10-20", "LOJA"))
        world.sync(made["items"]["btg"])
        [item] = world.pending()
        [source] = item["sources"]
        assert (source["connector_name"], source["bank_name"]) == ("MeuPluggy", "BTG Pactual")
