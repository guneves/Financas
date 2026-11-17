"""Quanto ainda cai em Revisar, por que, e quanto o dono corrigiu: so lendo.

A pergunta do dono (2026-11-17): da para tirar a revisao, com tudo 100%
automatico? Este script mede nos dados reais:

1. a fila de hoje (`needs_review = 1`), por tipo, por quem confirmou (so o
   aviso, ou a Pluggy tambem) e pelo motivo que nenhuma regra resolve (Pix para
   uma pessoa, Flash, Conta global, estorno), e ha quanto tempo espera;
2. os lancamentos gravados sozinhos nos ultimos N dias: quantos o dono deixou
   como nasceram e quantos ele corrigiu, e o que (categoria, conta/cartao,
   valor, data, tipo, divisao, comprovante) ou apagou. O snapshot do item (ou da
   linha da Pluggy que gravou) e o que o app gravou; o app renova o snapshot
   quando ele mesmo muda a linha, e a categoria escolhida em Revisar nao o
   renova: snapshot diferente = o dono mexeu.

No servidor (padrao do DEPLOY.md):

    sudo docker compose exec -T -w /app/backend app python scripts/review_breakdown.py --email X [--days 30]

Abre o SQLite somente leitura (`mode=ro`) e nunca importa `app`, `db` nem
`services` (o import do app migra o banco). Imprime contagens, nunca valores
nem descricoes. Saida 2: usuario nao encontrado.
"""

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH  # noqa: E402
from dates import local_today  # noqa: E402

TRANSACTION_FIELDS = {
    "category_id": "categoria", "account_id": "conta", "transfer_account_id": "conta",
    "amount": "valor", "date": "data", "type": "tipo", "description": "descricao",
    "share_mode": "divisao", "share_others_amount": "divisao", "share_person": "divisao",
    "attachments": "comprovante", "settled": "recorrencia", "transfer_amount": "valor",
}
CARD_COLUMNS = ("card_id", "amount", "purchase_date", "category_id", "description", "kind",
                "share_mode", "share_others_amount", "share_person")
CARD_FIELDS = {
    "card_id": "cartao", "amount": "valor", "purchase_date": "data", "category_id": "categoria",
    "description": "descricao", "kind": "tipo", "share_mode": "divisao", "share_others_amount": "divisao",
    "share_person": "divisao",
}


def cents(value):
    return None if value is None else int(round(float(value) * 100))


def current_snapshot(conn, user_id, table, target_id):
    """A mesma forma de services/recorded_snapshot.target_snapshot (sem importar
    services): so os campos que o dono pode mudar."""
    if table == "transactions":
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (target_id, user_id),
        ).fetchone()
        if not row:
            return None
        snapshot = {key: row[key] for key in TRANSACTION_FIELDS if key in row.keys()}
        snapshot["amount"] = cents(snapshot["amount"])
        if row["transfer_amount"] is not None:
            snapshot["transfer_amount"] = cents(row["transfer_amount"])
        else:
            snapshot.pop("transfer_amount", None)
        snapshot["attachments"] = conn.execute(
            "SELECT COUNT(*) FROM transaction_attachments WHERE user_id = ? AND transaction_id = ?",
            (user_id, target_id),
        ).fetchone()[0]
    elif table == "cc_expenses":
        first = conn.execute(
            "SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (target_id, user_id),
        ).fetchone()
        if not first:
            return None
        rows = conn.execute(
            f"SELECT id, {', '.join(CARD_COLUMNS)} FROM cc_expenses WHERE user_id = ? AND client_id = ? "
            "ORDER BY invoice_year, invoice_month, id",
            (user_id, first["client_id"]),
        ).fetchall()
        snapshot = {"rows": [[cents(row[c]) if c == "amount" else row[c] for c in CARD_COLUMNS] for row in rows]}
        ids = [row["id"] for row in rows]
        snapshot["attachments"] = conn.execute(
            f"SELECT COUNT(*) FROM cc_expense_attachments WHERE user_id = ? AND cc_expense_id IN "
            f"({', '.join('?' for _ in ids)})",
            (user_id, *ids),
        ).fetchone()[0]
    else:
        return None
    snapshot["settled"] = conn.execute(
        "SELECT COUNT(*) FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (user_id, table, target_id),
    ).fetchone()[0]
    return snapshot


def changed_fields(table, recorded, current):
    if table == "transactions":
        return sorted({TRANSACTION_FIELDS.get(key, key) for key in set(recorded) | set(current)
                       if recorded.get(key) != current.get(key)})
    fields = set()
    if recorded.get("attachments") != current.get("attachments"):
        fields.add("comprovante")
    if recorded.get("settled") != current.get("settled"):
        fields.add("recorrencia")
    old_rows, new_rows = recorded.get("rows") or [], current.get("rows") or []
    if len(old_rows) != len(new_rows):
        fields.add("parcelas")
    for old, new in zip(old_rows, new_rows):
        for column, a, b in zip(CARD_COLUMNS, old, new):
            if a != b:
                fields.add(CARD_FIELDS[column])
    return sorted(fields)


def load(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def special_accounts(conn, user_id):
    flash, foreign, broker = set(), set(), set()
    for row in conn.execute("SELECT id, name, institution, type, currency FROM accounts WHERE user_id = ?", (user_id,)):
        text = f"{row['name'] or ''} {row['institution'] or ''}".lower()
        if "flash" in text:
            flash.add(row["id"])
        if (row["currency"] or "BRL") != "BRL":
            foreign.add(row["id"])
        if row["type"] == "BROKERAGE":
            broker.add(row["id"])
    for row in conn.execute("SELECT id, name FROM credit_cards WHERE user_id = ?", (user_id,)):
        if "flash" in (row["name"] or "").lower():
            flash.add(row["id"])
    return flash, foreign, broker


def item_of(conn, user_id, table, target_id):
    return conn.execute(
        "SELECT * FROM inbox_items WHERE user_id = ? AND target_table = ? AND target_id = ? "
        "AND state IN ('APPROVED', 'MATCHED') ORDER BY created_at LIMIT 1",
        (user_id, table, target_id),
    ).fetchone()


def channels(conn, user_id, item_id):
    if not item_id:
        return set(), None
    found = set()
    person = None
    for row in conn.execute(
        "SELECT kind, counterparty, counterparty_doc FROM notify_detections WHERE user_id = ? AND item_id = ? "
        "AND role = 'SOURCE'", (user_id, item_id),
    ):
        found.add("aviso")
        person = person or (row["kind"] in ("PIX_OUT", "PIX_IN", "TRANSFER_OUT", "TRANSFER_IN")
                            and bool(row["counterparty"] or row["counterparty_doc"]))
    for row in conn.execute(
        "SELECT movement, counterparty, counterparty_doc FROM open_finance_transactions WHERE user_id = ? "
        "AND item_id = ? AND role IN ('SOURCE', 'MATCHED') AND COALESCE(conflict, '') <> 'vanished'",
        (user_id, item_id),
    ):
        found.add("pluggy")
        person = person or (row["movement"] in ("TRANSFER", "SELF_TRANSFER", "PIX")
                            and bool(row["counterparty"] or row["counterparty_doc"]))
    return found, person


def queue(conn, user_id, today):
    flash, foreign, broker = special_accounts(conn, user_id)
    rows = []
    for row in conn.execute(
        "SELECT 'transactions' AS tbl, id, type AS kind, account_id AS place, transfer_account_id AS other, "
        "date AS day FROM transactions WHERE user_id = ? AND needs_review = 1", (user_id,),
    ):
        rows.append(dict(row))
    seen = set()
    for row in conn.execute(
        "SELECT 'cc_expenses' AS tbl, id, client_id, CASE WHEN kind = 'REFUND' THEN 'ESTORNO' ELSE 'CARTAO' END "
        "AS kind, card_id AS place, NULL AS other, purchase_date AS day FROM cc_expenses "
        "WHERE user_id = ? AND needs_review = 1 ORDER BY invoice_year, invoice_month", (user_id,),
    ):
        if row["client_id"] in seen:
            continue
        seen.add(row["client_id"])
        rows.append(dict(row))
    reasons, kinds, ages, by_channel = Counter(), Counter(), Counter(), Counter()
    for row in rows:
        item = item_of(conn, user_id, row["tbl"], row["id"])
        found, person = channels(conn, user_id, item["id"] if item else None)
        channel = "+".join(sorted(found)) or "sem item"
        kinds[row["kind"]] += 1
        by_channel[channel] += 1
        age = (today - date.fromisoformat(row["day"][:10])).days if row["day"] else None
        ages["ate 7 dias" if age is not None and age <= 7 else "mais de 7 dias"] += 1
        if row["place"] in foreign or row["other"] in foreign:
            reason = "Conta global (revisa na tela dela)"
        elif row["place"] in flash or row["other"] in flash:
            reason = "Flash (a Pluggy nao cobre)"
        elif row["kind"] == "ESTORNO":
            reason = "estorno no cartao"
        elif row["kind"] == "TRANSFER":
            reason = ("transferencia com a Corretora" if row["place"] in broker or row["other"] in broker
                      else "transferencia entre contas") + (" (so uma ponta vista)" if len(found) < 2 else "")
        elif "pluggy" not in found:
            reason = "so o aviso (a Pluggy ainda nao confirmou)"
        elif person:
            reason = "Pix/TED para uma pessoa (categoria sem fonte segura)"
        else:
            reason = "compra/movimento confirmado, categoria da arvore da Pluggy ou padrao"
        reasons[reason] += 1
    return len(rows), kinds, by_channel, ages, reasons


def corrections(conn, user_id, since):
    totals, fields, by_kind = Counter(), Counter(), Counter()
    items = conn.execute(
        "SELECT * FROM inbox_items WHERE user_id = ? AND state IN ('APPROVED', 'MATCHED') "
        "AND target_table IS NOT NULL AND auto_recorded_at IS NOT NULL AND substr(auto_recorded_at, 1, 10) >= ?",
        (user_id, since),
    ).fetchall()
    pluggy_born = conn.execute(
        "SELECT o.item_id, o.target_table, o.target_id, o.recorded_snapshot, i.entry_type FROM "
        "open_finance_transactions o LEFT JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id "
        "WHERE o.user_id = ? AND o.auto_recorded_at IS NOT NULL AND o.recorded_snapshot IS NOT NULL "
        "AND o.role <> 'REMOVED' AND substr(o.auto_recorded_at, 1, 10) >= ?",
        (user_id, since),
    ).fetchall()
    observed = {}
    for item in items:
        if item["recorded_snapshot"]:
            observed[(item["target_table"], item["target_id"])] = (item["recorded_snapshot"], item["entry_type"])
    for row in pluggy_born:
        observed.setdefault((row["target_table"], row["target_id"]), (row["recorded_snapshot"], row["entry_type"]))
    for (table, target_id), (text, entry_type) in observed.items():
        recorded = load(text)
        if recorded is None:
            continue
        kind = entry_type or ("CARD" if table == "cc_expenses" else "?")
        current = current_snapshot(conn, user_id, table, target_id)
        if current is None:
            totals["apagado"] += 1
            by_kind[(kind, "apagado")] += 1
            continue
        changed = changed_fields(table, recorded, current)
        if changed:
            totals["corrigido"] += 1
            by_kind[(kind, "corrigido")] += 1
            fields.update(changed)
        else:
            totals["como nasceu"] += 1
            by_kind[(kind, "como nasceu")] += 1
    return totals, fields, by_kind


def show(title, counter):
    print(title)
    for key, value in counter.most_common():
        print(f"  {value:5d}  {key}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mede a fila de Revisar e as correcoes do dono, so lendo.")
    parser.add_argument("--email", required=True, help="O e-mail exato do usuario.")
    parser.add_argument("--days", type=int, default=30, help="Janela das correcoes (dias).")
    parser.add_argument("--today", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--database", default=DATABASE_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = os.path.abspath(args.database).replace("\\", "/")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (args.email,)).fetchone()
        if not user:
            print(f"Usuario nao encontrado: {args.email}", file=sys.stderr)
            return 2
        today = date.fromisoformat(args.today) if args.today else local_today()
        total, kinds, by_channel, ages, reasons = queue(conn, user["id"], today)
        print(f"Fila de Revisar hoje: {total}")
        show("por tipo:", kinds)
        show("por quem viu:", by_channel)
        show("idade:", ages)
        show("por que ficou:", reasons)
        since = (today - timedelta(days=args.days)).isoformat()
        totals, fields, by_kind = corrections(conn, user["id"], since)
        print(f"\nGravados sozinhos desde {since}: {sum(totals.values())}")
        show("destino:", totals)
        show("o que o dono mudou:", fields)
        show("por tipo:", Counter({f"{kind} / {state}": n for (kind, state), n in by_kind.items()}))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
