"""Copia em disco dos caches de historico dos graficos.

Os fechamentos diarios do Yahoo (`services/prices.py`) e as series do BCB
(`services/fixed_income.py`) ficam num cache do processo. Cada deploy ou
reinicio o esvaziava, e o primeiro grafico de Investimentos esperava o
download de anos de historico. Aqui cada secao ("daily", "bcb") vai para um
JSON ao lado do banco (`HISTORY_CACHE_FILE`) e e lida uma vez por processo,
no primeiro uso: um historico lido do disco vale pela idade que tinha
(fresco, vencido ou expirado, como na memoria), entao a tela abre na hora e a
busca nova corre em segundo plano.

E cache, nao dado: um arquivo ilegivel ou de outra versao e ignorado, e
apagar o arquivo so faz a proxima abertura baixar de novo. A gravacao roda
fora do pedido, numa fila de uma tarefa. `HISTORY_CACHE_FILE` vazio desliga
(e o que os testes usam; os de persistencia trocam o nome aqui).
"""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading

from applog import get_logger
from config import HISTORY_CACHE_FILE

logger = get_logger(__name__)

STORE_VERSION = 1

_lock = threading.Lock()
# {"secao": payload} depois da primeira leitura; None antes.
_sections = None
# Secoes a gravar: {"secao": funcao que devolve o payload (JSON)}.
_pending = {}
_queued = False
_save_executor = ThreadPoolExecutor(max_workers=1)
_last_save = None


def reset():
    """Esquece o que foi lido e o que estava na fila (para os testes)."""
    global _sections, _queued
    with _lock:
        _sections = None
        _pending.clear()
        _queued = False


def _read_file():
    if not HISTORY_CACHE_FILE:
        return {}
    try:
        with open(HISTORY_CACHE_FILE, encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning(f"Cache de historico em disco ilegivel, ignorado: {exc}")
        return {}
    if not isinstance(document, dict) or document.get("version") != STORE_VERSION:
        return {}
    sections = document.get("sections")
    return sections if isinstance(sections, dict) else {}


def read_section(name):
    """A secao `name` do arquivo ({} sem arquivo). O arquivo e lido uma vez."""
    global _sections
    with _lock:
        if _sections is None:
            _sections = _read_file()
        section = _sections.get(name)
    return section if isinstance(section, dict) else {}


def save_section(name, build):
    """Agenda a gravacao da secao `name`; `build()` monta o payload na hora de gravar.

    Devolve o Future da gravacao (ou None, desligado). Varias chamadas seguidas
    viram uma gravacao so."""
    global _queued, _last_save
    if not HISTORY_CACHE_FILE:
        return None
    with _lock:
        _pending[name] = build
        if not _queued:
            _queued = True
            _last_save = _save_executor.submit(_flush)
        return _last_save


def wait_saves(timeout=None):
    """Espera a gravacao agendada (para os testes)."""
    with _lock:
        future = _last_save
    if future is not None:
        future.result(timeout=timeout)


def _flush():
    global _sections, _queued
    with _lock:
        _queued = False
        builds = dict(_pending)
        _pending.clear()
        if _sections is None:
            _sections = _read_file()
    # Montar le os caches (com as travas deles), fora desta.
    built = {}
    for name, build in builds.items():
        try:
            built[name] = build()
        except Exception as exc:
            logger.warning(f"Cache de historico '{name}' nao montado para o disco: {exc}")
    with _lock:
        _sections.update(built)
        document = {"version": STORE_VERSION, "sections": dict(_sections)}
    path = HISTORY_CACHE_FILE
    if not path:
        return
    temporary = f"{path}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(document, handle, separators=(",", ":"))
        os.replace(temporary, path)
    except Exception as exc:
        logger.warning(f"Cache de historico nao gravado em disco: {exc}")
