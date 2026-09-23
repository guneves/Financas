"""Datas e meses: conversao de texto ISO e aritmetica de calendario."""

import calendar
from datetime import datetime, timezone


def clamped_date(year, month, day):
    """Dia `day` do mes, recuado para o ultimo dia quando o mes e mais curto."""
    year, month = int(year), int(month)
    return datetime(year, month, min(int(day), calendar.monthrange(year, month)[1])).date()


def subtract_months(date_value, months):
    month = date_value.month - months
    year = date_value.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(date_value.day, calendar.monthrange(year, month)[1])
    return date_value.replace(year=year, month=month, day=day)


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def parse_iso_datetime(value):
    if not value:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        parsed_date = parse_iso_date(raw_value)
        if not parsed_date:
            return None
        return parsed_date.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def month_label(date_value):
    return date_value.strftime("%m/%y")


def month_key(date_value):
    return date_value.strftime("%Y-%m")


def month_end(date_value):
    last_day = calendar.monthrange(date_value.year, date_value.month)[1]
    return datetime(date_value.year, date_value.month, last_day, 23, 59, 59)
