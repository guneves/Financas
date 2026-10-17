"""A tela do APK para o celular baixar (services/app_bundle.py).

Sem token, como `/`: e o mesmo frontend que o Flask ja serve a qualquer um que
chegue pelo Tailscale, so que compilado para o APK. Um app deslogado tambem se
atualiza — inclusive com o conserto de um problema no login.
"""

from flask import Blueprint, Response, jsonify

from services.app_bundle import current_bundle

bp = Blueprint("app_bundle", __name__)

NO_BUNDLE_MESSAGE = "Este servidor nao tem a tela do app."


@bp.route("/api/app-bundle", methods=["GET"])
def get_app_bundle():
    bundle = current_bundle()
    if bundle is None:
        return jsonify({"error": NO_BUNDLE_MESSAGE}), 404
    response = jsonify({
        "version": bundle["version"],
        "native_level": bundle["native_level"],
        "api_base": bundle["api_base"],
        "sha256": bundle["sha256"],
        "size": bundle["size"],
        "url": f"/api/app-bundle/{bundle['version']}.zip",
    })
    response.headers["Cache-Control"] = "no-cache"
    return response, 200


@bp.route("/api/app-bundle/<version>.zip", methods=["GET"])
def download_app_bundle(version):
    bundle = current_bundle()
    # So a versao atual: um pedido por uma antiga (o servidor mudou no meio) e 404,
    # e o app pergunta de novo na proxima vez.
    if bundle is None or bundle["version"] != version:
        return jsonify({"error": "Versao da tela nao encontrada."}), 404
    response = Response(bundle["data"], mimetype="application/zip")
    response.headers["Content-Length"] = str(bundle["size"])
    # O nome e o hash do conteudo: os bytes de uma versao nunca mudam.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response
