"""O nome e a categoria de uma transacao da Pluggy (open_finance_categories.py).

Ordem: regra do dono, comerciante, CNAE, categoria da Pluggy, padrao. Nunca uma
categoria que o dono nao tem.
"""

import importlib

import pytest

from open_finance_categories import (
    clean_description,
    cnae_categories,
    display_name,
    keyword_categories,
    pluggy_category_names,
)
from open_finance_world import World, bank_tx, card_tx, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_rebuild import connect


class TestCleanDescription:
    @pytest.mark.parametrize("raw, expected", [
        ("COMPRA CARTAO DEBITO PADARIA DO ZE", "Padaria do Ze"),
        ("COMPRA CARTAO PADARIA 12/10", "Padaria"),
        ("Compra com cartão MERCADO BOM", "Mercado Bom"),
        ("PIX ENVIADO JOAO SILVA", "Joao Silva"),
        ("PIX RECEBIDO DE MARIA", "Maria"),
        ("NETSHOES 03/10", "Netshoes"),
        ("LOJA X PARC 3/10", "Loja X"),
        ("LOJA X PARCELA 3 DE 10", "Loja X"),
        ("PAG*JOSEDASILVA", "Josedasilva"),
        ("MP *LOJINHA", "Lojinha"),
        ("UBER TRIP 12/10/2026 18:30", "Uber Trip"),
        ("DROGASIL 1234 BR", "Drogasil 1234"),
        ("Assinatura Spotify", "Assinatura Spotify"),
    ])
    def test_readable(self, raw, expected):
        assert clean_description(raw) == expected

    def test_nothing_left_keeps_the_original(self):
        assert clean_description("PIX") == "Pix"
        assert clean_description("COMPRA") == "Compra"
        assert clean_description("") is None

    def test_the_merchant_wins(self):
        assert display_name("PG *XYZ 123", "IFOOD.COM AGENCIA") == "Ifood.com Agencia"

    def test_a_pix_names_who_is_on_the_other_side(self):
        assert display_name("PIX ENVIADO", None, "JOAO DA SILVA", "TRANSFER", "OUT") == "Pix para Joao da Silva"
        assert display_name("TED RECEBIDA", None, "JOAO", "TRANSFER", "IN") == "Transferência de Joao"


class TestKeywords:
    @pytest.mark.parametrize("text, first", [
        ("IFOOD *RESTAURANTE", "Alimentação"), ("Uber Eats", "Alimentação"), ("UBER TRIP", "Transporte"),
        ("99 TECNOLOGIA", "Transporte"), ("POSTO IPIRANGA", "Transporte"), ("Pão de Açúcar", "Alimentação"),
        ("SUPERMERCADO BOM", "Alimentação"), ("MERCADO LIVRE", "Compras"), ("AMAZON MARKETPLACE", "Compras"),
        ("AMAZON PRIME", "Lazer"), ("DROGASIL", "Saúde"), ("Droga Raia", "Saúde"), ("UNIMED", "Saúde"),
        ("NETFLIX.COM", "Lazer"), ("SPOTIFY", "Lazer"), ("VIVO FIXO", "Serviços"), ("TIM CELULAR", "Serviços"),
        ("ENEL SP", "Moradia"), ("SABESP", "Moradia"), ("UDEMY", "Educação"),
    ])
    def test_merchants(self, text, first):
        assert keyword_categories(text)[0] == first

    @pytest.mark.parametrize("text", ["TIMBRE", "CLAROS", "ZZZ", "DIA A DIA", "ESTIMADO"])
    def test_only_whole_words(self, text):
        assert keyword_categories(text) == ()

    def test_any_of_the_texts(self):
        assert keyword_categories(None, "", "RAPPI")[0] == "Alimentação"


class TestCnae:
    @pytest.mark.parametrize("cnae, first", [
        ("5611-2/01", "Alimentação"), ("4711302", "Alimentação"), ("4731800", "Transporte"), ("4771701", "Saúde"),
        ("8630503", "Saúde"), ("8513900", "Educação"), ("6110801", "Serviços"), ("3514000", "Moradia"),
        ("4781400", "Compras"),
    ])
    def test_prefixes(self, cnae, first):
        assert cnae_categories(cnae)[0] == first

    def test_unknown(self):
        assert cnae_categories("0111301") == () and cnae_categories(None) == ()


class TestPluggyPreference:
    def test_shopping_prefers_compras_and_falls_back(self):
        assert pluggy_category_names("08020000") == ("Compras", "Outros")

    def test_housing_falls_back_to_servicos(self):
        assert pluggy_category_names("17010000") == ("Moradia", "Serviços")

    def test_no_table_no_names(self):
        assert pluggy_category_names("05000000") == ()


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def merchant_tx(amount, day, description, **merchant):
    return {**bank_tx(amount, day, description), "merchant": merchant}


class TestDecision:
    """Na ordem, com as categorias do dono."""

    def category_of(self, world, user, raw):
        db = importlib.import_module("db")
        rules = importlib.import_module("services.open_finance_inbox")
        with db.get_db() as conn:
            row = rules.normalize_transaction(raw, "BANK")
            return rules.category_decision(conn, user["id"], row, "EXPENSE", 10.0, None)

    def test_the_owners_rule_comes_first(self, world, user):
        world.call("post", "/api/import-rules", json={"pattern": "IFOOD", "category": "Lazer", "applies_to": "EXPENSE"})
        name, _id, source = self.category_of(world, user, bank_tx(-10, "2026-10-20", "IFOOD"))
        assert (name, source) == ("Lazer", "rule")

    def test_a_rule_also_reads_the_merchant(self, world, user):
        world.call("post", "/api/import-rules", json={"pattern": "PADOCA", "category": "Lazer", "applies_to": "EXPENSE"})
        raw = merchant_tx(-10, "2026-10-20", "PG *1234", name="PADOCA CENTRAL")
        assert self.category_of(world, user, raw)[2] == "rule"

    def test_the_merchant_beats_the_cnae_and_pluggy(self, world, user):
        raw = merchant_tx(-10, "2026-10-20", "XYZ", name="DROGASIL", cnae="5611201")
        raw["categoryId"] = "19000000"
        assert self.category_of(world, user, raw)[0::2] == ("Saúde", "merchant")

    def test_the_cnae_beats_pluggy(self, world, user):
        raw = merchant_tx(-10, "2026-10-20", "XYZ", cnae="5611201")
        raw["categoryId"] = "19000000"
        assert self.category_of(world, user, raw)[0::2] == ("Alimentação", "cnae")

    def test_pluggys_category_then_the_default(self, world, user):
        raw = bank_tx(-10, "2026-10-20", "XYZ", category_id="19000000")
        assert self.category_of(world, user, raw)[0::2] == ("Transporte", "pluggy")
        assert self.category_of(world, user, bank_tx(-10, "2026-10-20", "XYZ"))[0::2] == ("Outros", "default")

    def test_a_category_the_owner_does_not_have_is_skipped(self, world, user):
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE categories SET archived_at = '2026-01-01' WHERE user_id = ? AND name = 'Alimentação'", (user["id"],))
        raw = bank_tx(-10, "2026-10-20", "IFOOD", category_id="19000000")
        assert self.category_of(world, user, raw)[0::2] == ("Transporte", "pluggy")

    def test_compras_only_if_the_owner_has_it(self, world, user):
        assert self.category_of(world, user, bank_tx(-10, "2026-10-20", "AMAZON"))[0] == "Outros"
        world.call("post", "/api/categories", json={"name": "Compras", "kind": "EXPENSE"})
        assert self.category_of(world, user, bank_tx(-10, "2026-10-20", "AMAZON"))[0] == "Compras"

    def test_the_counterparty_of_a_pix_counts(self, world, user):
        raw = bank_tx(-10, "2026-10-20", "PIX ENVIADO", payment_method="PIX", counterparty="ENEL DISTRIBUICAO")
        assert self.category_of(world, user, raw)[0] == "Moradia"

    def test_income_ignores_the_merchant_table(self, world, user):
        db = importlib.import_module("db")
        rules = importlib.import_module("services.open_finance_inbox")
        with db.get_db() as conn:
            row = rules.normalize_transaction(bank_tx(10, "2026-10-20", "IFOOD"), "BANK")
            assert rules.category_decision(conn, user["id"], row, "INCOME", 10.0, None)[0::2] == ("Receita", "default")


class TestThroughThePull:
    def test_the_merchant_names_the_row_and_the_raw_text_stays(self, world, user):
        item, pluggy_account, account = connect(world, "BB")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        world.fake.add_tx(pluggy_account, merchant_tx(-25.0, "2026-10-20", "PG *1234", name="Drogasil", cnpj="61.585.865/0001-51", cnae="4771-7/01"))
        world.sync(item)
        [row] = world.transactions(account)
        assert (row["description"], row["category"]) == ("Drogasil", "Saúde")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            stored = conn.execute("SELECT * FROM open_finance_transactions WHERE user_id = ?", (user["id"],)).fetchone()
        assert (stored["description"], stored["merchant_name"], stored["merchant_cnpj"], stored["merchant_cnae"]) == (
            "PG *1234", "Drogasil", "61585865000151", "4771701",
        )

    def test_a_card_purchase_is_named_and_categorized_too(self, world, user):
        item, card_pluggy, card = connect(world, "Ourocard", kind="CREDIT")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        world.fake.add_tx(card_pluggy, card_tx(25.0, "2026-10-20", "COMPRA CARTAO IFOOD 3", docs_sign=True))
        world.sync(item)
        [row] = world.card_rows(card)
        assert (row["description"], row["category"]) == ("Ifood 3", "Alimentação")
