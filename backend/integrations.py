"""Ultimo resultado de cada provedor externo (yfinance, brapi, BCB).

Cada download real grava aqui se deu certo ou nao; o healthcheck
(services/health.py) junta isso com um teste ativo. Estado do processo, em
memoria: reiniciar o app zera, e tudo bem — o teste ativo refaz a foto.
"""

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_status = {}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_provider_result(provider, ok, detail=None):
    with _lock:
        entry = _status.setdefault(provider, {"consecutive_failures": 0})
        if ok:
            entry["last_success"] = _now()
            entry["consecutive_failures"] = 0
        else:
            entry["last_failure"] = _now()
            entry["last_error"] = str(detail or "falha sem detalhe")[:300]
            entry["consecutive_failures"] = entry.get("consecutive_failures", 0) + 1


def provider_snapshot(provider):
    with _lock:
        return dict(_status.get(provider, {}))


def reset_provider_status():
    """Para os testes."""
    with _lock:
        _status.clear()
