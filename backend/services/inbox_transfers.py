"""A transferencia entre contas do dono, no Aprovar.

Reconhecer que um movimento e do proprio dono (o "sou eu" aprendido, a BTG
Investimentos), achar a outra ponta, e fazer de uma despesa/receita ja gravada
a transferencia quando a outra ponta chega (`absorb_recorded_side()`), com a
revisao que sai sozinha quando as duas pontas foram observadas.

Saiu de services/inbox.py (2026-11-13), que continua reexportando todos estes
nomes. Depende so de services/inbox_store.py e services/inbox_rules.py.
"""


from db import row_to_dict
from money import to_cents
from services import recorded_snapshot, review
from services.inbox_rules import (
    BROKERAGE_APP,
    CLAIM_NOTIFY,
    FIELD_OF_NEED,
    ISSUER_ALIASES,
    ISSUER_OF_APP,
    KIND_SHAPES,
    _date_gap,
    _is_movement_source,
    _jlist,
    _mentions,
    _pick_closest,
    _shift,
    _side_need,
    _source_direction,
    counterparties_conflict,
    issuer_of_institution,
    item_dict,
    recompute_needs,
    transfer_hint_key,
)
from services.inbox_store import (
    CLAIM_PLUGGY,
    SOURCE,
    TRANSFER_CATEGORY,
    _active_accounts,
    _hint_usable,
    _movement_sources,
    _pending_items,
    _source_directions,
    fetch_hint,
    fetch_item,
    item_detections,
    open_finance_sources,
    save_item,
)

APPROVED = "APPROVED"


# As duas pontas de uma transferencia entre contas proprias: Pix e TED caem no
# mesmo dia; um dia de folga cobre a virada da meia-noite e o D+1 do banco.
TRANSFER_MATCH_DAYS = 1


def _brl_active_account(conn, current_user_id, account_id):
    return conn.execute(
        """
        SELECT id, name FROM accounts
        WHERE id = ? AND user_id = ? AND archived_at IS NULL AND COALESCE(currency, 'BRL') = 'BRL'
        """,
        (account_id, current_user_id),
    ).fetchone()


def _brl_account(conn, current_user_id, account_id):
    """Uma conta em reais do dono (arquivada tambem)."""
    return conn.execute(
        "SELECT id FROM accounts WHERE id = ? AND user_id = ? AND COALESCE(currency, 'BRL') = 'BRL'",
        (account_id, current_user_id),
    ).fetchone()


def transfer_partner(conn, current_user_id, *, account_id, direction, cents, date_text, detection=None):
    """O item pendente que e a outra ponta de uma transferencia entre contas do
    dono: saida numa conta e entrada noutra (ou o contrario), mesmo valor, ate
    TRANSFER_MATCH_DAYS dias; ou uma transferencia pendente sem esta ponta (a
    conta deste lado vazia, palpite, ou esta mesma). Uma ponta cujo outro lado
    contradiz o desta (`detection`: outro CPF, outro nome) nao e o par."""
    if not account_id or not _brl_active_account(conn, current_user_id, account_id):
        return None
    other_direction = "IN" if direction == "OUT" else "OUT"
    found = []
    for row in _pending_items(conn, current_user_id, cents=cents, date_text=date_text, days=TRANSFER_MATCH_DAYS):
        if int(row["installments"] or 1) != 1 or to_cents(row["amount"]) != cents:
            continue
        if detection and any(
            counterparties_conflict(detection, source)
            for source in _movement_sources(conn, current_user_id, row["id"])
        ):
            continue
        edited = set(_jlist(row["edited"]))
        if row["entry_type"] in ("EXPENSE", "INCOME"):
            if "entry_type" in edited or row["direction"] != other_direction:
                continue
            if not row["account_id"] or row["account_id"] == account_id:
                continue
            if not _brl_active_account(conn, current_user_id, row["account_id"]):
                continue
            found.append(row)
        elif row["entry_type"] == "TRANSFER":
            side_field = FIELD_OF_NEED[_side_need(direction)]
            other_field = FIELD_OF_NEED[_side_need(other_direction)]
            side_account = row[side_field]
            side_open = side_account is None or (
                _side_need(direction) in _jlist(row["guessed"]) and side_field not in edited
            )
            if side_account != account_id and not side_open:
                continue
            if row[other_field] == account_id:
                continue
            if direction in _source_directions(conn, current_user_id, row["id"]):
                continue
            found.append(row)
    return _pick_closest(found, date_text)


def make_transfer(conn, current_user_id, item, *, account_id, direction, guessed=False):
    """O item vira transferencia: a nova ponta (account_id, direction) entra.
    `guessed`: a conta da nova ponta e um palpite (o dono confirma). Num item
    que ja e transferencia (de uma ponta so, o outro lado reconhecido como o
    dono), a nova ponta preenche o lado dela."""
    if item["entry_type"] == "TRANSFER":
        need = _side_need(direction)
        field = FIELD_OF_NEED[need]
        if field in set(item.get("edited") or []):
            return item
        changes = {field: account_id}
        guesses = [value for value in item.get("guessed") or [] if value != need]
        if guessed:
            guesses.append(need)
        changes["guessed"] = guesses
        changes["needs"] = recompute_needs({**item, **changes})
        if "description" not in set(item.get("edited") or []):
            merged = {**item, **changes}
            changes["description"] = _transfer_description(
                conn, current_user_id, merged["account_id"], merged["transfer_account_id"], item.get("description"),
            )
        return save_item(conn, current_user_id, item, changes)
    if direction == "OUT":
        origin, destination = account_id, item["account_id"]
    else:
        origin, destination = item["account_id"], account_id
    changes = {
        "entry_type": "TRANSFER",
        "direction": "OUT",
        "account_id": origin,
        "transfer_account_id": destination,
        "card_id": None,
        "reason": "own_transfer",
    }
    edited = set(item.get("edited") or [])
    if "category" not in edited:
        changes.update({"category": TRANSFER_CATEGORY, "category_id": None})
    if "description" not in edited:
        changes["description"] = _transfer_description(
            conn, current_user_id, origin, destination, item.get("description"),
        )
    merged = {**item, **changes}
    changes["needs"] = recompute_needs(merged)
    # Um palpite continua palpite do lado em que estava: o dono confirma.
    guesses = []
    if "account" in (item.get("guessed") or []):
        guesses.append("transfer_account" if direction == "OUT" else "account")
    if guessed:
        guesses.append("account" if direction == "OUT" else "transfer_account")
    changes["guessed"] = guesses
    return save_item(conn, current_user_id, item, changes)


def _transfer_description(conn, current_user_id, origin, destination, fallback=None):
    """"Origem -> Destino" com os nomes das contas; com um lado so, o que a
    notificacao disse."""
    if not origin or not destination:
        return fallback
    names = [
        (_brl_active_account(conn, current_user_id, value) or {"name": "?"})["name"]
        for value in (origin, destination)
    ]
    return f"{names[0]} -> {names[1]}"


def guess_other_side(conn, current_user_id, detection, own_account_id):
    """A conta do dono do outro lado de uma transferencia de uma ponta so: a
    unica conta ativa em reais da instituicao que a notificacao citou (a
    corretora nao cita nenhuma: o outro lado e o banco do mesmo grupo)."""
    issuer = issuer_of_institution(detection.get("counterparty_bank"))
    if not issuer and detection.get("app") == BROKERAGE_APP:
        issuer = ISSUER_OF_APP[BROKERAGE_APP]
    if not issuer:
        return None
    found = [
        row for row in _active_accounts(conn, current_user_id)
        if row["id"] != own_account_id and (row["currency"] or "BRL") == "BRL"
        and (_mentions(row["name"], ISSUER_ALIASES[issuer]) or _mentions(row["institution"], ISSUER_ALIASES[issuer]))
    ]
    return found[0]["id"] if len(found) == 1 else None


def remembered_transfer(conn, current_user_id, *, account_id, direction, description):
    """A transferencia que o dono mandou lembrar para esta descricao nesta conta."""
    key = transfer_hint_key(account_id, direction, description)
    hint = fetch_hint(conn, current_user_id, key)
    if not hint or hint["entry_type"] != "TRANSFER" or not _hint_usable(conn, current_user_id, hint):
        return None
    return hint


def approved_transfer_awaiting(conn, current_user_id, *, account_id, direction, cents, date_text, channel=None):
    """Uma transferencia que o dono ja decidiu aqui (aprovou, ou disse "e esta")
    com uma ponta so, e este movimento e a outra (a outra conta notificou
    depois): confirma a transferencia, nao e um movimento
    novo."""
    rows = conn.execute(
        """
        SELECT i.id, i.target_id, i.created_at, t.date AS occurred_at,
               t.account_id AS origin, t.transfer_account_id AS destination, t.amount AS transfer_amount
        FROM inbox_items i
        JOIN transactions t ON t.id = i.target_id AND t.user_id = i.user_id
        WHERE i.user_id = ? AND i.state IN ('APPROVED', 'MATCHED')
          AND i.target_table = 'transactions' AND t.type = 'TRANSFER'
          AND t.date BETWEEN ? AND ?
        """,
        (current_user_id, _shift(date_text, -TRANSFER_MATCH_DAYS), _shift(date_text, TRANSFER_MATCH_DAYS)),
    ).fetchall()
    found = []
    for row in rows:
        if to_cents(row["transfer_amount"]) != cents:
            continue
        side_account = row["destination"] if direction == "IN" else row["origin"]
        if side_account != account_id:
            continue
        if direction in _source_directions(conn, current_user_id, row["id"], channel):
            continue
        found.append(row)
    return _pick_closest(found, date_text)


def _side_sources(conn, current_user_id, item_id):
    """As observacoes vivas de um item: as notificacoes fonte e as transacoes
    da Pluggy fonte (a sumida nao conta)."""
    detections = [
        {**row_to_dict(row), "channel": CLAIM_NOTIFY}
        for row in item_detections(conn, current_user_id, item_id) if row["role"] == SOURCE
    ]
    rows = [
        {**row_to_dict(row), "channel": CLAIM_PLUGGY}
        for row in open_finance_sources(conn, current_user_id, item_id, roles=(SOURCE,))
        if (row["conflict"] or "") != "vanished"
    ]
    return detections + rows


def _source_untouched(conn, current_user_id, item, source):
    """Intocado pelo snapshot (nunca por needs_review): o do item, se a fonte e
    uma notificacao; o da transacao da Pluggy, se e ela. A notificacao que entrou
    num item que a Pluggy gravou (o item sem snapshot proprio) nao gravou nada:
    None, quem decide e a linha da Pluggy (sessao 5, semente 158)."""
    if source["channel"] == CLAIM_NOTIFY:
        if not item.get("recorded_snapshot"):
            return None
        return recorded_snapshot.snapshot_unchanged(conn, current_user_id, item)
    return recorded_snapshot.untouched(conn, current_user_id, source)


def absorb_recorded_side(conn, current_user_id, *, account_id, direction, cents, date_text, occurred_at=None,
                         counterparty=None, description=None):
    """Defeito I: a outra ponta de uma transferencia entre
    contas do dono chega (notificacao ou Pluggy) e a primeira ja virou
    despesa/receita sozinha. Se aquela linha esta como nasceu, ela vira a
    transferencia: uma linha so, nunca despesa numa conta e receita na outra.

    O par: lancamento gravado de um item (APPROVED) do tipo oposto, mesmos
    centavos, outra conta ativa em reais, ate TRANSFER_MATCH_DAYS dias, sem
    divisao, o item com UM lado (no maximo uma observacao por canal: a
    notificacao e a Pluggy que a confirmou), todas movimento (Pix/TED; nunca
    compra ou boleto), contrapartes que podem ser a mesma pessoa. Devolve o item ja
    transferencia (o chamador liga a nova observacao e chama finish_absorb), ou None."""
    if not account_id or not _brl_active_account(conn, current_user_id, account_id):
        return None
    twin_type = "EXPENSE" if direction == "IN" else "INCOME"
    rows = conn.execute(
        """
        SELECT i.*, t.account_id AS twin_account, t.date AS twin_date, t.occurred_at AS twin_occurred
        FROM inbox_items i
        JOIN transactions t ON t.id = i.target_id AND t.user_id = i.user_id
        WHERE i.user_id = ? AND i.state = 'APPROVED' AND i.target_table = 'transactions'
          AND t.type = ? AND t.account_id <> ? AND t.share_mode IS NULL
          AND CAST(ROUND(t.amount * 100) AS INTEGER) = ? AND t.date BETWEEN ? AND ?
        """,
        (current_user_id, twin_type, account_id, int(cents), _shift(date_text, -TRANSFER_MATCH_DAYS),
         _shift(date_text, TRANSFER_MATCH_DAYS)),
    ).fetchall()
    candidates = []
    for row in rows:
        if not _brl_active_account(conn, current_user_id, row["twin_account"]):
            continue
        sources = _side_sources(conn, current_user_id, row["id"])
        # Um lado so (a notificacao e a Pluggy da mesma ponta contam como um):
        # no maximo uma observacao por canal, todas movimento, na mesma direcao.
        channels = [source["channel"] for source in sources]
        if not sources or len(channels) != len(set(channels)):
            continue
        if not all(_is_movement_source(source) for source in sources):
            continue
        if len({_source_direction(source) for source in sources}) != 1:
            continue
        if counterparty and any(counterparties_conflict(counterparty, source) for source in sources):
            continue
        item = item_dict(row)
        checks = [_source_untouched(conn, current_user_id, item, source) for source in sources]
        if False in checks or True not in checks:
            continue
        candidates.append((row, item))
    if not candidates:
        return None
    row, item = sorted(
        candidates, key=lambda pair: (_date_gap(pair[0]["twin_date"], date_text), pair[0]["twin_date"], pair[0]["id"]),
    )[0]
    if direction == "OUT":
        origin, destination, day, occurred = account_id, row["twin_account"], date_text, occurred_at
    else:
        origin, destination, day, occurred = row["twin_account"], account_id, row["twin_date"], row["twin_occurred"]
    occurred = occurred or day
    text = _transfer_description(conn, current_user_id, origin, destination, description or item.get("description"))
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = 'transactions' AND target_id = ?",
        (current_user_id, item["target_id"]),
    )
    conn.execute(
        """
        UPDATE transactions SET type = 'TRANSFER', account_id = ?, transfer_account_id = ?, date = ?, occurred_at = ?,
            category = ?, category_id = NULL, description = ?, card_id = NULL
        WHERE id = ? AND user_id = ?
        """,
        (origin, destination, day, occurred, TRANSFER_CATEGORY, text, item["target_id"], current_user_id),
    )
    # O palpite continua palpite do lado em que estava.
    old_side = _side_need("IN" if direction == "OUT" else "OUT")
    guessed = [old_side] if "account" in (item.get("guessed") or []) else []
    save_item(conn, current_user_id, item, {
        "entry_type": "TRANSFER", "direction": "OUT", "account_id": origin, "transfer_account_id": destination,
        "card_id": None, "occurred_at": occurred, "category": TRANSFER_CATEGORY, "category_id": None,
        "description": text, "reason": "own_transfer", "guessed": guessed, "needs": [],
    })
    return item


def finish_absorb(conn, current_user_id, item):
    """Depois de ligar a nova observacao: os snapshots passam a ser o da
    transferencia (o app mudou a linha, nao o dono); com a Pluggy numa das
    pontas, sai da revisao (settle_transfer_review)."""
    recorded_snapshot.mark_auto_recorded(conn, current_user_id, item["id"], "transactions", item["target_id"])
    recorded_snapshot.refresh_snapshots(conn, current_user_id, item["id"], "transactions", item["target_id"])
    settle_transfer_review(conn, current_user_id, item["id"])


def transfer_confirmed(conn, current_user_id, item_id):
    """As duas pontas da transferencia estao no app (uma saida e uma entrada
    observadas) e ao menos uma veio da Pluggy: nao ha o que
    revisar. A sumida e a REMOVED nao contam."""
    directions, pluggy = set(), False
    for row in conn.execute(
        """
        SELECT direction FROM open_finance_transactions
        WHERE user_id = ? AND item_id = ? AND role IN ('SOURCE', 'MATCHED') AND COALESCE(conflict, '') <> 'vanished'
        """,
        (current_user_id, item_id),
    ).fetchall():
        directions.add(row["direction"])
        pluggy = True
    for row in conn.execute(
        "SELECT kind FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE'",
        (current_user_id, item_id),
    ).fetchall():
        if row["kind"] in KIND_SHAPES:
            directions.add(KIND_SHAPES[row["kind"]][0])
    return pluggy and directions >= {"IN", "OUT"}


def settle_transfer_review(conn, current_user_id, item_id):
    """A transferencia gravada sozinha com as duas pontas confirmadas sai da
    revisao. A conta global revisa na tela dela; a editada pelo dono fica como
    ele deixou. Devolve True se saiu."""
    row = fetch_item(conn, current_user_id, item_id)
    if not row or row["state"] != APPROVED or row["target_table"] != "transactions" or not row["target_id"]:
        return False
    target = conn.execute(
        "SELECT type, account_id, transfer_account_id, needs_review FROM transactions WHERE id = ? AND user_id = ?",
        (row["target_id"], current_user_id),
    ).fetchone()
    if not target or target["type"] != "TRANSFER" or not target["needs_review"]:
        return False
    for account_id in (target["account_id"], target["transfer_account_id"]):
        if not account_id or not _brl_account(conn, current_user_id, account_id):
            return False
    if not transfer_confirmed(conn, current_user_id, item_id):
        return False
    item = item_dict(row)
    sources = [
        row_to_dict(source) for source in open_finance_sources(conn, current_user_id, item_id, roles=(SOURCE, "MATCHED"))
        if source["recorded_snapshot"]
    ]
    if not (
        recorded_snapshot.snapshot_unchanged(conn, current_user_id, item)
        or any(recorded_snapshot.untouched(conn, current_user_id, source) for source in sources)
    ):
        return False
    review.clear(conn, current_user_id, "transactions", row["target_id"])
    return True
