"""Conferencia do Open Finance (Ajustes › Open Finance): o banco contra o app.

So aponta, nunca grava nem ajusta. Para cada conta mapeada, na janela ja
puxada (do primeiro movimento que a Pluggy trouxe ate `synced_until`):

- `bank_only`: movimentos do banco sem lancamento no app — o dono recusou o
  item no Aprovar, ou o lancamento tem outro valor/data;
- `app_only`: lancamentos do app que o banco nao tem — digitado errado, em
  dobro, na conta errada;
- `awaiting`: movimentos do banco que ainda esperam no Aprovar (nao sao
  inconsistencia, so ainda nao decididos).

O saldo (Confere/Diferenca) continua em list_view. Pares: mesmo valor com
sinal, ate MATCH_DAYS dias de distancia, o mais proximo primeiro, um para um.
Uma compra parcelada no cartao vem da Pluggy como parcela x n (os conectores
nao mandam o total), entao aceita ate n centavos de diferenca.
"""

from datetime import date as date_type

from services import inbox

MATCH_DAYS = 3
MAX_LISTED = 50


def _ordinal(text):
    return date_type.fromisoformat(str(text)[:10]).toordinal()


def match_movements(bank, app, days=MATCH_DAYS):
    """Puro. `bank` e `app`: listas de {id, date, cents, tolerance?} (cents com
    sinal: + entra, - sai). Devolve (bank sem par, app sem par), cada um na
    ordem de entrada. Um para um; entre candidatos, o de data mais proxima,
    depois o de valor mais proximo."""
    free = list(range(len(app)))
    unmatched_bank = []
    for entry in sorted(bank, key=lambda item: (str(item["date"]), str(item["id"]))):
        tolerance = int(entry.get("tolerance") or 0)
        day = _ordinal(entry["date"])
        best = None
        for index in free:
            candidate = app[index]
            if (candidate["cents"] > 0) != (entry["cents"] > 0):
                continue
            gap = abs(candidate["cents"] - entry["cents"])
            distance = abs(_ordinal(candidate["date"]) - day)
            if gap > tolerance or distance > days:
                continue
            key = (distance, gap)
            if best is None or key < best[0]:
                best = (key, index)
        if best is None:
            unmatched_bank.append(entry)
        else:
            free.remove(best[1])
    bank_ids = {id(entry) for entry in unmatched_bank}
    return [entry for entry in bank if id(entry) in bank_ids], [app[index] for index in sorted(free)]


def _cents(amount):
    return int(round(float(amount) * 100))


def _bank_rows(conn, current_user_id, of_account, card):
    rows = conn.execute(
        """
        SELECT id, date, direction, amount_cents, description, role, item_id, movement, total_installments,
               installment_number, target_id, conflict, conflict_amount_cents
        FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND role NOT IN ('REMOVED', 'COVERED')
        ORDER BY date, id
        """,
        (current_user_id, of_account["id"]),
    ).fetchall()
    entries = []
    awaiting = []
    for row in rows:
        if card and row["movement"] == "INVOICE_PAYMENT":
            # O pagamento da fatura esta na conta que pagou, nao no cartao.
            continue
        cents = row["conflict_amount_cents"] if row["conflict"] == "changed" and row["conflict_amount_cents"] else (
            row["amount_cents"]
        )
        if card and row["role"] == "SOURCE" and (row["installment_number"] or 1) > 1 and row["total_installments"]:
            # A compra anterior ao historico (adopt_orphan_installments): uma
            # parcela responde pela compra inteira.
            cents *= row["total_installments"]
        entry = {
            "id": row["id"],
            "date": row["date"],
            "cents": -cents if row["direction"] == "OUT" else cents,
            "description": row["description"],
            "tolerance": (row["total_installments"] or 1) if card and (row["total_installments"] or 1) > 1 else 0,
            "reason": _bank_reason(conn, current_user_id, row),
        }
        if row["conflict"] == "vanished":
            # O banco nao tem mais; o lancamento editado pelo dono ficou.
            continue
        if row["item_id"]:
            item = inbox.fetch_item(conn, current_user_id, row["item_id"])
            if item and item["state"] == inbox.PENDING:
                entry["reason"] = "awaiting"
                awaiting.append(entry)
                continue
        entries.append(entry)
    return entries, awaiting


def _bank_reason(conn, current_user_id, row):
    """Por que um movimento do banco pode nao ter par no app (a tela traduz)."""
    if row["conflict"] == "changed":
        return "changed_after_edit"
    if row["movement"] == "INVOICE_PAYMENT":
        return "invoice_payment_linked" if row["target_id"] else "invoice_payment_missing"
    if row["role"] == "UNMAPPED":
        return "unmapped"
    if row["role"] == "PAIRED":
        return "denied"
    if row["item_id"]:
        item = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item and item["state"] == inbox.DENIED:
            return "denied"
    return "different_amount_or_date"


def _conflicts(conn, current_user_id, of_account):
    """Gravados sozinhos que o banco mudou ou apagou depois que o dono editou:
    o app nao mexeu, o dono decide."""
    rows = conn.execute(
        """
        SELECT date, direction, amount_cents, conflict_amount_cents, description, conflict
        FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND conflict IS NOT NULL
        ORDER BY date, id
        """,
        (current_user_id, of_account["id"]),
    ).fetchall()
    sign = {"OUT": -1, "IN": 1}
    return [
        {
            "date": row["date"],
            "amount": sign[row["direction"]] * row["amount_cents"] / 100,
            "bank_amount": (sign[row["direction"]] * row["conflict_amount_cents"] / 100
                            if row["conflict_amount_cents"] else None),
            "description": row["description"],
            "reason": row["conflict"],
        }
        for row in rows[:MAX_LISTED]
    ]


def _account_rows(conn, current_user_id, account_id, date_from, date_to):
    rows = conn.execute(
        """
        SELECT id, date, description,
            CASE
                WHEN type = 'INCOME' THEN amount
                WHEN type = 'TRANSFER' AND transfer_account_id = ? AND account_id != ? THEN COALESCE(transfer_amount, amount)
                ELSE -amount
            END AS signed
        FROM transactions
        WHERE user_id = ? AND (account_id = ? OR (type = 'TRANSFER' AND transfer_account_id = ?))
          AND date BETWEEN ? AND ?
        ORDER BY date, id
        """,
        (account_id, account_id, current_user_id, account_id, account_id, date_from, date_to),
    ).fetchall()
    return [
        {"id": row["id"], "date": row["date"], "cents": _cents(row["signed"]), "description": row["description"]}
        for row in rows
    ]


def _card_rows(conn, current_user_id, card_id, date_from, date_to):
    """Uma entrada por compra (todas as parcelas: o client_id), na data da compra."""
    rows = conn.execute(
        """
        SELECT MIN(id) AS id, purchase_date AS date, MIN(description) AS description,
            SUM(CASE kind WHEN 'REFUND' THEN amount ELSE -amount END) AS signed
        FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND purchase_date BETWEEN ? AND ?
        GROUP BY COALESCE(client_id, id), purchase_date
        ORDER BY purchase_date, MIN(id)
        """,
        (current_user_id, card_id, date_from, date_to),
    ).fetchall()
    return [
        {"id": row["id"], "date": row["date"], "cents": _cents(row["signed"]), "description": row["description"]}
        for row in rows if row["signed"]
    ]


def _listed(entries):
    listed = []
    for entry in entries[:MAX_LISTED]:
        item = {"date": entry["date"], "amount": entry["cents"] / 100, "description": entry.get("description")}
        if entry.get("reason"):
            item["reason"] = entry["reason"]
        listed.append(item)
    return listed


def balance_explanation(difference_cents, bank_only, app_only, awaiting):
    """Puro. Saldo do banco - saldo do app = o que so o banco tem (inclusive o
    que espera no Aprovar) - o que so o app tem + o que ja era diferente antes
    da janela conferida (o saldo inicial da conta no app, um lancamento antigo).
    Devolve as quatro partes em centavos, ou None sem a diferenca."""
    if difference_cents is None:
        return None
    bank_cents = sum(entry["cents"] for entry in bank_only)
    waiting_cents = sum(entry["cents"] for entry in awaiting)
    app_cents = sum(entry["cents"] for entry in app_only)
    return {
        "difference": difference_cents,
        "bank_only": bank_cents,
        "awaiting": waiting_cents,
        "app_only": -app_cents,
        "before": difference_cents - bank_cents - waiting_cents + app_cents,
    }


def account_check(conn, current_user_id, of_account, difference_cents=None):
    """A conferencia de uma conta da Pluggy mapeada, ou None (sem mapeamento
    ou nada puxado ainda). Com `difference_cents` (saldo do banco - do app, na
    conta), `explanation` diz de onde ela vem (balance_explanation)."""
    card = of_account["type"] == "CREDIT"
    target = of_account["card_id"] if card else of_account["account_id"]
    if not target or not of_account["synced_until"]:
        return None
    bank, awaiting = _bank_rows(conn, current_user_id, of_account, card)
    conflicts = _conflicts(conn, current_user_id, of_account)
    dates = [entry["date"] for entry in bank + awaiting]
    if not dates:
        return {"from": None, "to": of_account["synced_until"], "bank_only": [], "app_only": [], "awaiting": [],
                "bank_only_count": 0, "app_only_count": 0, "awaiting_count": 0, "conflicts": conflicts,
                "explanation": balance_explanation(difference_cents, [], [], [])}
    date_from, date_to = min(dates), max(max(dates), of_account["synced_until"])
    app = (_card_rows if card else _account_rows)(conn, current_user_id, target, date_from, date_to)
    # Os que esperam no Aprovar tambem tiram seu par do app: um lancamento
    # digitado a mao para eles ja existe.
    _waiting, app = match_movements(awaiting, app)
    bank_only, app_only = match_movements(bank, app)
    for entry in app_only:
        entry["reason"] = "not_in_bank"
    return {
        "from": date_from,
        "to": date_to,
        "bank_only": _listed(bank_only),
        "app_only": _listed(app_only),
        "awaiting": _listed(awaiting),
        "bank_only_count": len(bank_only),
        "app_only_count": len(app_only),
        "awaiting_count": len(awaiting),
        "conflicts": conflicts,
        "explanation": balance_explanation(difference_cents, bank_only, app_only, _waiting),
    }
