"""A tela do APK, para o celular se atualizar sem instalar um APK novo.

A imagem traz o build do frontend feito para o APK (`APP_BUNDLE_DIR`, com a API
do servidor compilada) e o `bundle.json` que `frontend/scripts/bundle-manifest.mjs`
grava nele: a versao (hash do conteudo), o nivel nativo e o endereco da API.

O app pergunta `GET /api/app-bundle`, compara com o que roda e, se mudou, baixa o
zip, confere o SHA-256 e troca na proxima abertura (android/.../bundle/). Quem
decide se serve e o app: so baixa uma tela do mesmo nivel nativo do APK.

O zip e montado aqui, uma vez por versao, com datas fixas: o mesmo conteudo da
sempre os mesmos bytes, e o SHA-256 do manifesto vale para qualquer pedido.
"""

import hashlib
import io
import json
import os
import re
import threading
import zipfile

from applog import get_logger
from config import APP_BUNDLE_DIR

logger = get_logger(__name__)

MANIFEST_NAME = "bundle.json"
VERSION_PATTERN = re.compile(r"^[0-9a-f]{16}$")
# Data fixa de cada entrada: o zip nao muda de bytes entre um boot e outro.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)

_lock = threading.Lock()
_cache = {"key": None, "bundle": None}


def _read_manifest(bundle_dir):
    path = os.path.join(bundle_dir, MANIFEST_NAME)
    if not os.path.isfile(path) or not os.path.isfile(os.path.join(bundle_dir, "index.html")):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning(f"bundle.json ilegivel em {bundle_dir}: {exc}")
        return None
    version = manifest.get("version")
    native_level = manifest.get("native_level")
    api_base = manifest.get("api_base")
    if (
        not isinstance(version, str)
        or not VERSION_PATTERN.match(version)
        or not isinstance(native_level, int)
        or isinstance(native_level, bool)
        or native_level < 1
        or not isinstance(api_base, str)
        or not api_base.startswith("https://")
    ):
        logger.warning(f"bundle.json invalido em {bundle_dir}: {manifest!r}")
        return None
    return {"version": version, "native_level": native_level, "api_base": api_base.rstrip("/")}


def _build_zip(bundle_dir):
    paths = []
    for root, _dirs, files in os.walk(bundle_dir):
        for name in files:
            full = os.path.join(root, name)
            paths.append((os.path.relpath(full, bundle_dir).replace(os.sep, "/"), full))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, full in sorted(paths):
            info = zipfile.ZipInfo(relative, date_time=ZIP_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(full, "rb") as handle:
                archive.writestr(info, handle.read())
    return buffer.getvalue()


def current_bundle():
    """A tela servida agora: {version, native_level, api_base, sha256, size, data}, ou None."""
    manifest = _read_manifest(APP_BUNDLE_DIR)
    if manifest is None:
        return None
    key = (APP_BUNDLE_DIR, manifest["version"])
    with _lock:
        if _cache["key"] != key:
            data = _build_zip(APP_BUNDLE_DIR)
            _cache["key"] = key
            _cache["bundle"] = {
                **manifest,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "data": data,
            }
        return _cache["bundle"]


def reset_cache():
    with _lock:
        _cache["key"] = None
        _cache["bundle"] = None
