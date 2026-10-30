"""O Open Finance puxado sozinho (043), como as cotacoes em quote_refresh.py.

O servidor so e alcancavel dentro da tailnet: a Pluggy nao chega nele por
webhook. Uma thread acorda a cada TICK_SECONDS e chama `open_finance.sync_user()`
para cada usuario cuja "Busca automatica" (Ajustes, `sync_hours`; quem nunca
escolheu fica com OPEN_FINANCE_SYNC_SECONDS, 6 h: toda conta mapeada atualiza
sem o dono) venceu desde o ultimo pull
ou a ultima tentativa. O pull e passivo (dono, 2026-10-27): so GET do que a
Pluggy ja trouxe do banco — ela atualiza o banco sozinha, de 6 a 24 h. O app
nunca pede dados novos (`PATCH /items`): no plano gratis do MeuPluggy isso
gasta o limite mensal do CPF e, esgotado, bloqueia ate o mes seguinte. Por
isso o intervalo nao desce de 6 h. So "Desligada", escolhida em Ajustes
(`sync_hours = 0` na API), deixa so o botao "Atualizar". Uma recusa da Pluggy fica em `last_sync_error` (Ajustes) e no
log do container.

OPEN_FINANCE_SYNC_SECONDS = 0 desliga a thread para todos (os testes, em
conftest.py). Sem as credenciais da Pluggy, a thread
nem comeca. A primeira rodada vem FIRST_DELAY_SECONDS depois do boot: um pull
vencido (o servidor ficou fora, um deploy) e recuperado logo, porque o que
decide e `last_sync_at`, que esta no banco; `_attempts` comeca vazio.
"""

import threading
import time

from applog import get_logger
from config import OPEN_FINANCE_SYNC_SECONDS
from db import get_db
from services import open_finance

logger = get_logger(__name__)

FIRST_DELAY_SECONDS = 60
TICK_SECONDS = 15 * 60

_lock = threading.Lock()
_started = False
# Ultima tentativa por usuario: um pull que falha nao grava last_sync_at, e
# sem isto seria tentado de novo a cada TICK_SECONDS.
_attempts = {}


def user_ids_with_items():
    with get_db() as conn:
        return [
            row["user_id"] for row in conn.execute(
                "SELECT DISTINCT user_id FROM open_finance_items WHERE archived_at IS NULL ORDER BY user_id",
            ).fetchall()
        ]


def due_user_ids(now_seconds=None):
    """Os usuarios cuja busca automatica venceu: a conexao puxada ha mais
    tempo (ou nunca) passou do intervalo escolhido, e a ultima tentativa
    tambem."""
    now_seconds = time.time() if now_seconds is None else now_seconds
    due = []
    with get_db() as conn:
        for current_user_id in [
            row["user_id"] for row in conn.execute(
                "SELECT DISTINCT user_id FROM open_finance_items WHERE archived_at IS NULL ORDER BY user_id",
            ).fetchall()
        ]:
            hours = open_finance.sync_hours(conn, current_user_id)
            if hours <= 0:
                continue
            oldest = min(
                (open_finance._seconds(row["last_sync_at"]) if row["last_sync_at"] else 0)
                for row in open_finance.active_items(conn, current_user_id)
            )
            last = max(oldest, _attempts.get(current_user_id, 0))
            if now_seconds - last >= hours * 3600:
                due.append(current_user_id)
    return due


def refresh_all_users(now_seconds=None):
    """Uma rodada; um usuario (ou item) que falha nao impede os outros."""
    now_seconds = time.time() if now_seconds is None else now_seconds
    results = {}
    for current_user_id in due_user_ids(now_seconds):
        _attempts[current_user_id] = now_seconds
        try:
            results[current_user_id] = open_finance.sync_user(current_user_id)
        except Exception as exc:  # a rodada nao para por um usuario
            logger.warning(f"Open Finance automatico falhou para {current_user_id}: {exc}")
    return results


def reset_attempts():
    _attempts.clear()


def start_auto_refresh(interval_seconds=None, first_delay_seconds=FIRST_DELAY_SECONDS):
    """Liga a thread (uma por processo). Chamado no boot (app.py); com
    OPEN_FINANCE_SYNC_SECONDS = 0 ou sem credenciais nao faz nada e devolve
    False. `interval_seconds` e so o passo de acordar (TICK_SECONDS); quem
    decide se um usuario puxa e o intervalo dele (due_user_ids)."""
    global _started
    if OPEN_FINANCE_SYNC_SECONDS <= 0 or not open_finance.is_configured():
        return False
    interval = TICK_SECONDS if interval_seconds is None else max(60, int(interval_seconds))
    with _lock:
        if _started:
            return False
        _started = True

    def loop():
        time.sleep(max(0, first_delay_seconds))
        while True:
            try:
                refresh_all_users()
            except Exception as exc:  # a thread nao pode morrer
                logger.warning(f"Open Finance automatico falhou: {exc}")
            time.sleep(interval)

    threading.Thread(target=loop, name="open-finance-refresh", daemon=True).start()
    return True
