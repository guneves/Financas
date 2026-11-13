"""Gemeos: duas compras iguais de verdade ganham "2× igual" (Fase 4).

Duas observacoes do mesmo canal sao dois movimentos (I2), entao o app guarda as
duas. Para o dono ver sem pergunta nenhuma (o segundo cafe nao custa toque; a
cobranca em dobro aparece onde ele ja olha), a linha leva `twin: true` quando
outra despesa:

- e despesa tambem (EXPENSE, ou compra no cartao);
- esta na mesma conta (ou no mesmo cartao), com os mesmos centavos e a mesma
  descricao normalizada (a de inbox.normalized());
- tem `occurred_at` ate TWIN_WINDOW_MINUTES de distancia quando as duas tem
  hora; senao, a mesma data.

So um selo neutro: sem cartao de atencao, nada a dispensar, nenhuma acao. A
consulta pega so a janela da pagina (±1 dia), sempre com user_id.
"""

from datetime import datetime, timedelta

import statement_import
from money import to_cents

TWIN_WINDOW_MINUTES = 60


def _normalized(value):
    return statement_import.normalize_description(value or "")


def _twin_cents(value):
    return to_cents(value or 0)


def _when(occurred_at):
    if len(str(occurred_at or "")) <= 10:
        return None
    try:
        return datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))
    except ValueError:
        return None


def close_in_time(a_date, a_occurred, b_date, b_occurred):
    """As duas na janela: ate 60 min com hora nas duas, senao a mesma data."""
    first, second = _when(a_occurred), _when(b_occurred)
    if first is None or second is None:
        return str(a_date or "")[:10] == str(b_date or "")[:10]
    if (first.tzinfo is None) != (second.tzinfo is None):
        first, second = first.replace(tzinfo=None), second.replace(tzinfo=None)
    return abs(first - second) <= timedelta(minutes=TWIN_WINDOW_MINUTES)


def twin_keys(entries):
    """As chaves (`key`) que tem um gemeo entre `entries`: dicts com key,
    target, cents, description, date, occurred_at. Puro."""
    groups = {}
    for entry in entries:
        groups.setdefault((entry["target"], entry["cents"], _normalized(entry["description"])), []).append(entry)
    twins = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        for index, entry in enumerate(group):
            for other in group[index + 1:]:
                if close_in_time(entry["date"], entry["occurred_at"], other["date"], other["occurred_at"]):
                    twins.add(entry["key"])
                    twins.add(other["key"])
    return twins


def _window(dates):
    days = [str(day)[:10] for day in dates if day]
    if not days:
        return None
    low = datetime.strptime(min(days), "%Y-%m-%d") - timedelta(days=1)
    high = datetime.strptime(max(days), "%Y-%m-%d") + timedelta(days=1)
    return low.strftime("%Y-%m-%d"), high.strftime("%Y-%m-%d")


def transaction_twin_ids(conn, current_user_id, rows):
    """As ids das despesas de `rows` (linhas de transactions) que tem gemeo."""
    expenses = [row for row in rows if row["type"] == "EXPENSE"]
    window = _window(row["date"] for row in expenses)
    if not window:
        return set()
    accounts = sorted({row["account_id"] for row in expenses if row["account_id"]})
    if not accounts:
        return set()
    candidates = conn.execute(
        f"""
        SELECT id, account_id, amount, description, date, occurred_at FROM transactions
        WHERE user_id = ? AND type = 'EXPENSE' AND date BETWEEN ? AND ?
          AND account_id IN ({', '.join('?' for _ in accounts)})
        """,
        (current_user_id, *window, *accounts),
    ).fetchall()
    found = twin_keys([
        {"key": row["id"], "target": row["account_id"], "cents": _twin_cents(row["amount"]),
         "description": row["description"], "date": row["date"], "occurred_at": row["occurred_at"]}
        for row in candidates
    ])
    return {row["id"] for row in expenses if row["id"] in found}


def card_twin_keys(conn, current_user_id, purchases):
    """Os client_id das compras no cartao de `purchases` (dicts com client_id,
    card_id, date) que tem gemeo: mesma compra = o total das parcelas."""
    wanted = [entry for entry in purchases if entry.get("type", "CARD") == "CARD" and entry.get("client_id")]
    window = _window(entry["date"] for entry in wanted)
    if not window:
        return set()
    cards = sorted({entry["card_id"] for entry in wanted if entry.get("card_id")})
    if not cards:
        return set()
    rows = conn.execute(
        f"""
        SELECT COALESCE(client_id, 'legacy:' || id) AS key, card_id, SUM(amount) AS amount,
               MIN(description) AS description, MIN(purchase_date) AS date, MIN(occurred_at) AS occurred_at
        FROM cc_expenses
        WHERE user_id = ? AND COALESCE(kind, 'PURCHASE') <> 'REFUND'
          AND card_id IN ({', '.join('?' for _ in cards)})
          AND COALESCE(client_id, 'legacy:' || id) IN (
              SELECT COALESCE(client_id, 'legacy:' || id) FROM cc_expenses
              WHERE user_id = ? AND purchase_date BETWEEN ? AND ?
          )
        GROUP BY COALESCE(client_id, 'legacy:' || id), card_id
        """,
        (current_user_id, *cards, current_user_id, *window),
    ).fetchall()
    found = twin_keys([
        {"key": row["key"], "target": row["card_id"], "cents": _twin_cents(row["amount"]),
         "description": row["description"], "date": row["date"], "occurred_at": row["occurred_at"]}
        for row in rows
    ])
    return {entry["client_id"] for entry in wanted if entry["client_id"] in found}
