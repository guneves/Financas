"""Cotacoes da renda variavel atualizadas sozinhas, de hora em hora (dono, 2026-10-22).

Antes a cotacao so mudava quando alguem abria a carteira (GET
/api/investments/portfolio) ou tocava "Atualizar cotacoes"; a Posicao, o
patrimonio e os graficos mostravam a ultima que alguem tinha pedido. Agora uma
thread do servidor chama `refresh_market_prices(force=True)` para cada usuario
a cada QUOTE_AUTO_REFRESH_SECONDS (3600 por padrao): o mesmo caminho do botao,
entao vale o mesmo provedor (brapi com token, senao yfinance), o mesmo registro
em `integrations` e so os ativos cotados com posicao aberta (acoes, FIIs, ETFs,
BDRs e cripto; `is_quoted_asset()`). O Tesouro tem a sua propria thread
(`tesouro_client.start_auto_refresh()`).

0 desliga (os testes, em conftest.py). A primeira rodada espera
QUOTE_AUTO_REFRESH_FIRST_DELAY_SECONDS depois do boot, para nao disputar o
inicio com o backup e as migracoes.
"""

import threading
import time

from applog import get_logger
from config import PRICE_REFRESH_TIMEOUT_SECONDS, QUOTE_AUTO_REFRESH_SECONDS
from db import get_db
from services.portfolio import refresh_market_prices

logger = get_logger(__name__)

QUOTE_AUTO_REFRESH_FIRST_DELAY_SECONDS = 60

_lock = threading.Lock()
_auto_refresh_started = False


def user_ids():
    with get_db() as conn:
        return [row["id"] for row in conn.execute("SELECT id FROM users ORDER BY created_at, id").fetchall()]


def refresh_all_users():
    """Uma rodada: as cotacoes de cada usuario, um de cada vez. Devolve
    {user_id: atualizadas}; um usuario que falha nao impede os outros."""
    results = {}
    for current_user_id in user_ids():
        try:
            outcome = refresh_market_prices(current_user_id, force=True, timeout=PRICE_REFRESH_TIMEOUT_SECONDS)
        except Exception as exc:  # um provedor fora do ar nao derruba a rodada
            logger.warning(f"Atualizacao automatica de cotacoes falhou para {current_user_id}: {exc}")
            continue
        results[current_user_id] = outcome["updated_count"]
        if outcome["requested_tickers"]:
            logger.info(
                "Cotacoes atualizadas automaticamente",
                extra={
                    "user_id": current_user_id,
                    "updated": outcome["updated_count"],
                    "requested": outcome["requested_tickers"],
                    "failed": outcome["failed_tickers"],
                },
            )
    return results


def start_auto_refresh(interval_seconds=None, first_delay_seconds=QUOTE_AUTO_REFRESH_FIRST_DELAY_SECONDS):
    """Liga a thread (uma por processo). Chamado no boot (app.py); com
    intervalo 0 nao faz nada e devolve False."""
    global _auto_refresh_started
    interval = QUOTE_AUTO_REFRESH_SECONDS if interval_seconds is None else int(interval_seconds)
    with _lock:
        if _auto_refresh_started or interval <= 0:
            return False
        _auto_refresh_started = True

    def loop():
        time.sleep(max(0, first_delay_seconds))
        while True:
            try:
                refresh_all_users()
            except Exception as exc:  # a thread nao pode morrer
                logger.warning(f"Atualizacao automatica de cotacoes falhou: {exc}")
            time.sleep(interval)

    threading.Thread(target=loop, name="quote-auto-refresh", daemon=True).start()
    return True
