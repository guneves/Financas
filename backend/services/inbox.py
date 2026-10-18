"""Aprovar: o que o celular traz espera o dono aqui (028).

O celular manda cada notificacao de banco que um parser leu
(`ingest_detections`, POST /api/inbox/detections) — so os campos lidos (valor,
hora, cartao, estabelecimento), nunca o texto. Nada grava sozinho.

Cada movimento do mundo real vira UM item (`inbox_items`), por mais fontes que
o contem:

- a notificacao do banco e a do Samsung Wallet da mesma compra (a regra de
  NotifyPairing.java: mesmo valor ao centavo, um cartao que nenhuma das duas
  contradiz, ate NOTIFY_WINDOW_MS de distancia, uma com uma, a mais proxima; o
  banco ganha, e so a negativa do banco cancela a do Samsung);
- as duas pontas de uma transferencia entre contas do dono (saida numa conta,
  entrada de mesmo valor noutra, ate TRANSFER_MATCH_DAYS dias): um item
  TRANSFER, que vira uma linha so e nunca conta como receita ou despesa.

Um item guarda o rascunho do lancamento, que o dono corrige antes de aprovar,
e a hora que a fonte disse (`source_occurred_at`, que nunca muda). Quando a fonte nao diz credito ou
debito, ou nao da para saber de qual cartao ou conta e, o item diz o que falta
(`needs`); a escolha do dono fica lembrada (`inbox_hints`) e decide sozinha da
proxima vez. Um palpite (o unico cartao do Itau, por exemplo) vem preenchido
mas marcado (`guessed`) ate o dono confirmar uma vez.

Decidir (aprovar, recusar, "e este") mora em services/inbox_decisions.py; este
modulo so guarda e junta.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import statement_import
from config import INBOX_MATCH_DAYS
from dates import parse_iso_date
from db import new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import recurring
from services.import_rules import (
    DEFAULT_IMPORT_CATEGORIES,
    import_default_category,
    import_rules_for_matching,
)
from source_types import (
    CC_AUTOPAY_SOURCE_TYPE,
    CC_INVOICE_PAYMENT_SOURCE_TYPE,
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
)
from validators import CLIENT_ID_PATTERN, ValidationError

PENDING = "PENDING"
APPROVED = "APPROVED"
MATCHED = "MATCHED"
DENIED = "DENIED"
REMOVED = "REMOVED"

SOURCE = "SOURCE"
PAIRED = "PAIRED"
DECLINED_ROLE = "DECLINED"
CANCELLED = "CANCELLED"

SAMSUNG_WALLET = "com.samsung.android.spay"
# Mesma janela de NotifyPairing.DEFAULT_WINDOW_MS (10 min, inclusiva), a ser
# ajustada pelo atraso que a captura do dono mostrar.
NOTIFY_WINDOW_MS = 10 * 60 * 1000
# Uma notificacao repostada pelo proprio app chega em milissegundos; duas
# compras iguais no mesmo segundo nao acontecem.
REPEAT_WINDOW_MS = 60 * 1000
# As duas pontas de uma transferencia entre contas proprias: Pix e TED caem no
# mesmo dia; um dia de folga cobre a virada da meia-noite e o D+1 do banco.
TRANSFER_MATCH_DAYS = 1
# O mesmo de routes/accounts.py: a categoria de uma transferencia.
TRANSFER_CATEGORY = "Transferencia"

APP_LABELS = {
    "com.itau": "Itaú",
    "br.com.bb.android": "Banco do Brasil",
    "com.btg.pactual.banking": "BTG Pactual",
    "com.btg.pactual.digital.mobile": "BTG Investimentos",
    SAMSUNG_WALLET: "Samsung Wallet",
    "com.android.shell": "Teste (adb)",
}
# O app da corretora: dinheiro so entra ou sai dela de uma conta do proprio dono
# (dono, 2026-10-17: a transferencia do BTG Banking para a corretora e
# transferencia, nunca despesa nem aporte).
BROKERAGE_APP = "com.btg.pactual.digital.mobile"
ISSUER_OF_APP = {
    "com.itau": "itau",
    "br.com.bb.android": "bb",
    "com.btg.pactual.banking": "btg",
    "com.btg.pactual.digital.mobile": "btg",
}
# Como o emissor aparece no nome de uma conta ou cartao do dono.
ISSUER_ALIASES = {
    "itau": ("itau",),
    "bb": ("banco do brasil", "bb", "ourocard"),
    "btg": ("btg",),
}

# kind do parser -> (direcao, tipo de lancamento, metodo da chave lembrada).
# PURCHASE: a notificacao nao diz credito nem debito (o dono decide).
KIND_SHAPES = {
    "CREDIT_PURCHASE": ("OUT", "CARD", "CREDIT"),
    "DEBIT_PURCHASE": ("OUT", "EXPENSE", "DEBIT"),
    "PURCHASE": ("OUT", None, "ANY"),
    "PIX_OUT": ("OUT", "EXPENSE", "PIX"),
    "TRANSFER_OUT": ("OUT", "EXPENSE", "PIX"),
    "PIX_IN": ("IN", "INCOME", "PIX"),
    "TRANSFER_IN": ("IN", "INCOME", "PIX"),
    "REFUND": ("IN", "INCOME", "REFUND"),
}
DETECTION_KINDS = set(KIND_SHAPES) | {"DECLINED"}
PURCHASE_KINDS = {"CREDIT_PURCHASE", "DEBIT_PURCHASE", "PURCHASE"}
MOVEMENT_KINDS = {"PIX_OUT", "TRANSFER_OUT", "PIX_IN", "TRANSFER_IN"}
METHOD_LABELS = {
    "CREDIT": "crédito",
    "DEBIT": "débito",
    "ANY": "sem crédito/débito",
    "PIX": "Pix/transferência",
    "REFUND": "estorno",
}

ENTRY_TYPES = ("EXPENSE", "INCOME", "TRANSFER", "CARD")
# O que cada tipo precisa para virar lancamento.
REQUIRED_TARGETS = {
    None: ("method",),
    "CARD": ("card",),
    "EXPENSE": ("account",),
    "INCOME": ("account",),
    "TRANSFER": ("account", "transfer_account"),
}
FIELD_OF_NEED = {
    "card": "card_id",
    "account": "account_id",
    "transfer_account": "transfer_account_id",
}

OUT_OF_REACH_SOURCES = {
    CC_INVOICE_PAYMENT_SOURCE_TYPE: "invoice_payment",
    CC_AUTOPAY_SOURCE_TYPE: "invoice_payment",
    INVESTMENT_CASH_SOURCE_TYPE: "investment_cash",
    INVESTMENT_PROCEED_SOURCE_TYPE: "proceed",
}

PACKAGE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
LAST4_PATTERN = re.compile(r"^\d{4}$")
# Os digitos que o banco deixa ver de um CPF/CNPJ mascarado ("***.378.195-**").
DOC_PATTERN = re.compile(r"^\d{3,14}$")
# Quem e o dono do outro lado de um Pix (031): aprendido, nunca digitado.
SELF_DOC_PREFIX = "self:doc:"
SELF_NAME_PREFIX = "self:name:"
# 2020-01-01 a 2100-01-01: um posted_ms fora disso e lixo, nao uma data.
MIN_POSTED_MS = 1_577_836_800_000
MAX_POSTED_MS = 4_102_444_800_000
MAX_AMOUNT_CENTS = 10_000_000_000
MAX_DETECTIONS_PER_REQUEST = 200


# ---------------------------------------------------------------------------
# Puro: horas, chaves, pareamento
# ---------------------------------------------------------------------------

def _cents(value):
    return int(round(float(value) * 100))


def _reais(cents):
    return rounded_money(cents / 100)


def _jlist(value):
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _jdump(values):
    values = [value for value in dict.fromkeys(values or []) if value]
    return json.dumps(values) if values else None


def local_offset_minutes(epoch_ms):
    """O fuso do servidor (TZ do container, America/Sao_Paulo) naquele instante."""
    moment = datetime.fromtimestamp(epoch_ms / 1000).astimezone()
    return int(moment.utcoffset().total_seconds() // 60)


def local_timestamp(epoch_ms, offset_minutes):
    """O instante na hora local de quem viu: 2026-10-18T14:32:05-03:00.

    A data local e o comeco do texto, entao uma compra as 22h30 em Brasilia
    fica no dia certo (em UTC ela ja seria o dia seguinte).
    """
    zone = timezone(timedelta(minutes=int(offset_minutes)))
    return datetime.fromtimestamp(int(epoch_ms) / 1000, zone).isoformat(timespec="seconds")


def date_of(occurred_at):
    """A data local de um occurred_at (com ou sem hora)."""
    return str(occurred_at or "")[:10]


def has_time(occurred_at):
    return len(str(occurred_at or "")) > 10


def normalize_occurred_at(value, fallback_offset=None):
    """Valida o que o dono digitou: AAAA-MM-DD, ou com hora (o fuso, se faltar,
    e o do item ou o do servidor). Devolve o texto guardado."""
    text = str(value or "").strip()
    if not text:
        raise ValidationError("Informe a data.")
    if len(text) == 10:
        if not parse_iso_date(text):
            raise ValidationError("Data invalida.")
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("Data e hora invalidas.") from exc
    if parsed.tzinfo is None:
        if fallback_offset is None:
            parsed = parsed.astimezone()
        else:
            parsed = parsed.replace(tzinfo=timezone(timedelta(minutes=fallback_offset)))
    if not (2000 <= parsed.year <= 2100):
        raise ValidationError("Data invalida.")
    return parsed.isoformat(timespec="seconds")


def offset_of(occurred_at):
    """O fuso de um occurred_at com hora, em minutos; None sem hora."""
    if not has_time(occurred_at):
        return None
    try:
        parsed = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return int(parsed.utcoffset().total_seconds() // 60)


def normalized(value):
    return statement_import.normalize_description(value or "")


def counterpart_text(value):
    """A descricao sem numeros (autorizacao, agencia, hora): o que se repete
    entre duas transferencias para a mesma pessoa."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", " ", normalized(value))).strip()


def issuer_of(detection):
    return detection.get("issuer") or ISSUER_OF_APP.get(detection.get("app"))


def card_hint_part(detection):
    if detection.get("card_last4"):
        return detection["card_last4"]
    name = normalized(detection.get("card_name"))
    return name.replace(" ", "-") if name else "-"


def detection_hint_key(detection):
    """A chave da escolha lembrada: app + metodo + cartao (final ou nome)."""
    _direction, _entry, method = KIND_SHAPES[detection["kind"]]
    card = card_hint_part(detection) if method in ("CREDIT", "DEBIT", "ANY") else "-"
    return f"notify:{detection['app']}:{method}:{card}"


def detection_hint_label(detection):
    _direction, _entry, method = KIND_SHAPES[detection["kind"]]
    parts = [APP_LABELS.get(detection["app"], detection["app"]), METHOD_LABELS[method]]
    if method in ("CREDIT", "DEBIT", "ANY"):
        if detection.get("card_last4"):
            parts.append(f"final {detection['card_last4']}")
        elif detection.get("card_name"):
            parts.append(detection["card_name"])
    return " · ".join(parts)


def transfer_hint_key(account_id, direction, description):
    text = counterpart_text(description)
    if not account_id or not text:
        return None
    return f"transfer:{account_id}:{direction}:{text}"


def detection_description(detection):
    """A descricao do rascunho: o estabelecimento; num Pix sem ele, quem esta
    do outro lado ("Pix para Fulano", "Transferência de Fulano")."""
    if detection.get("merchant"):
        return detection["merchant"]
    name = detection.get("counterparty")
    if not name or detection.get("kind") not in MOVEMENT_KINDS:
        return None
    label = "Pix" if detection["kind"].startswith("PIX") else "Transferência"
    preposition = "para" if KIND_SHAPES[detection["kind"]][0] == "OUT" else "de"
    return f"{label} {preposition} {name}"


def issuer_of_institution(text):
    """O emissor (itau, bb, btg) do nome da instituicao que a notificacao deu."""
    if not text:
        return None
    found = [issuer for issuer, aliases in ISSUER_ALIASES.items() if _mentions(text, aliases)]
    return found[0] if len(found) == 1 else None


def _first_name(value):
    words = normalized(value).split()
    return words[0] if words else ""


def counterparties_conflict(a, b):
    """Duas pontas que nao podem ser a mesma pessoa: CPFs diferentes, ou
    primeiros nomes diferentes. Numa transferencia entre contas do dono, a
    saida diz "para <dono>" e a entrada "de <dono>": o outro lado e o mesmo."""
    if a.get("counterparty_doc") and b.get("counterparty_doc"):
        return a["counterparty_doc"] != b["counterparty_doc"]
    first_a, first_b = _first_name(a.get("counterparty")), _first_name(b.get("counterparty"))
    return bool(first_a and first_b and first_a != first_b)


def self_keys(detection):
    keys = []
    if detection.get("counterparty_doc"):
        keys.append(SELF_DOC_PREFIX + detection["counterparty_doc"])
    name = normalized(detection.get("counterparty"))
    if name:
        keys.append(SELF_NAME_PREFIX + name)
    return keys


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


def kinds_match(a, b):
    """Credito, debito e compra sem metodo pareiam entre si (o Samsung pode nao
    saber qual foi); a negada, com compra; o resto, so com o mesmo kind."""
    purchase_a = a in PURCHASE_KINDS or a == "DECLINED"
    purchase_b = b in PURCHASE_KINDS or b == "DECLINED"
    if purchase_a and purchase_b:
        return not (a == "DECLINED" and b == "DECLINED")
    return a == b


def same_purchase(a, b, window_ms=NOTIFY_WINDOW_MS):
    """As duas deteccoes podem ser a mesma compra? (NotifyPairing.samePurchase)"""
    if abs(int(a["posted_ms"]) - int(b["posted_ms"])) > window_ms:
        return False
    if int(a["amount_cents"]) != int(b["amount_cents"]):
        return False
    if (a.get("currency") or "BRL") != (b.get("currency") or "BRL"):
        return False
    if not kinds_match(a["kind"], b["kind"]):
        return False
    if a.get("card_last4") and b.get("card_last4") and a["card_last4"] != b["card_last4"]:
        return False
    issuer_a, issuer_b = issuer_of(a), issuer_of(b)
    if issuer_a and issuer_b and issuer_a != issuer_b:
        return False
    return True


def closest_detection(incoming, candidates, window_ms=NOTIFY_WINDOW_MS):
    """A candidata que pode ser a mesma compra, a mais proxima no tempo
    (empate: a mais antiga, depois o menor id)."""
    best = None
    for candidate in candidates:
        if candidate["id"] == incoming.get("id"):
            continue
        if not same_purchase(incoming, candidate, window_ms):
            continue
        key = (
            abs(int(candidate["posted_ms"]) - int(incoming["posted_ms"])),
            int(candidate["posted_ms"]),
            str(candidate["id"]),
        )
        if best is None or key < best[0]:
            best = (key, candidate)
    return best[1] if best else None


def _int(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValidationError(f"{label} invalido.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} invalido.") from exc
    if isinstance(value, float) and value != number:
        raise ValidationError(f"{label} invalido.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{label} invalido.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{label} invalido.")
    return number


def _short_text(raw, key, max_length):
    value = raw.get(key)
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:max_length] or None


def parse_detection(raw):
    """Uma deteccao enviada pelo celular, validada; ValidationError se nao serve.

    Campos: key (o dedupKey da notificacao), app (pacote), kind, amount_cents,
    currency, posted_ms, when_ms (Notification.when, opcional),
    utc_offset_minutes (o fuso do celular), merchant, card_last4, card_name,
    issuer, installments; num Pix ou transferencia, counterparty (o nome do
    outro lado), counterparty_doc (os digitos visiveis do CPF mascarado) e
    counterparty_bank (a instituicao do outro lado, como o banco escreveu).
    """
    if not isinstance(raw, dict):
        raise ValidationError("Deteccao invalida.")
    key = str(raw.get("key") or "")
    if not CLIENT_ID_PATTERN.match(key):
        raise ValidationError("Chave da deteccao invalida.")
    app = str(raw.get("app") or "")
    if len(app) > 100 or not PACKAGE_PATTERN.match(app):
        raise ValidationError("App da deteccao invalido.")
    kind = str(raw.get("kind") or "").upper()
    if kind not in DETECTION_KINDS:
        raise ValidationError("Tipo da deteccao invalido.")
    amount_cents = _int(raw.get("amount_cents"), "Valor", minimum=1, maximum=MAX_AMOUNT_CENTS)
    currency = str(raw.get("currency") or "BRL").strip().upper()
    if not re.match(r"^[A-Z]{3}$", currency):
        raise ValidationError("Moeda invalida.")
    posted_ms = _int(raw.get("posted_ms"), "Hora", minimum=MIN_POSTED_MS, maximum=MAX_POSTED_MS)
    when_ms = raw.get("when_ms")
    occurred_ms = posted_ms
    if when_ms not in (None, "", 0):
        when_ms = _int(when_ms, "Hora", minimum=0)
        # Notification.when e a hora do evento quando o app a preenche; longe
        # demais da postagem, e outra coisa (um lembrete, um 0).
        if abs(when_ms - posted_ms) <= 24 * 60 * 60 * 1000:
            occurred_ms = when_ms
    offset = raw.get("utc_offset_minutes")
    offset = local_offset_minutes(posted_ms) if offset in (None, "") else _int(
        offset, "Fuso", minimum=-720, maximum=840
    )
    last4 = str(raw.get("card_last4") or "").strip() or None
    if last4 and not LAST4_PATTERN.match(last4):
        raise ValidationError("Final do cartao invalido.")
    issuer = str(raw.get("issuer") or "").strip().lower() or None
    if issuer and not re.match(r"^[a-z0-9_-]{1,20}$", issuer):
        raise ValidationError("Emissor invalido.")
    installments = raw.get("installments")
    installments = 1 if installments in (None, "") else _int(installments, "Parcelas", minimum=1, maximum=72)
    counterparty_doc = re.sub(r"\D", "", str(raw.get("counterparty_doc") or "")) or None
    if counterparty_doc and not DOC_PATTERN.match(counterparty_doc):
        raise ValidationError("Documento do outro lado invalido.")
    return {
        "key": key,
        "app": app,
        "kind": kind,
        "amount_cents": amount_cents,
        "currency": currency,
        "posted_ms": posted_ms,
        "occurred_at": local_timestamp(occurred_ms, offset),
        "posted_at": local_timestamp(posted_ms, offset),
        "merchant": _short_text(raw, "merchant", 200),
        "card_last4": last4,
        "card_name": _short_text(raw, "card_name", 80),
        "issuer": issuer,
        "installments": installments,
        "counterparty": _short_text(raw, "counterparty", 120) if kind in MOVEMENT_KINDS else None,
        "counterparty_doc": counterparty_doc if kind in MOVEMENT_KINDS else None,
        "counterparty_bank": _short_text(raw, "counterparty_bank", 80) if kind in MOVEMENT_KINDS else None,
    }


# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------

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
    return conn.execute(
        "SELECT id, name FROM credit_cards WHERE user_id = ? ORDER BY name",
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
            "SELECT 1 FROM credit_cards WHERE id = ? AND user_id = ?",
            (hint["card_id"], current_user_id),
        ).fetchone() is not None
    for account_id in (hint["account_id"], hint["transfer_account_id"]):
        if account_id and not conn.execute(
            "SELECT 1 FROM accounts WHERE id = ? AND user_id = ? AND archived_at IS NULL",
            (account_id, current_user_id),
        ).fetchone():
            return False
    return bool(hint["account_id"] or hint["transfer_account_id"])


# ---------------------------------------------------------------------------
# De qual cartao ou conta e: lembrado, palpite, ou o dono decide
# ---------------------------------------------------------------------------

def _mentions(row_text, aliases):
    words = f" {normalized(row_text)} "
    return any(f" {alias} " in words for alias in aliases)


def guess_card(conn, current_user_id, detection):
    cards = _cards(conn, current_user_id)
    issuer = issuer_of(detection)
    if detection.get("card_last4"):
        by_digits = [card for card in cards if detection["card_last4"] in (card["name"] or "")]
        if len(by_digits) == 1:
            return by_digits[0]["id"]
    if detection.get("card_name"):
        wanted = normalized(detection["card_name"])
        by_name = [card for card in cards if wanted and normalized(card["name"]) == wanted]
        if len(by_name) == 1:
            return by_name[0]["id"]
    if issuer in ISSUER_ALIASES:
        by_issuer = [card for card in cards if _mentions(card["name"], ISSUER_ALIASES[issuer])]
        if len(by_issuer) == 1:
            return by_issuer[0]["id"]
    if len(cards) == 1:
        return cards[0]["id"]
    return None


def guess_account(conn, current_user_id, detection):
    accounts = [row for row in _active_accounts(conn, current_user_id) if (row["currency"] or "BRL") == "BRL"]
    brokerage_app = detection.get("app") == BROKERAGE_APP
    usable = [row for row in accounts if (row["type"] == "BROKERAGE") == brokerage_app]
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
        if (remembered_type == "CARD") == bool(hint["card_id"]):
            draft.update({
                "entry_type": remembered_type,
                "account_id": hint["account_id"] if remembered_type != "CARD" else None,
                "card_id": hint["card_id"] if remembered_type == "CARD" else None,
                "remembered": True,
            })
            return draft
    # Sem metodo (o dono ainda vai dizer credito ou debito), os dois palpites
    # ficam prontos: escolhido o metodo, o cartao ou a conta ja esta la.
    if entry_type in (None, "CARD"):
        draft["card_id"] = guess_card(conn, current_user_id, detection)
        if draft["card_id"]:
            draft["guessed"].append("card")
    if entry_type in (None, "EXPENSE", "INCOME"):
        draft["account_id"] = guess_account(conn, current_user_id, detection)
        if draft["account_id"]:
            draft["guessed"].append("account")
    draft["needs"] = recompute_needs(draft)
    return draft


def relevant_guesses(item):
    """Os palpites que contam para o tipo escolhido (um cartao adivinhado nao
    importa se o dono disse que foi no debito)."""
    wanted = REQUIRED_TARGETS.get(item.get("entry_type"), ())
    return [guess for guess in item.get("guessed") or [] if guess in wanted]


def missing_targets(draft):
    return [
        need for need in REQUIRED_TARGETS.get(draft.get("entry_type"), ())
        if need in FIELD_OF_NEED and not draft.get(FIELD_OF_NEED[need])
    ]


def recompute_needs(item):
    """needs de um item a partir do rascunho: o metodo, se nao ha tipo; o
    cartao/contas que o tipo pede e estao vazios; o valor, em outra moeda."""
    needs = []
    if item.get("entry_type") is None:
        needs.append("method")
    needs.extend(missing_targets(item))
    edited = set(item.get("edited") or [])
    if (item.get("currency") or "BRL") != "BRL" and "amount" not in edited:
        needs.append("amount")
    return needs


# ---------------------------------------------------------------------------
# Categoria
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Gravar itens
# ---------------------------------------------------------------------------

ITEM_COLUMNS = (
    "state", "reason", "entry_type", "direction", "amount", "currency", "installments",
    "occurred_at", "source_occurred_at", "description", "category", "category_id",
    "account_id", "card_id", "transfer_account_id", "needs", "guessed", "edited",
    "hint_key", "hint_label", "candidates", "client_key", "target_table", "target_id",
    "decided_at",
)


def item_dict(row):
    item = row_to_dict(row)
    for key in ("needs", "guessed", "edited"):
        item[key] = _jlist(item.get(key))
    item["candidates"] = _jlist(item.get("candidates"))
    return item


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


def _date_gap(a, b):
    first, second = parse_iso_date(date_of(a)), parse_iso_date(date_of(b))
    if not first or not second:
        return 10 ** 6
    return abs((first - second).days)


def _pick_closest(rows, when):
    best = None
    for row in rows:
        key = (_date_gap(row["occurred_at"], when), row["created_at"], row["id"])
        if best is None or key < best[0]:
            best = (key, row)
    return best[1] if best else None


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


def _amount_matches(item_row, cents):
    total = _cents(item_row["amount"])
    if total == cents:
        return True
    installments = int(item_row["installments"] or 1)
    # No cartao a notificacao pode dizer a parcela ou o total.
    return installments > 1 and abs(total - cents * installments) <= installments


def _shift(date_text, days):
    return (parse_iso_date(date_text) + timedelta(days=days)).strftime("%Y-%m-%d")


def _has_detection_source(conn, current_user_id, item_id):
    return conn.execute(
        "SELECT 1 FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE' LIMIT 1",
        (current_user_id, item_id),
    ).fetchone() is not None


def _source_directions(conn, current_user_id, item_id):
    directions = set()
    for row in conn.execute(
        "SELECT kind FROM notify_detections WHERE user_id = ? AND item_id = ? AND role = 'SOURCE'",
        (current_user_id, item_id),
    ).fetchall():
        if row["kind"] in KIND_SHAPES:
            directions.add(KIND_SHAPES[row["kind"]][0])
    return directions


# ---------------------------------------------------------------------------
# Transferencia entre contas do dono
# ---------------------------------------------------------------------------

def _brl_active_account(conn, current_user_id, account_id):
    return conn.execute(
        """
        SELECT id, name FROM accounts
        WHERE id = ? AND user_id = ? AND archived_at IS NULL AND COALESCE(currency, 'BRL') = 'BRL'
        """,
        (account_id, current_user_id),
    ).fetchone()


def _side_need(direction):
    """O campo de uma transferencia que a ponta desta direcao preenche."""
    return "account" if direction == "OUT" else "transfer_account"


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
        if int(row["installments"] or 1) != 1 or _cents(row["amount"]) != cents:
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


def approved_transfer_awaiting(conn, current_user_id, *, account_id, direction, cents, date_text):
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
        if _cents(row["transfer_amount"]) != cents:
            continue
        side_account = row["destination"] if direction == "IN" else row["origin"]
        if side_account != account_id:
            continue
        if direction in _source_directions(conn, current_user_id, row["id"]):
            continue
        found.append(row)
    return _pick_closest(found, date_text)


# ---------------------------------------------------------------------------
# Lancamentos parecidos ja gravados
# ---------------------------------------------------------------------------

def candidate_kind(row):
    if row["type"] == "TRANSFER":
        return "transfer"
    return OUT_OF_REACH_SOURCES.get(row["source_type"], "entry")


def existing_rows(conn, current_user_id, *, entry_type, direction, cents, date_text,
                  account_id=None, card_id=None, days=None, for_notification=False):
    """Lancamentos ja gravados que podem ser este movimento.

    Mesmo valor e data a `days` dias; na conta/cartao, quando se sabe. Para uma
    notificacao, fica de fora o que outra notificacao ja explica (duas compras
    de mesmo valor no mesmo dia continuam duas).
    """
    days = INBOX_MATCH_DAYS if days is None else days
    start, end = _shift(date_text, -days), _shift(date_text, days)
    found = []
    if entry_type in (None, "CARD"):
        sql = """
            SELECT id, purchase_date AS date, amount, installment_info, card_id FROM cc_expenses e
            WHERE user_id = ? AND purchase_date BETWEEN ? AND ?
              AND installment_info LIKE '1/%' AND kind = 'PURCHASE'
        """
        params = [current_user_id, start, end]
        if card_id:
            sql += " AND card_id = ?"
            params.append(card_id)
        for row in conn.execute(sql, params).fetchall():
            count = _installment_count(row["installment_info"])
            if _cents(row["amount"]) == cents or abs(_cents(row["amount"]) * count - cents) <= count:
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
    if for_notification:
        found = [entry for entry in found if not _explained_by_notification(conn, current_user_id, entry)]
    found.sort(key=lambda entry: (_date_gap(entry["date"], date_text), entry["date"]))
    return [{key: entry[key] for key in ("table", "id", "kind")} for entry in found]


def _installment_count(info):
    try:
        return max(1, int(str(info).split("/", 1)[1]))
    except (IndexError, ValueError):
        return 1


def _explained_by_notification(conn, current_user_id, entry):
    return conn.execute(
        """
        SELECT 1 FROM notify_detections
        WHERE user_id = ? AND target_table = ? AND target_id = ? LIMIT 1
        """,
        (current_user_id, entry["table"], entry["id"]),
    ).fetchone() is not None


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


# ---------------------------------------------------------------------------
# Notificacoes do celular
# ---------------------------------------------------------------------------

def _detection_dict(row):
    return row_to_dict(row) if row else None


def _window_detections(conn, current_user_id, posted_ms, *, samsung, roles):
    rows = conn.execute(
        f"""
        SELECT * FROM notify_detections
        WHERE user_id = ? AND posted_ms BETWEEN ? AND ?
          AND role IN ({', '.join('?' for _ in roles)})
          AND {'app = ?' if samsung else 'app <> ?'}
        """,
        (current_user_id, posted_ms - NOTIFY_WINDOW_MS, posted_ms + NOTIFY_WINDOW_MS, *roles, SAMSUNG_WALLET),
    ).fetchall()
    paired = {
        value
        for row in conn.execute(
            """
            SELECT id, paired_with FROM notify_detections
            WHERE user_id = ? AND paired_with IS NOT NULL
              AND posted_ms BETWEEN ? AND ?
            """,
            (current_user_id, posted_ms - 2 * NOTIFY_WINDOW_MS, posted_ms + 2 * NOTIFY_WINDOW_MS),
        ).fetchall()
        for value in (row["id"], row["paired_with"])
    }
    return [_detection_dict(row) for row in rows if row["id"] not in paired and not row["paired_with"]]


def _update_detection(conn, current_user_id, detection_id, **changes):
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(
        f"UPDATE notify_detections SET {assignments} WHERE id = ? AND user_id = ?",
        (*changes.values(), detection_id, current_user_id),
    )


def _insert_detection(conn, current_user_id, detection, role, **extra):
    detection_id = new_id()
    row = {
        "id": detection_id,
        "user_id": current_user_id,
        "dedup_key": detection["key"],
        "app": detection["app"],
        "kind": detection["kind"],
        "amount_cents": detection["amount_cents"],
        "currency": detection["currency"],
        "installments": detection["installments"],
        "posted_ms": detection["posted_ms"],
        "occurred_at": detection["occurred_at"],
        "posted_at": detection["posted_at"],
        "merchant": detection["merchant"],
        "card_last4": detection["card_last4"],
        "card_name": detection["card_name"],
        "issuer": detection["issuer"],
        "counterparty": detection.get("counterparty"),
        "counterparty_doc": detection.get("counterparty_doc"),
        "counterparty_bank": detection.get("counterparty_bank"),
        "role": role,
    }
    row.update(extra)
    conn.execute(
        f"INSERT INTO notify_detections ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
        tuple(row.values()),
    )
    return detection_id


def ingest_detections(conn, current_user_id, raw_detections):
    """As deteccoes do celular, cada uma decidida; uma lista de resultados na
    mesma ordem: {key, status, item_id?, error?}.

    status: known (ja recebida), new (item novo), merged (juntou-se a um item
    pendente: o par do Samsung, a outra ponta da transferencia),
    matched (era um lancamento que ja existe), denied (o par ja foi recusado),
    declined (compra negada), cancelled (Samsung de uma compra negada),
    invalid (nao serviu; o celular nao manda de novo).
    """
    if not isinstance(raw_detections, list) or not raw_detections:
        raise ValidationError("Envie uma lista de deteccoes.")
    if len(raw_detections) > MAX_DETECTIONS_PER_REQUEST:
        raise ValidationError(f"No maximo {MAX_DETECTIONS_PER_REQUEST} deteccoes por envio.")
    rules = import_rules_for_matching(conn, current_user_id)
    parsed = []
    results = [None] * len(raw_detections)
    for index, raw in enumerate(raw_detections):
        try:
            parsed.append((index, parse_detection(raw)))
        except ValidationError as exc:
            key = raw.get("key") if isinstance(raw, dict) else None
            results[index] = {"key": key if isinstance(key, str) else None, "status": "invalid", "error": str(exc)}
    # Na ordem em que aconteceram: o pareamento depende de quem chegou antes.
    for index, detection in sorted(parsed, key=lambda pair: (pair[1]["posted_ms"], pair[0])):
        results[index] = ingest_detection(conn, current_user_id, detection, rules)
    return results


def ingest_detection(conn, current_user_id, detection, rules=None):
    known = conn.execute(
        "SELECT id, item_id, role FROM notify_detections WHERE user_id = ? AND dedup_key = ?",
        (current_user_id, detection["key"]),
    ).fetchone()
    if known:
        return {"key": detection["key"], "status": "known", "item_id": known["item_id"]}

    repeated = _repeated_posting(conn, current_user_id, detection)
    if repeated:
        _insert_detection(
            conn, current_user_id, detection, PAIRED, paired_with=repeated["id"], item_id=repeated["item_id"],
            target_table=repeated["target_table"], target_id=repeated["target_id"],
        )
        return {"key": detection["key"], "status": "repeated", "item_id": repeated["item_id"]}

    samsung = detection["app"] == SAMSUNG_WALLET
    detection["issuer"] = detection["issuer"] or ISSUER_OF_APP.get(detection["app"])

    if detection["kind"] == "DECLINED":
        return _ingest_declined(conn, current_user_id, detection, samsung)

    if samsung:
        partner = closest_detection(
            detection,
            [row for row in _window_detections(conn, current_user_id, detection["posted_ms"], samsung=False,
                                               roles=(SOURCE, "MATCHED"))
             if row["kind"] != "DECLINED"],
        )
        if partner:
            return _join_partner(conn, current_user_id, detection, partner, newcomer_wins=False)
        refusal = closest_detection(
            detection,
            _window_detections(conn, current_user_id, detection["posted_ms"], samsung=False, roles=(DECLINED_ROLE,)),
        )
        if refusal:
            _insert_detection(conn, current_user_id, detection, CANCELLED, paired_with=refusal["id"])
            return {"key": detection["key"], "status": "cancelled", "item_id": None}
    else:
        partner = closest_detection(
            detection,
            _window_detections(conn, current_user_id, detection["posted_ms"], samsung=True, roles=(SOURCE, "MATCHED")),
        )
        if partner:
            return _join_partner(conn, current_user_id, detection, partner, newcomer_wins=True, rules=rules)

    return _ingest_alone(conn, current_user_id, detection, rules)


def _repeated_posting(conn, current_user_id, detection):
    """A mesma notificacao postada de novo pelo app (o BTG posta cada compra
    duas vezes, 24 ms uma da outra, com o mesmo Notification.when): mesmo app,
    tipo, valor, hora do evento e estabelecimento, ate REPEAT_WINDOW_MS. Outro
    dedupKey (outra hora de postagem), mas o mesmo aviso: nao e outra compra."""
    rows = conn.execute(
        """
        SELECT * FROM notify_detections
        WHERE user_id = ? AND app = ? AND kind = ? AND amount_cents = ? AND occurred_at = ?
          AND posted_ms BETWEEN ? AND ? AND paired_with IS NULL
        ORDER BY posted_ms, id
        """,
        (
            current_user_id, detection["app"], detection["kind"], detection["amount_cents"],
            detection["occurred_at"], detection["posted_ms"] - REPEAT_WINDOW_MS,
            detection["posted_ms"] + REPEAT_WINDOW_MS,
        ),
    ).fetchall()
    for row in rows:
        if (row["merchant"] or "") == (detection.get("merchant") or "") and (
            row["counterparty_doc"] or ""
        ) == (detection.get("counterparty_doc") or ""):
            return row_to_dict(row)
    return None


def _ingest_declined(conn, current_user_id, detection, samsung):
    detection_id = _insert_detection(conn, current_user_id, detection, DECLINED_ROLE)
    if samsung:
        # So a negativa do banco cancela: o banco ganha (NotifyPairing).
        return {"key": detection["key"], "status": "declined", "item_id": None}
    held = closest_detection(
        {**detection, "id": detection_id},
        [
            row for row in _window_detections(conn, current_user_id, detection["posted_ms"], samsung=True, roles=(SOURCE,))
            if row["kind"] in PURCHASE_KINDS
        ],
    )
    if not held or not held["item_id"]:
        return {"key": detection["key"], "status": "declined", "item_id": None}
    item_row = fetch_item(conn, current_user_id, held["item_id"])
    if not item_row or item_row["state"] != PENDING:
        return {"key": detection["key"], "status": "declined", "item_id": None}
    _update_detection(conn, current_user_id, held["id"], role=CANCELLED, paired_with=detection_id)
    item = item_dict(item_row)
    if not _has_detection_source(conn, current_user_id, item["id"]):
        save_item(conn, current_user_id, item, {"state": REMOVED, "reason": "declined", "decided_at": utc_timestamp()})
    return {"key": detection["key"], "status": "declined", "item_id": item["id"]}


def _join_partner(conn, current_user_id, detection, partner, *, newcomer_wins, rules=None):
    """A mesma compra notificada pelo banco e pelo Samsung Wallet: um item so."""
    item_row = fetch_item(conn, current_user_id, partner["item_id"]) if partner["item_id"] else None
    if partner["role"] == "MATCHED" or not item_row:
        _insert_detection(
            conn, current_user_id, detection, PAIRED, paired_with=partner["id"],
            target_table=partner["target_table"], target_id=partner["target_id"],
        )
        return {"key": detection["key"], "status": "matched", "item_id": None}

    item = item_dict(item_row)
    status = {PENDING: "merged", APPROVED: "matched", MATCHED: "matched"}.get(item["state"], "denied")
    if not newcomer_wins or item["state"] != PENDING:
        _insert_detection(
            conn, current_user_id, detection, PAIRED, paired_with=partner["id"], item_id=item["id"],
            target_table=item["target_table"], target_id=item["target_id"],
        )
        return {"key": detection["key"], "status": status, "item_id": item["id"]}

    # O banco chegou depois do Samsung, e o dono ainda nao decidiu: o banco
    # vira a fonte do item, e o que ele diz melhor (credito/debito, cartao,
    # estabelecimento) entra onde o dono nao mexeu.
    detection_id = _insert_detection(conn, current_user_id, detection, SOURCE, item_id=item["id"])
    _update_detection(conn, current_user_id, partner["id"], role=PAIRED, paired_with=detection_id)
    edited = set(item["edited"])
    changes = {}
    if detection["merchant"] and "description" not in edited:
        changes["description"] = detection["merchant"]
    target = resolve_detection(conn, current_user_id, detection)
    if not ({"entry_type", "card_id", "account_id"} & edited):
        changes.update({
            "entry_type": target["entry_type"],
            "card_id": target["card_id"],
            "account_id": target["account_id"],
            "guessed": target["guessed"],
        })
    changes["hint_key"] = target["hint_key"]
    changes["hint_label"] = target["hint_label"]
    if "description" in changes and "category" not in edited:
        merged = {**item, **changes}
        changes["category"], changes["category_id"] = suggest_category(
            conn, current_user_id, merged["description"], merged["entry_type"], merged["amount"],
            merged["account_id"], rules,
        )
    merged = {**item, **changes}
    changes["needs"] = recompute_needs(merged)
    save_item(conn, current_user_id, item, changes)
    return {"key": detection["key"], "status": "merged", "item_id": item["id"]}


def _ingest_alone(conn, current_user_id, detection, rules):
    target = resolve_detection(conn, current_user_id, detection)
    when = detection["occurred_at"]
    cents = detection["amount_cents"]

    known_account = target["account_id"] if target["remembered"] else None
    direction = target["direction"]

    # 1. A outra ponta de uma transferencia entre contas do dono.
    if detection["kind"] in MOVEMENT_KINDS and target["account_id"] and "account" not in target["needs"]:
        approved = approved_transfer_awaiting(
            conn, current_user_id, account_id=target["account_id"], direction=direction, cents=cents,
            date_text=date_of(when),
        )
        if approved:
            _insert_detection(
                conn, current_user_id, detection, SOURCE, item_id=approved["id"],
                target_table="transactions", target_id=approved["target_id"],
            )
            return {"key": detection["key"], "status": "matched", "item_id": approved["id"]}
        partner = transfer_partner(
            conn, current_user_id, account_id=target["account_id"], direction=direction, cents=cents,
            date_text=date_of(when), detection=detection,
        )
        if partner:
            others = _movement_sources(conn, current_user_id, partner["id"])
            _insert_detection(conn, current_user_id, detection, SOURCE, item_id=partner["id"])
            item = make_transfer(
                conn, current_user_id, item_dict(partner), account_id=target["account_id"], direction=direction,
                guessed="account" in target["guessed"],
            )
            # Saida "para X" e entrada "de X" do mesmo valor, entre duas contas
            # do dono: X e o dono. Da proxima vez, uma ponta so ja basta.
            if any(
                (detection.get("counterparty_doc") or detection.get("counterparty"))
                and (other.get("counterparty_doc") or other.get("counterparty"))
                for other in others
            ):
                learn_self(conn, current_user_id, [detection, *others])
            return {"key": detection["key"], "status": "merged", "item_id": item["id"]}

    # 2. Um item novo, com os lancamentos parecidos ja gravados (o dono pode
    # ter digitado antes do aviso chegar): ele decide no Aprovar se e o mesmo.
    # Nada que uma notificacao trouxe se resolve sem passar por la.
    candidates = existing_rows(
        conn, current_user_id, entry_type=target["entry_type"], direction=direction, cents=cents,
        date_text=date_of(when),
        account_id=known_account,
        card_id=target["card_id"] if target["remembered"] else None,
        for_notification=True,
    )
    item_id = new_item_for_detection(conn, current_user_id, detection, target, candidates, rules)
    _insert_detection(conn, current_user_id, detection, SOURCE, item_id=item_id)
    return {"key": detection["key"], "status": "new", "item_id": item_id}


def detection_from_row(row):
    """Uma linha de notify_detections no formato de parse_detection."""
    item = row_to_dict(row)
    item["key"] = item.pop("dedup_key")
    return item


def new_item_for_detection(conn, current_user_id, detection, target=None, candidates=None, rules=None):
    """Abre um item so desta deteccao (sem procurar com quem juntar)."""
    if target is None:
        target = resolve_detection(conn, current_user_id, detection)
    direction = target["direction"]
    candidates = candidates or []
    values = {
        "reason": "several_candidates" if len(candidates) > 1 else ("possible_duplicate" if candidates else "new"),
        "entry_type": target["entry_type"],
        "direction": direction,
        "amount": _reais(detection["amount_cents"]),
        "currency": detection["currency"],
        "installments": detection["installments"] if target["entry_type"] in (None, "CARD") else 1,
        "occurred_at": detection["occurred_at"],
        "description": detection_description(detection),
        "account_id": target["account_id"],
        "card_id": target["card_id"],
        "transfer_account_id": target["transfer_account_id"],
        "guessed": target["guessed"],
        "hint_key": target["hint_key"],
        "hint_label": target["hint_label"],
        "candidates": candidates,
        "client_key": detection["key"],
    }
    hint = None
    if detection["kind"] in MOVEMENT_KINDS and target["account_id"]:
        hint = remembered_transfer(
            conn, current_user_id, account_id=target["account_id"], direction=direction,
            description=detection_description(detection),
        )
        if hint:
            other = hint["transfer_account_id"]
            values.update({
                "entry_type": "TRANSFER",
                "direction": "OUT",
                "account_id": target["account_id"] if direction == "OUT" else other,
                "transfer_account_id": other if direction == "OUT" else target["account_id"],
                "card_id": None,
                "reason": "own_transfer",
                "guessed": (["account" if direction == "OUT" else "transfer_account"]
                            if "account" in target["guessed"] else []),
            })
    if detection["kind"] in MOVEMENT_KINDS and not hint:
        if is_self_counterparty(conn, current_user_id, detection):
            # So esta ponta notificou (a outra conta e de um banco que o app nao
            # ouve, ou ainda vai chegar): transferencia, o outro lado pela
            # instituicao citada, ou o dono escolhe.
            own = target["account_id"]
            other = guess_other_side(conn, current_user_id, detection, own)
            guesses = []
            if "account" in target["guessed"]:
                guesses.append(_side_need(direction))
            if other:
                guesses.append(_side_need("IN" if direction == "OUT" else "OUT"))
            origin, destination = (own, other) if direction == "OUT" else (other, own)
            values.update({
                "entry_type": "TRANSFER",
                "direction": "OUT",
                "account_id": origin,
                "transfer_account_id": destination,
                "card_id": None,
                "reason": "own_transfer" if values["reason"] == "new" else values["reason"],
                "guessed": guesses,
                "description": _transfer_description(
                    conn, current_user_id, origin, destination, values["description"],
                ),
            })
        elif detection.get("counterparty") or detection.get("counterparty_doc"):
            if values["reason"] == "new":
                values["reason"] = "external_transfer"
    values["category"], values["category_id"] = suggest_category(
        conn, current_user_id, values["description"], values["entry_type"], values["amount"],
        values["account_id"], rules,
    )
    values["needs"] = recompute_needs(values)
    return insert_item(conn, current_user_id, values)


# ---------------------------------------------------------------------------
# Lembrar
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Para a tela
# ---------------------------------------------------------------------------

def _names(conn, current_user_id):
    accounts = {
        row["id"]: row["name"]
        for row in conn.execute("SELECT id, name FROM accounts WHERE user_id = ?", (current_user_id,)).fetchall()
    }
    cards = {
        row["id"]: row["name"]
        for row in conn.execute("SELECT id, name FROM credit_cards WHERE user_id = ?", (current_user_id,)).fetchall()
    }
    return accounts, cards


def serialize_item(conn, current_user_id, row, names=None, recurrences=None):
    item = item_dict(row) if not isinstance(row, dict) else dict(row)
    accounts, cards = names or _names(conn, current_user_id)
    item["account_name"] = accounts.get(item.get("account_id"))
    item["card_name"] = cards.get(item.get("card_id"))
    item["transfer_account_name"] = accounts.get(item.get("transfer_account_id"))
    item["candidates"] = candidate_details(conn, current_user_id, item.get("candidates"))
    sources = []
    for detection in item_detections(conn, current_user_id, item["id"]):
        sources.append({
            "source": "notification",
            "id": detection["id"],
            "role": detection["role"],
            "app": detection["app"],
            "app_label": APP_LABELS.get(detection["app"], detection["app"]),
            "kind": detection["kind"],
            "amount": _reais(detection["amount_cents"]),
            "currency": detection["currency"],
            "occurred_at": detection["occurred_at"],
            "posted_at": detection["posted_at"],
            "merchant": detection["merchant"],
            "card_last4": detection["card_last4"],
            "card_name": detection["card_name"],
            "counterparty": detection["counterparty"],
            "counterparty_bank": detection["counterparty_bank"],
            "received_at": detection["created_at"],
        })
    item["sources"] = sources
    item["confirm"] = relevant_guesses(item)
    # A recorrencia que aprovar da como feita (034): a sugestao enquanto
    # pendente (mesmo com "nao e esta", para poder desfazer), a gravada depois.
    item["recurring_off"] = bool(item.get("recurring_off"))
    if item.get("state") == PENDING:
        item["recurring"] = recurring.suggest_for_item(conn, current_user_id, item, rows=recurrences)
    else:
        item["recurring"] = recurring.settlement_of_item(conn, current_user_id, item["id"])
    # Pronto para "Aprovar todos": nada a escolher e nenhum palpite a confirmar.
    item["ready"] = item.get("state") == PENDING and not item.get("needs") and not item["confirm"]
    return item


def list_items(conn, current_user_id, view="pending", limit=200):
    if view == "decided":
        rows = conn.execute(
            """
            SELECT * FROM inbox_items
            WHERE user_id = ? AND state <> 'PENDING'
            ORDER BY COALESCE(decided_at, updated_at) DESC
            LIMIT ?
            """,
            (current_user_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM inbox_items
            WHERE user_id = ? AND state = 'PENDING'
            ORDER BY occurred_at DESC, created_at DESC
            LIMIT ?
            """,
            (current_user_id, limit),
        ).fetchall()
    names = _names(conn, current_user_id)
    recurrences = recurring.recurring_rows(conn, current_user_id, include_inactive=False)
    return [serialize_item(conn, current_user_id, row, names, recurrences) for row in rows]
