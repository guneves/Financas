"""Leitura e validacao do corpo das requisicoes.

Os `require_*` / `parse_*` levantam `ValidationError` com a mensagem em
portugues que vai para a tela; a rota a transforma em 400 com
`validation_error(str(exc))`.
"""

import math
from datetime import datetime

from flask import jsonify, request


def safe_float(value, default=0):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class ValidationError(ValueError):
    pass


def validation_error(message, status=400):
    return jsonify({"error": message}), status


def require_string(payload, key, label, max_length=255):
    value = str(payload.get(key, "") or "").strip()
    if not value:
        raise ValidationError(f"{label} e obrigatorio.")
    if len(value) > max_length:
        raise ValidationError(f"{label} deve ter no maximo {max_length} caracteres.")
    return value


def optional_string(payload, key, max_length=500):
    value = payload.get(key)
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) > max_length:
        raise ValidationError(f"{key} deve ter no maximo {max_length} caracteres.")
    return value


def require_choice(payload, key, label, choices):
    value = str(payload.get(key, "") or "").strip().upper()
    if value not in choices:
        raise ValidationError(f"{label} invalido.")
    return value


def parse_number(payload, key, label, *, minimum=None, maximum=None, allow_zero=True):
    try:
        value = float(payload.get(key))
    except (TypeError, ValueError):
        raise ValidationError(f"{label} deve ser um numero valido.")

    if not math.isfinite(value):
        raise ValidationError(f"{label} deve ser um numero valido.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} deve ser maior ou igual a {minimum}.")
    if not allow_zero and value == 0:
        raise ValidationError(f"{label} deve ser maior que zero.")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{label} deve ser menor ou igual a {maximum}.")
    return value


def parse_optional_number(payload, key, label, *, minimum=None, maximum=None):
    if key not in payload or payload.get(key) in (None, ""):
        return None
    return parse_number(payload, key, label, minimum=minimum, maximum=maximum)


def parse_int_number(payload, key, label, *, minimum=None, maximum=None):
    value = parse_number(payload, key, label, minimum=minimum, maximum=maximum)
    if not float(value).is_integer():
        raise ValidationError(f"{label} deve ser um numero inteiro.")
    return int(value)


def require_date(payload, key, label):
    value = require_string(payload, key, label, max_length=10)
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"{label} deve estar no formato AAAA-MM-DD.")
    return value


def optional_date(payload, key, label):
    if key not in payload or payload.get(key) in (None, ""):
        return None
    return require_date(payload, key, label)


def require_month(payload, key, label):
    value = require_string(payload, key, label, max_length=7)
    return normalize_month(value, label)


def normalize_month(value, label="Mes"):
    """Valida e devolve um mes no formato AAAA-MM."""
    text = str(value or "").strip()
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError:
        raise ValidationError(f"{label} deve estar no formato AAAA-MM.")
    return text


def shift_month(month, offset):
    """Soma (ou subtrai) meses a um AAAA-MM, com virada de ano."""
    year, _, raw_month = month.partition("-")
    index = (int(year) * 12 + int(raw_month) - 1) + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def require_id_list(payload, key="ids"):
    raw_ids = payload.get(key)
    if not isinstance(raw_ids, list):
        raise ValidationError("Informe uma lista de ids.")

    ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    if not ids:
        raise ValidationError("Informe ao menos um id.")
    return ids


def parse_json_body():
    return request.get_json(silent=True) or {}
