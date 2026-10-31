"""O pagamento de fatura que o banco manda (dono, 2026-10-30): segue a Pluggy.

Uma saida da conta que a Pluggy marca como pagamento de fatura (role
INVOICE_PAYMENT) nunca e despesa: as compras ja contam no cartao. Depois de cada
pull (com as compras do pull ja gravadas), `record_bank_payments()` cuida de cada
uma ainda sem lancamento (`invoice_payment_link()` ja ligou as que tem um
pay-invoice do app):

- achado o cartao e a fatura, a baixa e a de sempre (`settle_invoice()`: itens
  PAID, `paid_by`), datada no dia do banco e com o valor do banco;
- sem fatura para baixar (a compra e de antes do que a Pluggy guarda), o
  lancamento fica sozinho, na origem de pagamento de fatura, que nenhum total de
  despesa conta: o dinheiro saiu, e o saldo da conta tem de dizer isso.

Idempotente pelo id da Pluggy, no `source_id` e no `target_id` da linha.

**A fatura de uma compra e a do banco** (`mirror_cards()`, dono 2026-10-30): cada
linha da Pluggy diz em que fatura esta (`bill_month`, o billForecastDate) e por
quanto; a compra aberta que veio dela fica assim, uma linha do app por linha do
banco: a parcela que ele nao lista sai, a que chegou entra.

**Parcelas adiantadas** (dono, 2026-10-31): o banco desconta cada parcela
adiantada ("Desconto Na Parcela 3 De 6 Rota Transportes") e cobra a parcela na
fatura do desconto, mas a Pluggy nao lista a cobranca e segue mostrando as
parcelas seguintes como PENDING nas faturas futuras (BTG: fatura de outubro =
linhas + 237,16 das 9 parcelas, no centavo). O credito de desconto manda: a
parcela N vai para a fatura dele, com o status dele, e nunca mais volta.

**Pagamento que o app ja tem**: `invoice_payment_link()` so liga o de mesmo
valor. Um pagamento do app ainda sem transacao, na mesma conta e no mesmo dia (ou
de mesmo valor, ate CARD_SIDE_DAYS), e este: fica com o valor do banco. Sem isso
a saida virava uma segunda linha "solta" (2026-10-31: 11 pagamentos em dobro).

**Fatura paga antes de fechar**: de um cartao certo e com o valor exato da fatura
aberta, a baixa e a de sempre; o que entrar depois fica aberto, como no banco.

**Qual cartao**: o credito de mesmo valor na conta do cartao, ate
CARD_SIDE_DAYS dias; senao os cartoes conectados da mesma conexao, depois os do
mesmo banco; o resto so entra com o valor exato de uma fatura.
**Qual fatura**: a mais antiga fechada de valor exato (no banco que arredonda,
o valor que arredonda para o do banco); senao, de um cartao certo, a mais antiga
fechada perto do vencimento (DUE_WINDOW_DAYS): a fatura do app nao fecha igual a do
banco quando falta uma parcela antiga ou a data da compra difere.
"""

import re
from collections import defaultdict
from datetime import date as date_type

from db import new_id, row_to_dict, utc_timestamp
from money import rounded_money
from open_finance_categories import plain_text
from services import inbox, invoices
from source_types import CC_INVOICE_PAYMENT_SOURCE_TYPE, INVOICE_PAYMENT_SOURCE_TYPES

CARD_SIDE_DAYS = 5
DUE_WINDOW_DAYS = 45
ANTICIPATED_TEXT = re.compile(r"^desconto na parcela (\d+) de (\d+) (.+)$")


def _ordinal(text):
    return date_type.fromisoformat(str(text)[:10]).toordinal()


def _cents(value):
    return int(round(float(value) * 100))


def mapped_cards(conn, current_user_id):
    """Os cartoes conectados, com a conta da Pluggy de cada um."""
    return [row_to_dict(row) for row in conn.execute(
        """
        SELECT c.*, o.id AS of_account_id, o.of_item_id, o.name AS of_name
        FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        JOIN credit_cards c ON c.id = o.card_id AND c.user_id = o.user_id
        WHERE o.user_id = ? AND o.ignored_at IS NULL AND i.archived_at IS NULL
        ORDER BY c.created_at, c.id
        """,
        (current_user_id,),
    ).fetchall()]


def open_invoices(conn, current_user_id, card):
    """[{month, year, cents, closing, due}] das faturas com item em aberto, da
    mais antiga para a mais nova."""
    rows = conn.execute(
        f"""
        SELECT invoice_month, invoice_year, SUM({invoices.signed_amount_sql()} * amount) AS total
        FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND status = 'OPEN'
        GROUP BY invoice_year, invoice_month
        ORDER BY invoice_year, invoice_month
        """,
        (current_user_id, card["id"]),
    ).fetchall()
    return [
        {
            "month": row["invoice_month"], "year": row["invoice_year"], "cents": _cents(row["total"]),
            "closing": invoices.invoice_closing_date(
                row["invoice_month"], row["invoice_year"], card["due_day"], card["closing_day"],
            ),
            "due": invoices.invoice_due_date(row["invoice_month"], row["invoice_year"], card["due_day"]),
        }
        for row in rows
    ]


def _card_side_claims(conn, current_user_id):
    """Os creditos de pagamento nas contas dos cartoes, ainda sem par."""
    return [row_to_dict(row) for row in conn.execute(
        """
        SELECT t.id, t.date, t.amount_cents, a.card_id FROM open_finance_transactions t
        JOIN open_finance_accounts a ON a.id = t.of_account_id AND a.user_id = t.user_id
        WHERE t.user_id = ? AND t.role = 'INVOICE_PAYMENT' AND t.direction = 'IN' AND a.card_id IS NOT NULL
        ORDER BY t.date, t.id
        """,
        (current_user_id,),
    ).fetchall()]


def _known_cards(row, account, cards, claims):
    """Os cartoes que esta saida pode pagar com certeza (nao so pelo valor)."""
    day = _ordinal(row["date"])
    for claim in claims:
        if claim["amount_cents"] == row["amount_cents"] and abs(_ordinal(claim["date"]) - day) <= CARD_SIDE_DAYS:
            claims.remove(claim)
            found = [card for card in cards if card["id"] == claim["card_id"]]
            if found:
                return found
    same_item = [card for card in cards if card["of_item_id"] == account["of_item_id"]]
    if same_item:
        return same_item
    issuer = inbox.issuer_of_institution(account["name"])
    return [card for card in cards if issuer and inbox.issuer_of_institution(card["of_name"]) == issuer]


def _pick_invoice(conn, current_user_id, row, account, known, cards):
    """(cartao, fatura) ou None."""
    cents = int(row["amount_cents"])
    rounds_up = inbox.open_finance_rounds_up(conn, current_user_id, account["id"])
    lowest = cents - 99 if rounds_up and cents % 100 == 0 else cents
    paid_on = date_type.fromisoformat(row["date"])
    ordered = known + [card for card in cards if card["id"] not in {entry["id"] for entry in known}]
    usable = {}
    for card in ordered:
        usable[card["id"]] = [
            invoice for invoice in open_invoices(conn, current_user_id, card)
            if invoice["closing"] <= paid_on and abs((invoice["due"] - paid_on).days) <= DUE_WINDOW_DAYS
        ]
        for invoice in usable[card["id"]]:
            if lowest <= invoice["cents"] <= cents:
                return card, invoice
    if len(known) == 1:
        for invoice in usable[known[0]["id"]]:
            if invoice["cents"] > 0:
                return known[0], invoice
    # Pago antes de fechar (BTG, 31/07): so de um cartao certo, com o valor exato.
    for card in known:
        for invoice in open_invoices(conn, current_user_id, card):
            ahead = invoice["closing"] > paid_on and abs((invoice["due"] - paid_on).days) <= DUE_WINDOW_DAYS
            if ahead and lowest <= invoice["cents"] <= cents:
                return card, invoice
    return None


def _purchase_groups(rows):
    """As linhas do banco de cada compra: as parcelas tem o dia da compra, o texto
    e o total em comum; a compra a vista e uma linha so."""
    groups = defaultdict(list)
    for row in rows:
        total = row["total_installments"] or 1
        key = (row["date"], plain_text(row["description"]), total) if total > 1 else row["id"]
        groups[key].append(row)
    return list(groups.values())


def _text_key(text):
    """O banco escreve "Ig Duo Gourmet" na compra e "Ig Duogourmet" no desconto."""
    return plain_text(text).replace(" ", "")


def _anticipations(rows, groups):
    """{indice do grupo: {parcela: linha do desconto}}: cada desconto vale para a
    compra mais antiga de mesmo texto e mesmo total, feita ate o dia dele, em que a
    parcela N ainda nao foi cobrada nem adiantada por outro desconto."""
    found = defaultdict(dict)
    by_age = sorted(range(len(groups)), key=lambda index: groups[index][0]["date"])
    for row in sorted(rows, key=lambda entry: (entry["date"], entry["id"])):
        match = ANTICIPATED_TEXT.match(plain_text(row["description"]))
        if row["direction"] != "IN" or not match:
            continue
        number, total, name = int(match[1]), int(match[2]), _text_key(match[3])
        for index in by_age:
            group = groups[index]
            if (
                (group[0]["total_installments"] or 1) == total and _text_key(group[0]["description"]) == name
                and group[0]["date"] <= row["date"] and number not in found[index]
                and not any(
                    entry["installment_number"] == number and entry["bill_month"] <= row["bill_month"] for entry in group
                )
            ):
                found[index][number] = row
                break
    return found


def _bank_card_rows(conn, current_user_id, of_account_id):
    return conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND bill_month IS NOT NULL
          AND role NOT IN ('REMOVED', 'UNMAPPED', 'INVOICE_PAYMENT')
        """,
        (current_user_id, of_account_id),
    ).fetchall()


def unlisted_anticipated_cents(conn, current_user_id, of_account_id):
    """{(dia, texto, total): centavos} das parcelas adiantadas que o banco nao lista
    mais: sao da compra, embora faltem nas linhas dele (a Conferencia soma)."""
    rows = _bank_card_rows(conn, current_user_id, of_account_id)
    groups = _purchase_groups(rows)
    extra = {}
    for index, early in _anticipations(rows, groups).items():
        group = groups[index]
        listed = {row["installment_number"] or 1 for row in group}
        missing = [number for number in early if number not in listed]
        if missing:
            cents = min(abs(int(row["raw_amount_cents"])) for row in group)
            anchor = group[0]
            extra[(anchor["date"], anchor["description"], anchor["total_installments"])] = cents * len(missing)
    return extra


def _installment_of(entry):
    return int(str(entry["installment_info"] or "1/1").split("/")[0] or 1)


def _set_line(conn, current_user_id, entry_id, row):
    year, month = (int(part) for part in row["bill_month"].split("-"))
    conn.execute(
        "UPDATE cc_expenses SET invoice_month = ?, invoice_year = ?, amount = ? WHERE id = ? AND user_id = ?",
        (month, year, abs(int(row["raw_amount_cents"])) / 100, entry_id, current_user_id),
    )


def _copy_line(conn, current_user_id, model, row, number):
    """A parcela que o banco passou a listar depois da compra gravada."""
    values = dict(model)
    values.update({"id": new_id(), "status": "OPEN", "installment_info": f"{number}/{row['total_installments']}",
                   "created_at": utc_timestamp()})
    conn.execute(
        f"INSERT INTO cc_expenses ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})", tuple(values.values()),
    )
    _set_line(conn, current_user_id, values["id"], row)


def _credit_invoice(conn, current_user_id, credit):
    """(mes, ano, status, paid_by) da fatura do credito de desconto."""
    year, month = (int(part) for part in credit["bill_month"].split("-"))
    target = conn.execute(
        "SELECT status, paid_by FROM cc_expenses WHERE id = ? AND user_id = ?", (credit["target_id"], current_user_id),
    ).fetchone()
    return (month, year, target["status"], target["paid_by"]) if target else (month, year, "OPEN", None)


def _advance_line(conn, current_user_id, entry_id, credit):
    conn.execute(
        "UPDATE cc_expenses SET invoice_month = ?, invoice_year = ?, status = ?, paid_by = ? WHERE id = ? AND user_id = ?",
        (*_credit_invoice(conn, current_user_id, credit), entry_id, current_user_id),
    )


def _copy_advanced_line(conn, current_user_id, model, credit, number, total, amount):
    """A parcela adiantada que o banco ja nem lista."""
    month, year, status, paid_by = _credit_invoice(conn, current_user_id, credit)
    values = dict(model)
    values.update({
        "id": new_id(), "status": status, "paid_by": paid_by, "invoice_month": month, "invoice_year": year,
        "installment_info": f"{number}/{total}", "amount": amount, "created_at": utc_timestamp(),
    })
    conn.execute(
        f"INSERT INTO cc_expenses ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})", tuple(values.values()),
    )


def mirror_cards(conn, current_user_id):
    """Deixa as compras abertas de cada cartao conectado como o banco as mostra."""
    for card in mapped_cards(conn, current_user_id):
        rows = _bank_card_rows(conn, current_user_id, card["of_account_id"])
        groups = _purchase_groups(rows)
        anticipated = _anticipations(rows, groups)
        for index, group in enumerate(groups):
            anchor = next((row for row in group if row["target_table"] == "cc_expenses" and row["target_id"]), None)
            if anchor:
                _mirror_purchase(conn, current_user_id, group, anchor, anticipated.get(index, {}))


def _mirror_purchase(conn, current_user_id, group, anchor, early):
    owner = conn.execute(
        "SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (anchor["target_id"], current_user_id),
    ).fetchone()
    if not owner or not str(owner["client_id"] or "").startswith("pluggy:"):
        return
    entries = [row_to_dict(row) for row in conn.execute(
        "SELECT * FROM cc_expenses WHERE user_id = ? AND client_id = ?", (current_user_id, owner["client_id"]),
    ).fetchall()]
    by_number = {row["installment_number"] or 1: row for row in group}
    known = set()
    for entry in entries:
        number = _installment_of(entry)
        known.add(number)
        if entry["status"] != "OPEN":
            continue
        if number in early:
            _advance_line(conn, current_user_id, entry["id"], early[number])
        elif number in by_number:
            _set_line(conn, current_user_id, entry["id"], by_number[number])
        else:
            conn.execute("DELETE FROM cc_expenses WHERE id = ? AND user_id = ?", (entry["id"], current_user_id))
    for number, row in by_number.items():
        if number not in known and number not in early:
            _copy_line(conn, current_user_id, entries[0], row, number)
    for number, credit in early.items():
        if number not in known:
            amount = min(entry["amount"] for entry in entries)
            _copy_advanced_line(conn, current_user_id, entries[0], credit, number, group[0]["total_installments"], amount)


def record_bank_payments(conn, current_user_id):
    """Grava as saidas de pagamento de fatura ainda sem lancamento. Devolve
    {settled, linked, loose, amount_differs}: `linked` ligou um pagamento que o
    app ja tinha; `loose` sem fatura para baixar; `amount_differs` baixou uma
    fatura de outro valor (vale o do banco)."""
    mirror_cards(conn, current_user_id)
    rows = conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND role = 'INVOICE_PAYMENT' AND direction = 'OUT' AND target_id IS NULL
        ORDER BY date, id
        """,
        (current_user_id,),
    ).fetchall()
    counts = {"settled": 0, "linked": 0, "loose": 0, "amount_differs": 0}
    if not rows:
        return counts
    cards = mapped_cards(conn, current_user_id)
    claims = _card_side_claims(conn, current_user_id)
    for row in rows:
        account = conn.execute(
            "SELECT * FROM open_finance_accounts WHERE id = ? AND user_id = ?",
            (row["of_account_id"], current_user_id),
        ).fetchone()
        if not account or not account["account_id"] or account["ignored_at"]:
            continue
        counts[_record_one(conn, current_user_id, row, account, cards, claims)] += 1
    return counts


def _link(conn, current_user_id, row, transaction_id):
    conn.execute(
        "UPDATE open_finance_transactions SET target_table = 'transactions', target_id = ?, updated_at = ?"
        " WHERE id = ? AND user_id = ?",
        (transaction_id, utc_timestamp(), row["id"], current_user_id),
    )


def _kept_payment(conn, current_user_id, row, account):
    """O pagamento de fatura do app, sem transacao, que esta saida do banco explica."""
    kinds = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    day = _ordinal(row["date"])
    cents = int(row["amount_cents"])
    found = [
        payment for payment in conn.execute(
            f"""
            SELECT t.id, t.date, t.amount FROM transactions t
            WHERE t.user_id = ? AND t.account_id = ? AND t.source_type IN ({', '.join('?' for _ in kinds)})
              AND NOT EXISTS (
                  SELECT 1 FROM open_finance_transactions o
                  WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                    AND o.role <> 'REMOVED'
              )
            """,
            (current_user_id, account["account_id"], *kinds),
        ).fetchall()
        if payment["date"] == row["date"] or (
            _cents(payment["amount"]) == cents and abs(_ordinal(payment["date"]) - day) <= CARD_SIDE_DAYS
        )
    ]
    if not found:
        return None
    kept = min(found, key=lambda payment: (abs(_cents(payment["amount"]) - cents), payment["date"] != row["date"], payment["id"]))
    # Dois pagamentos do banco no dia: o do app e o de valor mais perto dele.
    same_day = conn.execute(
        """
        SELECT amount_cents FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND date = ? AND role = 'INVOICE_PAYMENT' AND direction = 'OUT'
          AND target_id IS NULL
        """,
        (current_user_id, row["of_account_id"], row["date"]),
    ).fetchall()
    wanted = _cents(kept["amount"])
    closest = min(abs(int(other["amount_cents"]) - wanted) for other in same_day) if same_day else 0
    return kept if abs(cents - wanted) == closest else None


def _record_one(conn, current_user_id, row, account, cards, claims):
    amount = rounded_money(int(row["amount_cents"]) / 100)
    kept = _kept_payment(conn, current_user_id, row, account)
    if kept:
        conn.execute(
            "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?", (amount, kept["id"], current_user_id),
        )
        _link(conn, current_user_id, row, kept["id"])
        return "linked"
    known = _known_cards(row, account, cards, claims)
    picked = _pick_invoice(conn, current_user_id, row, account, known, cards)
    if picked:
        card, invoice = picked
        payment = invoices.settle_invoice(
            conn, current_user_id, card, invoice["month"], invoice["year"],
            account_id=account["account_id"], payment_date=row["date"],
            source_type=CC_INVOICE_PAYMENT_SOURCE_TYPE,
            source_id=f"{card['id']}:{invoice['year']:04d}-{invoice['month']:02d}:{row['pluggy_transaction_id']}",
        )
        if payment:
            differs = _cents(payment["amount"]) != int(row["amount_cents"])
            conn.execute(
                "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
                (amount, payment["id"], current_user_id),
            )
            _link(conn, current_user_id, row, payment["id"])
            return "amount_differs" if differs else "settled"
    return _record_loose(conn, current_user_id, row, account, amount, known)


def _record_loose(conn, current_user_id, row, account, amount, known):
    label = known[0]["name"] if len(known) == 1 else "cartão"
    transaction_id = new_id()
    conn.execute(
        """
        INSERT OR IGNORE INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'EXPENSE', ?, ?)
        """,
        (
            transaction_id, current_user_id, account["account_id"], amount, row["date"],
            f"Pagamento Fatura {label}", "Pagamento de fatura", CC_INVOICE_PAYMENT_SOURCE_TYPE,
            f"pluggy:{row['pluggy_transaction_id']}",
        ),
    )
    found = conn.execute(
        "SELECT id FROM transactions WHERE user_id = ? AND source_type = ? AND source_id = ?",
        (current_user_id, CC_INVOICE_PAYMENT_SOURCE_TYPE, f"pluggy:{row['pluggy_transaction_id']}"),
    ).fetchone()
    _link(conn, current_user_id, row, found["id"])
    return "loose"


def close_past_invoices(conn, current_user_id, today):
    """Na reconstrucao: fatura vencida que nenhum pagamento da Pluggy baixou
    (de antes do que ela guarda, ou paga por uma conta sem Pluggy) e historia,
    nao atraso: PAID sem lancamento. Devolve as baixadas, para o relatorio."""
    closed = []
    for card in mapped_cards(conn, current_user_id):
        for invoice in open_invoices(conn, current_user_id, card):
            if invoice["due"] >= today:
                continue
            conn.execute(
                """
                UPDATE cc_expenses SET status = 'PAID', paid_by = NULL
                WHERE user_id = ? AND card_id = ? AND status = 'OPEN' AND invoice_month = ? AND invoice_year = ?
                """,
                (current_user_id, card["id"], invoice["month"], invoice["year"]),
            )
            closed.append({
                "card": card["name"], "invoice": invoices.invoice_label(invoice["month"], invoice["year"]),
                "due": invoice["due"].isoformat(), "amount": invoice["cents"] / 100,
            })
    return closed
