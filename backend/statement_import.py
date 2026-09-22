"""Leitura de extrato bancario: CSV com mapeamento de colunas, e OFX.

Modulo sem banco de dados de proposito — tudo aqui e funcao pura sobre o texto
do arquivo. O app.py cuida de conta, categoria, regras e gravacao.

O formato de saida e sempre o mesmo, venha de CSV ou de OFX:

    {"line": 3, "date": "2026-09-01", "amount": 42.9, "type": "EXPENSE",
     "description": "PADARIA DO ZE", "fitid": None, "error": None}

`amount` e sempre positivo; o sinal do arquivo vira `type`.
"""

import csv
import hashlib
import io
import re
import unicodedata
from datetime import datetime

# Cabecalhos que os bancos brasileiros costumam usar, normalizados (sem acento,
# minusculos). Servem para adivinhar o mapeamento; o dono pode sobrescrever.
HEADER_HINTS = {
    "date": (
        "data", "data lancamento", "data do lancamento", "data mov",
        "data movimento", "data da compra", "dt", "date", "posted date",
    ),
    "description": (
        "descricao", "historico", "lancamento", "detalhes", "titulo",
        "estabelecimento", "memo", "description", "name",
    ),
    "amount": (
        "valor", "valor (r$)", "valor r$", "montante", "quantia",
        "amount", "value",
    ),
    "debit": ("debito", "saida", "despesa", "debit", "withdrawal"),
    "credit": ("credito", "entrada", "receita", "credit", "deposit"),
    "type": ("tipo", "tipo de lancamento", "type", "natureza"),
}

DELIMITERS = (";", ",", "\t", "|")

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)

# Palavras que, na coluna de tipo, dizem que o valor sai da conta.
DEBIT_WORDS = ("debito", "saida", "despesa", "pagamento", "d", "debit")

MAX_IMPORT_ROWS = 2000


class ImportError_(ValueError):
    """Arquivo ilegivel como um todo (nao uma linha ruim)."""


def strip_accents(value):
    decomposed = unicodedata.normalize("NFD", str(value))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize_text(value):
    """Minusculo, sem acento, sem espaco duplicado. Base de hash e de regra."""
    text = strip_accents(value or "").lower()
    return re.sub(r"\s+", " ", text).strip()


def normalize_description(value):
    """Normalizacao do hash: tira tambem pontuacao e numeros de autorizacao.

    O mesmo lancamento reexportado pelo banco costuma variar em espaco e
    pontuacao; o que nao varia e data, valor e as palavras da descricao.
    """
    text = normalize_text(value)
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def row_hash(account_id, date_value, amount, description, occurrence=0):
    """Chave de deduplicacao de uma linha importada.

    Inclui a conta porque a mesma compra pode aparecer em dois extratos
    diferentes e sao dois lancamentos de verdade. `occurrence` separa linhas
    identicas dentro do mesmo arquivo (dois cafes iguais no mesmo dia).
    """
    base = "|".join([
        str(account_id or ""),
        str(date_value or ""),
        f"{float(amount or 0):.2f}",
        normalize_description(description),
    ])
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]
    return digest if occurrence == 0 else f"{digest}:{occurrence}"


def ofx_source_id(account_id, fitid):
    """Identificador do proprio banco: melhor chave de dedupe que existe."""
    return f"ofx:{account_id or ''}:{fitid}"


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # OFX: AAAAMMDD, com ou sem hora/fuso colados atras.
    digits = re.match(r"^(\d{8})", re.sub(r"\D", "", text))
    if digits:
        try:
            return datetime.strptime(digits.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def parse_amount(value, decimal_separator="auto"):
    """Valor monetario em pt-BR ou en-US, com ou sem R$, parenteses = negativo."""
    text = str(value or "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^\d,.\-+]", "", text)
    if not text or text in ("-", "+", ".", ","):
        return None
    if text.startswith("-"):
        negative = True
    text = text.lstrip("+-")

    separator = decimal_separator
    if separator == "auto":
        last_comma = text.rfind(",")
        last_dot = text.rfind(".")
        if last_comma == -1 and last_dot == -1:
            separator = None
        elif last_comma > last_dot:
            separator = ","
        elif last_dot > last_comma:
            separator = "."
        else:
            separator = None

    if separator == ",":
        text = text.replace(".", "").replace(",", ".")
    elif separator == ".":
        text = text.replace(",", "")
    else:
        text = text.replace(",", "").replace(".", "")

    try:
        amount = float(text)
    except ValueError:
        return None
    return -amount if negative else amount


def sniff_delimiter(sample):
    """Delimitador mais frequente na primeira linha que tem algum deles."""
    for line in sample.splitlines():
        if not line.strip():
            continue
        counts = {delimiter: line.count(delimiter) for delimiter in DELIMITERS}
        best = max(counts, key=counts.get)
        if counts[best] > 0:
            return best
    return ";"


def looks_like_header(cells):
    """Cabecalho e a linha sem data nem valor reconheciveis em nenhuma celula."""
    for cell in cells:
        if parse_date(cell) is not None:
            return False
    numeric = sum(1 for cell in cells if parse_amount(cell) is not None)
    return numeric < max(1, len(cells) // 2)


def guess_mapping(header):
    """Mapeia papel -> indice de coluna a partir dos nomes do cabecalho."""
    mapping = {}
    normalized = [normalize_text(cell) for cell in header]
    for role, hints in HEADER_HINTS.items():
        for index, cell in enumerate(normalized):
            if index in mapping.values():
                continue
            if cell in hints or any(cell.startswith(hint) for hint in hints):
                mapping[role] = index
                break
    return mapping


def guess_mapping_positional(rows):
    """Sem cabecalho: acha a primeira coluna que e data e a que e valor."""
    mapping = {}
    for row in rows:
        for index, cell in enumerate(row):
            if "date" not in mapping and parse_date(cell) is not None:
                mapping["date"] = index
            elif "amount" not in mapping and parse_amount(cell) is not None:
                mapping["amount"] = index
        if "date" in mapping and "amount" in mapping:
            break
    if "date" in mapping and "amount" in mapping:
        used = set(mapping.values())
        for index in range(max(used) + 1):
            if index not in used:
                mapping["description"] = index
                break
    return mapping


def resolve_mapping(requested, header):
    """Aceita nome de coluna ou indice no mapeamento vindo do cliente."""
    if requested and not isinstance(requested, dict):
        raise ImportError_("Mapeamento de colunas invalido.")
    resolved = {}
    normalized = [normalize_text(cell) for cell in (header or [])]
    for role, column in (requested or {}).items():
        if column in (None, ""):
            continue
        if isinstance(column, int) or str(column).lstrip("-").isdigit():
            resolved[role] = int(column)
            continue
        wanted = normalize_text(column)
        if wanted in normalized:
            resolved[role] = normalized.index(wanted)
        else:
            raise ImportError_(f"Coluna '{column}' nao existe no arquivo.")
    return resolved


def cell(row, index):
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def signed_amount(row, mapping, decimal_separator, type_column_says_debit):
    """Valor com sinal, cobrindo as tres formas que os bancos exportam.

    Uma coluna Valor com sinal; duas colunas Debito/Credito; ou uma coluna
    Valor sem sinal mais uma coluna Tipo dizendo a natureza.
    """
    if "amount" in mapping:
        amount = parse_amount(cell(row, mapping["amount"]), decimal_separator)
        if amount is None:
            return None
        if amount > 0 and type_column_says_debit:
            amount = -amount
        return amount

    debit = parse_amount(cell(row, mapping.get("debit")), decimal_separator) if "debit" in mapping else None
    credit = parse_amount(cell(row, mapping.get("credit")), decimal_separator) if "credit" in mapping else None
    if debit:
        return -abs(debit)
    if credit:
        return abs(credit)
    return None


def parse_csv(content, *, mapping=None, delimiter=None, has_header=None,
              decimal_separator="auto", invert_sign=False, skip_rows=0):
    """Le o CSV e devolve (linhas normalizadas, metadados do arquivo)."""
    text = (content or "").lstrip("﻿")
    if not text.strip():
        raise ImportError_("Arquivo vazio.")

    delimiter = delimiter or sniff_delimiter(text)
    if len(delimiter) != 1:
        raise ImportError_("O separador de colunas precisa ser um unico caractere.")
    try:
        skip_rows = max(int(skip_rows or 0), 0)
    except (TypeError, ValueError):
        raise ImportError_("Linhas a pular precisa ser um numero.")

    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        raw_rows = [row for row in reader if any(str(c).strip() for c in row)]
    except csv.Error as exc:
        raise ImportError_(f"Nao consegui ler o CSV: {exc}")
    if skip_rows:
        raw_rows = raw_rows[skip_rows:]
    if not raw_rows:
        raise ImportError_("Nenhuma linha util no arquivo.")

    if has_header is None:
        has_header = looks_like_header(raw_rows[0])
    header = [str(c).strip() for c in raw_rows[0]] if has_header else []
    body = raw_rows[1:] if has_header else raw_rows

    effective = guess_mapping(header) if has_header else guess_mapping_positional(body)
    effective.update(resolve_mapping(mapping, header))

    if "date" not in effective:
        raise ImportError_("Nao encontrei a coluna de data. Ajuste o mapeamento.")
    if not ({"amount", "debit", "credit"} & set(effective)):
        raise ImportError_("Nao encontrei a coluna de valor. Ajuste o mapeamento.")

    rows = []
    first_data_line = (2 if has_header else 1) + skip_rows
    for offset, raw in enumerate(body[:MAX_IMPORT_ROWS]):
        line = first_data_line + offset
        date_value = parse_date(cell(raw, effective.get("date")))
        type_text = normalize_text(cell(raw, effective.get("type"))) if "type" in effective else ""
        says_debit = any(word == type_text or type_text.startswith(word) for word in DEBIT_WORDS)
        amount = signed_amount(raw, effective, decimal_separator, says_debit)
        description = cell(raw, effective.get("description"))

        if date_value is None:
            rows.append(error_row(line, "Data invalida.", raw))
            continue
        if amount is None:
            rows.append(error_row(line, "Valor invalido.", raw))
            continue
        if invert_sign:
            amount = -amount
        if amount == 0:
            rows.append(error_row(line, "Valor zero.", raw))
            continue

        rows.append({
            "line": line,
            "date": date_value,
            "amount": abs(amount),
            "type": "INCOME" if amount > 0 else "EXPENSE",
            "description": description,
            "fitid": None,
            "error": None,
        })

    meta = {
        "format": "CSV",
        "delimiter": delimiter,
        "has_header": bool(has_header),
        "columns": header,
        "mapping": {role: index for role, index in sorted(effective.items())},
        "truncated": len(body) > MAX_IMPORT_ROWS,
    }
    return rows, meta


def error_row(line, message, raw=None):
    return {
        "line": line,
        "date": None,
        "amount": None,
        "type": None,
        "description": " ".join(str(c).strip() for c in (raw or []) if str(c).strip())[:200],
        "fitid": None,
        "error": message,
    }


def ofx_tag(block, tag):
    """Valor de uma tag OFX (SGML: abre sem fechar, termina na proxima tag)."""
    match = re.search(rf"<{tag}>([^<\r\n]*)", block, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_ofx(content, *, invert_sign=False):
    """Le os <STMTTRN> de um OFX/OFC. FITID vira a chave de deduplicacao."""
    text = content or ""
    if "<STMTTRN>" not in text.upper():
        raise ImportError_("Arquivo OFX sem lancamentos (<STMTTRN>).")

    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.IGNORECASE | re.DOTALL)
    bank_account = ofx_tag(text, "ACCTID")
    rows = []
    for index, block in enumerate(blocks[:MAX_IMPORT_ROWS]):
        line = index + 1
        date_value = parse_date(ofx_tag(block, "DTPOSTED"))
        amount = parse_amount(ofx_tag(block, "TRNAMT"), ".")
        description = ofx_tag(block, "MEMO") or ofx_tag(block, "NAME")

        if date_value is None:
            rows.append(error_row(line, "Data invalida."))
            continue
        if amount is None or amount == 0:
            rows.append(error_row(line, "Valor invalido."))
            continue
        if invert_sign:
            amount = -amount

        rows.append({
            "line": line,
            "date": date_value,
            "amount": abs(amount),
            "type": "INCOME" if amount > 0 else "EXPENSE",
            "description": description,
            "fitid": ofx_tag(block, "FITID") or None,
            "error": None,
        })

    meta = {
        "format": "OFX",
        "delimiter": None,
        "has_header": False,
        "columns": [],
        "mapping": {},
        "bank_account": bank_account or None,
        "truncated": len(blocks) > MAX_IMPORT_ROWS,
    }
    return rows, meta


def detect_format(content, filename=None):
    name = normalize_text(filename or "")
    if name.endswith(".ofx") or name.endswith(".ofc"):
        return "OFX"
    if name.endswith(".csv") or name.endswith(".txt"):
        return "CSV"
    head = (content or "")[:4000].upper()
    if "<OFX>" in head or "OFXHEADER" in head or "<STMTTRN>" in head:
        return "OFX"
    return "CSV"


def parse_statement(content, *, file_format=None, filename=None, **options):
    """Porta de entrada: detecta o formato e delega."""
    resolved = (file_format or "").upper() or detect_format(content, filename)
    if resolved == "OFX":
        return parse_ofx(content, invert_sign=bool(options.get("invert_sign")))
    return parse_csv(
        content,
        mapping=options.get("mapping"),
        delimiter=options.get("delimiter"),
        has_header=options.get("has_header"),
        decimal_separator=options.get("decimal_separator", "auto"),
        invert_sign=bool(options.get("invert_sign")),
        skip_rows=options.get("skip_rows", 0),
    )


def rule_matches(rule, description_normalized, transaction_type):
    """Uma regra casa por texto e, opcionalmente, pela natureza do lancamento."""
    applies_to = rule.get("applies_to") or "BOTH"
    if applies_to != "BOTH" and applies_to != transaction_type:
        return False
    pattern = normalize_text(rule.get("pattern"))
    if not pattern:
        return False
    match_type = rule.get("match_type") or "CONTAINS"
    if match_type == "EQUALS":
        return description_normalized == pattern
    if match_type == "STARTS_WITH":
        return description_normalized.startswith(pattern)
    return pattern in description_normalized


def first_matching_rule(rules, description, transaction_type):
    """Primeira regra que casa, na ordem em que o chamador as entregou."""
    normalized = normalize_text(description)
    if not normalized:
        return None
    for rule in rules:
        if rule_matches(rule, normalized, transaction_type):
            return rule
    return None
