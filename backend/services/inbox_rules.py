"""As regras puras do Aprovar: quem fala, como um aviso e lido, quando dois avisos
(ou um aviso e uma linha da Pluggy) sao o mesmo movimento, e as contas de hora e
de data. Nada aqui toca o banco de dados: sao funcoes de valores para valores.

Saiu de services/inbox.py (2026-11-12), que continua reexportando todos estes
nomes: `inbox.notification_wanted`, `inbox.same_purchase`... valem como antes,
e quem substitui um nome num teste (`monkeypatch.setattr(inbox, ...)`) continua
substituindo o que o motor le. O motor (itens, pareamento com o banco de dados,
absorcao de transferencias) fica em services/inbox.py.
"""

import json
import re
from datetime import datetime, timedelta, timezone

import statement_import
from config import (
    NEAR_MATCH_DOMESTIC_PERCENT,
    NEAR_MATCH_FOREIGN_PERCENT,
)
from dates import parse_iso_date
from db import row_to_dict
from money import to_cents
from source_types import (
    CC_AUTOPAY_SOURCE_TYPE,
    CC_INVOICE_PAYMENT_SOURCE_TYPE,
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
)
from validators import CLIENT_ID_PATTERN, ValidationError

SAMSUNG_WALLET = "com.samsung.android.spay"


# Flash Beneficios (dono, 2026-10-22): o cartao de beneficios. O pacote vem das
# listagens do app (nenhuma notificacao dele capturada ainda); a compra com ele
# no Samsung Wallet chega como "Card used for Meal and Voucher".
FLASH_APP = "br.com.flashapp"


FLASH_ISSUER = "flash"


# Mesma janela de NotifyPairing.DEFAULT_WINDOW_MS (10 min, inclusiva), a ser
# ajustada pelo atraso que a captura do dono mostrar.
NOTIFY_WINDOW_MS = 10 * 60 * 1000


APP_LABELS = {
    "com.itau": "Itaú",
    "br.com.bb.android": "Banco do Brasil",
    "com.btg.pactual.banking": "BTG Pactual",
    "com.btg.pactual.digital.mobile": "BTG Investimentos",
    FLASH_APP: "Flash",
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
    FLASH_APP: FLASH_ISSUER,
}


# Como o emissor aparece no nome de uma conta ou cartao do dono.
ISSUER_ALIASES = {
    "itau": ("itau",),
    "bb": ("banco do brasil", "bb", "ourocard"),
    "btg": ("btg",),
    # "Meal and Voucher" e como o Samsung Wallet chama o cartao de beneficios
    # (captura de 2026-10-21); o unico do dono e o Flash.
    FLASH_ISSUER: ("flash", "meal and voucher"),
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
        day = parse_iso_date(text)
        # A mesma faixa da data com hora, abaixo: 9999-12-31 estourava a janela
        # de dias da procura de lancamentos parecidos.
        if not day or not (2000 <= day.year <= 2100):
            raise ValidationError("Data invalida.")
        return day.strftime("%Y-%m-%d")
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


# A aplicacao automatica (o dinheiro so dorme fora da conta): o Rende Facil do
# Banco do Brasil ("RENDE FACIL", "REND.FACIL") e a conta remunerada da BTG
# ("CONTA REMUNERADA - APLICACAO AUTOMATICA", "- RESGATE APLICACAO"). O dono
# nunca quer isso no app (nem lancamento, nem item, nem conferencia),
# 2026-10-27 e 2026-10-28.
AUTO_INVEST_TEXT = re.compile(r"\brende? facil\b|\bconta remunerada\b|\baplicacao automatica\b")


def is_auto_invest(value):
    return bool(AUTO_INVEST_TEXT.search(normalized(value)))


def counterpart_text(value):
    """A descricao sem numeros (autorizacao, agencia, hora): o que se repete
    entre duas transferencias para a mesma pessoa."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", " ", normalized(value))).strip()


def issuer_of(detection):
    return detection.get("issuer") or ISSUER_OF_APP.get(detection.get("app"))


def is_flash_detection(detection):
    """O app do Flash, ou o Samsung Wallet com o cartao dele ("Card used for
    Meal and Voucher": o emissor sai do nome do cartao em parse_detection)."""
    app = detection.get("app")
    return app == FLASH_APP or (app == SAMSUNG_WALLET and issuer_of(detection) == FLASH_ISSUER)


# Quem fala e do que (dono 2026-11-04):
# os tres bancos mandam tudo o que o parser reconhece; o app da corretora so a
# transferencia de ou para um banco (ordem, provento, aplicacao e taxa vem pela
# Pluggy); o Samsung Wallet so o cartao do Flash (is_flash_detection()). O resto
# nao fala. A notificacao grava na hora; a Pluggy confere depois.
BANK_APPS = ("com.itau", "br.com.bb.android", "com.btg.pactual.banking")


NOTIFICATION_POLICY = {
    **{app: frozenset(DETECTION_KINDS) for app in BANK_APPS},
    BROKERAGE_APP: frozenset(MOVEMENT_KINDS),
}


# Palavras de investimento: a aplicacao, o resgate, a ordem na corretora e o
# provento nunca sao Pix nem compra. Valem no Pix/TED (outro lado e
# estabelecimento) e em tudo do app da corretora; nunca no estabelecimento de
# uma compra no cartao ("FUNDO DE QUINTAL BAR" e um bar).
INVESTMENT_TEXT = re.compile(
    r"\b(?:aplicac(?:ao|oes)|resgates?|cdbs?|lcis?|lcas?|tesouro\s+direto|fundos?\s+de\s+investimento"
    r"|ordem\s+de\s+compra|ordem\s+de\s+venda|proventos?|dividendos?|jcp)\b"
)


def is_investment_text(*values):
    return any(INVESTMENT_TEXT.search(normalized(value)) for value in values if value)


def notification_wanted(detection):
    """A porta do servidor, pura (so olha a deteccao): um APK velho que mande
    qualquer coisa passa por ela. O Flash, como sempre: so gasto (o beneficio
    que cai e digitado pelo dono; "credito" num cartao so debito e o aviso do
    deposito). Os bancos: a tabela NOTIFICATION_POLICY, menos o texto de
    investimento. O interruptor bank_notifications e lido em ingest_detection()."""
    kind = detection["kind"]
    if is_flash_detection(detection):
        return kind == "DECLINED" or (KIND_SHAPES[kind][0] == "OUT" and kind != "CREDIT_PURCHASE")
    app = detection.get("app")
    if kind not in NOTIFICATION_POLICY.get(app, ()):
        return False
    if app == BROKERAGE_APP or kind in MOVEMENT_KINDS:
        return not is_investment_text(detection.get("merchant"), detection.get("counterparty"))
    return True


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
    card_name = _short_text(raw, "card_name", 80)
    if not issuer and app == SAMSUNG_WALLET:
        # O Samsung Wallet poe o nome do cartao no titulo ("BTG Pactual Banking"):
        # dele sai o emissor, que impede parear a compra com a de outro banco.
        issuer = issuer_of_institution(card_name)
    installments = raw.get("installments")
    installments = 1 if installments in (None, "") else _int(installments, "Parcelas", minimum=1, maximum=72)
    international = raw.get("international")
    if international is None:
        international = False
    elif not isinstance(international, bool):
        raise ValidationError("Internacional invalido.")
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
        "card_name": card_name,
        "issuer": issuer,
        "installments": installments,
        "counterparty": _short_text(raw, "counterparty", 120) if kind in MOVEMENT_KINDS else None,
        "counterparty_doc": counterparty_doc if kind in MOVEMENT_KINDS else None,
        "counterparty_bank": _short_text(raw, "counterparty_bank", 80) if kind in MOVEMENT_KINDS else None,
        # A compra no exterior (a estimativa em reais do banco): o APK manda
        # desde a Fase 2; em outra moeda, e internacional de qualquer jeito.
        "international": international or currency != "BRL",
    }


def bank_of_row(row):
    """O banco (itau, bb, btg) de uma conta ou cartao, pelo campo de banco —
    nunca pelo nome. Sem banco (o campo vazio, ou um cartao, que ainda nao tem
    o campo), None: o app nao sabe contar quantos ha naquele banco."""
    keys = row.keys()
    text = (row["bank"] if "bank" in keys else None) or (row["institution"] if "institution" in keys else None)
    return issuer_of_institution(text)


def _mentions(row_text, aliases):
    words = f" {normalized(row_text)} "
    return any(f" {alias} " in words for alias in aliases)


def pick_card(cards, detection, only_one_counts=True):
    """O cartao que a notificacao nomeia: o final no nome do cartao, o nome que
    o Samsung Wallet mostrou, o emissor; com `only_one_counts`, o unico cartao."""
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
    if only_one_counts and len(cards) == 1:
        return cards[0]["id"]
    return None


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
    cartao/contas que o tipo pede e estao vazios; o valor, em outra moeda (a
    linha da Pluggy da conta global ja vem na moeda da conta: `edited` traz
    "amount")."""
    needs = []
    if item.get("entry_type") is None:
        needs.append("method")
    needs.extend(missing_targets(item))
    edited = set(item.get("edited") or [])
    if (item.get("currency") or "BRL") != "BRL" and "amount" not in edited:
        needs.append("amount")
    return needs


def item_dict(row):
    item = row_to_dict(row)
    for key in ("needs", "guessed", "edited"):
        item[key] = _jlist(item.get(key))
    item["candidates"] = _jlist(item.get("candidates"))
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


def _amount_matches(item_row, cents, rounds_up=False):
    total = to_cents(item_row["amount"])
    if total == cents or (rounds_up and rounded_up(total, cents)):
        return True
    installments = int(item_row["installments"] or 1)
    # No cartao a notificacao pode dizer a parcela ou o total.
    return installments > 1 and abs(total - cents * installments) <= installments


def _shift(date_text, days):
    return (parse_iso_date(date_text) + timedelta(days=days)).strftime("%Y-%m-%d")


def _day_ms(date_text):
    """A meia-noite UTC do dia, em ms (para comparar com posted_ms)."""
    return int(datetime.combine(parse_iso_date(date_text), datetime.min.time(), timezone.utc).timestamp() * 1000)


def _side_need(direction):
    """O campo de uma transferencia que a ponta desta direcao preenche."""
    return "account" if direction == "OUT" else "transfer_account"


def _is_movement_source(source):
    if source["channel"] == CLAIM_NOTIFY:
        return source["kind"] in MOVEMENT_KINDS
    return source.get("movement") in ("TRANSFER", "SELF_TRANSFER")


def _source_direction(source):
    if source["channel"] == CLAIM_NOTIFY:
        return KIND_SHAPES.get(source["kind"], (None,))[0]
    return source.get("direction")


def candidate_kind(row):
    if row["type"] == "TRANSFER":
        return "transfer"
    return OUT_OF_REACH_SOURCES.get(row["source_type"], "entry")


CLAIM_NOTIFY = "notify"


def _installment_count(info):
    try:
        return max(1, int(str(info).split("/", 1)[1]))
    except (IndexError, ValueError):
        return 1


def _detection_dict(row):
    return row_to_dict(row) if row else None


def detection_from_row(row):
    """Uma linha de notify_detections no formato de parse_detection."""
    item = row_to_dict(row)
    item["key"] = item.pop("dedup_key")
    return item


# A Pluggy da a data (quase nunca a hora); a notificacao, o instante. Um dia de
# folga cobre a virada da meia-noite e o D+1 de quem lanca no dia seguinte.
OPEN_FINANCE_PAIR_DAYS = 1


# O banco pode lancar dias depois do aviso (o debito do fim de semana, o
# feriado). Sem par no dia, a Pluggy ainda procura, ate estes dias antes da
# data dela, a notificacao que ja virou lancamento: senao gravaria o mesmo
# movimento duas vezes. So para tras e so o que ja tem lancamento (o pendente
# e o descartado ficam no dia).
OPEN_FINANCE_LATE_POST_DAYS = 5


# Folga do pull (services/open_finance.py): o banco lanca com data de dias antes
# (o D+1 do cartao, a compensacao, a compra internacional que fica "em
# processamento" dias e entra com a data da compra); a chave pluggy:<id> faz a
# repeticao nao custar nada. Com 7 dias, um lancamento que a Pluggy listou com
# data de 8+ dias atras nunca era puxado (2026-11-04). 35 cobre o prazo de
# liquidacao das bandeiras (30 dias). Mora aqui, e nao no modulo do pull, porque
# aquele importa este: o caminho inverso era um import dentro de funcao, e um
# ciclo entre dez modulos.
LATE_POSTING_DAYS = 35


def rounded_up(true_cents, bank_cents):
    """O valor do banco e o verdadeiro arredondado para cima, em reais inteiros."""
    return int(bank_cents) % 100 == 0 and 0 < int(bank_cents) - int(true_cents) < 100


def _target_open(item, field, need):
    """O campo do item nao contradiz: vazio, ou palpite que o dono nao tocou."""
    return not item.get(field) or (need in (item.get("guessed") or []) and field not in (item.get("edited") or []))


def open_finance_fits_item(item, *, entry_type, direction, account_id=None, card_id=None):
    """Uma transacao do Open Finance (tipo, direcao e conta/cartao certos, do
    mapeamento) pode ser o movimento deste item? O item pode nao saber o
    metodo (compra sem credito/debito) e ter so palpites; o que ele SABE tem
    de bater."""
    item_type = item.get("entry_type")
    if item_type == "TRANSFER":
        if entry_type == "CARD":
            return False
        field, need = ("account_id", "account") if direction == "OUT" else ("transfer_account_id", "transfer_account")
        return item.get(field) == account_id or _target_open(item, field, need)
    if item.get("direction") != direction:
        return False
    if entry_type == "CARD":
        if direction == "OUT" and item_type not in (None, "CARD"):
            return False
        if direction == "IN" and item_type not in ("CARD", "INCOME"):
            return False
        if item_type == "INCOME":
            return True
        return item.get("card_id") == card_id or _target_open(item, "card_id", "card")
    if item_type not in (None, entry_type):
        return False
    return item.get("account_id") == account_id or _target_open(item, "account_id", "account")


NEAR_STOP_WORDS = {
    "compra", "cartao", "debito", "credito", "pagamento", "pagto", "transferencia", "ltda", "eireli", "comercio",
    "servicos", "brasil", "internet", "online", "loja", "store", "sao", "paulo", "rio", "janeiro",
}


def merchant_agrees(merchant, *texts):
    """O estabelecimento da notificacao e o da Pluggy (nome ou descricao) sao o
    mesmo: uma palavra de 4+ letras que nao e generica aparece no outro, ou o
    nome sem espacos (5+) esta dentro do outro sem espacos ("SMART FIT" e
    "SMARTFIT"). So palavras genericas ("COMPRA") nunca bastam."""
    wanted = normalized(merchant)
    if not wanted:
        return False
    tokens = [token for token in wanted.split() if len(token) >= 4 and token.isalpha() and token not in NEAR_STOP_WORDS]
    meaningful = any(token not in NEAR_STOP_WORDS for token in wanted.split())
    squeezed = wanted.replace(" ", "")
    for text in texts:
        other = normalized(text)
        if not other:
            continue
        words = set(other.split())
        if any(token in words for token in tokens):
            return True
        if meaningful and len(squeezed) >= 5 and squeezed in other.replace(" ", ""):
            return True
    return False


def near_amount(notified_cents, bank_cents, international):
    """O valor do banco esta na faixa do notificado: +-NEAR_MATCH_FOREIGN_PERCENT
    (internacional) ou +-NEAR_MATCH_DOMESTIC_PERCENT, so inteiros."""
    notified, bank = int(notified_cents), int(bank_cents)
    if notified <= 0 or bank <= 0:
        return False
    percent = NEAR_MATCH_FOREIGN_PERCENT if international else NEAR_MATCH_DOMESTIC_PERCENT
    return abs(bank - notified) * 100 <= percent * notified


def is_international(detection):
    return bool(detection.get("international")) or (detection.get("currency") or "BRL") != "BRL"


def late_posting_days():
    """A folga do pull (LATE_POSTING_DAYS), em dias."""
    return LATE_POSTING_DAYS


def near_detection_ok(detection):
    """So compra (credito, debito, sem metodo), com estabelecimento, a vista."""
    return (
        detection["kind"] in PURCHASE_KINDS and bool(detection.get("merchant"))
        and int(detection.get("installments") or 1) == 1
    )


def _near_window(notified_date, bank_date, international, recorded):
    """A data do banco menos a do aviso: -1..+1 (ate +5 no ja gravado, como o
    par exato), ou ate LATE_POSTING_DAYS na compra internacional (fica "em
    processamento" e o banco lista dias depois)."""
    first, second = parse_iso_date(date_of(notified_date)), parse_iso_date(date_of(bank_date))
    if not first or not second:
        return False
    gap = (second - first).days
    if international:
        high = late_posting_days()
    else:
        high = OPEN_FINANCE_LATE_POST_DAYS if recorded else OPEN_FINANCE_PAIR_DAYS
    return -OPEN_FINANCE_PAIR_DAYS <= gap <= high


ISSUER_LABELS = {"itau": "Itaú", "bb": "Banco do Brasil", "btg": "BTG Pactual", FLASH_ISSUER: "Flash"}


# Conectores que juntam varios bancos (o plano gratis da Pluggy): o nome dele
# nao diz o banco, o da conta diz.
AGGREGATOR_CONNECTORS = {"meupluggy", "meu pluggy"}


def open_finance_bank_name(account_name, connector_name):
    """O banco de uma conta da Pluggy para a tela: pelo nome da conta ("Cartão
    BTG BLACK" -> BTG Pactual); senao o conector, se ele for um banco; senao o
    nome da conta."""
    issuer = issuer_of_institution(account_name)
    if issuer:
        return ISSUER_LABELS.get(issuer, account_name)
    connector = (connector_name or "").strip()
    if connector and normalized(connector) not in AGGREGATOR_CONNECTORS:
        issuer = issuer_of_institution(connector)
        return ISSUER_LABELS.get(issuer, connector) if issuer else connector
    return account_name or connector or None
