"""O Open Finance puxado sozinho (043), como as cotacoes em quote_refresh.py.

O servidor so e alcancavel dentro da tailnet: a Pluggy nao chega nele por
webhook. Uma thread chama `open_finance.sync_user()` para cada usuario a cada
OPEN_FINANCE_SYNC_SECONDS (6 h por padrao): pede dados novos ao banco e puxa
o que chegou para o Aprovar. Pedir dados novos gasta o limite mensal de
requisicoes da instituicao (compartilhado por todos os itens do CPF; esgotado,
so volta no mes seguinte), entao o intervalo nao desce de 1 h, e um item que
espera o dono (senha, codigo, termos) nunca e pedido — sync_item() pula o
pedido e so le.

0 desliga (os testes, em conftest.py). Sem as credenciais da Pluggy, a thread
nem comeca. A primeira rodada espera FIRST_DELAY_SECONDS depois do boot.
"""

import threading
import time

from applog import get_logger
from config import OPEN_FINANCE_SYNC_SECONDS
from db import get_db
from services import open_finance

logger = get_logger(__name__)

FIRST_DELAY_SECONDS = 5 * 60
MIN_INTERVAL_SECONDS = 3600

_lock = threading.Lock()
_started = False


def user_ids_with_items():
    with get_db() as conn:
        return [
            row["user_id"] for row in conn.execute(
                "SELECT DISTINCT user_id FROM open_finance_items WHERE archived_at IS NULL ORDER BY user_id",
            ).fetchall()
        ]


def refresh_all_users():
    """Uma rodada; um usuario (ou item) que falha nao impede os outros."""
    results = {}
    for current_user_id in user_ids_with_items():
        try:
            results[current_user_id] = open_finance.sync_user(current_user_id, request_update=True)
        except Exception as exc:  # a rodada nao para por um usuario
            logger.warning(f"Open Finance automatico falhou para {current_user_id}: {exc}")
    return results


def start_auto_refresh(interval_seconds=None, first_delay_seconds=FIRST_DELAY_SECONDS):
    """Liga a thread (uma por processo). Chamado no boot (app.py); com
    intervalo 0 ou sem credenciais nao faz nada e devolve False."""
    global _started
    interval = OPEN_FINANCE_SYNC_SECONDS if interval_seconds is None else int(interval_seconds)
    if interval <= 0 or not open_finance.is_configured():
        return False
    interval = max(interval, MIN_INTERVAL_SECONDS)
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
