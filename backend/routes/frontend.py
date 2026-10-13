"""O frontend construido (`frontend/dist`), servido pelo proprio Flask.

Uma origem so para a tela e para a API: e o que o celular abre pelo endereco
do Tailscale, sem CORS e sem um segundo servidor. Em desenvolvimento nada muda
— o Vite continua na 5173 e este blueprint so responde se alguem abrir a 5000.

Tudo que nao e arquivo do build cai no `index.html`, porque as rotas de tela
(/lancamentos, /investimentos...) sao do React Router. `/api/*` nunca cai:
uma rota de API que nao existe continua sendo um 404 em JSON.
"""

import os

from flask import Blueprint, jsonify, send_from_directory

from config import FRONTEND_DIST_DIR

bp = Blueprint("frontend", __name__)


@bp.route("/", defaults={"path": ""}, methods=["GET"])
@bp.route("/<path:path>", methods=["GET"])
def frontend(path):
    if path == "api" or path.startswith("api/"):
        return jsonify({"error": "Rota nao encontrada."}), 404

    if not os.path.isfile(os.path.join(FRONTEND_DIST_DIR, "index.html")):
        return jsonify({
            "error": "O frontend ainda nao foi construido. Rode `npm run build` em frontend/ "
                     "(ou `.\\start.ps1 -Built`)."
        }), 404

    # send_from_directory recusa caminho que escapa da pasta (NotFound).
    if path and os.path.isfile(os.path.join(FRONTEND_DIST_DIR, path)):
        return send_from_directory(FRONTEND_DIST_DIR, path)

    # index.html nunca fica em cache: e ele que aponta para os assets do build novo.
    response = send_from_directory(FRONTEND_DIST_DIR, "index.html", max_age=0)
    response.headers["Cache-Control"] = "no-cache"
    return response
