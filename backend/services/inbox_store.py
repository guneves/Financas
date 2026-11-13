"""O Aprovar por dentro: ler e gravar itens, e as buscas que o motor faz no banco.

Preferencias (036), as leituras de itens, deteccoes, contas e cartoes, de qual
cartao ou conta e um aviso (o lembrado, o palpite, o dono decide), a categoria
sugerida, gravar um item, os lancamentos parecidos ja gravados e o "lembrar".
Nada aqui decide o que fazer com um aviso: isso e o motor, em services/inbox.py
(notificacoes, Open Finance, par aproximado) e em services/inbox_transfers.py.

Saiu de services/inbox.py (2026-11-13), que continua reexportando todos estes
nomes: `inbox.fetch_item`, `inbox.save_item`... valem como antes.
"""

import json

import statement_import
from config import (
    INBOX_MATCH_DAYS,
)
from db import new_id, row_to_dict, utc_timestamp
from money import to_cents
from services.import_rules import (
    DEFAULT_IMPORT_CATEGORIES,
    import_default_category,
    import_rules_for_matching,
)
from services.inbox_rules import (
    BROKERAGE_APP,
    CLAIM_NOTIFY,
    FIELD_OF_NEED,
    ISSUER_ALIASES,
    ISSUER_OF_APP,
    KIND_SHAPES,
    MOVEMENT_KINDS,
    PURCHASE_KINDS,
    REQUIRED_TARGETS,
    SELF_DOC_PREFIX,
    SELF_NAME_PREFIX,
    _amount_matches,
    _date_gap,
    _installment_count,
    _jdump,
    _mentions,
    _shift,
    bank_of_row,
    candidate_kind,
    detection_hint_key,
    detection_hint_label,
    issuer_of,
    item_dict,
    normalized,
    pick_card,
    recompute_needs,
    relevant_guesses,
    self_keys,
)

PENDING = "PENDING"


SOURCE = "SOURCE"


# O mesmo de routes/accounts.py: a categoria de uma transferencia.
TRANSFER_CATEGORY = "Transferencia"


def is_self_counterparty(conn, current_user_id, detection):
    """O outro lado deste Pix e o proprio dono (aprendido de uma transferencia
    que ele ja teve entre as contas)? Pelo CPF quando a notificacao o mostra;
    pelo nome so quando ela nao mostra CPF nenhum."""
    if detection.get("kind") not in MOVEMENT_KINDS:
        return False
    if detection.get("app") == BROKERAGE_APP:
        return True
    if detection.get("counterparty_doc"):
        return fetch_hint(conn, current_user_id, SELF_DOC_PREFIX + detection["counterparty_doc"]) is not None
    name = normalized(detection.get("counterparty"))
    return bool(name) and fetch_hint(conn, current_user_id, SELF_NAME_PREFIX + name) is not None


def learn_self(conn, current_user_id, detections):
    """Lembra o outro lado destas pontas como o dono (CPF e nome)."""
    for detection in detections:
        if detection.get("kind") not in MOVEMENT_KINDS:
            continue
        for key in self_keys(detection):
            remember(conn, current_user_id, key, detection.get("counterparty"), entry_type="TRANSFER")


def _movement_sources(conn, current_user_id, item_id):
    return [
        row_to_dict(row) for row in item_detections(conn, current_user_id, item_id)
        if row["role"] == SOURCE and row["kind"] in MOVEMENT_KINDS
    ]


def fetch_item(conn, current_user_id, item_id):
    return conn.execute(
        "SELECT * FROM inbox_items WHERE id = ? AND user_id = ?",
        (item_id, current_user_id),
    ).fetchone()


def item_detections(conn, current_user_id, item_id):
    return conn.execute(
        """
        SELECT * FROM notify_detections
        WHERE user_id = ? AND item_id = ?
        ORDER BY posted_ms, id
        """,
        (current_user_id, item_id),
    ).fetchall()


def pending_count(conn, current_user_id):
    return conn.execute(
        "SELECT COUNT(*) FROM inbox_items WHERE user_id = ? AND state = 'PENDING'",
        (current_user_id,),
    ).fetchone()[0]


def _active_accounts(conn, current_user_id):
    return conn.execute(
        """
        SELECT id, name, type, institution, currency FROM accounts
        WHERE user_id = ? AND archived_at IS NULL
        ORDER BY is_default DESC, name
        """,
        (current_user_id,),
    ).fetchall()


def _cards(conn, current_user_id):
    """Os cartoes onde uma compra pode ir para a fatura: ativos e com credito (041)."""
    return conn.execute(
        """
        SELECT id, name FROM credit_cards
        WHERE user_id = ? AND archived_at IS NULL AND credit_enabled = 1
        ORDER BY name
        """,
        (current_user_id,),
    ).fetchall()


def _debit_cards(conn, current_user_id):
    """Os cartoes com a funcao debito (041), cuja conta ainda esta ativa."""
    return conn.execute(
        """
        SELECT c.id, c.name, c.credit_enabled, c.debit_account_id
        FROM credit_cards c JOIN accounts a ON a.id = c.debit_account_id AND a.user_id = c.user_id
        WHERE c.user_id = ? AND c.archived_at IS NULL AND a.archived_at IS NULL
        ORDER BY c.name
        """,
        (current_user_id,),
    ).fetchall()


def fetch_hint(conn, current_user_id, key):
    if not key:
        return None
    return conn.execute(
        "SELECT * FROM inbox_hints WHERE user_id = ? AND hint_key = ?",
        (current_user_id, key),
    ).fetchone()


def _hint_usable(conn, current_user_id, hint):
    """A escolha lembrada ainda aponta para uma conta ativa ou um cartao do dono?"""
    if not hint:
        return False
    if hint["entry_type"] == "CARD":
        return bool(hint["card_id"]) and conn.execute(
            """
            SELECT 1 FROM credit_cards
            WHERE id = ? AND user_id = ? AND archived_at IS NULL AND credit_enabled = 1
            """,
            (hint["card_id"], current_user_id),
        ).fetchone() is not None
    for account_id in (hint["account_id"], hint["transfer_account_id"]):
        if account_id and not conn.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ? AND archived_at IS NULL",
            (account_id, current_user_id),
        ).fetchone():
            return False
    return bool(hint["account_id"] or hint["transfer_account_id"])


def ambiguous_target(conn, current_user_id, key, entry_type):
    """A notificacao nao diz o final do cartao e o dono tem mais de uma conta
    (ou cartao, para CARD) ativa naquele banco: a escolha nao fica lembrada e
    o item pergunta toda vez. Contas/cartoes sem banco nao entram na conta;
    com menos de dois no banco, vale o de sempre (lembrar, palpite)."""
    parts = (key or "").split(":", 3)
    if len(parts) != 4 or parts[0] != "notify" or parts[3] != "-" or entry_type not in REQUIRED_TARGETS:
        return False
    issuer = ISSUER_OF_APP.get(parts[1])
    if not issuer or entry_type is None or entry_type == "TRANSFER":
        return False
    if entry_type == "CARD":
        rows = conn.execute(
            "SELECT * FROM credit_cards WHERE user_id = ? AND archived_at IS NULL", (current_user_id,)
        ).fetchall()
    else:
        ids = [row["id"] for row in _usable_accounts(conn, current_user_id, parts[1])]
        rows = [
            row for row in conn.execute("SELECT * FROM accounts WHERE user_id = ?", (current_user_id,)).fetchall()
            if row["id"] in ids
        ]
    return sum(1 for row in rows if bank_of_row(row) == issuer) > 1


def guess_card(conn, current_user_id, detection):
    return pick_card(_cards(conn, current_user_id), detection)


def debit_card_for(conn, current_user_id, detection):
    """O cartao com debito (041) que esta compra nomeia, ou None. So pelo final,
    pelo nome ou pelo emissor: o unico cartao do dono nao basta, porque a compra
    pode ter sido no credito de outro banco."""
    if detection.get("kind") not in PURCHASE_KINDS:
        return None
    cards = _debit_cards(conn, current_user_id)
    card_id = pick_card(cards, detection, only_one_counts=False)
    return next((card for card in cards if card["id"] == card_id), None)


def _usable_accounts(conn, current_user_id, app):
    """As contas onde a notificacao deste app pode cair: ativas, em reais, e
    a Corretora so para o app da corretora."""
    accounts = [row for row in _active_accounts(conn, current_user_id) if (row["currency"] or "BRL") == "BRL"]
    brokerage_app = app == BROKERAGE_APP
    return [row for row in accounts if (row["type"] == "BROKERAGE") == brokerage_app]


def guess_account(conn, current_user_id, detection):
    usable = _usable_accounts(conn, current_user_id, detection.get("app"))
    issuer = issuer_of(detection)
    if issuer in ISSUER_ALIASES:
        by_issuer = [
            row for row in usable
            if _mentions(row["name"], ISSUER_ALIASES[issuer])
            or _mentions(row["institution"], ISSUER_ALIASES[issuer])
        ]
        if len(by_issuer) == 1:
            return by_issuer[0]["id"]
    if len(usable) == 1:
        return usable[0]["id"]
    return None


def resolve_detection(conn, current_user_id, detection):
    """O rascunho de cartao/conta de uma deteccao: o que o dono lembrou, senao
    um palpite marcado, senao o que ele precisa escolher."""
    direction, entry_type, _method = KIND_SHAPES[detection["kind"]]
    key = detection_hint_key(detection)
    draft = {
        "direction": direction,
        "entry_type": entry_type,
        "account_id": None,
        "card_id": None,
        "transfer_account_id": None,
        "needs": [],
        "guessed": [],
        "hint_key": key,
        "hint_label": detection_hint_label(detection),
        "remembered": False,
    }
    hint = fetch_hint(conn, current_user_id, key)
    if _hint_usable(conn, current_user_id, hint) and hint["entry_type"] != "TRANSFER":
        # O tipo vem da notificacao quando ela diz (um Pix enviado e uma saida,
        # um recebido uma entrada, na mesma conta lembrada); so a compra sem
        # credito/debito leva o tipo que o dono escolheu.
        remembered_type = hint["entry_type"] if entry_type is None else entry_type
        if (remembered_type == "CARD") == bool(hint["card_id"]) and not ambiguous_target(
            conn, current_user_id, key, remembered_type,
        ):
            draft.update({
                "entry_type": remembered_type,
                "account_id": hint["account_id"] if remembered_type != "CARD" else None,
                "card_id": hint["card_id"] if remembered_type == "CARD" else None,
                "remembered": True,
            })
            return draft
    # Um cartao com a funcao debito (041) que a notificacao nomeia: a compra no
    # debito sai da conta dele. So debito (o Flash), a compra sem metodo ja e
    # despesa nessa conta; com os dois, a conta fica pronta para quando o dono
    # disser debito. Palpite marcado: o dono confirma uma vez, depois fica lembrado.
    debit_card = None
    if entry_type in (None, "EXPENSE"):
        debit_card = debit_card_for(conn, current_user_id, detection)
    if debit_card is not None:
        if entry_type is None and not debit_card["credit_enabled"]:
            entry_type = draft["entry_type"] = "EXPENSE"
        draft["account_id"] = debit_card["debit_account_id"]
        draft["guessed"].append("account")
    # Sem metodo (o dono ainda vai dizer credito ou debito), os dois palpites
    # ficam prontos: escolhido o metodo, o cartao ou a conta ja esta la.
    # Ambiguo (mais de um no banco, sem o final): nem palpite, o dono escolhe.
    if entry_type in (None, "CARD") and not ambiguous_target(conn, current_user_id, key, "CARD"):
        draft["card_id"] = guess_card(conn, current_user_id, detection)
        if draft["card_id"]:
            draft["guessed"].append("card")
    if debit_card is None and entry_type in (None, "EXPENSE", "INCOME") and not ambiguous_target(
        conn, current_user_id, key, entry_type or "EXPENSE",
    ):
        draft["account_id"] = guess_account(conn, current_user_id, detection)
        if draft["account_id"]:
            draft["guessed"].append("account")
    draft["needs"] = recompute_needs(draft)
    return draft


def confirm_targets(item, always_ask=False):
    """O que o dono confirma antes do item ficar pronto: os palpites que contam
    e, com "Sempre perguntar a conta/cartao", tambem o cartao/conta lembrado
    (so o que ele mesmo escolheu neste item fica de fora)."""
    confirm = relevant_guesses(item)
    if not always_ask or item.get("state", PENDING) != PENDING:
        return confirm
    edited = set(item.get("edited") or [])
    for need in REQUIRED_TARGETS.get(item.get("entry_type"), ()):
        field = FIELD_OF_NEED.get(need)
        if field and item.get(field) and field not in edited and need not in confirm:
            confirm.append(need)
    return confirm


def suggest_category(conn, current_user_id, description, entry_type, amount, account_id=None, rules=None):
    """(nome, id): a regra do extrato que casa com a descricao, senao a padrao."""
    if entry_type == "TRANSFER":
        return TRANSFER_CATEGORY, None
    transaction_type = "INCOME" if entry_type == "INCOME" else "EXPENSE"
    if rules is None:
        rules = import_rules_for_matching(conn, current_user_id)
    rule = statement_import.first_matching_rule(
        rules, description or "", transaction_type, amount, account_id if entry_type != "CARD" else None
    )
    if rule:
        return rule["category"], rule["category_id"]
    name, category_id = import_default_category(conn, current_user_id, transaction_type)
    return name or DEFAULT_IMPORT_CATEGORIES[transaction_type], category_id


ITEM_COLUMNS = (
    "state", "reason", "entry_type", "direction", "amount", "currency", "installments",
    "occurred_at", "source_occurred_at", "description", "category", "category_id",
    "account_id", "card_id", "transfer_account_id", "needs", "guessed", "edited",
    "hint_key", "hint_label", "candidates", "client_key", "target_table", "target_id",
    "decided_at", "recurring_off", "transfer_amount",
)


def insert_item(conn, current_user_id, values):
    values = dict(values)
    values.setdefault("state", PENDING)
    values.setdefault("currency", "BRL")
    values.setdefault("installments", 1)
    values.setdefault("source_occurred_at", values["occurred_at"])
    item_id = new_id()
    row = {"id": item_id, "user_id": current_user_id}
    for column in ITEM_COLUMNS:
        if column in values and column != "candidates":
            value = values[column]
            row[column] = _jdump(value) if column in ("needs", "guessed", "edited") else value
    if "candidates" in values:
        row["candidates"] = json.dumps(values["candidates"]) if values["candidates"] else None
    conn.execute(
        f"INSERT INTO inbox_items ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
        tuple(row.values()),
    )
    return item_id


def save_item(conn, current_user_id, item, changes, *, bump=True):
    """Grava `changes` no item (um dict de item_dict) e sobe a versao."""
    if not changes:
        return item
    row = {}
    for column, value in changes.items():
        if column in ("needs", "guessed", "edited"):
            row[column] = _jdump(value)
        elif column == "candidates":
            row[column] = json.dumps(value) if value else None
        else:
            row[column] = value
    row["updated_at"] = utc_timestamp()
    assignments = ", ".join(f"{column} = ?" for column in row)
    version_sql = ", version = version + 1" if bump else ""
    conn.execute(
        f"UPDATE inbox_items SET {assignments}{version_sql} WHERE id = ? AND user_id = ?",
        (*row.values(), item["id"], current_user_id),
    )
    item.update(changes)
    if bump:
        item["version"] = int(item.get("version") or 1) + 1
    return item


def _pending_items(conn, current_user_id, *, cents, date_text, days, direction=None):
    sql = """
        SELECT * FROM inbox_items
        WHERE user_id = ? AND state = 'PENDING'
          AND substr(occurred_at, 1, 10) BETWEEN ? AND ?
    """
    params = [current_user_id, _shift(date_text, -days), _shift(date_text, days)]
    if direction:
        sql += " AND direction = ?"
        params.append(direction)
    rows = conn.execute(sql, params).fetchall()
    return [row for row in rows if _amount_matches(row, cents)]


def _has_detection_source(conn, current_user_id, item_id):
    """O item ainda tem uma fonte viva: uma notificacao ou uma transacao do
    Open Finance (043) que o alimenta."""
    return conn.execute(
        "SELECT 1 FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE' LIMIT 1",
        (current_user_id, item_id),
    ).fetchone() is not None or bool(open_finance_sources(conn, current_user_id, item_id, roles=(SOURCE,)))


def _has_notification_source(conn, current_user_id, item_id):
    return conn.execute(
        "SELECT 1 FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE' LIMIT 1",
        (current_user_id, item_id),
    ).fetchone() is not None


def open_finance_sources(conn, current_user_id, item_id, roles=None):
    """As transacoes do Open Finance ligadas a um item (043)."""
    sql = "SELECT * FROM open_finance_transactions WHERE user_id = ? AND item_id = ?"
    params = [current_user_id, item_id]
    if roles:
        sql += f" AND role IN ({', '.join('?' for _ in roles)})"
        params.extend(roles)
    return conn.execute(sql + " ORDER BY date, created_at, id", params).fetchall()


def _source_directions(conn, current_user_id, item_id, channel=None):
    """Os lados que as fontes do item ja observaram; `channel` (CLAIM_NOTIFY ou
    CLAIM_PLUGGY) olha so as daquele canal: a vaga e por canal e lado (I2)."""
    directions = set()
    if channel == CLAIM_PLUGGY:
        return {row["direction"] for row in open_finance_sources(conn, current_user_id, item_id, roles=(SOURCE,))}
    for row in conn.execute(
        "SELECT kind FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE'",
        (current_user_id, item_id),
    ).fetchall():
        if row["kind"] in KIND_SHAPES:
            directions.add(KIND_SHAPES[row["kind"]][0])
    if channel == CLAIM_NOTIFY:
        return directions
    for row in open_finance_sources(conn, current_user_id, item_id, roles=(SOURCE,)):
        directions.add(row["direction"])
    return directions


CLAIM_PLUGGY = "pluggy"


def pluggy_claimed(conn, current_user_id, table, target_id, exclude_item_id=None):
    """Uma transacao viva da Pluggy aponta para este lancamento (a que sumiu do
    banco, `vanished`, e a REMOVED nao contam). Um digitado pelo dono nao tem
    dono: e livre para os dois canais."""
    sql = """
        SELECT 1 FROM open_finance_transactions
        WHERE user_id = ? AND target_table = ? AND target_id = ? AND role <> 'REMOVED'
          AND COALESCE(conflict, '') <> 'vanished'
    """
    params = [current_user_id, table, target_id]
    if exclude_item_id:
        sql += " AND COALESCE(item_id, '') <> ?"
        params.append(exclude_item_id)
    return conn.execute(sql + " LIMIT 1", params).fetchone() is not None


def notification_claimed(conn, current_user_id, table, target_id, exclude_item_id=None):
    """Uma notificacao viva (fonte, par ou ligada) aponta para este lancamento."""
    sql = """
        SELECT 1 FROM notify_detections
        WHERE user_id = ? AND target_table = ? AND target_id = ? AND role IN ('SOURCE', 'PAIRED', 'MATCHED')
    """
    params = [current_user_id, table, target_id]
    if exclude_item_id:
        sql += " AND COALESCE(item_id, '') <> ?"
        params.append(exclude_item_id)
    return conn.execute(sql + " LIMIT 1", params).fetchone() is not None


def claimed(conn, current_user_id, channel, table, target_id, exclude_item_id=None):
    """O lancamento ja e de outra observacao deste canal (I2: uma por canal)."""
    check = pluggy_claimed if channel == CLAIM_PLUGGY else notification_claimed
    return check(conn, current_user_id, table, target_id, exclude_item_id)


def existing_rows(conn, current_user_id, *, entry_type, direction, cents, date_text,
                  account_id=None, card_id=None, days=None, claimed_by=None):
    """Lancamentos ja gravados que podem ser este movimento.

    Mesmo valor e data a `days` dias; na conta/cartao, quando se sabe.
    `claimed_by` ("notify" ou "pluggy"): fica de fora o que outra observacao do
    MESMO canal ja explica (duas compras de mesmo valor no mesmo dia continuam
    duas); a de outro canal nao esconde nada (a notificacao nunca segura a Pluggy).
    """
    days = INBOX_MATCH_DAYS if days is None else days
    start, end = _shift(date_text, -days), _shift(date_text, days)
    found = []
    if entry_type in (None, "CARD"):
        # Um credito no cartao (o Open Finance traz estornos) procura estornos;
        # o resto, compras.
        card_kind = "REFUND" if entry_type == "CARD" and direction == "IN" else "PURCHASE"
        sql = """
            SELECT id, purchase_date AS date, amount, installment_info, card_id FROM cc_expenses e
            WHERE user_id = ? AND purchase_date BETWEEN ? AND ?
              AND installment_info LIKE '1/%' AND kind = ?
        """
        params = [current_user_id, start, end, card_kind]
        if card_id:
            sql += " AND card_id = ?"
            params.append(card_id)
        for row in conn.execute(sql, params).fetchall():
            count = _installment_count(row["installment_info"])
            if to_cents(row["amount"]) == cents or abs(to_cents(row["amount"]) * count - cents) <= count:
                found.append({"table": "cc_expenses", "id": row["id"], "kind": "card_purchase", "date": row["date"]})
    if entry_type in (None, "EXPENSE", "INCOME", "TRANSFER"):
        sql = """
            SELECT id, date, type, source_type, account_id, transfer_account_id FROM transactions
            WHERE user_id = ? AND date BETWEEN ? AND ?
              AND CAST(ROUND(amount * 100) AS INTEGER) = ?
        """
        params = [current_user_id, start, end, cents]
        for row in conn.execute(sql, params).fetchall():
            if row["type"] == "TRANSFER":
                side = row["transfer_account_id"] if direction == "IN" else row["account_id"]
                if account_id and side != account_id:
                    continue
            else:
                if row["type"] != ("INCOME" if direction == "IN" else "EXPENSE"):
                    continue
                if account_id and row["account_id"] != account_id:
                    continue
            found.append({"table": "transactions", "id": row["id"], "kind": candidate_kind(row), "date": row["date"]})
    if claimed_by:
        found = [
            entry for entry in found if not claimed(conn, current_user_id, claimed_by, entry["table"], entry["id"])
        ]
    found.sort(key=lambda entry: (_date_gap(entry["date"], date_text), entry["date"]))
    return [{key: entry[key] for key in ("table", "id", "kind")} for entry in found]


def candidate_details(conn, current_user_id, candidates):
    """Os lancamentos parecidos como a tela mostra; o que sumiu fica de fora."""
    details = []
    for entry in candidates or []:
        table = entry.get("table")
        if table == "transactions":
            row = conn.execute(
                """
                SELECT t.id, t.date, t.occurred_at, t.amount, t.description, t.category, t.type,
                       t.source_type, a.name AS account_name,
                       d.name AS transfer_account_name
                FROM transactions t
                LEFT JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
                LEFT JOIN accounts d ON d.id = t.transfer_account_id AND d.user_id = t.user_id
                WHERE t.id = ? AND t.user_id = ?
                """,
                (entry.get("id"), current_user_id),
            ).fetchone()
        elif table == "cc_expenses":
            row = conn.execute(
                """
                SELECT e.id, e.purchase_date AS date, e.occurred_at, e.amount, e.description,
                       e.category, e.installment_info, c.name AS card_name
                FROM cc_expenses e
                LEFT JOIN credit_cards c ON c.id = e.card_id AND c.user_id = e.user_id
                WHERE e.id = ? AND e.user_id = ?
                """,
                (entry.get("id"), current_user_id),
            ).fetchone()
        else:
            row = None
        if row:
            details.append({**entry, **row_to_dict(row)})
    return details


def remember(conn, current_user_id, key, label, *, entry_type, account_id=None, card_id=None,
             transfer_account_id=None):
    """Grava (ou troca) a escolha lembrada desta chave."""
    if not key:
        return None
    stamp = utc_timestamp()
    existing = fetch_hint(conn, current_user_id, key)
    if existing:
        conn.execute(
            """
            UPDATE inbox_hints
            SET label = COALESCE(?, label), entry_type = ?, account_id = ?, card_id = ?,
                transfer_account_id = ?, uses = uses + 1, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (label, entry_type, account_id, card_id, transfer_account_id, stamp, existing["id"], current_user_id),
        )
        return existing["id"]
    hint_id = new_id()
    conn.execute(
        """
        INSERT INTO inbox_hints
        (id, user_id, hint_key, label, entry_type, account_id, card_id, transfer_account_id, uses,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (hint_id, current_user_id, key, label, entry_type, account_id, card_id, transfer_account_id, stamp, stamp),
    )
    return hint_id


def apply_hint_to_pending(conn, current_user_id, key, *, exclude_id=None):
    """A escolha que o dono acabou de mandar lembrar decide os outros itens
    pendentes da mesma chave que ainda esperavam por ela."""
    hint = fetch_hint(conn, current_user_id, key)
    if not _hint_usable(conn, current_user_id, hint) or hint["entry_type"] == "TRANSFER":
        return 0
    rows = conn.execute(
        "SELECT * FROM inbox_items WHERE user_id = ? AND state = 'PENDING' AND hint_key = ?",
        (current_user_id, key),
    ).fetchall()
    changed = 0
    for row in rows:
        if row["id"] == exclude_id:
            continue
        item = item_dict(row)
        edited = set(item["edited"])
        if {"entry_type", "card_id", "account_id"} & edited:
            continue
        if not (item["needs"] or item["guessed"]) or item["entry_type"] == "TRANSFER":
            continue
        # Como em resolve_detection: o tipo que a notificacao diz fica; o
        # lembrado so decide a compra sem credito/debito.
        entry_type = item["entry_type"] or hint["entry_type"]
        if (entry_type == "CARD") != bool(hint["card_id"]):
            continue
        if ambiguous_target(conn, current_user_id, key, entry_type):
            continue
        changes = {
            "entry_type": entry_type,
            "card_id": hint["card_id"] if entry_type == "CARD" else None,
            "account_id": hint["account_id"] if entry_type != "CARD" else None,
            "guessed": [],
        }
        changes["needs"] = recompute_needs({**item, **changes})
        save_item(conn, current_user_id, item, changes)
        changed += 1
    return changed


def list_hints(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT h.*, a.name AS account_name, c.name AS card_name, d.name AS transfer_account_name
        FROM inbox_hints h
        LEFT JOIN accounts a ON a.id = h.account_id AND a.user_id = h.user_id
        LEFT JOIN credit_cards c ON c.id = h.card_id AND c.user_id = h.user_id
        LEFT JOIN accounts d ON d.id = h.transfer_account_id AND d.user_id = h.user_id
        WHERE h.user_id = ?
        ORDER BY h.updated_at DESC
        """,
        (current_user_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


ALWAYS_ASK_SETTING = "inbox_always_ask"


# Avisos dos bancos (Fase 2): Itau, BB e BTG gravam na hora pelo aviso do
# celular. Sem escolha, vale BANK_NOTIFICATIONS_DEFAULT (ligado).
BANK_NOTIFICATIONS_SETTING = "bank_notifications"


def setting_value(conn, current_user_id, key):
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND setting_key = ?",
        (current_user_id, key),
    ).fetchone()
    return row["value"] if row else None


def save_setting(conn, current_user_id, key, value):
    conn.execute(
        """
        INSERT INTO user_settings (user_id, setting_key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, setting_key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (current_user_id, key, value, utc_timestamp()),
    )


def set_bank_notifications(conn, current_user_id, value):
    save_setting(conn, current_user_id, BANK_NOTIFICATIONS_SETTING, "1" if value else "0")


def always_ask(conn, current_user_id):
    """"Sempre perguntar a conta/cartao" (Ajustes, desligado por padrao)."""
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND setting_key = ?",
        (current_user_id, ALWAYS_ASK_SETTING),
    ).fetchone()
    return bool(row) and row["value"] == "1"


def set_always_ask(conn, current_user_id, value):
    conn.execute(
        """
        INSERT INTO user_settings (user_id, setting_key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, setting_key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (current_user_id, ALWAYS_ASK_SETTING, "1" if value else "0", utc_timestamp()),
    )
