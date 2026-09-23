"""Log estruturado: uma linha JSON por evento.

Antes cada modulo fazia `print()`; um erro de cotacao as 3 da manha sumia no
terminal. Agora todo modulo pega um logger (`logger = get_logger(__name__)`) e
`configure_logging()` (chamado no boot, em app.py) manda tudo para o stderr e,
com LOG_TO_FILE, para LOG_DIR/app.log com rotacao.

Campos de cada linha: ts (UTC, ISO), level, logger, msg, e os `extra=` que o
chamador passar (ex.: `logger.warning("...", extra={"provider": "yfinance"})`).
Com excecao, `exc` traz o traceback.
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone

from config import LOG_DIR, LOG_LEVEL, LOG_TO_FILE

# Atributos que todo LogRecord tem; o resto veio de `extra=` e vai para o JSON.
_STANDARD_ATTRS = set(vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))) | {"message", "asctime", "taskName"}
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging():
    """Idempotente: o app e os testes podem chamar mais de uma vez."""
    global _configured
    if _configured:
        return
    formatter = JsonFormatter()
    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if LOG_TO_FILE:
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                os.path.join(LOG_DIR, "app.log"), maxBytes=1_000_000, backupCount=5, encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:
            root.warning("Nao foi possivel abrir o arquivo de log: %s", exc)

    # O yfinance loga cada ticker que falha em ERROR; o app ja resume isso.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    _configured = True


def get_logger(name):
    return logging.getLogger(name)
