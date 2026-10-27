"""Ler uma transacao da Pluggy (services/open_finance_inbox.py, puro).

A convencao de sinal foi conferida no sandbox (Pluggy Bank, 2026-10-27):
- conta: DEBIT negativo (sai), CREDIT positivo (entra);
- cartao: compras negativas com type CREDIT — o contrario da doc ("positivo e
  debito"). Por isso o cartao aprende o sinal de uma compra.
Datas: T03:00:00.000Z (sandbox) e T00:00:00.000Z (doc) sao "so a data".
"""

import importlib

import pytest

from open_finance_world import bank_tx, card_tx


@pytest.fixture()
def rules(app_module):
    return importlib.import_module("services.open_finance_inbox")


class TestMoney:
    @pytest.mark.parametrize("value, cents", [(-89.9, -8990), (8500, 850000), (0.1 + 0.2, 30), (12.345, 1235), ("-0.005", -1)])
    def test_reais_to_cents_round_half_up(self, rules, value, cents):
        assert rules.to_cents(value) == cents

    def test_zero_and_garbage_are_skipped(self, rules):
        with pytest.raises(rules.Skip):
            rules.normalize_transaction(bank_tx(0, "2026-10-20"), "BANK")
        with pytest.raises(rules.Skip):
            rules.to_cents("abc")


class TestDates:
    def test_sandbox_midnight_in_brasilia_is_a_date(self, rules):
        assert rules.local_moment("2026-10-05T03:00:00.000Z") == ("2026-10-05", "2026-10-05")

    def test_docs_midnight_utc_is_the_same_date_not_the_day_before(self, rules):
        assert rules.local_moment("2020-10-15T00:00:00.000Z") == ("2020-10-15", "2020-10-15")

    def test_a_real_time_becomes_local(self, rules):
        assert rules.local_moment("2026-10-27T15:55:02.329Z") == ("2026-10-27", "2026-10-27T12:55:02-03:00")

    def test_late_evening_stays_on_its_local_day(self, rules):
        assert rules.local_moment("2026-10-28T01:30:00.000Z") == ("2026-10-27", "2026-10-27T22:30:00-03:00")

    def test_a_plain_date(self, rules):
        assert rules.local_moment("2026-10-05") == ("2026-10-05", "2026-10-05")


class TestBankSign:
    def test_debit_goes_out_credit_comes_in(self, rules):
        out = rules.normalize_transaction(bank_tx(-100, "2026-10-20"), "BANK")
        income = rules.normalize_transaction(bank_tx(8500, "2026-10-05", "SALARIO"), "BANK")
        assert (out["direction"], out["amount_cents"], out["raw_amount_cents"]) == ("OUT", 10000, -10000)
        assert (income["direction"], income["amount_cents"]) == ("IN", 850000)

    def test_the_type_wins_over_the_sign(self, rules):
        raw = bank_tx(-50, "2026-10-20")
        raw["type"] = "CREDIT"
        assert rules.normalize_transaction(raw, "BANK")["direction"] == "IN"

    def test_without_type_the_sign_decides(self, rules):
        raw = bank_tx(-50, "2026-10-20")
        raw["type"] = None
        assert rules.normalize_transaction(raw, "BANK")["direction"] == "OUT"


class TestCardSign:
    def test_sandbox_shape_with_a_learned_negative_sign(self, rules):
        purchase = rules.normalize_transaction(card_tx(89.9, "2026-10-10"), "CREDIT", charge_sign=-1)
        refund = rules.normalize_transaction(card_tx(-30, "2026-10-12"), "CREDIT", charge_sign=-1)
        assert (purchase["direction"], purchase["amount_cents"]) == ("OUT", 8990)
        assert (refund["direction"], refund["amount_cents"]) == ("IN", 3000)

    def test_docs_shape_with_a_positive_sign(self, rules):
        purchase = rules.normalize_transaction(card_tx(89.9, "2026-10-10", docs_sign=True), "CREDIT", charge_sign=1)
        assert purchase["direction"] == "OUT"

    def test_an_invoice_payment_teaches_the_sign(self, rules):
        sandbox = [card_tx(10, "2026-10-01"), card_tx(-500, "2026-10-02", "PAGAMENTO RECEBIDO", category_id="05100000")]
        docs = [card_tx(10, "2026-10-01", docs_sign=True),
                card_tx(-500, "2026-10-02", "PAGAMENTO RECEBIDO", category_id="05100000", docs_sign=True)]
        assert rules.learn_charge_sign(sandbox) == (-1, "payment")
        assert rules.learn_charge_sign(docs) == (1, "payment")

    def test_a_payment_beats_an_old_majority(self, rules):
        txs = [card_tx(-500, "2026-10-02", "PAGAMENTO RECEBIDO", category_id="05100000")]
        assert rules.learn_charge_sign(txs, 1, "majority") == (-1, "payment")

    def test_the_majority_decides_without_a_payment(self, rules):
        txs = [card_tx(10, "2026-10-01"), card_tx(20, "2026-10-02"), card_tx(-5, "2026-10-03")]
        assert rules.learn_charge_sign(txs) == (-1, "majority")

    def test_a_payment_learned_once_is_kept(self, rules):
        txs = [card_tx(10, "2026-10-01", docs_sign=True)] * 5
        assert rules.learn_charge_sign(txs, -1, "payment") == (-1, "payment")

    def test_too_few_rows_keep_what_was_known_or_the_docs(self, rules):
        txs = [card_tx(10, "2026-10-01")]
        assert rules.learn_charge_sign(txs) == (1, "default")
        assert rules.learn_charge_sign(txs, -1, "majority") == (-1, "majority")


class TestInstallments:
    def test_the_first_installment_carries_the_purchase_total_and_date(self, rules):
        raw = card_tx(55.9, "2026-11-01", "NETFLIX", installment=1, total_installments=6, total_amount=335.4,
                      purchase_date="2026-10-10T03:00:00.000Z")
        tx = rules.normalize_transaction(raw, "CREDIT", charge_sign=-1)
        assert (tx["amount_cents"], tx["installment_number"], tx["total_installments"]) == (33540, 1, 6)
        assert tx["date"] == "2026-10-10"

    def test_open_finance_connectors_send_no_total(self, rules):
        raw = card_tx(50, "2026-10-10", installment=1, total_installments=3)
        assert rules.normalize_transaction(raw, "CREDIT", charge_sign=-1)["amount_cents"] == 15000

    def test_a_later_installment_keeps_its_own_amount(self, rules):
        raw = card_tx(55.9, "2026-11-01", installment=2, total_installments=6, total_amount=335.4)
        tx = rules.normalize_transaction(raw, "CREDIT", charge_sign=-1)
        assert (tx["amount_cents"], tx["installment_number"]) == (5590, 2)


class TestMovements:
    def test_invoice_payment_on_the_bank_and_on_the_card(self, rules):
        bank = rules.normalize_transaction(bank_tx(-838.5, "2026-10-10", "PAGAMENTO FATURA", category_id="05100000"), "BANK")
        card = rules.normalize_transaction(
            card_tx(-838.5, "2026-10-10", "PAGAMENTO RECEBIDO", category_id="05100000"), "CREDIT", charge_sign=-1,
        )
        assert bank["movement"] == card["movement"] == "INVOICE_PAYMENT"
        assert card["direction"] == "IN"

    def test_payment_words_without_category(self, rules):
        tx = rules.normalize_transaction(bank_tx(-200, "2026-10-10", "PAG FATURA CARTAO ITAU"), "BANK")
        assert tx["movement"] == "INVOICE_PAYMENT"

    def test_same_owner_pix_and_third_party_pix(self, rules):
        own = rules.normalize_transaction(bank_tx(-300, "2026-10-10", category_id="04020000"), "BANK")
        pix = rules.normalize_transaction(bank_tx(-300, "2026-10-10", category_id="05090004"), "BANK")
        assert own["movement"] == "SELF_TRANSFER"
        assert pix["movement"] == "TRANSFER"

    def test_a_bank_slip_is_a_bill_not_a_transfer(self, rules):
        tx = rules.normalize_transaction(
            bank_tx(-100, "2026-10-10", category_id="05010000", payment_method="BOLETO", counterparty="Loja"), "BANK",
        )
        assert tx["movement"] is None

    def test_payment_method_pix_is_a_transfer(self, rules):
        tx = rules.normalize_transaction(bank_tx(-100, "2026-10-10", payment_method="PIX", counterparty="Ana"), "BANK")
        assert tx["movement"] == "TRANSFER"
        assert tx["counterparty"] == "Ana"

    def test_a_cpf_keeps_only_the_digits_the_bank_shows(self, rules):
        tx = rules.normalize_transaction(
            bank_tx(-100, "2026-10-10", payment_method="PIX", counterparty="Ana", doc="123.378.195-00"), "BANK",
        )
        assert tx["counterparty_doc"] == "378195"


class TestStatus:
    def test_pending_is_skipped(self, rules):
        with pytest.raises(rules.Skip) as skip:
            rules.normalize_transaction(bank_tx(-10, "2026-10-20", status="PENDING"), "BANK")
        assert str(skip.value) == rules.STATUS_SKIPPED_PENDING

    def test_the_key_is_the_pluggy_id(self, rules):
        tx = rules.normalize_transaction(bank_tx(-10, "2026-10-20", tx_id="abc-1"), "BANK")
        assert tx["dedup_key"] == "pluggy:abc-1"

    def test_foreign_currency_uses_the_account_currency_amount(self, rules):
        raw = bank_tx(-58, "2026-10-20")
        raw.update({"currencyCode": "USD", "amountInAccountCurrency": -298.19})
        tx = rules.normalize_transaction(raw, "BANK")
        assert (tx["currency"], tx["amount_cents"]) == ("BRL", 29819)
