"""Conta global (dono, 2026-10-27): a conta em dolar (Wise) e a unica tela do
app fora de reais.

O dinheiro chega nela por Pix de uma conta em reais ("Pix para Wise", para
"WISE BRASIL CORRETORA DE CAMBIO"): uma transferencia so, que sai em reais e
entra em dolar (`transfer_amount`, 047). Nunca despesa nem receita.

As duas pontas vem da Pluggy em contas diferentes e nunca no mesmo valor, entao
o par nao e pelos centavos (como numa transferencia em reais) e sim:

- a ponta em reais: uma saida de uma conta em reais cuja contraparte (ou
  descricao) nomeia a conta global — o nome ou o banco dela;
- a ponta em dolar: uma entrada na conta global;
- no mesmo dia, ate FX_MATCH_DAYS de distancia. Com duas no mesmo dia, a de
  cambio mais perto da PTAX do dia (o Pix de R$ 253 e o credito de US$ 46,
  nao o de US$ 18).

So aqui se sabe disso; open_finance_inbox.place() pergunta antes do par em
reais, e o resto do motor (gravar sozinho, revisar, snapshot) segue igual.
"""

from datetime import date as date_type

from services import inbox
from services.fx import BASE_CURRENCY, FxUnavailable, normalize_currency, rate_on
from validators import ValidationError

FX_MATCH_DAYS = 1
# Palavras do nome/banco da conta que nao nomeiam nada ("conta", "global").
GENERIC_WORDS = {"conta", "global", "corrente", "banco", "dolar", "dolares", "usd", "the", "bank"}


def _ordinal(text):
    return date_type.fromisoformat(str(text)[:10]).toordinal()


def account_currency(conn, current_user_id, account_id):
    if not account_id:
        return None
    row = conn.execute(
        "SELECT currency FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    return normalize_currency(row["currency"]) if row else None


def is_foreign(conn, current_user_id, account_id):
    currency = account_currency(conn, current_user_id, account_id)
    return currency is not None and currency != BASE_CURRENCY


def foreign_accounts(conn, current_user_id):
    return conn.execute(
        """
        SELECT id, name, institution, currency FROM accounts
        WHERE user_id = ? AND archived_at IS NULL AND COALESCE(currency, 'BRL') <> 'BRL'
        ORDER BY created_at, id
        """,
        (current_user_id,),
    ).fetchall()


def names_of(account):
    """As palavras que nomeiam a conta: "Wise" (nome) e o banco, sem as genericas."""
    words = set()
    for text in (account["name"], account["institution"]):
        words.update(word for word in inbox.normalized(text).split() if len(word) >= 3 and word not in GENERIC_WORDS)
    return words


def named_account(conn, current_user_id, *texts):
    """A conta global que a contraparte/descricao nomeia, ou None (nenhuma ou
    mais de uma)."""
    words = set(inbox.normalized(" ".join(str(text or "") for text in texts)).split())
    if not words:
        return None
    found = [row for row in foreign_accounts(conn, current_user_id) if names_of(row) & words]
    return found[0] if len(found) == 1 else None


def destination_for_row(conn, current_user_id, row, account_id):
    """A conta global para onde vai esta saida de uma conta em reais, ou None."""
    if row["direction"] != "OUT" or is_foreign(conn, current_user_id, account_id):
        return None
    return named_account(conn, current_user_id, row["counterparty"], row["description"])


def _implied_gap(conn, current_user_id, currency, date_text, brl_cents, foreign_cents):
    """Quao longe o cambio do par (reais / dolar) esta da PTAX do dia; sem PTAX,
    0 (decide a data)."""
    try:
        rate = rate_on(conn, current_user_id, currency, date_text)
    except FxUnavailable:
        return 0.0
    if not foreign_cents or not rate:
        return 0.0
    return abs((brl_cents / foreign_cents) / rate - 1)


def _best(conn, current_user_id, currency, date_text, candidates, brl_of, foreign_of):
    """O candidato de data mais perto, depois o de cambio mais perto da PTAX."""
    day = _ordinal(date_text)
    scored = []
    for candidate in candidates:
        distance = abs(_ordinal(candidate["date"]) - day)
        if distance > FX_MATCH_DAYS:
            continue
        gap = _implied_gap(conn, current_user_id, currency, candidate["date"], brl_of(candidate), foreign_of(candidate))
        scored.append(((distance, gap, str(candidate["id"])), candidate))
    return min(scored, key=lambda pair: pair[0])[1] if scored else None


def _item_texts(conn, current_user_id, item_id):
    texts = []
    for source in inbox.open_finance_sources(conn, current_user_id, item_id, roles=(inbox.SOURCE,)):
        texts.extend((source["counterparty"], source["description"]))
    for detection in inbox.item_detections(conn, current_user_id, item_id):
        if detection["role"] == inbox.SOURCE:
            texts.extend((detection["counterparty"], detection["merchant"]))
    return texts


def awaiting_real_side(conn, current_user_id, global_account, cents, date_text):
    """A ponta em reais que espera esta entrada em dolar: um item pendente,
    transferencia de uma conta em reais, sem `transfer_amount`, para a conta
    global (ou sem destino ainda, mas nomeando ela)."""
    rows = conn.execute(
        """
        SELECT i.*, substr(i.occurred_at, 1, 10) AS date FROM inbox_items i
        JOIN accounts a ON a.id = i.account_id AND a.user_id = i.user_id
        WHERE i.user_id = ? AND i.state = 'PENDING' AND i.entry_type = 'TRANSFER'
          AND i.transfer_amount IS NULL AND COALESCE(a.currency, 'BRL') = 'BRL'
          AND (i.transfer_account_id = ? OR i.transfer_account_id IS NULL)
        """,
        (current_user_id, global_account["id"]),
    ).fetchall()
    candidates = []
    for row in rows:
        if row["transfer_account_id"] != global_account["id"]:
            if named_account(conn, current_user_id, *_item_texts(conn, current_user_id, row["id"])) is None:
                continue
        candidates.append(row)
    return _best(
        conn, current_user_id, normalize_currency(global_account["currency"]), date_text, candidates,
        brl_of=lambda candidate: inbox._cents(candidate["amount"]), foreign_of=lambda candidate: cents,
    )


def awaiting_foreign_side(conn, current_user_id, global_account, brl_cents, date_text):
    """A ponta em dolar que espera esta saida em reais: um item pendente de
    entrada na conta global (receita em dolar, da Pluggy)."""
    rows = conn.execute(
        """
        SELECT i.*, substr(i.occurred_at, 1, 10) AS date FROM inbox_items i
        WHERE i.user_id = ? AND i.state = 'PENDING' AND i.entry_type = 'INCOME' AND i.account_id = ?
          AND EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = i.user_id AND o.item_id = i.id AND o.role = 'SOURCE'
          )
        """,
        (current_user_id, global_account["id"]),
    ).fetchall()
    return _best(
        conn, current_user_id, normalize_currency(global_account["currency"]), date_text, rows,
        brl_of=lambda candidate: brl_cents, foreign_of=lambda candidate: inbox._cents(candidate["amount"]),
    )


def recorded_transfer(conn, current_user_id, global_account, cents, date_text):
    """Uma transferencia ja no app para a conta global que nenhuma linha da
    Pluggy pegou ainda: com este valor em dolar (digitada), ou sem valor em
    dolar (a conta virou global depois, `convert_to_foreign()`) — esta, a de
    cambio mais perto da PTAX. Devolve a linha, ou None."""
    rows = conn.execute(
        """
        SELECT t.id, t.date, t.amount, t.transfer_amount FROM transactions t
        JOIN accounts o ON o.id = t.account_id AND o.user_id = t.user_id
        WHERE t.user_id = ? AND t.type = 'TRANSFER' AND t.transfer_account_id = ?
          AND COALESCE(o.currency, 'BRL') <> ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions x
              WHERE x.user_id = t.user_id AND x.target_table = 'transactions' AND x.target_id = t.id
                AND x.of_account_id IN (
                    SELECT id FROM open_finance_accounts WHERE user_id = t.user_id AND account_id = ?
                )
          )
        """,
        (current_user_id, global_account["id"], normalize_currency(global_account["currency"]), global_account["id"]),
    ).fetchall()
    currency = normalize_currency(global_account["currency"])
    for candidates in (
        [row for row in rows if row["transfer_amount"] is not None and inbox._cents(row["transfer_amount"]) == cents],
        [row for row in rows if row["transfer_amount"] is None],
    ):
        best = _best(
            conn, current_user_id, currency, date_text, candidates,
            brl_of=lambda candidate: inbox._cents(candidate["amount"]), foreign_of=lambda candidate: cents,
        )
        if best:
            return best
    return None


def unconfirmed_transfers(conn, current_user_id, account_id):
    """Quantas transferencias entram nesta conta em outra moeda sem o valor que
    entrou (ficam fora do saldo ate a Pluggy ou o dono dizer)."""
    return conn.execute(
        """
        SELECT COUNT(*) FROM transactions t
        JOIN accounts o ON o.id = t.account_id AND o.user_id = t.user_id
        JOIN accounts d ON d.id = t.transfer_account_id AND d.user_id = t.user_id
        WHERE t.user_id = ? AND t.type = 'TRANSFER' AND t.transfer_account_id = ?
          AND t.transfer_amount IS NULL AND COALESCE(o.currency, 'BRL') <> COALESCE(d.currency, 'BRL')
        """,
        (current_user_id, account_id),
    ).fetchone()[0]


CONVERT_MESSAGE = (
    "So vira conta global uma conta que so recebeu transferencias de contas em reais, "
    "sem saldo inicial."
)


def convert_to_foreign(conn, current_user_id, account, currency):
    """A conta em reais que so recebeu Pix (a "Wise" criada antes da conta
    global) passa a ser em `currency`. As transferencias ficam sem o valor em
    dolar ate a Pluggy da conta global trazer o credito de cada uma
    (`recorded_transfer()`), ou o dono informar; ate la ficam fora do saldo.
    Qualquer outra conta: ValidationError."""
    if account["type"] == "BROKERAGE" or account["is_default"] or float(account["initial_balance"] or 0):
        raise ValidationError(CONVERT_MESSAGE)
    other = conn.execute(
        """
        SELECT COUNT(*) FROM transactions t
        LEFT JOIN accounts o ON o.id = t.account_id AND o.user_id = t.user_id
        WHERE t.user_id = ? AND (t.account_id = ? OR t.transfer_account_id = ?)
          AND NOT (t.type = 'TRANSFER' AND t.transfer_account_id = ? AND t.transfer_amount IS NULL
                   AND COALESCE(o.currency, 'BRL') = 'BRL')
        """,
        (current_user_id, account["id"], account["id"], account["id"]),
    ).fetchone()[0]
    mapped = conn.execute(
        "SELECT COUNT(*) FROM open_finance_accounts WHERE user_id = ? AND account_id = ?",
        (current_user_id, account["id"]),
    ).fetchone()[0]
    if other or mapped:
        raise ValidationError(CONVERT_MESSAGE)
    conn.execute(
        "UPDATE accounts SET currency = ? WHERE id = ? AND user_id = ?",
        (currency, account["id"], current_user_id),
    )


def transfer_description(origin_name, destination_name):
    return f"{origin_name} -> {destination_name}"


def account_name(conn, current_user_id, account_id):
    row = conn.execute(
        "SELECT name FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    return row["name"] if row else "?"
