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
        SELECT id, date, direction, amount_cents, description, role, item_id, movement, total_installments
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
        entry = {
            "id": row["id"],
            "date": row["date"],
            "cents": -row["amount_cents"] if row["direction"] == "OUT" else row["amount_cents"],
            "description": row["description"],
            "tolerance": (row["total_installments"] or 1) if card and (row["total_installments"] or 1) > 1 else 0,
        }
        if row["item_id"]:
            item = inbox.fetch_item(conn, current_user_id, row["item_id"])
            if item and item["state"] == inbox.PENDING:
                awaiting.append(entry)
                continue
        entries.append(entry)
    return entries, awaiting


def _account_rows(conn, current_user_id, account_id, date_from, date_to):
    rows = conn.execute(
        """
        SELECT id, date, description,
            CASE
                WHEN type = 'INCOME' THEN amount
                WHEN type = 'TRANSFER' AND transfer_account_id = ? AND account_id != ? THEN amount
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
    return [
        {"date": entry["date"], "amount": entry["cents"] / 100, "description": entry.get("description")}
        for entry in entries[:MAX_LISTED]
    ]


def account_check(conn, current_user_id, of_account):
    """A conferencia de uma conta da Pluggy mapeada, ou None (sem mapeamento
    ou nada puxado ainda)."""
    card = of_account["type"] == "CREDIT"
    target = of_account["card_id"] if card else of_account["account_id"]
    if not target or not of_account["synced_until"]:
        return None
    bank, awaiting = _bank_rows(conn, current_user_id, of_account, card)
    dates = [entry["date"] for entry in bank + awaiting]
    if not dates:
        return {"from": None, "to": of_account["synced_until"], "bank_only": [], "app_only": [], "awaiting": [],
                "bank_only_count": 0, "app_only_count": 0, "awaiting_count": 0}
    date_from, date_to = min(dates), max(max(dates), of_account["synced_until"])
    app = (_card_rows if card else _account_rows)(conn, current_user_id, target, date_from, date_to)
    # Os que esperam no Aprovar tambem tiram seu par do app: um lancamento
    # digitado a mao para eles ja existe.
    _waiting, app = match_movements(awaiting, app)
    bank_only, app_only = match_movements(bank, app)
    return {
        "from": date_from,
        "to": date_to,
        "bank_only": _listed(bank_only),
        "app_only": _listed(app_only),
        "awaiting": _listed(awaiting),
        "bank_only_count": len(bank_only),
        "app_only_count": len(app_only),
        "awaiting_count": len(awaiting),
    }
