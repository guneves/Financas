"""Aprovar: o que o celular traz espera o dono aqui (028).

O celular manda cada notificacao que um parser leu (`ingest_detections`, POST
/api/inbox/detections) — so os campos lidos (valor, hora, cartao,
estabelecimento), nunca o texto. Nada grava sozinho aqui.

Dono, 2026-11-04: a notificacao grava
na hora, a Pluggy confere depois e e o registro. Passam o Flash (app e Samsung
Wallet com o cartao dele), Itau, BB e BTG Banking, e do BTG Investimentos so o
Pix/TED (`NOTIFICATION_POLICY`, `notification_wanted()`, seja o que for que um
APK antigo mande; o freio e `bank_notifications`). O resto responde `ignored` e
nao deixa rastro.

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


from config import (
    BANK_NOTIFICATIONS_DEFAULT,
)
from db import new_id, row_to_dict, utc_timestamp
from money import from_cents, to_cents
from services import recurring
from services.import_rules import (
    import_rules_for_matching,
)
from services.inbox_rules import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    AGGREGATOR_CONNECTORS,
    APP_LABELS,
    AUTO_INVEST_TEXT,
    BANK_APPS,
    BROKERAGE_APP,
    CLAIM_NOTIFY,
    DETECTION_KINDS,
    DOC_PATTERN,
    FIELD_OF_NEED,
    FLASH_APP,
    FLASH_ISSUER,
    INVESTMENT_TEXT,
    ISSUER_ALIASES,
    ISSUER_LABELS,
    ISSUER_OF_APP,
    KIND_SHAPES,
    LAST4_PATTERN,
    LATE_POSTING_DAYS,
    MAX_AMOUNT_CENTS,
    MAX_POSTED_MS,
    METHOD_LABELS,
    MIN_POSTED_MS,
    MOVEMENT_KINDS,
    NEAR_STOP_WORDS,
    NOTIFICATION_POLICY,
    NOTIFY_WINDOW_MS,
    OPEN_FINANCE_LATE_POST_DAYS,
    OPEN_FINANCE_PAIR_DAYS,
    OUT_OF_REACH_SOURCES,
    PACKAGE_PATTERN,
    PURCHASE_KINDS,
    REQUIRED_TARGETS,
    SAMSUNG_WALLET,
    SELF_DOC_PREFIX,
    SELF_NAME_PREFIX,
    _amount_matches,
    _date_gap,
    _day_ms,
    _detection_dict,
    _first_name,
    _installment_count,
    _int,
    _is_movement_source,
    _jdump,
    _jlist,
    _mentions,
    _near_window,
    _pick_closest,
    _shift,
    _short_text,
    _side_need,
    _source_direction,
    _target_open,
    bank_of_row,
    candidate_kind,
    card_hint_part,
    closest_detection,
    counterpart_text,
    counterparties_conflict,
    date_of,
    detection_description,
    detection_from_row,
    detection_hint_key,
    detection_hint_label,
    has_time,
    is_auto_invest,
    is_flash_detection,
    is_international,
    is_investment_text,
    issuer_of,
    issuer_of_institution,
    item_dict,
    kinds_match,
    late_posting_days,
    local_offset_minutes,
    local_timestamp,
    merchant_agrees,
    missing_targets,
    near_amount,
    near_detection_ok,
    normalize_occurred_at,
    normalized,
    notification_wanted,
    offset_of,
    open_finance_bank_name,
    open_finance_fits_item,
    parse_detection,
    pick_card,
    recompute_needs,
    relevant_guesses,
    rounded_up,
    same_purchase,
    self_keys,
    transfer_hint_key,
)
from services.inbox_store import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    ALWAYS_ASK_SETTING,
    BANK_NOTIFICATIONS_SETTING,
    CLAIM_PLUGGY,
    ITEM_COLUMNS,
    PENDING,
    SOURCE,
    TRANSFER_CATEGORY,
    _active_accounts,
    _cards,
    _debit_cards,
    _has_detection_source,
    _has_notification_source,
    _hint_usable,
    _movement_sources,
    _pending_items,
    _source_directions,
    _usable_accounts,
    always_ask,
    ambiguous_target,
    apply_hint_to_pending,
    candidate_details,
    claimed,
    confirm_targets,
    debit_card_for,
    existing_rows,
    fetch_hint,
    fetch_item,
    guess_account,
    guess_card,
    insert_item,
    is_self_counterparty,
    item_detections,
    learn_self,
    list_hints,
    notification_claimed,
    open_finance_sources,
    pending_count,
    pluggy_claimed,
    remember,
    resolve_detection,
    save_item,
    save_setting,
    set_always_ask,
    set_bank_notifications,
    setting_value,
    suggest_category,
)
from services.inbox_transfers import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    APPROVED,
    TRANSFER_MATCH_DAYS,
    _brl_account,
    _brl_active_account,
    _side_sources,
    _source_untouched,
    _transfer_description,
    absorb_recorded_side,
    approved_transfer_awaiting,
    finish_absorb,
    guess_other_side,
    make_transfer,
    remembered_transfer,
    settle_transfer_review,
    transfer_confirmed,
    transfer_partner,
)
from validators import ValidationError

MATCHED = "MATCHED"
DENIED = "DENIED"
REMOVED = "REMOVED"

PAIRED = "PAIRED"
DECLINED_ROLE = "DECLINED"
CANCELLED = "CANCELLED"

# Uma notificacao repostada pelo proprio app chega em milissegundos; duas
# compras iguais no mesmo segundo nao acontecem.
REPEAT_WINDOW_MS = 60 * 1000
ENTRY_TYPES = ("EXPENSE", "INCOME", "TRANSFER", "CARD")
MAX_DETECTIONS_PER_REQUEST = 200


# ---------------------------------------------------------------------------
# Categoria
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Notificacoes do celular
# ---------------------------------------------------------------------------

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
        "international": 1 if is_international(detection) else 0,
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
    ignored (fora da politica de quem fala, o freio desligado, ou a aplicacao
    automatica: nada guardado),
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

    if is_auto_invest(detection.get("merchant")):
        return {"key": detection["key"], "status": "ignored", "item_id": None}

    if not notification_wanted(detection):
        return {"key": detection["key"], "status": "ignored", "item_id": None}
    if not is_flash_detection(detection) and not bank_notifications(conn, current_user_id):
        # O freio (Ajustes > Avisos dos bancos): desligado, o banco nao deixa
        # rastro, para que ligar de novo nao grave avisos velhos de uma vez.
        return {"key": detection["key"], "status": "ignored", "item_id": None}

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
    if item_row and item_row["state"] == APPROVED and item_row["auto_recorded_at"]:
        # O Samsung nao espera mais o aviso do Flash: a compra ja foi gravada, e
        # a negativa a desfaz se ninguem mexeu (auto_record.undo_declined).
        _update_detection(conn, current_user_id, held["id"], role=CANCELLED, paired_with=detection_id)
        return {"key": detection["key"], "status": "declined", "item_id": item_row["id"]}
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
            date_text=date_of(when), channel=CLAIM_NOTIFY,
        )
        if approved:
            _insert_detection(
                conn, current_user_id, detection, SOURCE, item_id=approved["id"],
                target_table="transactions", target_id=approved["target_id"],
            )
            settle_transfer_review(conn, current_user_id, approved["id"])
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
        # A outra ponta ja virou despesa/receita sozinha (defeito I): a mesma
        # linha vira a transferencia.
        absorbed = absorb_recorded_side(
            conn, current_user_id, account_id=target["account_id"], direction=direction, cents=cents,
            date_text=date_of(when), occurred_at=when, counterparty=detection,
            description=detection_description(detection),
        )
        if absorbed:
            _insert_detection(
                conn, current_user_id, detection, SOURCE, item_id=absorbed["id"], target_table="transactions",
                target_id=absorbed["target_id"],
            )
            finish_absorb(conn, current_user_id, absorbed)
            return {"key": detection["key"], "status": "merged", "item_id": absorbed["id"]}

    # 2. O Open Finance ja trouxe este movimento (a notificacao chegou depois,
    # o celular estava sem rede): a mesma compra e o mesmo item.
    of_item = open_finance_item_for_detection(conn, current_user_id, detection, target)
    if of_item:
        return _join_open_finance_item(conn, current_user_id, detection, of_item)

    # 2b. O Open Finance ja trouxe esta compra com outro valor:
    # o unico par de cada lado, mesma loja, na faixa. O valor do banco fica.
    near = near_item_for_detection(conn, current_user_id, detection, target)
    if near:
        return _join_open_finance_item(conn, current_user_id, detection, near)

    # 3. Um item novo, com os lancamentos parecidos ja gravados (o dono pode
    # ter digitado antes do aviso chegar): ele decide no Aprovar se e o mesmo.
    # Nada que uma notificacao trouxe se resolve sem passar por la.
    candidates = existing_rows(
        conn, current_user_id, entry_type=target["entry_type"], direction=direction, cents=cents,
        date_text=date_of(when),
        account_id=known_account,
        card_id=target["card_id"] if target["remembered"] else None,
        claimed_by=CLAIM_NOTIFY,
    )
    item_id = new_item_for_detection(conn, current_user_id, detection, target, candidates, rules)
    _insert_detection(conn, current_user_id, detection, SOURCE, item_id=item_id)
    return {"key": detection["key"], "status": "new", "item_id": item_id}


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
        "amount": from_cents(detection["amount_cents"]),
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
# Open Finance (043): a notificacao e a transacao da Pluggy do mesmo movimento
# ---------------------------------------------------------------------------

PAIRABLE_STATES = (PENDING, APPROVED, MATCHED, DENIED)
RECORDED_STATES = (APPROVED, MATCHED)
# O Banco do Brasil manda a Pluggy o valor arredondado para cima, em reais
# inteiros (dono, 2026-10-27: 18,19 chega 19,00). A notificacao tem os
# centavos certos; o par aceita o valor que arredonda para o do banco.
ROUNDS_UP_ISSUERS = {"bb"}


def open_finance_rounds_up(conn, current_user_id, of_account_id):
    """A conta da Pluggy e de um banco que arredonda o valor (ROUNDS_UP_ISSUERS)."""
    row = conn.execute(
        """
        SELECT a.name, i.connector_name FROM open_finance_accounts a
        JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
        WHERE a.id = ? AND a.user_id = ?
        """,
        (of_account_id, current_user_id),
    ).fetchone()
    if not row:
        return False
    issuer = issuer_of_institution(row["connector_name"]) or issuer_of_institution(row["name"])
    return issuer in ROUNDS_UP_ISSUERS


def notification_item_for_open_finance(conn, current_user_id, *, entry_type, direction, cents, date_text,
                                       account_id=None, card_id=None, rounds_up=False):
    """O item que uma notificacao ja abriu para este movimento (pendente ou ja
    decidido) com a vaga da Pluggy DESTE lado livre (I2: numa transferencia, uma
    por ponta; a sumida e a REMOVED nao ocupam): a mesma compra, o mesmo item.
    Sem par no dia (+-1), o que ja virou lancamento ate OPEN_FINANCE_LATE_POST_DAYS
    antes (o banco lancou depois). `rounds_up`: o banco arredondou o valor."""
    def look(states, date_from, date_to):
        rows = conn.execute(
            f"""
            SELECT i.* FROM inbox_items i
            WHERE i.user_id = ? AND i.state IN ({', '.join('?' for _ in states)})
              AND substr(i.occurred_at, 1, 10) BETWEEN ? AND ?
              AND EXISTS (SELECT 1 FROM notify_detections d
                          WHERE d.user_id = i.user_id AND d.item_id = i.id AND d.role = 'SOURCE')
              AND NOT EXISTS (SELECT 1 FROM open_finance_transactions o
                              WHERE o.user_id = i.user_id AND o.item_id = i.id AND o.role <> 'REMOVED'
                                AND COALESCE(o.conflict, '') <> 'vanished' AND o.direction = ?)
            """,
            (current_user_id, *states, date_from, date_to, direction),
        ).fetchall()
        found = [
            row for row in rows
            if _amount_matches(row, cents, rounds_up) and open_finance_fits_item(
                item_dict(row), entry_type=entry_type, direction=direction, account_id=account_id, card_id=card_id,
            )
        ]
        return _pick_closest(found, date_text)

    return look(
        PAIRABLE_STATES, _shift(date_text, -OPEN_FINANCE_PAIR_DAYS), _shift(date_text, OPEN_FINANCE_PAIR_DAYS),
    ) or look(RECORDED_STATES, _shift(date_text, -OPEN_FINANCE_LATE_POST_DAYS), _shift(date_text, -OPEN_FINANCE_PAIR_DAYS - 1))


def _detection_fits_open_finance(conn, current_user_id, detection, target, row):
    """Uma notificacao que chega depois cabe no item que o Open Finance abriu?
    O item sabe o cartao/conta (mapeamento); a notificacao so contradiz com o
    que o dono lembrou, nunca com um palpite."""
    item = item_dict(row)
    of_rows = open_finance_sources(conn, current_user_id, row["id"], roles=(SOURCE, MATCHED, PAIRED))
    if not of_rows:
        return False
    direction = target["direction"]
    entry_type = target["entry_type"]
    item_type = item.get("entry_type")
    if item_type == "TRANSFER":
        if detection["kind"] not in MOVEMENT_KINDS:
            return False
        side = item["account_id"] if direction == "OUT" else item["transfer_account_id"]
        return not (target["remembered"] and target["account_id"] and side and target["account_id"] != side)
    if item.get("direction") != direction:
        return False
    if item_type == "CARD":
        if direction == "OUT" and entry_type not in (None, "CARD"):
            return False
        if direction == "IN" and detection["kind"] != "REFUND":
            return False
        return not (target["remembered"] and target["card_id"] and target["card_id"] != item.get("card_id"))
    if entry_type is not None and entry_type != item_type:
        return False
    return not (target["remembered"] and target["account_id"] and target["account_id"] != item.get("account_id"))


def open_finance_item_for_detection(conn, current_user_id, detection, target):
    """O item que o Open Finance ja abriu para o movimento desta notificacao
    (pendente ou decidido), ainda sem notificacao."""
    when = date_of(detection["occurred_at"])
    rows = conn.execute(
        f"""
        SELECT i.* FROM inbox_items i
        WHERE i.user_id = ? AND i.state IN ({', '.join('?' for _ in PAIRABLE_STATES)})
          AND substr(i.occurred_at, 1, 10) BETWEEN ? AND ?
          AND NOT EXISTS (SELECT 1 FROM notify_detections d
                          WHERE d.user_id = i.user_id AND d.item_id = i.id AND d.role = 'SOURCE')
        """,
        (current_user_id, *PAIRABLE_STATES, _shift(when, -OPEN_FINANCE_PAIR_DAYS), _shift(when, OPEN_FINANCE_PAIR_DAYS)),
    ).fetchall()
    found = [
        row for row in rows
        if (
            _amount_matches(row, detection["amount_cents"])
            or (rounded_up(detection["amount_cents"], to_cents(row["amount"])) and _item_rounds_up(conn, current_user_id, row))
        )
        and _detection_fits_open_finance(conn, current_user_id, detection, target, row)
    ]
    return _pick_closest(found, when)


def _item_rounds_up(conn, current_user_id, row):
    return any(
        open_finance_rounds_up(conn, current_user_id, source["of_account_id"])
        for source in open_finance_sources(conn, current_user_id, row["id"], roles=(SOURCE,))
    )


def _join_open_finance_item(conn, current_user_id, detection, row):
    """A notificacao entra no item que o Open Finance abriu. O cartao/conta do
    item (do mapeamento) fica; o estabelecimento da notificacao, que costuma
    ser mais limpo que a descricao do banco, entra se o dono nao mexeu."""
    item = item_dict(row)
    if item["state"] != PENDING:
        _insert_detection(
            conn, current_user_id, detection, SOURCE if item["state"] != DENIED else PAIRED, item_id=item["id"],
            target_table=item["target_table"], target_id=item["target_id"],
        )
        status = "denied" if item["state"] == DENIED else "matched"
        return {"key": detection["key"], "status": status, "item_id": item["id"]}
    _insert_detection(conn, current_user_id, detection, SOURCE, item_id=item["id"])
    description = detection_description(detection)
    if description and "description" not in set(item["edited"]) and item["entry_type"] != "TRANSFER":
        save_item(conn, current_user_id, item, {"description": description})
    return {"key": detection["key"], "status": "merged", "item_id": item["id"]}


# ---------------------------------------------------------------------------
# A mesma compra com outro valor: o par aproximado
# ---------------------------------------------------------------------------

def near_row_ok(conn, current_user_id, row):
    """A transacao da Pluggy pode ser o par aproximado: uma compra (sem
    movimento), de saida, a vista, num cartao ou conta em reais que nao e a
    Corretora nem a conta global."""
    if row["movement"] or row["direction"] != "OUT":
        return False
    if (row["total_installments"] or 1) > 1 or (row["installment_number"] or 1) > 1:
        return False
    target = conn.execute(
        """
        SELECT a.account_id, a.card_id, x.type AS app_type, x.currency FROM open_finance_accounts a
        LEFT JOIN accounts x ON x.id = a.account_id AND x.user_id = a.user_id
        WHERE a.id = ? AND a.user_id = ?
        """,
        (row["of_account_id"], current_user_id),
    ).fetchone()
    if not target or not (target["account_id"] or target["card_id"]):
        return False
    if target["account_id"] and (target["app_type"] == "BROKERAGE" or (target["currency"] or "BRL") != "BRL"):
        return False
    return True


def row_target(conn, current_user_id, row):
    """(entry_type, account_id, card_id) do mapeamento da transacao."""
    account = conn.execute(
        "SELECT type, account_id, card_id FROM open_finance_accounts WHERE id = ? AND user_id = ?",
        (row["of_account_id"], current_user_id),
    ).fetchone()
    if account["type"] == "CREDIT":
        return "CARD", None, account["card_id"]
    return ("EXPENSE" if row["direction"] == "OUT" else "INCOME"), account["account_id"], None


def near_notification_items(conn, current_user_id, row, exclude_item_id=None):
    """Os itens de notificacao que podem ser esta transacao com outro valor:
    a vaga da Pluggy livre, cabem no mapeamento, mesma loja, na faixa e na janela."""
    if not near_row_ok(conn, current_user_id, row):
        return []
    entry_type, account_id, card_id = row_target(conn, current_user_id, row)
    first, last = _shift(row["date"], -late_posting_days()), _shift(row["date"], OPEN_FINANCE_PAIR_DAYS)
    # Pelas notificacoes da janela (indice user_id, posted_ms; a hora do item
    # fica a ate 24 h do aviso), nunca por todos os itens: roda uma vez por
    # linha nova do pull, e os itens da Pluggy sao a maioria (sessao 5).
    rows = conn.execute(
        f"""
        SELECT i.* FROM (
            SELECT DISTINCT d.item_id FROM notify_detections d
            WHERE d.user_id = ? AND d.role = 'SOURCE' AND d.posted_ms BETWEEN ? AND ? AND d.item_id IS NOT NULL
        ) n CROSS JOIN inbox_items i ON i.id = n.item_id
        WHERE i.user_id = ? AND i.state IN ({', '.join('?' for _ in PAIRABLE_STATES)})
          AND i.occurred_at >= ? AND i.occurred_at < ?
          AND NOT EXISTS (SELECT 1 FROM open_finance_transactions o
                          WHERE o.user_id = i.user_id AND o.item_id = i.id AND o.role <> 'REMOVED'
                            AND COALESCE(o.conflict, '') <> 'vanished' AND o.direction = 'OUT')
        """,
        (current_user_id, _day_ms(_shift(first, -2)), _day_ms(_shift(last, 3)),
         current_user_id, *PAIRABLE_STATES, first, _shift(last, 1)),
    ).fetchall()
    found = []
    for item_row in rows:
        if item_row["id"] == exclude_item_id or int(item_row["installments"] or 1) != 1:
            continue
        detection = next(
            (entry for entry in map(row_to_dict, item_detections(conn, current_user_id, item_row["id"]))
             if entry["role"] == SOURCE and near_detection_ok(entry)),
            None,
        )
        if detection is None:
            continue
        international = is_international(detection) or bool(row.get("original_currency"))
        if not _near_window(item_row["occurred_at"], row["date"], international, item_row["state"] in RECORDED_STATES):
            continue
        if not open_finance_fits_item(
            item_dict(item_row), entry_type=entry_type, direction="OUT", account_id=account_id, card_id=card_id,
        ):
            continue
        if not merchant_agrees(detection["merchant"], row.get("merchant_name"), row.get("description")):
            continue
        if not near_amount(to_cents(item_row["amount"]), row["amount_cents"], international):
            continue
        found.append(item_row)
    return found


def near_open_finance_items(conn, current_user_id, detection, target):
    """Os itens da Pluggy (pendentes ou gravados, sem notificacao) que podem ser
    esta compra com outro valor. Devolve [(item, transacao)]."""
    if not near_detection_ok(detection):
        return []
    when = date_of(detection["occurred_at"])
    international = is_international(detection)
    rows = conn.execute(
        f"""
        SELECT i.* FROM inbox_items i
        WHERE i.user_id = ? AND i.state IN ({', '.join('?' for _ in PAIRABLE_STATES)})
          AND substr(i.occurred_at, 1, 10) BETWEEN ? AND ?
          AND NOT EXISTS (SELECT 1 FROM notify_detections d
                          WHERE d.user_id = i.user_id AND d.item_id = i.id AND d.role = 'SOURCE')
        """,
        (current_user_id, *PAIRABLE_STATES, _shift(when, -OPEN_FINANCE_PAIR_DAYS), _shift(when, late_posting_days())),
    ).fetchall()
    found = []
    for item_row in rows:
        sources = [
            row_to_dict(entry)
            for entry in open_finance_sources(conn, current_user_id, item_row["id"], roles=(SOURCE, MATCHED))
            if (entry["conflict"] or "") != "vanished"
        ]
        if len(sources) != 1 or not near_row_ok(conn, current_user_id, sources[0]):
            continue
        row = sources[0]
        both = international or bool(row.get("original_currency"))
        if not _near_window(detection["occurred_at"], row["date"], both, item_row["state"] in RECORDED_STATES):
            continue
        if not _detection_fits_open_finance(conn, current_user_id, detection, target, item_row):
            continue
        if not merchant_agrees(detection["merchant"], row.get("merchant_name"), row.get("description")):
            continue
        if not near_amount(detection["amount_cents"], row["amount_cents"], both):
            continue
        found.append((item_row, row))
    return found


def near_item_for_detection(conn, current_user_id, detection, target):
    """Passo 5b: o unico item da Pluggy que a notificacao pode ser com outro
    valor, e ela a unica notificacao que sobra para ele. Senao None."""
    found = near_open_finance_items(conn, current_user_id, detection, target)
    if len(found) != 1:
        return None
    item_row, row = found[0]
    if near_notification_items(conn, current_user_id, row):
        return None
    return item_row


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


def serialize_item(conn, current_user_id, row, names=None, recurrences=None, ask=None):
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
            "amount": from_cents(detection["amount_cents"]),
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
    for row in conn.execute(
        """
        SELECT t.*, a.name AS of_account_name, a.number AS of_account_number, a.type AS of_account_type,
               i.connector_name
        FROM open_finance_transactions t
        JOIN open_finance_accounts a ON a.id = t.of_account_id AND a.user_id = t.user_id
        JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = t.user_id
        WHERE t.user_id = ? AND t.item_id = ?
        ORDER BY t.date, t.created_at, t.id
        """,
        (current_user_id, item["id"]),
    ).fetchall():
        sources.append({
            "source": "open_finance",
            "id": row["id"],
            "role": row["role"],
            "connector_name": row["connector_name"],
            "bank_name": open_finance_bank_name(row["of_account_name"], row["connector_name"]),
            "account_name": row["of_account_name"],
            "account_type": row["of_account_type"],
            "direction": row["direction"],
            "movement": row["movement"],
            "amount": from_cents(row["amount_cents"]),
            "currency": row["currency"],
            "date": row["date"],
            "occurred_at": row["occurred_at"],
            "description": row["description"],
            "pluggy_category": row["pluggy_category"],
            "installment_number": row["installment_number"],
            "total_installments": row["total_installments"],
            "counterparty": row["counterparty"],
            "received_at": row["created_at"],
        })
    item["sources"] = sources
    if ask is None:
        ask = always_ask(conn, current_user_id)
    item["confirm"] = confirm_targets(item, ask)
    # Mais de uma conta/cartao no banco e a notificacao sem o final: a tela
    # pergunta toda vez e nao oferece "Lembrar a escolha".
    item["ambiguous"] = item.get("state") == PENDING and ambiguous_target(
        conn, current_user_id, item.get("hint_key"), item.get("entry_type"),
    )
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
    ask = always_ask(conn, current_user_id)
    return [serialize_item(conn, current_user_id, row, names, recurrences, ask) for row in rows]


# ---------------------------------------------------------------------------
# Preferencias (036)
# ---------------------------------------------------------------------------

def bank_notifications(conn, current_user_id):
    value = setting_value(conn, current_user_id, BANK_NOTIFICATIONS_SETTING)
    return BANK_NOTIFICATIONS_DEFAULT if value is None else value == "1"


# ---------------------------------------------------------------------------
# O nome do banco de uma conta da Pluggy
# ---------------------------------------------------------------------------
