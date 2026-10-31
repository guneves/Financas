"""Conferencia do Open Finance (Ajustes › Open Finance): o banco contra o app.

So aponta, nunca grava nem ajusta (os botoes de cada linha estao em
services/open_finance_resolve.py). Para cada conta mapeada, na janela ja puxada
(do primeiro movimento que a Pluggy trouxe ate `synced_until`):

- `bank_only`: movimentos do banco sem lancamento no app — o dono recusou o
  item no Aprovar, ou o lancamento tem outro valor/data;
- `app_only`: lancamentos do app que o banco nao tem — digitado errado, em
  dobro, na conta errada;
- `confirmed`: lancamentos que o banco nao tem e o dono disse que aconteceram;
- `awaiting`: movimentos do banco que ainda esperam no Aprovar (nao sao
  inconsistencia, so ainda nao decididos);
- `awaiting_bank`: lancamentos do app que a Pluggy ainda nao teve como trazer
  (feitos depois da ultima vez que ela falou com o banco, ou no dia dela). So
  viram `app_only` quando uma atualizacao passar e nao os identificar.

O saldo (Confere/Diferenca) continua em list_view. Pares: mesmo valor com
sinal, ate MATCH_DAYS dias de distancia, o mais proximo primeiro, um para um.
Uma compra parcelada no cartao vem da Pluggy como parcela x n (os conectores
nao mandam o total), entao aceita ate n centavos de diferenca.
"""

from datetime import date as date_type

from services import inbox, open_finance_invoices
from source_types import INVESTMENT_CASH_SOURCE_TYPE

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


def _bank_purchase_cents(conn, current_user_id, of_account):
    """O que o banco lista de cada compra parcelada (a soma das parcelas dele)."""
    totals = {}
    for row in conn.execute(
        """
        SELECT date, description, total_installments, raw_amount_cents FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND role <> 'REMOVED' AND total_installments > 1
          AND bill_month IS NOT NULL
        """,
        (current_user_id, of_account["id"]),
    ).fetchall():
        key = (row["date"], row["description"], row["total_installments"])
        totals[key] = totals.get(key, 0) + abs(int(row["raw_amount_cents"]))
    for key, cents in open_finance_invoices.unlisted_anticipated_cents(conn, current_user_id, of_account["id"]).items():
        totals[key] = totals.get(key, 0) + cents
    return totals


def _bank_rows(conn, current_user_id, of_account, card):
    purchases = _bank_purchase_cents(conn, current_user_id, of_account) if card else {}
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
        if card and row["role"] == "SOURCE" and row["total_installments"] and row["total_installments"] > 1:
            # A compra inteira, como o banco a lista (a parcela responde por ela).
            cents = purchases.get((row["date"], row["description"], row["total_installments"]), cents)
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
    # O caixa de uma operacao corresponde ao bruto do pregao, que fica fora daqui. O
    # deposito em dolar a Wise manda em outra gaveta (a "BRL", nao usada): tambem.
    rows = conn.execute(
        """
        SELECT id, date, description, created_at,
            CASE
                WHEN type = 'INCOME' THEN amount
                WHEN type = 'TRANSFER' AND transfer_account_id = ? AND account_id != ? THEN COALESCE(transfer_amount, amount)
                ELSE -amount
            END AS signed
        FROM transactions
        WHERE user_id = ? AND (account_id = ? OR (type = 'TRANSFER' AND transfer_account_id = ?))
          AND date BETWEEN ? AND ?
          AND NOT (COALESCE(source_type, '') = ? AND account_id IN (
              SELECT id FROM accounts WHERE user_id = ? AND type = 'BROKERAGE'
          ))
          AND NOT (type = 'TRANSFER' AND transfer_account_id = ? AND transfer_amount IS NOT NULL)
        ORDER BY date, id
        """,
        (
            account_id, account_id, current_user_id, account_id, account_id, date_from, date_to,
            INVESTMENT_CASH_SOURCE_TYPE, current_user_id, account_id,
        ),
    ).fetchall()
    return [
        {"id": row["id"], "table": "transactions", "date": row["date"], "cents": _cents(row["signed"]),
         "description": row["description"], "created_at": row["created_at"]}
        for row in rows
    ]


def _card_rows(conn, current_user_id, card_id, date_from, date_to):
    """Uma entrada por compra (todas as parcelas: o client_id), na data da compra."""
    rows = conn.execute(
        """
        SELECT MIN(id) AS id, purchase_date AS date, MIN(description) AS description, MAX(created_at) AS created_at,
            SUM(CASE kind WHEN 'REFUND' THEN amount ELSE -amount END) AS signed
        FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND purchase_date BETWEEN ? AND ?
        GROUP BY COALESCE(client_id, id), purchase_date
        ORDER BY purchase_date, MIN(id)
        """,
        (current_user_id, card_id, date_from, date_to),
    ).fetchall()
    return [
        {"id": row["id"], "table": "cc_expenses", "date": row["date"], "cents": _cents(row["signed"]),
         "description": row["description"], "created_at": row["created_at"]}
        for row in rows if row["signed"]
    ]


def _listed(entries):
    listed = []
    for entry in entries[:MAX_LISTED]:
        item = {"id": entry.get("id"), "date": entry["date"], "amount": entry["cents"] / 100,
                "description": entry.get("description")}
        if entry.get("table"):
            item["table"] = entry["table"]
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


def newer_than_bank(entry, bank_stamp):
    """Puro. O lancamento do app veio depois do que a Pluggy sabe do banco. Sem a
    hora da Pluggy, nada a concluir: espera."""
    if not bank_stamp:
        return True
    stamp = str(bank_stamp)
    return str(entry.get("created_at") or "") >= stamp or str(entry["date"]) >= stamp[:10]


def _confirmed_keys(conn, current_user_id):
    return {
        (row["target_table"], row["target_id"]) for row in conn.execute(
            "SELECT target_table, target_id FROM open_finance_confirmed WHERE user_id = ?", (current_user_id,),
        ).fetchall()
    }


def _bank_stamp(conn, current_user_id, of_account):
    row = conn.execute(
        "SELECT pluggy_updated_at FROM open_finance_items WHERE id = ? AND user_id = ?",
        (of_account["of_item_id"], current_user_id),
    ).fetchone()
    return row["pluggy_updated_at"] if row else None


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
                "awaiting_bank": [], "confirmed": [], "bank_only_count": 0, "app_only_count": 0, "awaiting_count": 0,
                "awaiting_bank_count": 0, "conflicts": conflicts,
                "explanation": balance_explanation(difference_cents, [], [], [])}
    date_from, date_to = min(dates), max(max(dates), of_account["synced_until"])
    app = (_card_rows if card else _account_rows)(conn, current_user_id, target, date_from, date_to)
    # Os que esperam no Aprovar tambem tiram seu par do app: um lancamento
    # digitado a mao para eles ja existe.
    _waiting, app = match_movements(awaiting, app)
    bank_only, unmatched = match_movements(bank, app)
    stamp = _bank_stamp(conn, current_user_id, of_account)
    done = _confirmed_keys(conn, current_user_id)
    confirmed = [entry for entry in unmatched if (entry["table"], entry["id"]) in done]
    open_rows = [entry for entry in unmatched if (entry["table"], entry["id"]) not in done]
    awaiting_bank = [entry for entry in open_rows if newer_than_bank(entry, stamp)]
    app_only = [entry for entry in open_rows if not newer_than_bank(entry, stamp)]
    for entry in app_only:
        entry["reason"] = "not_in_bank"
    return {
        "from": date_from,
        "to": date_to,
        "bank_only": _listed(bank_only),
        "app_only": _listed(app_only),
        "awaiting": _listed(awaiting),
        "awaiting_bank": _listed(awaiting_bank),
        "confirmed": _listed(confirmed),
        "bank_only_count": len(bank_only),
        "app_only_count": len(app_only),
        "awaiting_count": len(awaiting),
        "awaiting_bank_count": len(awaiting_bank),
        "conflicts": conflicts,
        "explanation": balance_explanation(difference_cents, bank_only, unmatched, _waiting),
    }
