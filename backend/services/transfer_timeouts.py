"""Nada espera para sempre (automation-prompt 1.3, dono 2026-11-18).

A transferencia entre contas do dono com uma ponta so ja vira despesa/receita
na hora (one_side_now()); duas ainda esperavam o dono, e agora, passado
TRANSFER_MATCH_DAYS sem a outra ponta, grava sozinha por uma regra escrita:

- **a que toca a Corretora** (`awaiting_transfer`): vira o aporte/resgate que o
  lado implica, banco <-> Corretora, com o lado do banco adivinhado (`guessed`):
  a conta da mesma instituicao da Corretora, senao a padrao. A ponta real que
  chegar depois, noutra conta, move o palpite (inbox.move_guessed_side), e a da
  mesma conta junta (uma linha so);
O Pix para/da conta global ja nao espera: a Pluggy (one_side_now()) e o aviso
gravam o lado em reais na hora, e o credito em dolar faz a transferencia.

Fica no registro (auto_decisions `transfer_guess`),
com "Desfazer" (devolve a linha ao Revisar, onde o dono corrige o lado).
"""

from dates import local_today, parse_iso_date
from services import inbox
from services.accounts import ensure_default_account
from services.inbox_transfers import TRANSFER_MATCH_DAYS


def _elapsed_days(item, today):
    day = parse_iso_date(str(item.get("occurred_at") or "")[:10])
    return (today - day.date()).days if day else 0


def held_long_enough(item, today=None):
    """Passou TRANSFER_MATCH_DAYS (a janela em que a outra ponta ainda casa)."""
    return _elapsed_days(item, today or local_today()) > TRANSFER_MATCH_DAYS


def _account(conn, current_user_id, account_id):
    if not account_id:
        return None
    return conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ? AND archived_at IS NULL", (account_id, current_user_id),
    ).fetchone()


def is_brokerage(conn, current_user_id, account_id):
    account = _account(conn, current_user_id, account_id)
    return bool(account) and account["type"] == "BROKERAGE"


def bank_beside(conn, current_user_id, brokerage):
    """A conta em reais ao lado da Corretora: a da mesma instituicao (a BTG
    conta corrente da BTG Corretora), senao a conta padrao (nunca a Corretora)."""
    words = {
        word for word in inbox.normalized(f"{brokerage['institution'] or ''} {brokerage['name'] or ''}").split()
        if len(word) >= 3 and word not in {"corretora", "investimentos", "invest", "conta"}
    }
    if words:
        for row in conn.execute(
            """
            SELECT * FROM accounts
            WHERE user_id = ? AND archived_at IS NULL AND type <> 'BROKERAGE' AND COALESCE(currency, 'BRL') = 'BRL'
            ORDER BY created_at, id
            """,
            (current_user_id,),
        ).fetchall():
            names = set(inbox.normalized(f"{row['institution'] or ''} {row['name'] or ''}").split())
            if words & names:
                return row["id"]
    return ensure_default_account(conn, current_user_id)


def brokerage_side_now(conn, current_user_id, item, today=None):
    """A ponta so da Corretora, passada a janela: o aporte/resgate com o lado do
    banco adivinhado. Devolve o item mudado, ou None."""
    if item.get("entry_type") != "TRANSFER" or not held_long_enough(item, today):
        return None
    origin, destination = item.get("account_id"), item.get("transfer_account_id")
    if bool(origin) == bool(destination):
        return None
    seen = _account(conn, current_user_id, origin or destination)
    if not seen or seen["type"] != "BROKERAGE":
        return None
    bank = bank_beside(conn, current_user_id, seen)
    if not bank or bank == seen["id"]:
        return None
    # A Corretora recebeu (destino): o dinheiro saiu do banco (origem), e vice-versa.
    field, need = ("account_id", "account") if not origin else ("transfer_account_id", "transfer_account")
    changes = {
        field: bank,
        "guessed": list(dict.fromkeys([*(item.get("guessed") or []), need])),
        "reason": "own_transfer",
    }
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)
    return inbox.item_dict(inbox.fetch_item(conn, current_user_id, item["id"]))
