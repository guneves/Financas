"""Open Finance -> Aprovar (043): cada transacao da Pluggy vira, no maximo, um
item do Aprovar — nada e gravado sem o dono aprovar.

Duas metades:

1. **Ler a Pluggy** (puro): `normalize_transaction()` tira de uma transacao da
   API o que o app usa — direcao, valor em centavos, data local, parcela, se e
   transferencia ou pagamento de fatura, quem esta do outro lado.
   - Conta (BANK): `type` DEBIT sai, CREDIT entra (o sinal do valor, se faltar
     o tipo). Visto no sandbox: DEBIT negativo, CREDIT positivo.
   - Cartao (CREDIT): nem `type` nem o sinal valem as cegas. A doc da Pluggy
     diz "positivo e debito"; o sandbox manda compras negativas com type
     CREDIT. Cada cartao aprende o sinal de uma compra (`learn_charge_sign()`):
     um pagamento de fatura no pull (categoria 05100000, entrada por
     definicao) decide; senao a maioria (>= 3 transacoes); senao a doc (+).
   - Data: a Pluggy manda AAAA-MM-DDT03:00:00.000Z (sandbox) ou T00:00:00.000Z
     (doc) para "so a data"; outra hora e um instante, convertido para -03:00.
2. **Por no Aprovar** (`ingest()`), reusando services/inbox.py:
   - a mesma compra que uma notificacao ja trouxe e o MESMO item
     (`inbox.notification_item_for_open_finance()`; o contrario, a notificacao
     depois, em `inbox.open_finance_item_for_detection()`);
   - as duas pontas de uma transferencia entre contas do dono (ambas
     conectadas, ou uma notificada) sao UM item TRANSFER (`transfer_partner`);
   - parcela 2..n de uma compra no cartao: COVERED, nunca item — aprovar a
     compra (`POST /api/cc-expenses/purchases`, a parcela 1 com o total) ja
     gera todas, na fatura que `compute_invoice_start()` diz;
   - pagamento de fatura (na conta ou no cartao): nunca despesa; na conta ele
     paga a fatura depois do pull (services/open_finance_invoices.py);
   - credito no cartao (estorno): item CARD de entrada, vira kind REFUND (033);
   - o resto: item novo, com os lancamentos parecidos ja gravados.
   - A categoria: a regra de importacao do dono pela descricao; senao a da
     Pluggy traduzida (open_finance_categories.py); senao a padrao.
   - Na Corretora (a conta "BTG Investimentos"), so a transferencia com o
     banco vira item (aporte/resgate, 039); o resto e do caixa da carteira
     (services/broker_statement.py): as operacoes explicam o bruto do pregao,
     o resto vira linha, e o saldo da Corretora fica o do banco.
   - O pagamento de fatura na conta liga ao pagamento que o app ja tem
     (pay-invoice), nunca grava outro; sem ele, o pull o grava pela baixa da
     fatura (services/open_finance_invoices.py).

Com o interruptor ligado (044, services/open_finance_auto.py), o item pronto
nao espera o dono: e aprovado na hora. Uma transacao ja gravada sozinha que
muda de valor ou some e corrigida/apagada so se o lancamento esta como nasceu
(`apply_change()` / `apply_vanish()`); editado, fica `conflict`.

Idempotente pela chave `pluggy:<id>` por usuario: puxar de novo, a folga de
dias e reconectar nao duplicam. Uma transacao que some, ou muda de valor,
antes da aprovacao faz o que o Aprovar ja faz quando a fonte some: o item
sai (REMOVED) se nao tiver outra fonte.
"""

import calendar
import re

import money
import statement_import
from db import new_id, row_to_dict, utc_timestamp
from open_finance_categories import (
    cnae_categories,
    display_name,
    expected_type,
    keyword_categories,
    plain_text,
    pluggy_category_names,
)
from services import broker_statement, global_account, inbox, review
from services.accounts import category_id_for_name, fetch_category
from services.import_rules import import_rules_for_matching
from services.open_finance_rows import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    BILL_CATEGORIES,
    BRT,
    DEDUP_PREFIX,
    INCOME_CATEGORY_PREFIX,
    INVOICE_PAYMENT_CATEGORY,
    INVOICE_PAYMENT_LINK_DAYS,
    INVOICE_PAYMENT_TEXT,
    MIN_SIGN_SAMPLE,
    SALARY_TEXT,
    SELF_TRANSFER_PREFIX,
    STATUS_SKIPPED_PENDING,
    TRANSFER_CATEGORIES,
    TRANSFER_METHODS,
    Skip,
    _bill_month,
    _digits,
    _positive_int,
    _text,
    counterparty_doc,
    is_income_row,
    is_invoice_payment,
    learn_charge_sign,
    local_moment,
    movement_of,
    normalize_transaction,
    to_cents,
)
from services.recorded_snapshot import (  # noqa: F401  (reexportados: quem chamava daqui continua)
    CARD_SNAPSHOT_COLUMNS,
    TRANSACTION_SNAPSHOT_COLUMNS,
    _dump,
    mark_auto_recorded,
    refresh_snapshots,
    snapshot_amount_cents,
    snapshot_unchanged,
    target_snapshot,
    untouched,
)
from source_types import (
    BANK_INVESTMENT_SOURCE_TYPE,
    INVOICE_PAYMENT_SOURCE_TYPES,
    OPEN_FINANCE_SOURCE_TYPE,
)

# ---------------------------------------------------------------------------
# Por no Aprovar
# ---------------------------------------------------------------------------

ROW_FIELDS = (
    "pluggy_transaction_id", "dedup_key", "direction", "amount_cents", "raw_amount_cents", "currency", "date",
    "occurred_at", "description", "pluggy_type", "pluggy_category", "pluggy_category_id", "movement",
    "installment_number", "total_installments", "counterparty", "counterparty_doc", "merchant_name",
    "merchant_cnpj", "merchant_cnae", "posted_on", "bill_month", "original_currency",
)


def fetch_row(conn, current_user_id, dedup_key):
    return conn.execute(
        "SELECT * FROM open_finance_transactions WHERE user_id = ? AND dedup_key = ?",
        (current_user_id, dedup_key),
    ).fetchone()


def fetch_account(conn, current_user_id, of_account_id):
    return conn.execute(
        "SELECT * FROM open_finance_accounts WHERE id = ? AND user_id = ?",
        (of_account_id, current_user_id),
    ).fetchone()


def _update_row(conn, current_user_id, row_id, **changes):
    changes["updated_at"] = utc_timestamp()
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(
        f"UPDATE open_finance_transactions SET {assignments} WHERE id = ? AND user_id = ?",
        (*changes.values(), row_id, current_user_id),
    )


def mapped_target(account):
    """(entry_type, account_id, card_id) do mapeamento, ou None sem mapeamento."""
    if account["type"] == "CREDIT":
        return ("CARD", None, account["card_id"]) if account["card_id"] else None
    return (None, account["account_id"], None) if account["account_id"] else None


def _entry_type(account, direction):
    if account["type"] == "CREDIT":
        return "CARD"
    return "EXPENSE" if direction == "OUT" else "INCOME"


def ingest(conn, current_user_id, account, tx, rules=None, seen_at=None, missing=None, pulled=None):
    """Grava (ou reconhece) uma transacao normalizada e a poe no Aprovar.
    Devolve o status: new, merged, matched, denied, covered, invoice_payment,
    unmapped, succeeded ou known. `missing`: as transacoes desta conta que o
    pull nao devolveu (missing_rows); uma id nova que continua uma delas a
    sucede no lugar (hand_over), nunca vira um segundo movimento. `pulled`: as
    transacoes novas da conta neste pull (o "um de cada lado" da sucessao com
    outro valor)."""
    seen_at = seen_at or utc_timestamp()
    existing = fetch_row(conn, current_user_id, tx["dedup_key"])
    if existing is None:
        old = successor_for(conn, current_user_id, account, tx, missing, pulled)
        if old is not None:
            status = hand_over(conn, current_user_id, old, tx, account, seen_at)
            if not _same_amount(
                old["amount_cents"], tx["amount_cents"], inbox.open_finance_rounds_up(conn, current_user_id, account["id"]),
            ):
                follow_after_succession(conn, current_user_id, fetch_row(conn, current_user_id, tx["dedup_key"]), tx)
            return status
        row_id = new_id()
        values = {"id": row_id, "user_id": current_user_id, "of_account_id": account["id"], "role": "UNMAPPED",
                  "last_seen_at": seen_at}
        values.update({field: tx[field] for field in ROW_FIELDS})
        conn.execute(
            f"INSERT INTO open_finance_transactions ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
        return place(conn, current_user_id, row_to_dict(_by_id(conn, current_user_id, row_id)), account, rules)

    existing = row_to_dict(existing)
    _update_row(conn, current_user_id, existing["id"], last_seen_at=seen_at)
    if existing["role"] == "REMOVED" and existing.get("superseded_by"):
        # Ja sucedida: a sucessora e o movimento; a velha nunca volta a ser outro.
        return "known"
    changed = (existing["amount_cents"], existing["direction"]) != (tx["amount_cents"], tx["direction"])
    if changed and existing["role"] == "INVOICE_PAYMENT" and existing["target_id"]:
        return apply_payment_change(conn, current_user_id, existing, tx)
    if changed:
        if existing["role"] in ("SOURCE", "PAIRED", "MATCHED") and not _item_pending(conn, current_user_id, existing):
            # Ja decidido: so o gravado sozinho e ainda intocado se corrige;
            # o resto fica como esta, apontado na Conferencia.
            return apply_change(conn, current_user_id, existing, tx)
        if existing["role"] == "SOURCE":
            vanish(conn, current_user_id, existing, reason="changed")
        _update_row(
            conn, current_user_id, existing["id"], role="UNMAPPED", item_id=None, target_table=None, target_id=None,
            **{field: tx[field] for field in ROW_FIELDS if field != "dedup_key"},
        )
        return place(conn, current_user_id, row_to_dict(_by_id(conn, current_user_id, existing["id"])), account, rules)
    details = {field: tx[field] for field in ROW_FIELDS if field != "dedup_key" and existing[field] != tx[field]}
    if details:
        # Mesmo valor, outros detalhes (a pendente que liquidou): a linha
        # acompanha; o item do Aprovar fica como o dono o deixou.
        _update_row(conn, current_user_id, existing["id"], **details)
        existing.update(details)
    if existing["role"] == "REMOVED" or (existing["role"] == "UNMAPPED" and mapped_target(account)):
        return place(conn, current_user_id, existing, account, rules)
    return "known"


def _by_id(conn, current_user_id, row_id):
    return conn.execute(
        "SELECT * FROM open_finance_transactions WHERE id = ? AND user_id = ?", (row_id, current_user_id),
    ).fetchone()


def _item_pending(conn, current_user_id, row):
    if not row.get("item_id"):
        return True
    item = inbox.fetch_item(conn, current_user_id, row["item_id"])
    return bool(item) and item["state"] == inbox.PENDING


def place(conn, current_user_id, row, account, rules=None):
    """Decide o papel de uma linha ja gravada e liga ao item certo."""
    target = mapped_target(account)
    if target is None:
        _update_row(conn, current_user_id, row["id"], role="UNMAPPED", item_id=None)
        return "unmapped"
    if row["movement"] == "INVOICE_PAYMENT":
        link = invoice_payment_link(conn, current_user_id, row, account) if account["type"] == "BANK" else None
        _update_row(
            conn, current_user_id, row["id"], role="INVOICE_PAYMENT", item_id=None,
            target_table="transactions" if link else None, target_id=link,
        )
        return "invoice_payment"
    if (
        account["type"] == "BANK" and not is_broker_transfer(row)
        and is_brokerage(conn, current_user_id, account["account_id"])
    ):
        # O caixa da carteira (services/broker_statement.py): compra, venda e
        # provento ja tem o caminho deles; a taxa, o IR e a renda fixa viram linha.
        role, entry = broker_statement.settle_line(conn, current_user_id, row, account["account_id"])
        _update_row(
            conn, current_user_id, row["id"], role=role, item_id=None,
            target_table="transactions" if entry else None, target_id=entry,
        )
        return "matched" if entry else "covered"
    if account["type"] == "CREDIT" and row["direction"] == "OUT" and (row["installment_number"] or 1) > 1:
        _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
        return "covered"
    if account["type"] == "BANK" and is_auto_invest_row(row):
        if inbox.is_auto_invest(row["description"]) or not SOLD_INVESTMENT_TEXT.search(inbox.normalized(row["description"])):
            # A aplicacao automatica (Rende Facil, conta remunerada): nunca no app,
            # nem na conferencia.
            _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
            return "covered"
        # O resgate de outra aplicacao (Tesouro Reserva) e dinheiro de verdade.
        entry = broker_statement.write_line(conn, current_user_id, row, account["account_id"])
        _update_row(conn, current_user_id, row["id"], role="MATCHED", item_id=None, target_table="transactions", target_id=entry)
        return "matched"

    entry_type = _entry_type(account, row["direction"])
    _, account_id, card_id = target
    cents = int(row["amount_cents"])

    # 1. Uma notificacao ja trouxe este movimento: o mesmo item.
    partner = inbox.notification_item_for_open_finance(
        conn, current_user_id, entry_type=entry_type, direction=row["direction"], cents=cents,
        date_text=row["date"], account_id=account_id, card_id=card_id,
        rounds_up=inbox.open_finance_rounds_up(conn, current_user_id, account["id"]),
    )
    if partner:
        return _join_item(conn, current_user_id, row, inbox.item_dict(partner), entry_type, account_id, card_id)

    # 1b. Uma transferencia que o app ja tem com uma conta sem Pluggy (a Flash):
    #     esta transacao e a ponta do banco dela, nunca um segundo movimento.
    if account["type"] == "BANK":
        recorded = recorded_transfer_for_row(conn, current_user_id, row, account_id, cents)
        if recorded:
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=None,
                target_table="transactions", target_id=recorded,
            )
            return "matched"

    # 2. A outra ponta de uma transferencia para a conta global (em dolar):
    #    o par e pela contraparte e pelo dia, nunca pelos centavos.
    if account["type"] == "BANK":
        crossed = _place_cross_currency(conn, current_user_id, row, account_id, cents)
        if crossed:
            return crossed

    # 3. A outra ponta de uma transferencia entre contas do dono.
    if account["type"] == "BANK" and row["movement"] in ("TRANSFER", "SELF_TRANSFER"):
        approved = inbox.approved_transfer_awaiting(
            conn, current_user_id, account_id=account_id, direction=row["direction"], cents=cents,
            date_text=row["date"],
        )
        if approved:
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=approved["id"],
                target_table="transactions", target_id=approved["target_id"],
            )
            inbox.settle_transfer_review(conn, current_user_id, approved["id"])
            return "matched"
        other = inbox.transfer_partner(
            conn, current_user_id, account_id=account_id, direction=row["direction"], cents=cents,
            date_text=row["date"], detection={"counterparty": row["counterparty"], "counterparty_doc": row["counterparty_doc"]},
        )
        if other and _is_movement_item(conn, current_user_id, other):
            _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=other["id"])
            inbox.make_transfer(
                conn, current_user_id, inbox.item_dict(other), account_id=account_id, direction=row["direction"],
            )
            return "merged"
        # A outra ponta ja virou despesa/receita sozinha (notificacao ou Pluggy):
        # a mesma linha vira a transferencia (inbox.absorb_recorded_side).
        absorbed = inbox.absorb_recorded_side(
            conn, current_user_id, account_id=account_id, direction=row["direction"], cents=cents,
            date_text=row["date"], occurred_at=row["occurred_at"],
            counterparty={"counterparty": row["counterparty"], "counterparty_doc": row["counterparty_doc"]},
            description=row["description"],
        )
        if absorbed:
            _update_row(
                conn, current_user_id, row["id"], role="SOURCE", item_id=absorbed["id"],
                target_table="transactions", target_id=absorbed["target_id"],
            )
            inbox.finish_absorb(conn, current_user_id, absorbed)
            return "merged"

    # 4. Um item novo.
    new_item_for_row(conn, current_user_id, row, account, rules)
    return "new"


def recorded_transfer_for_row(conn, current_user_id, row, account_id, cents):
    """A transferencia ja gravada (esta conta deste lado, mesmo valor, ate
    TRANSFER_MATCH_DAYS dias) que so espera esta ponta: a outra conta nao tem
    Pluggy, entao ela nunca vem, ou o dono apontou como transferencia uma linha
    que a Pluggy trouxe da outra ponta. Uma por transacao: a que nenhuma outra
    deste lado ja explica."""
    if row["direction"] == "OUT":
        side, other, value = "t.account_id", "t.transfer_account_id", "t.amount"
    else:
        side, other, value = "t.transfer_account_id", "t.account_id", "COALESCE(t.transfer_amount, t.amount)"
    found = conn.execute(
        f"""
        SELECT t.id, t.date FROM transactions t
        WHERE t.user_id = ? AND t.type = 'TRANSFER' AND {side} = ? AND {other} IS NOT NULL
          AND CAST(ROUND({value} * 100) AS INTEGER) = ? AND t.date BETWEEN ? AND ?
          AND (
              NOT EXISTS (
                  SELECT 1 FROM open_finance_accounts a
                  JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
                  WHERE a.user_id = t.user_id AND a.account_id = {other} AND i.archived_at IS NULL
              )
              OR EXISTS (
                  SELECT 1 FROM open_finance_transactions o
                  WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                    AND o.direction <> ? AND o.role <> 'REMOVED'
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                AND o.id <> ? AND o.direction = ? AND o.role <> 'REMOVED'
          )
        """,
        (
            current_user_id, account_id, cents, inbox._shift(row["date"], -inbox.TRANSFER_MATCH_DAYS),
            inbox._shift(row["date"], inbox.TRANSFER_MATCH_DAYS), row["direction"], row["id"], row["direction"],
        ),
    ).fetchall()
    found = sorted(found, key=lambda entry: (inbox._date_gap(entry["date"], row["date"]), entry["date"], entry["id"]))
    return found[0]["id"] if found else None


def _place_cross_currency(conn, current_user_id, row, account_id, cents):
    """A conta global (services/global_account.py): a entrada em dolar acha a
    saida em reais que a espera (ou a transferencia ja no app), e a saida em
    reais acha a entrada em dolar. Devolve o status, ou None (segue o resto)."""
    if global_account.is_foreign(conn, current_user_id, account_id):
        if row["direction"] != "IN":
            return None
        target = _app_account(conn, current_user_id, account_id)
        recorded = global_account.recorded_transfer(conn, current_user_id, target, cents, row["date"])
        if recorded:
            if recorded["transfer_amount"] is None:
                # A conta virou global depois: o valor em dolar e o do banco.
                conn.execute(
                    "UPDATE transactions SET transfer_amount = ? WHERE id = ? AND user_id = ?",
                    (money.from_cents(cents), recorded["id"], current_user_id),
                )
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=None,
                target_table="transactions", target_id=recorded["id"],
            )
            return "matched"
        waiting = global_account.awaiting_real_side(conn, current_user_id, target, cents, row["date"])
        if not waiting:
            return _absorb_recorded_real_side(conn, current_user_id, row, target, cents)
        item = inbox.item_dict(waiting)
        _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
        changes = {
            "transfer_account_id": target["id"],
            "transfer_amount": money.from_cents(cents),
            "guessed": [guess for guess in item.get("guessed") or [] if guess != "transfer_account"],
            "description": global_account.transfer_description(
                global_account.account_name(conn, current_user_id, item["account_id"]), target["name"],
            ),
        }
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, current_user_id, item, changes)
        return "merged"

    destination = global_account.destination_for_row(conn, current_user_id, row, account_id)
    if destination is None:
        return None
    waiting = global_account.awaiting_foreign_side(conn, current_user_id, destination, cents, row["date"])
    if not waiting:
        return _absorb_recorded_dollar_income(conn, current_user_id, row, account_id, destination, cents)
    item = inbox.item_dict(waiting)
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    changes = {
        "entry_type": "TRANSFER",
        "direction": "OUT",
        "account_id": account_id,
        "transfer_account_id": destination["id"],
        "amount": money.from_cents(cents),
        "currency": "BRL",
        "transfer_amount": item["amount"],
        # A data da transferencia e a da saida.
        "occurred_at": row["occurred_at"],
        "category": inbox.TRANSFER_CATEGORY,
        "category_id": None,
        "edited": [field for field in item.get("edited") or [] if field != "amount"],
        "reason": "own_transfer",
        "description": global_account.transfer_description(
            global_account.account_name(conn, current_user_id, account_id), destination["name"],
        ),
    }
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)
    return "merged"


def _absorb_recorded_dollar_income(conn, current_user_id, row, account_id, destination, cents):
    """O credito em dolar ja virou receita sozinho (puxado antes, sem par em
    TRANSFER_HOLD_DAYS) e ainda esta como nasceu: a mesma linha vira a
    transferencia — nunca receita em dolar mais despesa em reais."""
    candidates = []
    for entry in conn.execute(
        """
        SELECT o.*, i.id AS the_item, i.target_id AS the_target, t.amount AS dollars,
               substr(i.occurred_at, 1, 10) AS item_date
        FROM open_finance_transactions o
        JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
        JOIN transactions t ON t.id = i.target_id AND t.user_id = i.user_id
        WHERE o.user_id = ? AND o.role = 'SOURCE' AND o.direction = 'IN' AND o.auto_recorded_at IS NOT NULL
          AND i.state = 'APPROVED' AND i.target_table = 'transactions'
          AND t.type = 'INCOME' AND t.account_id = ?
        """,
        (current_user_id, destination["id"]),
    ).fetchall():
        source = row_to_dict(entry)
        source.update(target_table="transactions", target_id=source["the_target"])
        if untouched(conn, current_user_id, source):
            candidates.append({**source, "id": source["the_item"], "date": source["item_date"]})
    best = global_account._best(
        conn, current_user_id, normalize_currency_of(destination), row["date"], candidates,
        brl_of=lambda candidate: cents, foreign_of=lambda candidate: money.to_cents(candidate["dollars"]),
    )
    if not best:
        return None
    item = inbox.item_dict(inbox.fetch_item(conn, current_user_id, best["the_item"]))
    target_id = best["the_target"]
    description = global_account.transfer_description(
        global_account.account_name(conn, current_user_id, account_id), destination["name"],
    )
    conn.execute(
        """
        UPDATE transactions SET type = 'TRANSFER', account_id = ?, transfer_account_id = ?, amount = ?,
            transfer_amount = ?, date = ?, occurred_at = ?, category = ?, category_id = NULL, description = ?,
            source_id = ?
        WHERE id = ? AND user_id = ?
        """,
        (account_id, destination["id"], money.from_cents(cents), best["dollars"], row["date"], row["occurred_at"],
         inbox.TRANSFER_CATEGORY, description, row["pluggy_transaction_id"], target_id, current_user_id),
    )
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    inbox.save_item(conn, current_user_id, item, {
        "entry_type": "TRANSFER", "direction": "OUT", "account_id": account_id,
        "transfer_account_id": destination["id"], "amount": money.from_cents(cents), "currency": "BRL",
        "transfer_amount": best["dollars"], "occurred_at": row["occurred_at"],
        "category": inbox.TRANSFER_CATEGORY, "category_id": None, "description": description,
    })
    mark_auto_recorded(conn, current_user_id, item["id"], "transactions", target_id)
    return "merged"


def _absorb_recorded_real_side(conn, current_user_id, row, target, dollar_cents):
    """O credito em dolar acha o Pix em reais que ja virou despesa sozinho (dono,
    2026-11-01: nada espera) e ainda esta como nasceu, nomeando a conta global:
    a mesma linha vira a transferencia, com o valor em dolar do banco — nunca
    despesa em reais mais receita em dolar."""
    candidates = []
    for entry in conn.execute(
        """
        SELECT o.*, i.id AS the_item, i.target_id AS the_target, t.account_id AS real_account, t.amount AS reais,
               t.date AS item_date
        FROM open_finance_transactions o
        JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
        JOIN transactions t ON t.id = i.target_id AND t.user_id = i.user_id
        WHERE o.user_id = ? AND o.role = 'SOURCE' AND o.direction = 'OUT' AND o.auto_recorded_at IS NOT NULL
          AND i.state = 'APPROVED' AND i.target_table = 'transactions'
          AND t.type = 'EXPENSE' AND t.share_mode IS NULL
        """,
        (current_user_id,),
    ).fetchall():
        source = row_to_dict(entry)
        if global_account.is_foreign(conn, current_user_id, source["real_account"]):
            continue
        named = global_account.destination_for_row(conn, current_user_id, source, source["real_account"])
        if not named or named["id"] != target["id"]:
            continue
        source.update(target_table="transactions", target_id=source["the_target"])
        if untouched(conn, current_user_id, source):
            candidates.append({**source, "id": source["the_item"], "date": source["item_date"]})
    best = global_account._best(
        conn, current_user_id, normalize_currency_of(target), row["date"], candidates,
        brl_of=lambda candidate: money.to_cents(candidate["reais"]), foreign_of=lambda candidate: dollar_cents,
    )
    if not best:
        return None
    item = inbox.item_dict(inbox.fetch_item(conn, current_user_id, best["the_item"]))
    description = global_account.transfer_description(
        global_account.account_name(conn, current_user_id, best["real_account"]), target["name"],
    )
    conn.execute(
        """
        UPDATE transactions SET type = 'TRANSFER', transfer_account_id = ?, transfer_amount = ?, category = ?,
            category_id = NULL, description = ?
        WHERE id = ? AND user_id = ?
        """,
        (target["id"], money.from_cents(dollar_cents), inbox.TRANSFER_CATEGORY, description, best["the_target"],
         current_user_id),
    )
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    inbox.save_item(conn, current_user_id, item, {
        "entry_type": "TRANSFER", "direction": "OUT", "transfer_account_id": target["id"],
        "transfer_amount": money.from_cents(dollar_cents), "category": inbox.TRANSFER_CATEGORY, "category_id": None,
        "description": description, "reason": "own_transfer",
    })
    mark_auto_recorded(conn, current_user_id, item["id"], "transactions", best["the_target"])
    return "merged"


def normalize_currency_of(account):
    return str(account["currency"] or "BRL").upper()


def _app_account(conn, current_user_id, account_id):
    return conn.execute(
        "SELECT id, name, institution, currency FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, current_user_id),
    ).fetchone()


def _is_movement_item(conn, current_user_id, item_row):
    """So uma transferencia junta com transferencia: o item tem uma fonte que
    e Pix/TED (notificacao ou Open Finance), ou ja e uma transferencia."""
    if item_row["entry_type"] == "TRANSFER":
        return True
    for detection in inbox.item_detections(conn, current_user_id, item_row["id"]):
        if detection["role"] == inbox.SOURCE and detection["kind"] in inbox.MOVEMENT_KINDS:
            return True
    return any(
        source["movement"] in ("TRANSFER", "SELF_TRANSFER")
        for source in inbox.open_finance_sources(conn, current_user_id, item_row["id"], roles=(inbox.SOURCE,))
    )


def _join_item(conn, current_user_id, row, item, entry_type, account_id, card_id):
    """A transacao entra no item que a notificacao abriu. Pendente: o
    cartao/conta do mapeamento (certo) entra onde o dono nao escolheu, e o que
    era palpite deixa de ser."""
    if item["state"] == inbox.APPROVED and item.get("auto_recorded_at"):
        return reconcile_recorded(conn, current_user_id, row, item, entry_type, account_id, card_id)
    if item["state"] != inbox.PENDING:
        role = "PAIRED" if item["state"] == inbox.DENIED else "MATCHED"
        _update_row(
            conn, current_user_id, row["id"], role=role, item_id=item["id"],
            target_table=item.get("target_table"), target_id=item.get("target_id"),
        )
        return "denied" if role == "PAIRED" else "matched"
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    edited = set(item.get("edited") or [])
    changes = {}
    if item["entry_type"] == "TRANSFER":
        field, need = ("account_id", "account") if row["direction"] == "OUT" else ("transfer_account_id", "transfer_account")
        if field not in edited:
            changes[field] = account_id
            changes["guessed"] = [guess for guess in item.get("guessed") or [] if guess != need]
    elif not ({"entry_type", "card_id", "account_id"} & edited):
        if entry_type == "CARD":
            changes.update({"entry_type": "CARD", "card_id": card_id, "account_id": None})
            if row["direction"] == "IN":
                changes["recurring_off"] = 1
        else:
            changes.update({"entry_type": entry_type, "account_id": account_id, "card_id": None})
        changes["guessed"] = [guess for guess in item.get("guessed") or [] if guess not in ("card", "account")]
    if changes:
        merged = {**item, **changes}
        changes["needs"] = inbox.recompute_needs(merged)
        inbox.save_item(conn, current_user_id, item, changes)
    return "merged"


# ---------------------------------------------------------------------------
# Conferencia do que a notificacao gravou (045)
# ---------------------------------------------------------------------------

def notification_untouched(conn, current_user_id, item):
    """O lancamento que a notificacao gravou sozinha esta como nasceu: o
    snapshot e a unica prova do que o dono mudou (Fase 4). Revisar ("e meu")
    nao toca; mudar a categoria, o valor, a data ou a conta toca. Por isso a
    revisao pode sair sozinha sem calar o banco."""
    return snapshot_unchanged(conn, current_user_id, item)


def bank_disagrees(item, row, entry_type, account_id, card_id):
    """O banco diz outra data ou outra conta/cartao do que a notificacao gravou."""
    if inbox.date_of(item["occurred_at"]) != row["date"]:
        return True
    if entry_type == "CARD":
        return item["entry_type"] != "CARD" or item.get("card_id") != card_id
    return item["entry_type"] != entry_type or item.get("account_id") != account_id


def _drop_target(conn, current_user_id, item):
    table, target_id = item["target_table"], item["target_id"]
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, table, target_id),
    )
    if table == "transactions":
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id))
    else:
        conn.execute(
            """
            DELETE FROM cc_expenses
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (current_user_id, target_id, current_user_id),
        )
    conn.execute(
        "UPDATE notify_detections SET target_table = NULL, target_id = NULL WHERE user_id = ? AND item_id = ?",
        (current_user_id, item["id"]),
    )


def follow_bank_side(conn, current_user_id, row, item, account_id):
    """Defeito R: a notificacao de uma ponta so gravou a transferencia com o
    outro lado adivinhado (`guessed`); a Pluggy mostra de qual conta o dinheiro
    saiu (ou para qual entrou). O lado adivinhado, que o dono nao mexeu, passa a
    ser o do banco. Nunca as duas pontas na mesma conta, nunca a conta global,
    nunca uma conta arquivada. Devolve True se corrigiu."""
    field, need = ("account_id", "account") if row["direction"] == "OUT" else ("transfer_account_id", "transfer_account")
    other_field = "transfer_account_id" if field == "account_id" else "account_id"
    current = item.get(field)
    if not account_id or current == account_id or not current:
        return False
    if need not in (item.get("guessed") or []) or field in (item.get("edited") or []):
        return False
    if item.get("target_table") != "transactions" or item.get(other_field) == account_id:
        return False
    if not inbox._brl_active_account(conn, current_user_id, account_id):
        return False
    if global_account.is_foreign(conn, current_user_id, current):
        return False
    if not snapshot_unchanged(conn, current_user_id, item):
        return False
    merged = {**item, field: account_id}
    changes = {field: account_id, "guessed": [guess for guess in item.get("guessed") or [] if guess != need]}
    if "description" not in (item.get("edited") or []):
        changes["description"] = inbox._transfer_description(
            conn, current_user_id, merged["account_id"], merged["transfer_account_id"], item.get("description"),
        )
    conn.execute(
        f"UPDATE transactions SET {field} = ?, description = ? WHERE id = ? AND user_id = ? AND type = 'TRANSFER'",
        (account_id, changes.get("description", item.get("description")), item["target_id"], current_user_id),
    )
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)
    refresh_snapshots(conn, current_user_id, item["id"], item["target_table"], item["target_id"])
    item["recorded_snapshot"] = _dump(target_snapshot(conn, current_user_id, item["target_table"], item["target_id"]))
    return True


def settle_review(conn, current_user_id, item, row, entry_type, account_id=None):
    """A Pluggy confirmou o lancamento que o item gravou (Fase 4):
    sai da revisao sozinho quando nao ha palpite.

    - transferencia: com as duas pontas no app (inbox.settle_transfer_review);
    - despesa, receita, compra no cartao: a categoria desta transacao vem de
      CONFIDENT_CATEGORY_SOURCES (regra do dono, comerciante, CNAE); ainda
      intocado pelo snapshot, a categoria passa a ser essa.

    Ficam a revisar: categoria da arvore da Pluggy ou a padrao, o estorno, a
    conta global (revisa na tela dela) e o editado pelo dono. Os snapshots
    (do item e das transacoes) passam a ser o de agora, na mesma transacao:
    o que o app mudou nunca conta como toque do dono. Devolve True se saiu."""
    table, target_id = item.get("target_table"), item.get("target_id")
    if not table or not target_id or not review.awaiting(conn, current_user_id, table, target_id):
        return False
    if item.get("entry_type") == "TRANSFER" or entry_type == "TRANSFER":
        return inbox.settle_transfer_review(conn, current_user_id, item["id"])
    if table == "transactions":
        target = conn.execute(
            "SELECT type, account_id FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        if not target or target["type"] not in ("EXPENSE", "INCOME"):
            return False
        if global_account.is_foreign(conn, current_user_id, target["account_id"]):
            return False
        kind_type = target["type"]
    else:
        target = conn.execute(
            "SELECT kind FROM cc_expenses WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        if not target or target["kind"] == "REFUND":
            return False
        kind_type = "CARD"
    fresh = conn.execute(
        "SELECT * FROM open_finance_transactions WHERE id = ? AND user_id = ?", (row["id"], current_user_id),
    ).fetchone()
    if not fresh:
        return False
    source = row_to_dict(fresh)
    if item.get("recorded_snapshot"):
        if not snapshot_unchanged(conn, current_user_id, item):
            return False
    elif not untouched(conn, current_user_id, source):
        return False
    name, category_id, origin = category_decision(
        conn, current_user_id, source, kind_type, item.get("amount"), account_id,
    )
    if origin not in CONFIDENT_CATEGORY_SOURCES:
        return False
    review.clear(conn, current_user_id, table, target_id, (name, category_id))
    refresh_snapshots(conn, current_user_id, item["id"], table, target_id)
    if item.get("recorded_snapshot"):
        item["recorded_snapshot"] = _dump(target_snapshot(conn, current_user_id, table, target_id))
    return True


def reconcile_recorded(conn, current_user_id, row, item, entry_type, account_id, card_id):
    """A transacao da Pluggy e o movimento que uma notificacao ja gravou
    sozinha. Nunca vira um segundo lancamento:

    - intocado e o banco concorda: a transacao passa a ser a fonte do
      lancamento (origem OPEN_FINANCE, o snapshot), e o que o banco mudar
      depois corrige como no gravado pela Pluggy (apply_change/apply_vanish);
    - intocado e o banco diz outra data ou conta/cartao: o lancamento sai e o
      item volta a esperar com o que o banco diz; a passada da Pluggy logo
      depois do pull o grava de novo, a revisar;
    - editado pelo dono (ou uma transferencia): so liga (MATCHED); a
      Conferencia aponta o que nao bater.

    "Intocado" e o snapshot (Fase 4): o "e meu" sem mudar nada nao conta como
    toque, e a revisao que saiu sozinha (settle_review) tambem nao.
    """
    table, target_id = item["target_table"], item["target_id"]
    if item["entry_type"] == "TRANSFER":
        follow_bank_side(conn, current_user_id, row, item, account_id)
    if item["entry_type"] == "TRANSFER" or not notification_untouched(conn, current_user_id, item):
        _update_row(
            conn, current_user_id, row["id"], role="MATCHED", item_id=item["id"],
            target_table=table, target_id=target_id,
        )
        if item["entry_type"] == "TRANSFER":
            inbox.settle_transfer_review(conn, current_user_id, item["id"])
        return "matched"
    if bank_disagrees(item, row, entry_type, account_id, card_id):
        _drop_target(conn, current_user_id, item)
        _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"], target_table=None, target_id=None)
        changes = {
            "state": inbox.PENDING, "target_table": None, "target_id": None, "decided_at": None,
            "auto_recorded_at": None, "recorded_snapshot": None, "occurred_at": row["occurred_at"] or row["date"],
            "client_key": row["dedup_key"],
            "guessed": [guess for guess in item.get("guessed") or [] if guess not in ("card", "account")],
        }
        if entry_type == "CARD":
            changes.update({"entry_type": "CARD", "card_id": card_id, "account_id": None})
        else:
            changes.update({"entry_type": entry_type, "account_id": account_id, "card_id": None})
        if changes["entry_type"] != item["entry_type"]:
            changes["category"], changes["category_id"] = category_for_row(
                conn, current_user_id, row, changes["entry_type"], item["amount"], changes["account_id"],
            )
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, current_user_id, item, changes)
        return "merged"
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"], target_table=table, target_id=target_id)
    if table == "transactions":
        conn.execute(
            "UPDATE transactions SET source_type = ?, source_id = ? WHERE id = ? AND user_id = ? AND source_type IS NULL",
            (OPEN_FINANCE_SOURCE_TYPE, row["pluggy_transaction_id"], target_id, current_user_id),
        )
    else:
        conn.execute(
            """
            UPDATE cc_expenses SET client_id = ?
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (row["dedup_key"], current_user_id, target_id, current_user_id),
        )
    mark_auto_recorded(conn, current_user_id, item["id"], table, target_id)
    settle_review(conn, current_user_id, item, row, entry_type, account_id)
    return "matched"


def new_item_for_row(conn, current_user_id, row, account=None, rules=None):
    """Abre um item so desta transacao (tambem o "nao e a mesma" do split)."""
    row = row_to_dict(row) if not isinstance(row, dict) else row
    if account is None:
        account = fetch_account(conn, current_user_id, row["of_account_id"])
    entry_type = _entry_type(account, row["direction"])
    direction = row["direction"]
    account_id = account["account_id"] if entry_type != "CARD" else None
    card_id = account["card_id"] if entry_type == "CARD" else None
    cents = int(row["amount_cents"])
    amount = money.from_cents(cents)
    candidates = inbox.existing_rows(
        conn, current_user_id, entry_type=entry_type, direction=direction, cents=cents, date_text=row["date"],
        account_id=account_id, card_id=card_id, claimed_by=inbox.CLAIM_PLUGGY,
    )
    installments = int(row["total_installments"] or 1) if entry_type == "CARD" and direction == "OUT" else 1
    values = {
        "reason": "several_candidates" if len(candidates) > 1 else ("possible_duplicate" if candidates else "new"),
        "entry_type": entry_type,
        "direction": direction,
        "amount": amount,
        "currency": row["currency"],
        "installments": installments,
        "occurred_at": row["occurred_at"],
        "description": display_name(
            row["description"], row.get("merchant_name"), row.get("counterparty"), row["movement"], direction,
        ),
        "account_id": account_id,
        "card_id": card_id,
        "transfer_account_id": None,
        "guessed": [],
        "candidates": candidates,
        "client_key": row["dedup_key"],
    }
    if entry_type == "CARD" and direction == "IN":
        # Estorno (033): a categoria "Estorno", e nunca a ocorrencia de uma
        # recorrencia de despesa.
        values["category"] = "Estorno"
        values["category_id"] = category_id_for_name(conn, current_user_id, "Estorno")
        values["recurring_off"] = 1
    elif entry_type != "CARD" and row["movement"] in ("TRANSFER", "SELF_TRANSFER"):
        hint = inbox.remembered_transfer(
            conn, current_user_id, account_id=account_id, direction=direction, description=row["description"],
        )
        to_global = global_account.destination_for_row(conn, current_user_id, row, account_id) is not None
        own = to_global or hint is not None or row["movement"] == "SELF_TRANSFER" or _is_self(conn, current_user_id, row)
        if own:
            # Para a conta global, o destino so entra com a ponta em dolar
            # (_place_cross_currency): ate la a transferencia espera.
            other = hint["transfer_account_id"] if hint and not to_global else None
            origin, destination = (account_id, other) if direction == "OUT" else (other, account_id)
            values.update({
                "entry_type": "TRANSFER",
                "direction": "OUT",
                "account_id": origin,
                "transfer_account_id": destination,
                "reason": "own_transfer" if values["reason"] == "new" else values["reason"],
                "description": inbox._transfer_description(conn, current_user_id, origin, destination, row["description"]),
            })
        elif (row["counterparty"] or row["counterparty_doc"]) and values["reason"] == "new":
            values["reason"] = "external_transfer"
    if (row["currency"] or "BRL") != "BRL" and account_id and (
        global_account.account_currency(conn, current_user_id, account_id) == row["currency"]
    ):
        # A conta global: o valor ja e o da conta, nada a converter.
        values["edited"] = ["amount"]
    if "category" not in values:
        values["category"], values["category_id"] = category_for_row(
            conn, current_user_id, row, values["entry_type"], amount, values["account_id"], rules,
        )
    values["needs"] = inbox.recompute_needs(values)
    item_id = inbox.insert_item(conn, current_user_id, values)
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item_id, target_table=None, target_id=None)
    return item_id


def _first_active_category(conn, current_user_id, names, transaction_type):
    """(nome, id) do primeiro nome que o dono tem ativo, ou None."""
    for name in names:
        if expected_type(name) != transaction_type:
            continue
        category_id = category_id_for_name(conn, current_user_id, name)
        category = fetch_category(conn, current_user_id, category_id) if category_id else None
        if category and not category["archived_at"]:
            return name, category_id
    return None


CONFIDENT_CATEGORY_SOURCES = ("rule", "merchant", "cnae")


def category_decision(conn, current_user_id, row, entry_type, amount, account_id=None, rules=None):
    """(nome, id, de onde veio): a regra do dono (`rule`), a tabela de
    comerciantes (`merchant`), o CNAE (`cnae`), a categoria da Pluggy (`pluggy`),
    a padrao (`default`). Os tres primeiros dizem o que a compra e
    (CONFIDENT_CATEGORY_SOURCES); os outros sao palpites largos."""
    if entry_type == "TRANSFER":
        return inbox.TRANSFER_CATEGORY, None, "transfer"
    transaction_type = "INCOME" if entry_type == "INCOME" else "EXPENSE"
    if rules is None:
        rules = import_rules_for_matching(conn, current_user_id)
    merchant = row.get("merchant_name")
    named = display_name(row.get("description"))
    for text in dict.fromkeys(filter(None, (row.get("description"), merchant, named))):
        rule = statement_import.first_matching_rule(
            rules, text, transaction_type, amount, account_id if entry_type != "CARD" else None,
        )
        if rule:
            return rule["category"], rule["category_id"], "rule"
    if transaction_type == "EXPENSE":
        found = _first_active_category(
            conn, current_user_id, keyword_categories(merchant, row.get("counterparty"), named), transaction_type,
        )
        if found:
            return (*found, "merchant")
        found = _first_active_category(conn, current_user_id, cnae_categories(row.get("merchant_cnae")), transaction_type)
        if found:
            return (*found, "cnae")
    found = _first_active_category(
        conn, current_user_id, pluggy_category_names(row.get("pluggy_category_id")), transaction_type,
    )
    if found:
        return (*found, "pluggy")
    return (*inbox.suggest_category(conn, current_user_id, None, entry_type, amount, account_id, rules=[]), "default")


def category_for_row(conn, current_user_id, row, entry_type, amount, account_id=None, rules=None):
    """(nome, id) de category_decision()."""
    return category_decision(conn, current_user_id, row, entry_type, amount, account_id, rules)[:2]


# "Automatic investment" da Pluggy (03010000): a aplicacao automatica que o
# banco faz sozinho, como o texto de inbox.is_auto_invest().
AUTO_INVEST_CATEGORY_PREFIX = "0301"
FIXED_INCOME_CATEGORY_PREFIX = "0302"

# No caixa da corretora a Pluggy chama de "Same person transfer" tambem a
# compra e a venda de renda fixa, o IR e o IOF (BTG, 2026-10-28): so a
# transferencia de verdade e aporte/resgate; o resto e da carteira.
BROKER_TRANSFER_TEXT = re.compile(r"\b(transferencia|pix|ted|doc|tef)\b")
SOLD_INVESTMENT_TEXT = re.compile(r"\bvend")


def mark_bank_investments(conn, current_user_id):
    """Aplicacao e resgate num fundo do banco (Pluggy 03020000, RF High, Tesouro
    Reserva): saiu ou voltou do saldo como aporte/resgate, nunca despesa ou receita.
    Nao ha o que revisar. Idempotente: roda depois de gravar o pull."""
    conn.execute(
        f"""
        UPDATE transactions SET source_type = ?, needs_review = 0
        WHERE user_id = ? AND source_type = ? AND type IN ('EXPENSE', 'INCOME')
          AND id IN (
              SELECT o.target_id FROM open_finance_transactions o
              WHERE o.user_id = ? AND o.target_table = 'transactions' AND o.role <> 'REMOVED'
                AND o.pluggy_category_id LIKE '{FIXED_INCOME_CATEGORY_PREFIX}%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM accounts a WHERE a.id = transactions.account_id AND a.type = 'BROKERAGE'
          )
        """,
        (BANK_INVESTMENT_SOURCE_TYPE, current_user_id, OPEN_FINANCE_SOURCE_TYPE, current_user_id),
    )


def is_auto_invest_row(row):
    return inbox.is_auto_invest(row["description"]) or str(row["pluggy_category_id"] or "").startswith(
        AUTO_INVEST_CATEGORY_PREFIX
    )


def is_broker_transfer(row):
    """Uma linha do caixa da corretora que e transferencia com o dono."""
    return row["movement"] in ("TRANSFER", "SELF_TRANSFER") and bool(
        BROKER_TRANSFER_TEXT.search(inbox.normalized(row["description"]))
    )


def is_brokerage(conn, current_user_id, account_id):
    if not account_id:
        return False
    row = conn.execute(
        "SELECT type FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    return bool(row) and row["type"] == "BROKERAGE"


def invoice_payment_link(conn, current_user_id, row, account):
    """O pagamento de fatura que o app ja tem para esta saida do banco (o
    pay-invoice ou o debito automatico, na conta mapeada, mesmo valor, ate
    INVOICE_PAYMENT_LINK_DAYS dias) e que nenhuma outra transacao explica.
    No banco que arredonda (inbox.ROUNDS_UP_ISSUERS), o valor que arredonda
    para o do banco tambem."""
    if row["direction"] != "OUT" or not account["account_id"]:
        return None
    kinds = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    cents = int(row["amount_cents"])
    lowest = cents - 99 if inbox.open_finance_rounds_up(conn, current_user_id, account["id"]) and cents % 100 == 0 else cents
    found = conn.execute(
        f"""
        SELECT t.id, t.date, CAST(ROUND(t.amount * 100) AS INTEGER) AS cents FROM transactions t
        WHERE t.user_id = ? AND t.account_id = ? AND t.source_type IN ({', '.join('?' for _ in kinds)})
          AND CAST(ROUND(t.amount * 100) AS INTEGER) BETWEEN ? AND ? AND t.date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                AND o.id <> ? AND o.role <> 'REMOVED'
          )
        """,
        (
            current_user_id, account["account_id"], *kinds, lowest, cents,
            inbox._shift(row["date"], -INVOICE_PAYMENT_LINK_DAYS), inbox._shift(row["date"], INVOICE_PAYMENT_LINK_DAYS),
            row["id"],
        ),
    ).fetchall()
    found = sorted(
        found,
        key=lambda entry: (entry["cents"] != cents, inbox._date_gap(entry["date"], row["date"]), entry["date"], entry["id"]),
    )
    return found[0]["id"] if found else None


def _is_self(conn, current_user_id, row):
    """O outro lado e o proprio dono, aprendido no Aprovar (031): pelo
    documento quando a Pluggy o da; pelo nome so sem documento."""
    if row["counterparty_doc"]:
        return inbox.fetch_hint(conn, current_user_id, inbox.SELF_DOC_PREFIX + row["counterparty_doc"]) is not None
    name = inbox.normalized(row["counterparty"])
    return bool(name) and inbox.fetch_hint(conn, current_user_id, inbox.SELF_NAME_PREFIX + name) is not None


def vanish(conn, current_user_id, row, reason="vanished"):
    """A transacao sumiu da Pluggy (ou mudou de valor) antes da aprovacao: a
    linha sai e, sem outra fonte viva, o item tambem (REMOVED) — o mesmo que o
    Aprovar faz com a compra que o banco negou. Um item ja decidido fica."""
    item_id = row.get("item_id")
    if item_id and not _item_pending(conn, current_user_id, row):
        return False
    _update_row(conn, current_user_id, row["id"], role="REMOVED")
    if not item_id:
        return True
    item_row = inbox.fetch_item(conn, current_user_id, item_id)
    if item_row and item_row["state"] == inbox.PENDING and not inbox._has_detection_source(conn, current_user_id, item_id):
        inbox.save_item(
            conn, current_user_id, inbox.item_dict(item_row),
            {"state": inbox.REMOVED, "reason": reason, "decided_at": utc_timestamp()},
        )
    return True


def _broker_line(row):
    return row["role"] == "MATCHED" and str(row.get("target_id") or "").startswith(broker_statement.ID_PREFIX)


def missing_rows(conn, current_user_id, account, seen_ids, date_from, date_to):
    """As transacoes vivas desta conta na janela do pull que a Pluggy nao
    devolveu (sem gravar nada): SOURCE e UNMAPPED, MATCHED e PAIRED (que antes
    ficavam vivas para sempre, a raiz do defeito A) e a linha do caixa da
    corretora. Fora: COVERED e INVOICE_PAYMENT (`_kept_payment()` ja liga o
    pagamento que voltou com outra id)."""
    rows = conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND date BETWEEN ? AND ?
          AND role IN ('SOURCE', 'UNMAPPED', 'MATCHED', 'PAIRED')
        ORDER BY date, created_at, id
        """,
        (current_user_id, account["id"], date_from, date_to),
    ).fetchall()
    return [row_to_dict(row) for row in rows if row["pluggy_transaction_id"] not in seen_ids]


def vanish_rows(conn, current_user_id, rows, seen_ids):
    """Some o que ficou de `missing_rows()` sem sucessora. Um pull que voltou
    vazio (`seen_ids` vazio) nao some nada gravado: pode ser a Pluggy, nao o
    banco. Devolve quantas sairam."""
    count = 0
    for row in rows:
        fresh = _by_id(conn, current_user_id, row["id"])
        if fresh is None or fresh["role"] == "REMOVED":
            continue
        row = row_to_dict(fresh)
        if _broker_line(row):
            if seen_ids:
                broker_statement.remove_line(conn, current_user_id, row)
                _update_row(conn, current_user_id, row["id"], role="REMOVED", target_table=None, target_id=None)
                count += 1
            continue
        if row["role"] in ("MATCHED", "PAIRED"):
            # So ligada (o lancamento e de outra fonte): sem sucessora, a ligacao
            # deixa de valer, e a Conferencia mostra.
            if seen_ids and row.get("conflict") != "vanished":
                _flag(conn, current_user_id, row, "vanished")
            continue
        if row["auto_recorded_at"] and not _item_pending(conn, current_user_id, row):
            if seen_ids and apply_vanish(conn, current_user_id, row) == "removed":
                count += 1
            continue
        if vanish(conn, current_user_id, row):
            count += 1
    return count


def vanish_missing(conn, current_user_id, account, seen_ids, date_from, date_to):
    """Depois de um pull de [date_from, date_to], sem sucessao: o que a Pluggy
    nao devolveu mais nessa janela, sumiu (vanish_rows)."""
    return vanish_rows(
        conn, current_user_id, missing_rows(conn, current_user_id, account, seen_ids, date_from, date_to), seen_ids,
    )


# ---------------------------------------------------------------------------
# Sucessao: a pendente que liquida com outra id
# ---------------------------------------------------------------------------

SUCCESSION_DAYS = 3


def _same_amount(old_cents, new_cents, rounds_up):
    old_cents, new_cents = int(old_cents), int(new_cents)
    if old_cents == new_cents:
        return True
    return rounds_up and (inbox.rounded_up(old_cents, new_cents) or inbox.rounded_up(new_cents, old_cents))


def successor_for(conn, current_user_id, account, tx, missing, pulled=None):
    """A transacao sumida deste pull que `tx` (id nova) continua: mesma conta e
    direcao, mesmo valor (ou o arredondado do BB), mesma parcela, ate
    SUCCESSION_DAYS dias. Uma por uma: a escolhida sai de `missing`. Empate: a
    mesma descricao, a data mais perto, a mais antiga."""
    if not missing:
        return None
    rounds_up = inbox.open_finance_rounds_up(conn, current_user_id, account["id"])
    found = [
        row for row in missing
        if row["of_account_id"] == account["id"] and row["direction"] == tx["direction"]
        and not _broker_line(row)
        and _same_amount(row["amount_cents"], tx["amount_cents"], rounds_up)
        and (row["installment_number"] or 1) == (tx["installment_number"] or 1)
        and (row["total_installments"] or 1) == (tx["total_installments"] or 1)
        and inbox._date_gap(row["date"], tx["date"]) <= SUCCESSION_DAYS
    ]
    if not found:
        return _near_successor(conn, current_user_id, account, tx, missing, pulled)
    wanted = plain_text(tx["description"] or "")
    best = sorted(found, key=lambda row: (
        plain_text(row["description"] or "") != wanted, inbox._date_gap(row["date"], tx["date"]),
        row["created_at"] or "", row["id"],
    ))[0]
    missing.remove(best)
    return best


def _purchase_like(row):
    return (
        not row.get("movement") and row["direction"] == "OUT"
        and (row.get("total_installments") or 1) == 1 and (row.get("installment_number") or 1) == 1
    )


def _near_twin(old, tx):
    """A sumida e a nova sao a mesma compra com outro valor (a gorjeta, a
    pre-autorizacao que fechou): compras a vista, mesma loja, na faixa, ate
    SUCCESSION_DAYS dias."""
    if not (_purchase_like(old) and _purchase_like(tx)) or old["direction"] != tx["direction"]:
        return False
    if inbox._date_gap(old["date"], tx["date"]) > SUCCESSION_DAYS:
        return False
    international = bool(old.get("original_currency") or tx.get("original_currency"))
    if not inbox.near_amount(old["amount_cents"], tx["amount_cents"], international):
        return False
    return any(
        inbox.merchant_agrees(name, tx.get("merchant_name"), tx.get("description"))
        for name in (old.get("merchant_name"), old.get("description")) if name
    )


def _near_successor(conn, current_user_id, account, tx, missing, pulled):
    """Sem sucessora exata: a unica sumida que e a mesma compra com outro valor,
    e a nova a unica deste pull para ela (um de cada lado)."""
    found = [
        row for row in missing
        if row["of_account_id"] == account["id"] and not _broker_line(row) and _near_twin(row, tx)
    ]
    if len(found) != 1:
        return None
    old = found[0]
    rivals = [
        other for other in (pulled or [])
        if other["dedup_key"] != tx["dedup_key"] and _near_twin(old, other)
    ]
    if rivals:
        return None
    missing.remove(old)
    return old


def follow_bank_amount(conn, current_user_id, item, bank_cents, snapshot_text=None):
    """O banco lancou a mesma compra com outro valor: o valor do
    banco entra no lancamento, revisado ou com outra categoria, salvo se o dono
    digitou o valor (o de agora nao e o com que ele nasceu). Na compra no cartao,
    so a de uma linha em aberto. Devolve True se o lancamento esta no valor do
    banco; False se o dono manda (so ligar, e a Conferencia aponta)."""
    table, target_id = item.get("target_table"), item.get("target_id")
    if not table or not target_id:
        return False
    recorded = snapshot_amount_cents(snapshot_text or item.get("recorded_snapshot"), table)
    if table == "transactions":
        current = conn.execute(
            "SELECT amount FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        rows = [current] if current else []
    else:
        rows = conn.execute(
            """
            SELECT id, amount, status FROM cc_expenses
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (current_user_id, target_id, current_user_id),
        ).fetchall()
        if len(rows) != 1 or rows[0]["status"] != "OPEN":
            return False
    if not rows or recorded is None or money.to_cents(rows[0]["amount"]) != int(recorded):
        return False
    if int(recorded) == int(bank_cents):
        return True
    amount = money.from_cents(bank_cents)
    if table == "transactions":
        conn.execute("UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?", (amount, target_id, current_user_id))
    else:
        conn.execute("UPDATE cc_expenses SET amount = ? WHERE id = ? AND user_id = ?", (amount, rows[0]["id"], current_user_id))
    inbox.save_item(conn, current_user_id, item, {"amount": amount})
    refresh_snapshots(conn, current_user_id, item["id"], table, target_id)
    item["recorded_snapshot"] = _dump(target_snapshot(conn, current_user_id, table, target_id))
    return True


def follow_after_succession(conn, current_user_id, row, tx):
    """A sucessora tem outro valor (sucessao aproximada): o lancamento segue o
    banco pela regra de follow_bank_amount(); o dono digitou, `conflict`."""
    row = row_to_dict(row)
    if not row.get("item_id"):
        return
    item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
    if not item_row:
        return
    item = inbox.item_dict(item_row)
    if item["state"] == inbox.PENDING:
        inbox.save_item(conn, current_user_id, item, {"amount": money.from_cents(tx["amount_cents"])})
        return
    if not follow_bank_amount(conn, current_user_id, item, tx["amount_cents"], row.get("recorded_snapshot")):
        _flag(conn, current_user_id, row, "changed", tx["amount_cents"])


# ---------------------------------------------------------------------------
# O par aproximado no pull
# ---------------------------------------------------------------------------

def pending_pluggy_items(conn, current_user_id):
    """Os itens pendentes que a Pluggy alimenta (para saber os novos do pull)."""
    return {
        row["id"] for row in conn.execute(
            """
            SELECT DISTINCT i.id FROM inbox_items i
            JOIN open_finance_transactions o ON o.item_id = i.id AND o.user_id = i.user_id AND o.role = 'SOURCE'
            WHERE i.user_id = ? AND i.state = 'PENDING'
            """,
            (current_user_id,),
        ).fetchall()
    }


def near_match_pass(conn, current_user_id, before):
    """Depois do ingest do pull e antes de gravar (record_pending): as compras
    da Pluggy que abriram item novo neste pull, sem par exato, procuram a
    notificacao da mesma compra com outro valor. So o par unico de cada lado.
    `before`: pending_pluggy_items() de antes do pull. Devolve quantos juntou."""
    leftovers = []
    for item_id in sorted(pending_pluggy_items(conn, current_user_id) - before):
        if inbox._has_notification_source(conn, current_user_id, item_id):
            continue
        sources = inbox.open_finance_sources(conn, current_user_id, item_id, roles=(inbox.SOURCE,))
        if len(sources) != 1:
            continue
        leftovers.append(row_to_dict(sources[0]))
    pairs = {row["id"]: inbox.near_notification_items(conn, current_user_id, row) for row in leftovers}
    wanted = {}
    for found in pairs.values():
        for item_row in found:
            wanted[item_row["id"]] = wanted.get(item_row["id"], 0) + 1
    joined = 0
    for row in leftovers:
        found = pairs[row["id"]]
        if len(found) != 1 or wanted[found[0]["id"]] != 1:
            continue
        near_join(conn, current_user_id, row, found[0])
        joined += 1
    return joined


def near_join(conn, current_user_id, row, notification_row):
    """A transacao da Pluggy e a compra que a notificacao trouxe com outro
    valor: o item da Pluggy sai (REMOVED, near_match), a transacao entra no da
    notificacao e o valor do banco fica, salvo o que o dono digitou."""
    entry_type, account_id, card_id = inbox.row_target(conn, current_user_id, row)
    own_item = row.get("item_id")
    if own_item:
        own = inbox.fetch_item(conn, current_user_id, own_item)
        if own and own["state"] == inbox.PENDING:
            inbox.save_item(conn, current_user_id, inbox.item_dict(own), {
                "state": inbox.REMOVED, "reason": "near_match", "decided_at": utc_timestamp(),
            })
    item = inbox.item_dict(notification_row)
    bank_cents = int(row["amount_cents"])
    if item["state"] == inbox.PENDING:
        inbox.save_item(conn, current_user_id, item, {"amount": money.from_cents(bank_cents)})
        return _join_item(conn, current_user_id, row, item, entry_type, account_id, card_id)
    if item["state"] == inbox.DENIED:
        return _join_item(conn, current_user_id, row, item, entry_type, account_id, card_id)
    if not follow_bank_amount(conn, current_user_id, item, bank_cents):
        _update_row(
            conn, current_user_id, row["id"], role="MATCHED", item_id=item["id"],
            target_table=item.get("target_table"), target_id=item.get("target_id"),
        )
        _flag(conn, current_user_id, row, "changed", bank_cents)
        return "matched"
    if (
        item.get("auto_recorded_at") and item.get("target_table") == "transactions"
        and inbox.date_of(item["occurred_at"]) != row["date"]
        and not bank_disagrees({**item, "occurred_at": row["date"]}, row, entry_type, account_id, card_id)
        and notification_untouched(conn, current_user_id, item)
    ):
        # A compra internacional que o banco lista dias depois: a linha fica a
        # mesma (comprovante, revisao), so a data passa a ser a do banco.
        occurred = row["occurred_at"] or row["date"]
        conn.execute(
            "UPDATE transactions SET date = ?, occurred_at = ? WHERE id = ? AND user_id = ?",
            (row["date"], occurred, item["target_id"], current_user_id),
        )
        inbox.save_item(conn, current_user_id, item, {"occurred_at": occurred})
        refresh_snapshots(conn, current_user_id, item["id"], "transactions", item["target_id"])
        item["recorded_snapshot"] = _dump(target_snapshot(conn, current_user_id, "transactions", item["target_id"]))
    return _join_item(conn, current_user_id, row, item, entry_type, account_id, card_id)


def hand_over(conn, current_user_id, old, tx, account, seen_at=None):
    """A id nova assume o lugar da sumida, no lugar: papel, item, lancamento e
    snapshot. Nada e apagado; a velha fica REMOVED com `superseded_by`. O
    lancamento que era desta transacao (origem OPEN_FINANCE/BANK_INVESTMENT, o
    client_id da compra) passa a ser da nova; um digitado ou gravado pela
    notificacao fica como esta. Devolve "succeeded"."""
    seen_at = seen_at or utc_timestamp()
    table, target_id = old.get("target_table"), old.get("target_id")
    # Antes de mudar a origem: a data so anda no lancamento intocado e desta transacao.
    movable = (
        table == "transactions" and old["date"] != tx["date"]
        and untouched(conn, current_user_id, old) and own_target(conn, current_user_id, old)
    )
    row_id = new_id()
    values = {
        "id": row_id, "user_id": current_user_id, "of_account_id": account["id"], "role": old["role"],
        "item_id": old.get("item_id"), "target_table": table, "target_id": target_id,
        "auto_recorded_at": old.get("auto_recorded_at"), "recorded_snapshot": old.get("recorded_snapshot"),
        "last_seen_at": seen_at,
    }
    values.update({field: tx[field] for field in ROW_FIELDS})
    conn.execute(
        f"INSERT INTO open_finance_transactions ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )
    _update_row(
        conn, current_user_id, old["id"], role="REMOVED", superseded_by=row_id, item_id=None, target_table=None,
        target_id=None, conflict=None, conflict_amount_cents=None,
    )
    if table == "transactions" and target_id:
        conn.execute(
            f"""
            UPDATE transactions SET source_id = ?
            WHERE id = ? AND user_id = ? AND source_type IN (?, ?) AND source_id = ?
            """,
            (tx["pluggy_transaction_id"], target_id, current_user_id, OPEN_FINANCE_SOURCE_TYPE,
             BANK_INVESTMENT_SOURCE_TYPE, old["pluggy_transaction_id"]),
        )
        conn.execute(
            "UPDATE transactions SET client_id = ? WHERE id = ? AND user_id = ? AND client_id = ?",
            (tx["dedup_key"], target_id, current_user_id, old["dedup_key"]),
        )
    # A compra no cartao e o client_id (035): todas as parcelas; comprovante e
    # divisao vao junto (pendurados no id da parcela e no client_id).
    conn.execute(
        "UPDATE cc_expenses SET client_id = ? WHERE user_id = ? AND client_id = ?",
        (tx["dedup_key"], current_user_id, old["dedup_key"]),
    )
    conn.execute(
        "UPDATE inbox_items SET client_key = ? WHERE user_id = ? AND client_key = ?",
        (tx["dedup_key"], current_user_id, old["dedup_key"]),
    )
    if movable:
        conn.execute(
            "UPDATE transactions SET date = ?, occurred_at = ? WHERE id = ? AND user_id = ?",
            (tx["date"], tx["occurred_at"] or tx["date"], target_id, current_user_id),
        )
        if old.get("item_id"):
            conn.execute(
                "UPDATE inbox_items SET occurred_at = ? WHERE id = ? AND user_id = ?",
                (tx["occurred_at"] or tx["date"], old["item_id"], current_user_id),
            )
        refresh_snapshots(conn, current_user_id, old.get("item_id"), table, target_id)
    return "succeeded"


# ---------------------------------------------------------------------------
# O que foi gravado sozinho (044): como nasceu, e a guarda de mudanca
# ---------------------------------------------------------------------------

# O snapshot (como o lancamento nasceu) mora em services/recorded_snapshot.py,
# reexportado aqui: TRANSACTION_SNAPSHOT_COLUMNS, CARD_SNAPSHOT_COLUMNS,
# target_snapshot, _dump, mark_auto_recorded, untouched.


def own_target(conn, current_user_id, row):
    """O lancamento foi gravado por esta transacao (nunca um digitado pelo dono
    que ela so ligou): a origem dele e ela."""
    if row.get("target_table") == "transactions":
        target = conn.execute(
            "SELECT source_type, source_id FROM transactions WHERE id = ? AND user_id = ?",
            (row["target_id"], current_user_id),
        ).fetchone()
        return bool(target) and target["source_id"] == row["pluggy_transaction_id"] and target["source_type"] in (
            OPEN_FINANCE_SOURCE_TYPE, BANK_INVESTMENT_SOURCE_TYPE,
        )
    if row.get("target_table") == "cc_expenses":
        target = conn.execute(
            "SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id),
        ).fetchone()
        return bool(target) and target["client_id"] == row["dedup_key"]
    return False


def _flag(conn, current_user_id, row, conflict, cents=None):
    _update_row(conn, current_user_id, row["id"], conflict=conflict, conflict_amount_cents=cents)
    return "conflict"


def apply_change(conn, current_user_id, row, tx):
    """O banco mudou o valor de uma transacao ja decidida. Gravada sozinha,
    intocada, na mesma direcao e de uma linha so (um lancamento, ou uma compra
    1/1 em aberto): o lancamento acompanha. Senao nada muda e a Conferencia
    aponta (`conflict = 'changed'`)."""
    if (
        tx["direction"] != row["direction"]
        or not untouched(conn, current_user_id, row)
        or not own_target(conn, current_user_id, row)
    ):
        return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
    amount = money.from_cents(tx["amount_cents"])
    if row["target_table"] == "transactions":
        conn.execute(
            "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
            (amount, row["target_id"], current_user_id),
        )
    else:
        rows = conn.execute(
            "SELECT id, status FROM cc_expenses WHERE user_id = ? AND client_id = ?",
            (current_user_id, row["dedup_key"]),
        ).fetchall()
        if len(rows) != 1 or rows[0]["status"] != "OPEN":
            return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
        conn.execute(
            "UPDATE cc_expenses SET amount = ? WHERE id = ? AND user_id = ?", (amount, rows[0]["id"], current_user_id),
        )
    if row.get("item_id"):
        item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item_row:
            inbox.save_item(conn, current_user_id, inbox.item_dict(item_row), {"amount": amount})
    _update_row(
        conn, current_user_id, row["id"], conflict=None, conflict_amount_cents=None,
        recorded_snapshot=_dump(target_snapshot(conn, current_user_id, row["target_table"], row["target_id"])),
        **{field: tx[field] for field in ROW_FIELDS if field != "dedup_key"},
    )
    # O app mudou o lancamento (nao o dono): o snapshot do item (notificacao)
    # e o das outras fontes tambem, ou o proximo ajuste do banco pararia.
    refresh_snapshots(conn, current_user_id, row.get("item_id"), row["target_table"], row["target_id"])
    return "corrected"


def apply_payment_change(conn, current_user_id, row, tx):
    """O banco mudou o valor de um pagamento de fatura ja gravado: nunca um
    segundo pagamento. O que esta transacao gravou acompanha; o pagamento feito no
    app (so ligado) fica como esta, apontado na Conferencia."""
    target = conn.execute(
        "SELECT source_type, source_id FROM transactions WHERE id = ? AND user_id = ?",
        (row["target_id"], current_user_id),
    ).fetchone()
    mine = (
        target and tx["direction"] == row["direction"] and target["source_type"] in INVOICE_PAYMENT_SOURCE_TYPES
        and str(target["source_id"] or "").endswith(str(row["pluggy_transaction_id"]))
    )
    if not mine:
        return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
    conn.execute(
        "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
        (money.from_cents(tx["amount_cents"]), row["target_id"], current_user_id),
    )
    _update_row(
        conn, current_user_id, row["id"], conflict=None, conflict_amount_cents=None,
        **{field: tx[field] for field in ROW_FIELDS if field != "dedup_key"},
    )
    return "corrected"


def apply_vanish(conn, current_user_id, row):
    """A transacao gravada sozinha sumiu do banco. Intocada e de quem ela
    gravou — nunca um digitado, nunca uma transferencia, nunca uma compra com
    parcela ja paga: o lancamento sai. Senao fica (`conflict = 'vanished'`)."""
    if row.get("conflict") == "vanished":
        return "conflict"
    removable = untouched(conn, current_user_id, row) and own_target(conn, current_user_id, row)
    if removable and row["target_table"] == "transactions":
        kind = conn.execute(
            "SELECT type FROM transactions WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id),
        ).fetchone()
        removable = bool(kind) and kind["type"] != "TRANSFER"
    if removable and row["target_table"] == "cc_expenses":
        removable = not conn.execute(
            "SELECT 1 FROM cc_expenses WHERE user_id = ? AND client_id = ? AND status <> 'OPEN'",
            (current_user_id, row["dedup_key"]),
        ).fetchone()
    if not removable:
        return _flag(conn, current_user_id, row, "vanished")
    # A ocorrencia de recorrencia que a aprovacao deu volta a ficar em aberto.
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, row["target_table"], row["target_id"]),
    )
    if row["target_table"] == "transactions":
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id))
    else:
        conn.execute("DELETE FROM cc_expenses WHERE user_id = ? AND client_id = ?", (current_user_id, row["dedup_key"]))
    _update_row(conn, current_user_id, row["id"], role="REMOVED", target_table=None, target_id=None)
    if row.get("item_id"):
        item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item_row:
            inbox.save_item(
                conn, current_user_id, inbox.item_dict(item_row),
                {"state": inbox.REMOVED, "reason": "vanished", "target_table": None, "target_id": None,
                 "decided_at": utc_timestamp()},
            )
    return "removed"


def _months_back(date_text, months):
    year, month, day = (int(part) for part in date_text[:10].split("-"))
    index = year * 12 + (month - 1) - months
    year, month = index // 12, index % 12 + 1
    return f"{year:04d}-{month:02d}-{min(day, calendar.monthrange(year, month)[1]):02d}"


def _installment_cents(row):
    count = int(row["total_installments"])
    return int(row["amount_cents"]) // count if (row["installment_number"] or 1) == 1 else int(row["amount_cents"])


def adopt_orphan_installments(conn, current_user_id, account, rules=None):
    """No historico, as parcelas de uma compra feita antes do que a Pluggy
    guarda: a parcela 1 nunca chega e parcela 2..n e COVERED, entao a compra
    sumiria (com as parcelas que ainda vao vencer). A menor parcela vista vira o
    item da compra inteira, parcela x n, na data da compra; o valor gravado na
    linha da Pluggy nao muda (o proximo pull compara com ele). Devolve quantas."""
    if account["type"] != "CREDIT":
        return 0
    rows = [row_to_dict(row) for row in conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND direction = 'OUT' AND total_installments > 1
          AND role <> 'REMOVED'
        ORDER BY date, posted_on, id
        """,
        (current_user_id, account["id"]),
    ).fetchall()]
    purchases = {}
    for row in rows:
        count = int(row["total_installments"])
        group = purchases.setdefault((plain_text(display_name(row["description"])), count), [])
        cents = _installment_cents(row)
        series = next((entry for entry in group if abs(entry["cents"] - cents) <= count), None)
        if series is None:
            series = {"cents": cents, "rows": []}
            group.append(series)
        series["rows"].append(row)
    adopted = 0
    for group in purchases.values():
        for series in group:
            members = series["rows"]
            if any((row["installment_number"] or 1) == 1 or row["role"] != "COVERED" for row in members):
                continue
            lowest = min(row["installment_number"] for row in members)
            for row in members:
                if row["installment_number"] != lowest:
                    continue
                date_text = row["date"]
                if row.get("posted_on") in (None, date_text):
                    # O conector nao mandou a data da compra: a parcela k caiu
                    # k-1 meses depois da primeira.
                    date_text = _months_back(date_text, lowest - 1)
                draft = {**row, "date": date_text, "occurred_at": date_text, "installment_number": 1,
                         "amount_cents": int(row["amount_cents"]) * int(row["total_installments"])}
                new_item_for_row(conn, current_user_id, draft, account, rules)
                adopted += 1
    return adopted


def place_unmapped(conn, current_user_id, account, rules=None):
    """Mapeada a conta, o que ja foi puxado sem mapeamento entra no Aprovar."""
    rows = conn.execute(
        "SELECT * FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND role = 'UNMAPPED'"
        " ORDER BY date, created_at, id",
        (current_user_id, account["id"]),
    ).fetchall()
    return [place(conn, current_user_id, row_to_dict(row), account, rules) for row in rows]
