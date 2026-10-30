"""Recorrencias: o calendario de cada molde e o que ele ja deve (010, 019).

Uma recorrencia e um modelo, nao dinheiro. `materialize_recurring` grava as
ocorrencias vencidas em `transactions` (`source_type = 'RECURRING_TRANSACTION'`,
`source_id = '<recorrencia>:<AAAA-MM-DD>'`); routes/recurring.py e a tela.

Uma ocorrencia tambem pode ser dada como feita por um lancamento que ja existe
(034, `recurring_settlements`): o dono aprovou em Aprovar a notificacao da
assinatura ou do salario. Ela deixa de ser pendente, sai da previsao e o /run
passa por ela sem gravar nada — o dinheiro ja esta no lancamento aprovado.
"""

import calendar
import json
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from dates import parse_iso_date
from db import new_id, serialize_metadata_row, serialize_transaction, utc_timestamp
from money import rounded_money
from services.accounts import ensure_default_account
from services.import_rules import DEFAULT_IMPORT_CATEGORIES
from source_types import RECURRING_SOURCE_TYPE

ALLOWED_RECURRING_TYPES = {"INCOME", "EXPENSE"}
ALLOWED_RECURRENCE_FREQUENCIES = {"WEEKLY", "MONTHLY", "YEARLY"}
# Teto por recorrencia numa unica chamada de /api/recurring/run: uma semanal
# esquecida por anos nao pode gerar milhares de lancamentos de uma vez.
RECURRING_MAX_OCCURRENCES = 400


def recurring_add_months(date_value, months, anchor_day=None):
    """Soma meses preservando o dia de ancoragem, com clamp no fim do mes.

    O dia vem de `start_date` e nao da ultima ocorrencia, senao uma recorrencia
    dia 31 cairia em 28 no primeiro fevereiro e ficaria presa no dia 28 para
    sempre.
    """
    index = date_value.year * 12 + (date_value.month - 1) + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    day = min(anchor_day or date_value.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


def recurring_next_date(date_value, frequency, interval_count, anchor_day=None):
    interval = max(1, int(interval_count or 1))
    if frequency == "WEEKLY":
        return date_value + timedelta(weeks=interval)
    if frequency == "YEARLY":
        return recurring_add_months(date_value, 12 * interval, anchor_day)
    return recurring_add_months(date_value, interval, anchor_day)


def recurring_today():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def recurring_pause_gaps(row):
    """Janelas de pausa ja retomadas (019), como pares (inicio, fim) exclusivos.

    Uma ocorrencia estritamente entre o dia da pausa e o dia da retomada nao e
    devida: a assinatura estava cancelada. O dia da pausa em si ainda vale (o
    que venceu nele ja tinha vencido quando o usuario pausou), e o dia da
    retomada tambem.
    """
    try:
        raw = json.loads(row["pause_gaps"] or "[]")
    except (TypeError, ValueError):
        return []
    gaps = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            gap_start, gap_end = parse_iso_date(item[0]), parse_iso_date(item[1])
            if gap_start and gap_end:
                gaps.append((gap_start, gap_end))
    return gaps


def encode_pause_gaps(gaps):
    if not gaps:
        return None
    return json.dumps(
        [[gap_start.strftime("%Y-%m-%d"), gap_end.strftime("%Y-%m-%d")] for gap_start, gap_end in gaps]
    )


def skip_pause_gaps(row, cursor_date, anchor_day, gaps=None):
    """Anda o cursor ate a primeira data fora de qualquer janela de pausa."""
    gaps = recurring_pause_gaps(row) if gaps is None else gaps
    guard = 0
    while (
        any(gap_start < cursor_date < gap_end for gap_start, gap_end in gaps)
        and guard < RECURRING_MAX_OCCURRENCES * 25
    ):
        cursor_date = recurring_next_date(
            cursor_date, row["frequency"], row["interval_count"], anchor_day
        )
        guard += 1
    return cursor_date


def recurring_occurrence_dates(row, through_date, *, limit=RECURRING_MAX_OCCURRENCES):
    """Datas devidas por esta recorrencia ate `through_date`, inclusive.

    Comeca em next_run_date (o que ainda nao foi materializado), salta as
    janelas de pausa, respeita end_date e tem um teto de seguranca: uma
    recorrencia semanal esquecida por anos nao pode gerar milhares de
    lancamentos numa chamada.

    next_run_date nulo e recorrencia encerrada: nao deve nada. Cair de volta em
    start_date aqui recontava o historico inteiro como pendente — o /run nao
    duplicava (o indice unico barra), mas o contador nunca zerava.
    """
    start = parse_iso_date(row["start_date"])
    cursor_date = parse_iso_date(row["next_run_date"])
    if not cursor_date or not through_date:
        return []

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    anchor_day = start.day if start else cursor_date.day
    gaps = recurring_pause_gaps(row)
    cursor_date = skip_pause_gaps(row, cursor_date, anchor_day, gaps)
    dates = []
    while cursor_date <= through_date and len(dates) < limit:
        if end and cursor_date > end:
            break
        dates.append(cursor_date)
        cursor_date = skip_pause_gaps(
            row,
            recurring_next_date(cursor_date, row["frequency"], row["interval_count"], anchor_day),
            anchor_day,
            gaps,
        )
    return dates


def recurring_date_after(row, date_value):
    """A ocorrencia seguinte a `date_value`, ou None se a recorrencia acabou."""
    start = parse_iso_date(row["start_date"])
    anchor_day = start.day if start else date_value.day
    following = skip_pause_gaps(
        row,
        recurring_next_date(date_value, row["frequency"], row["interval_count"], anchor_day),
        anchor_day,
    )
    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    if end and following > end:
        return None
    return following


def recurring_cursor_after_gaps(row):
    """next_run_date de `row` fora das janelas de pausa, ou None se passou do fim."""
    cursor_date = parse_iso_date(row["next_run_date"])
    if not cursor_date:
        return None
    start = parse_iso_date(row["start_date"])
    anchor_day = start.day if start else cursor_date.day
    cursor_date = skip_pause_gaps(row, cursor_date, anchor_day)
    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    if end and cursor_date > end:
        return None
    return cursor_date.strftime("%Y-%m-%d")


def recurring_resume_date(row, from_date):
    """Primeira ocorrencia em ou depois de `from_date`, ao retomar uma pausa
    sem `paused_at` (pausada antes de 019, quando o dia da pausa nao era guardado).

    Retomar nao pode gerar o periodo pausado: a assinatura foi cancelada
    naqueles meses, o dinheiro nao saiu, e materializar aquilo criaria despesas
    que nunca existiram — que o orcamento (009) e o saldo por conta (007)
    contariam como reais. Sem saber quando a pausa comecou, anda ate hoje.
    """
    cursor_date = parse_iso_date(row["next_run_date"])
    if not cursor_date:
        return None

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    start = parse_iso_date(row["start_date"])
    anchor_day = start.day if start else cursor_date.day
    guard = 0
    while cursor_date < from_date and guard < RECURRING_MAX_OCCURRENCES:
        cursor_date = recurring_next_date(
            cursor_date, row["frequency"], row["interval_count"], anchor_day
        )
        guard += 1

    if end and cursor_date > end:
        return None
    return cursor_date.strftime("%Y-%m-%d")


def recurring_revival_date(row):
    """Proxima ocorrencia de uma recorrencia encerrada cujo end_date foi estendido.

    Encerrada perde o next_run_date, entao o cursor e reconstruido: a primeira
    data do calendario (ancorado no dia de start_date, com a frequencia do
    DEPOIS do PATCH) estritamente posterior a `last_occurrence_date`, a ultima
    data que o /run percorreu. Sem nada percorrido, comeca em start_date.

    O ponto de partida e o cursor guardado (019), nao o ultimo lancamento
    gerado que ainda existe: apagar esse lancamento nao pode faze-lo voltar.

    Diferente de retomar uma pausa: prorrogar diz que o contrato continuou, e o
    intervalo entre o fim antigo e hoje fica pendente de proposito.
    """
    start = parse_iso_date(row["start_date"])
    if not start:
        return None

    last_date = parse_iso_date(row["last_occurrence_date"])

    cursor_date = start
    if last_date:
        guard = 0
        while cursor_date <= last_date and guard < RECURRING_MAX_OCCURRENCES * 25:
            cursor_date = recurring_next_date(
                cursor_date, row["frequency"], row["interval_count"], start.day
            )
            guard += 1
    cursor_date = skip_pause_gaps(row, cursor_date, start.day)

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    if end and cursor_date > end:
        return None
    return cursor_date.strftime("%Y-%m-%d")


def recurring_status(row):
    if not row["active"]:
        return "PAUSED"
    if not row["next_run_date"]:
        return "FINISHED"
    return "ACTIVE"


def recurring_source_id(recurring_id, date_text):
    return f"{recurring_id}:{date_text}"


def serialize_recurring(row, *, pending=None):
    item = serialize_metadata_row(row)
    if not item:
        return item
    item["active"] = bool(item.get("active"))
    item["amount"] = rounded_money(item.get("amount"))
    item["pause_gaps"] = [
        [gap_start.strftime("%Y-%m-%d"), gap_end.strftime("%Y-%m-%d")]
        for gap_start, gap_end in recurring_pause_gaps(row)
    ]
    item["status"] = recurring_status(row)
    if pending is not None:
        item["pending_count"] = pending
    return item


def fetch_recurring(conn, current_user_id, recurring_id):
    return conn.execute(
        "SELECT * FROM recurring_transactions WHERE id = ? AND user_id = ?",
        (recurring_id, current_user_id),
    ).fetchone()


def recurring_rows(conn, current_user_id, *, include_inactive=True):
    query = "SELECT * FROM recurring_transactions WHERE user_id = ?"
    if not include_inactive:
        query += " AND active = 1"
    query += " ORDER BY active DESC, next_run_date IS NULL, next_run_date, description COLLATE NOCASE, id"
    return conn.execute(query, (current_user_id,)).fetchall()


def recurring_archived_account(conn, current_user_id, row):
    """A conta arquivada desta recorrencia, ou None. Arquivada, a recorrencia
    nao lanca: o dinheiro iria para uma conta que saiu das telas. As
    ocorrencias ficam pendentes ate o dono trocar a conta (ou arquivar a
    recorrencia)."""
    if not row["account_id"]:
        return None
    account = conn.execute(
        "SELECT id, name, archived_at FROM accounts WHERE id = ? AND user_id = ?",
        (row["account_id"], current_user_id),
    ).fetchone()
    return account if account and account["archived_at"] else None


def _pluggy_account(conn, current_user_id, account_id):
    return conn.execute(
        """
        SELECT 1 FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        WHERE o.user_id = ? AND o.account_id = ? AND i.archived_at IS NULL
        """,
        (current_user_id, account_id),
    ).fetchone() is not None


def materialize_recurring(conn, current_user_id, row, through_date):
    """Gera em `transactions` tudo o que esta recorrencia deve ate `through_date`.

    Devolve (lancamentos criados, ja existentes). A repeticao e inofensiva: o
    indice unico (user_id, source_type, source_id) rejeita a segunda insercao
    da mesma data, e o INSERT OR IGNORE transforma isso em "ja existia".
    """
    created = []
    skipped = 0
    dates = recurring_occurrence_dates(row, through_date)
    if not dates or recurring_archived_account(conn, current_user_id, row):
        return created, skipped

    account_id = row["account_id"] or ensure_default_account(conn, current_user_id)
    amount = rounded_money(row["amount"])
    settled = settled_dates(conn, current_user_id, row["id"])
    from_bank = _pluggy_account(conn, current_user_id, account_id)
    for occurrence in dates:
        date_text = occurrence.strftime("%Y-%m-%d")
        if date_text in settled or from_bank:
            # Feita por um lancamento aprovado (034): o dinheiro ja esta nele. A
            # conta conectada a Pluggy so recebe o que o banco manda: a ocorrencia
            # passa sem gravar (o movimento vem do pull).
            skipped += 1
            continue
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO transactions
            (id, user_id, account_id, amount, date, category, category_id, description,
             type, source_type, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                current_user_id,
                account_id,
                amount,
                date_text,
                row["category"],
                row["category_id"],
                row["description"],
                row["type"],
                RECURRING_SOURCE_TYPE,
                recurring_source_id(row["id"], date_text),
            ),
        )
        if cursor.rowcount:
            item = conn.execute(
                """
                SELECT * FROM transactions
                WHERE user_id = ? AND source_type = ? AND source_id = ?
                """,
                (current_user_id, RECURRING_SOURCE_TYPE, recurring_source_id(row["id"], date_text)),
            ).fetchone()
            created.append(serialize_transaction(item))
        else:
            skipped += 1

    following = recurring_date_after(row, dates[-1])
    # O cursor so anda para a frente: um next_run_date rebobinado a mao nao
    # pode trazer last_occurrence_date de volta. Janelas de pausa que ficaram
    # para tras nunca mais valem nada.
    last_occurrence = dates[-1]
    previous_last = parse_iso_date(row["last_occurrence_date"])
    if previous_last and previous_last > last_occurrence:
        last_occurrence = previous_last
    remaining_gaps = [
        gap for gap in recurring_pause_gaps(row) if gap[1] > last_occurrence
    ]
    conn.execute(
        """
        UPDATE recurring_transactions
        SET next_run_date = ?, last_occurrence_date = ?, pause_gaps = ?,
            last_run_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            following.strftime("%Y-%m-%d") if following else None,
            last_occurrence.strftime("%Y-%m-%d"),
            encode_pause_gaps(remaining_gaps),
            utc_timestamp(),
            utc_timestamp(),
            row["id"],
            current_user_id,
        ),
    )
    return created, skipped


def recurring_pending_count(conn, current_user_id, row, today):
    if not row["active"]:
        return 0
    settled = settled_dates(conn, current_user_id, row["id"])
    return sum(
        1 for occurrence in recurring_occurrence_dates(row, today)
        if occurrence.strftime("%Y-%m-%d") not in settled
    )


def build_recurring_forecast(conn, current_user_id, days):
    """Previsao de caixa: o que as recorrencias ativas lancam ate hoje + `days`.

    Nada e gravado. Ocorrencias com data <= hoje aparecem como `pending` — elas
    ja venceram e so nao existem porque /run ainda nao foi chamado.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    horizon = today + timedelta(days=days)
    occurrences = []
    for row in recurring_rows(conn, current_user_id, include_inactive=False):
        settled = settled_dates(conn, current_user_id, row["id"])
        for occurrence in recurring_occurrence_dates(row, horizon):
            date_text = occurrence.strftime("%Y-%m-%d")
            if date_text in settled:
                continue
            occurrences.append({
                "recurring_id": row["id"],
                "date": date_text,
                "type": row["type"],
                "amount": rounded_money(row["amount"]),
                "category": row["category"],
                "category_id": row["category_id"],
                "description": row["description"],
                "account_id": row["account_id"],
                "pending": occurrence <= today,
            })
    occurrences.sort(key=lambda item: (item["date"], item["description"] or "", item["recurring_id"]))

    def totals_through(limit_date):
        income = sum(
            item["amount"] for item in occurrences
            if item["type"] == "INCOME" and item["date"] <= limit_date
        )
        expense = sum(
            item["amount"] for item in occurrences
            if item["type"] == "EXPENSE" and item["date"] <= limit_date
        )
        return {
            "income": rounded_money(income),
            "expense": rounded_money(expense),
            "net": rounded_money(income - expense),
        }

    buckets = {}
    for window in (30, 60, 90):
        if window <= days:
            limit_date = (today + timedelta(days=window)).strftime("%Y-%m-%d")
            buckets[str(window)] = totals_through(limit_date)

    return {
        "from_date": today.strftime("%Y-%m-%d"),
        "through_date": horizon.strftime("%Y-%m-%d"),
        "days": days,
        "occurrences": occurrences,
        "pending_count": sum(1 for item in occurrences if item["pending"]),
        "totals": totals_through(horizon.strftime("%Y-%m-%d")),
        "windows": buckets,
    }


# ---------------------------------------------------------------------------
# Ocorrencias feitas por um lancamento aprovado (034)
# ---------------------------------------------------------------------------

# Ate quantos dias da ocorrencia a notificacao ainda e ela: o salario cai no
# quinto dia util, a cobranca da assinatura escorrega num fim de semana.
RECURRING_MATCH_DAYS = 7
# Com o nome (ou a categoria) batendo, o valor pode ter mudado ate isto: a
# assinatura reajustou, o salario variou. Sem nada batendo, so o valor exato
# numa despesa; numa receita, a mesma folga.
RECURRING_AMOUNT_TOLERANCE = Decimal("0.20")
# Palavras que toda notificacao tem e nao dizem de quem e o movimento.
MATCH_STOPWORDS = {
    "pix", "para", "dos", "das", "com", "por", "compra", "compras", "pagamento", "pagto", "pag",
    "recebido", "recebida", "enviado", "enviada", "transferencia", "ted", "doc", "cartao",
    "credito", "debito", "final", "ltda", "www", "net", "brasil", "online", "mensal",
    "mensalidade", "assinatura", "parcela",
}


def settled_dates(conn, current_user_id, recurring_id):
    rows = conn.execute(
        "SELECT occurrence_date FROM recurring_settlements WHERE user_id = ? AND recurring_id = ?",
        (current_user_id, recurring_id),
    ).fetchall()
    return {row["occurrence_date"] for row in rows}


def match_tokens(text):
    plain = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return {
        token for token in re.split(r"[^a-z0-9]+", plain)
        if len(token) >= 3 and token not in MATCH_STOPWORDS and not token.isdigit()
    }


def recurring_type_of_item(item):
    """Que tipo de recorrencia um item pode fazer: a saida (despesa ou
    cartao) faz uma despesa, a entrada uma receita; transferencia, nenhuma."""
    entry_type = item.get("entry_type")
    if entry_type == "TRANSFER":
        return None
    if entry_type in ("EXPENSE", "CARD"):
        return "EXPENSE"
    if entry_type == "INCOME":
        return "INCOME"
    return "INCOME" if item.get("direction") == "IN" else "EXPENSE"


def _same_category(item, row):
    """A categoria do item diz a recorrencia, menos a padrao do import
    ("Outros", "Receita"), que todo item sem regra recebe."""
    name = item.get("category")
    if not name or name in DEFAULT_IMPORT_CATEGORIES.values():
        return False
    if item.get("category_id") and row["category_id"]:
        return item["category_id"] == row["category_id"]
    return name == row["category"]


def recurring_match(item, row):
    """(relacionado, valor exato) se `item` pode ser uma ocorrencia de `row`
    pelo valor e pelo nome, sem olhar a data; None se nao pode."""
    if not row["active"] or row["type"] != recurring_type_of_item(item):
        return None
    item_cents = int((Decimal(str(item["amount"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    row_cents = int((Decimal(str(row["amount"])) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    exact = item_cents == row_cents
    related = bool(match_tokens(item.get("description")) & match_tokens(row["description"])) or _same_category(item, row)
    close = abs(item_cents - row_cents) <= row_cents * RECURRING_AMOUNT_TOLERANCE
    # Uma entrada perto do valor do salario e o salario, mesmo vindo no nome
    # do empregador ("Pix de EMPRESA X LTDA" x "Salario"); uma saida perto do
    # valor de uma assinatura nao e a assinatura sem o nome bater.
    if exact or (close and (related or row["type"] == "INCOME")):
        return related, exact
    return None


def open_occurrences(conn, current_user_id, row, start, end):
    """Datas de `row` entre `start` e `end` (inclusive) que ainda devem: nem
    gravadas pelo /run (ficam antes do cursor) nem feitas por um lancamento."""
    settled = settled_dates(conn, current_user_id, row["id"])
    return [
        occurrence for occurrence in recurring_occurrence_dates(row, end)
        if occurrence >= start and occurrence.strftime("%Y-%m-%d") not in settled
    ]


def suggest_for_item(conn, current_user_id, item, rows=None):
    """A ocorrencia de recorrencia que este item de Aprovar parece ser, ou None.

    O nome (ou a categoria) batendo vale mais que o valor exato, e entre
    iguais ganha a data mais perto. Nada e gravado: e o que a tela mostra e o
    que aprovar marca como feito.
    """
    if recurring_type_of_item(item) is None or not item.get("amount"):
        return None
    when = parse_iso_date(str(item.get("occurred_at") or "")[:10])
    if not when:
        return None
    start = when - timedelta(days=RECURRING_MATCH_DAYS)
    end = when + timedelta(days=RECURRING_MATCH_DAYS)
    if rows is None:
        rows = recurring_rows(conn, current_user_id, include_inactive=False)
    best = None
    for row in rows:
        matched = recurring_match(item, row)
        if not matched:
            continue
        related, exact = matched
        for occurrence in open_occurrences(conn, current_user_id, row, start, end):
            key = (0 if related else 1, 0 if exact else 1, abs((occurrence - when).days), occurrence)
            if best is None or key < best[0]:
                best = (key, row, occurrence)
    if not best:
        return None
    _key, row, occurrence = best
    return occurrence_dict(row, occurrence.strftime("%Y-%m-%d"), exact_amount=best[0][1] == 0)


def occurrence_dict(row, date_text, *, exact_amount=None, settled=False):
    return {
        "recurring_id": row["id"],
        "date": date_text,
        "description": row["description"],
        "category": row["category"],
        "category_id": row["category_id"],
        "amount": rounded_money(row["amount"]),
        "type": row["type"],
        "frequency": row["frequency"],
        "exact_amount": exact_amount,
        "settled": settled,
    }


def settlement_of_item(conn, current_user_id, item_id):
    """A ocorrencia que a aprovacao deste item deu como feita, para a tela."""
    found = conn.execute(
        """
        SELECT s.occurrence_date, r.* FROM recurring_settlements s
        JOIN recurring_transactions r ON r.id = s.recurring_id AND r.user_id = s.user_id
        WHERE s.user_id = ? AND s.inbox_item_id = ?
        LIMIT 1
        """,
        (current_user_id, item_id),
    ).fetchone()
    return occurrence_dict(found, found["occurrence_date"], settled=True) if found else None


def settle_occurrence(conn, current_user_id, recurring_id, date_text, *, item, target_table, target_id):
    """Da a ocorrencia como feita pelo lancamento `target_*` (aprovado de
    `item`). Recusa (ValueError) uma que ja nao deve ou nao e deste tipo."""
    row = fetch_recurring(conn, current_user_id, recurring_id)
    occurrence = parse_iso_date(date_text)
    if not row or not occurrence:
        raise ValueError("Recorrencia nao encontrada.")
    if not row["active"] or row["type"] != recurring_type_of_item(item):
        raise ValueError("Esta recorrencia nao combina com o lancamento.")
    if occurrence not in open_occurrences(conn, current_user_id, row, occurrence, occurrence):
        raise ValueError("Esta ocorrencia da recorrencia ja foi lancada.")
    conn.execute(
        """
        INSERT INTO recurring_settlements
        (id, user_id, recurring_id, occurrence_date, target_table, target_id, inbox_item_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id(), current_user_id, row["id"], date_text, target_table, target_id, item.get("id")),
    )
    advance_past_settled(conn, current_user_id, row)
    return occurrence_dict(row, date_text, settled=True)


def advance_past_settled(conn, current_user_id, row):
    """Anda o cursor sobre as ocorrencias feitas logo a frente dele, para a
    tela dizer a proxima de verdade. Uma feita depois de outra ainda devida
    fica onde esta: o /run passa por ela sem gravar."""
    settled = settled_dates(conn, current_user_id, row["id"])
    cursor_text = recurring_cursor_after_gaps(row)
    cursor_date = parse_iso_date(cursor_text) if cursor_text else None
    walked = None
    while cursor_date and cursor_date.strftime("%Y-%m-%d") in settled:
        walked = cursor_date
        cursor_date = recurring_date_after(row, cursor_date)
    if walked is None:
        return
    previous_last = parse_iso_date(row["last_occurrence_date"])
    last_occurrence = max(walked, previous_last) if previous_last else walked
    remaining_gaps = [gap for gap in recurring_pause_gaps(row) if gap[1] > last_occurrence]
    conn.execute(
        """
        UPDATE recurring_transactions
        SET next_run_date = ?, last_occurrence_date = ?, pause_gaps = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            cursor_date.strftime("%Y-%m-%d") if cursor_date else None,
            last_occurrence.strftime("%Y-%m-%d"),
            encode_pause_gaps(remaining_gaps),
            utc_timestamp(),
            row["id"],
            current_user_id,
        ),
    )
