"""A notificacao que a Pluggy nunca listou: o saldo do banco decide (Fase 5,
design §3.4, decisao 1).

A notificacao grava na hora; a Pluggy e o registro. Se a Pluggy nunca lista a
linha, isso nao prova que o dinheiro nao andou: ela ja deixou linhas de fora
(R$ 41,89 da fatura de agosto do BTG), e a compra internacional fica "em
processamento" no banco, ja fora do saldo, ate 30 dias sem linha na Pluggy (o
caso do Claude, 2026-11-04). Entao quem decide e o **saldo do banco**, pela
diferenca da propria Conferencia (`open_finance_check.balance_difference()`:
banco - app, em centavos):

- tirar uma despesa orfa de X sobe o saldo do app em X: conserta uma diferenca
  de **+X**; uma receita orfa de X conserta **-X**;
- sai a orfa mais antiga cujo conserto e exatamente a diferenca, ou todas
  juntas quando a soma e exatamente a diferenca. Nada mais: sem busca de
  subconjunto, sem tolerancia. Na duvida, fica;
- diferenca 0: o saldo do banco ja a conta (a Pluggy deixou a linha de fora, ou
  a compra internacional em processamento). Fica, e a Conferencia mostra
  "confirmado pelo saldo" (`balance_confirmed()`); nada vai para o Revisar;
- qualquer outra diferenca: fica, "so no app" como sempre.

So conta bancaria mapeada (BANK), em reais, nunca a Corretora. **O cartao e so
lista**: o saldo dele mistura limite usado, retencoes pendentes e o
arredondamento do BB, entao "o saldo prova" ainda nao e seguro ali.

Uma orfa: lancamento (EXPENSE ou INCOME, nunca TRANSFER) gravado por um item de
notificacao (deteccao SOURCE e `auto_recorded_at`), sem transacao viva da
Pluggy (`inbox.pluggy_claimed()`), com data ate hoje - OPEN_FINANCE_LATE_POST_DAYS
e o banco atualizado depois de data + 5 dias, com o app ja tendo lido
(`open_finance_auto.bank_refreshed_since()`; uma conexao quebrada nunca passa).

Nunca sai, revisada ou nao (a categoria de um dinheiro que nao andou nao
protege nada): o que tem comprovante, divisao (A receber), "Aconteceu" na
Conferencia, ou um valor que o dono digitou (o de agora nao e o do snapshot).

Sair e como `auto_record.undo_declined()`: o lancamento sai, o item fica
REMOVED com reason `orphan`, as deteccoes perdem o alvo. O pull conta em
`removed_orphans`.
"""

from datetime import timedelta

from dates import parse_iso_date
from db import utc_timestamp
from services import global_account, inbox, invoices, open_finance_auto, open_finance_check, open_finance_inbox
from services.accounts import account_balance_rows, account_balance_until
from services.recorded_snapshot import _snapshot_cents, snapshot_amount_cents

# O banco precisa ter atualizado depois de data + REFRESH_AFTER_DAYS.
REFRESH_AFTER_DAYS = 5


def _shift(date_text, days):
    day = parse_iso_date(str(date_text or "")[:10])
    return (day + timedelta(days=days)).strftime("%Y-%m-%d") if day else None


def _bank_accounts(conn, current_user_id, of_item_id):
    """As contas BANK mapeadas desta conexao, em reais, fora a Corretora."""
    found = []
    for account in conn.execute(
        """
        SELECT o.* FROM open_finance_accounts o
        JOIN accounts a ON a.id = o.account_id AND a.user_id = o.user_id
        WHERE o.user_id = ? AND o.of_item_id = ? AND o.type = 'BANK' AND o.ignored_at IS NULL
          AND o.account_id IS NOT NULL AND a.type <> 'BROKERAGE' AND COALESCE(a.currency, 'BRL') = 'BRL'
        """,
        (current_user_id, of_item_id),
    ).fetchall():
        if not global_account.is_foreign(conn, current_user_id, account["account_id"]):
            found.append(dict(account))
    return found


def notified_rows(conn, current_user_id, account_id):
    """Os lancamentos da conta que so uma notificacao sustenta: gravados por um
    item de notificacao, sem transacao viva da Pluggy. Do mais antigo para o mais
    novo, com o item."""
    rows = conn.execute(
        """
        SELECT t.id, t.type, t.amount, t.date, t.created_at, t.share_mode,
               i.id AS item_id, i.recorded_snapshot
        FROM transactions t
        JOIN inbox_items i ON i.target_id = t.id AND i.user_id = t.user_id AND i.target_table = 'transactions'
        WHERE t.user_id = ? AND t.account_id = ? AND t.type IN ('EXPENSE', 'INCOME')
          AND i.state = 'APPROVED' AND i.auto_recorded_at IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM notify_detections d
              WHERE d.user_id = i.user_id AND d.item_id = i.id AND d.role = 'SOURCE'
          )
        ORDER BY t.date, t.created_at, t.id
        """,
        (current_user_id, account_id),
    ).fetchall()
    return [dict(row) for row in rows if not inbox.pluggy_claimed(conn, current_user_id, "transactions", row["id"])]


def fix_cents(row):
    """O que tirar a orfa faz na diferenca banco - app: a despesa +X, a receita -X."""
    cents = _snapshot_cents(row["amount"])
    return cents if row["type"] == "EXPENSE" else -cents


def protected(conn, current_user_id, row):
    """O que o dono pos e nao recupera: comprovante, divisao, "Aconteceu", o valor
    digitado. Sem snapshot, na duvida, protegido."""
    if row.get("share_mode"):
        return True
    if conn.execute(
        "SELECT 1 FROM transaction_attachments WHERE user_id = ? AND transaction_id = ? LIMIT 1",
        (current_user_id, row["id"]),
    ).fetchone():
        return True
    if conn.execute(
        """
        SELECT 1 FROM open_finance_confirmed
        WHERE user_id = ? AND target_table = 'transactions' AND target_id = ?
        """,
        (current_user_id, row["id"]),
    ).fetchone():
        return True
    recorded = snapshot_amount_cents(row.get("recorded_snapshot"), "transactions")
    return recorded is None or int(recorded) != _snapshot_cents(row["amount"])


def ripe(conn, current_user_id, row, today_text):
    """Velha o bastante e o banco ja falou depois de data + 5 dias."""
    if str(row["date"]) > (_shift(today_text, -inbox.OPEN_FINANCE_LATE_POST_DAYS) or ""):
        return False
    after = _shift(row["date"], REFRESH_AFTER_DAYS)
    return bool(after) and open_finance_auto.bank_refreshed_since(conn, current_user_id, f"{after}T23:59:59Z")


def account_difference(conn, current_user_id, of_account, today_text=None):
    """A diferenca banco - app da Conferencia, em centavos (ou None): o app ate
    hoje, como na tela. Com o saldo inteiro, um lancamento futuro digitado (um
    boleto agendado de X) virava uma diferenca de +X, e a orfa de X, real, saia."""
    today_text = today_text or invoices.local_today().strftime("%Y-%m-%d")
    balance_row = next(
        (row for row in account_balance_rows(conn, current_user_id) if row["id"] == of_account["account_id"]), None,
    )
    settled = account_balance_until(conn, current_user_id, of_account["account_id"], today_text) if balance_row else None
    return open_finance_check.balance_difference(of_account, balance_row, settled)[1]


def choose(orphans, difference_cents):
    """Puro. Quais orfas saem: todas, se a soma do conserto e exatamente a
    diferenca; senao a mais antiga cujo conserto e exatamente ela; senao nenhuma.
    Diferenca 0 ou desconhecida: nenhuma."""
    if not orphans or not difference_cents:
        return []
    if sum(fix_cents(row) for row in orphans) == difference_cents:
        return list(orphans)
    for row in orphans:
        if fix_cents(row) == difference_cents:
            return [row]
    return []


def _remove(conn, current_user_id, row):
    item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
    if not item_row:
        return False
    item = inbox.item_dict(item_row)
    open_finance_inbox._drop_target(conn, current_user_id, item)
    inbox.save_item(
        conn, current_user_id, item,
        {"state": inbox.REMOVED, "reason": "orphan", "target_table": None, "target_id": None,
         "decided_at": utc_timestamp()},
    )
    return True


def sweep(conn, current_user_id, of_item_id, today):
    """Depois do pull (o que ele trouxe ja esta no lugar e o app ja leu): em cada
    conta BANK mapeada da conexao, tira as orfas que o saldo prova. Devolve
    quantas sairam."""
    today_text = today.strftime("%Y-%m-%d") if hasattr(today, "strftime") else str(today)[:10]
    removed = 0
    for of_account in _bank_accounts(conn, current_user_id, of_item_id):
        orphans = [
            row for row in notified_rows(conn, current_user_id, of_account["account_id"])
            if ripe(conn, current_user_id, row, today_text) and not protected(conn, current_user_id, row)
        ]
        if not orphans:
            continue
        for row in choose(orphans, account_difference(conn, current_user_id, of_account, today_text)):
            removed += 1 if _remove(conn, current_user_id, row) else 0
    return removed


def balance_confirmed(conn, current_user_id, of_account, difference_cents):
    """Os lancamentos ({id: data}) que a Conferencia mostra "confirmado pelo
    saldo": so a notificacao os sustenta, a Pluggy nao os lista e o saldo do
    banco ja os conta (diferenca 0). So conta bancaria em reais; o cartao e so
    lista."""
    if difference_cents != 0 or of_account["type"] != "BANK" or not of_account["account_id"]:
        return {}
    if global_account.is_foreign(conn, current_user_id, of_account["account_id"]):
        return {}
    return {row["id"]: row["date"] for row in notified_rows(conn, current_user_id, of_account["account_id"])}
