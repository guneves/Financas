"""Catalogo de tickers da B3 para o autocompletar do formulario de investimento."""

from flask import Blueprint, jsonify, request

from asset_classes import parse_asset_class_filter
from auth import token_required
import market_catalog

bp = Blueprint("market", __name__)


@bp.route("/api/market/tickers", methods=["GET"])
@token_required
def market_tickers(current_user_id):
    """Busca no catalogo da B3 (acoes, ETFs, FIIs e BDRs).

    Alimenta o autocomplete da tela de lancamento. E dado de referencia, igual
    para todo mundo, entao nao ha filtro por user_id aqui -- nenhuma linha vem
    do banco.
    """
    results = market_catalog.search(
        query=request.args.get("q", ""),
        asset_class=parse_asset_class_filter(request.args.get("asset_class")),
        kind=request.args.get("kind"),
        limit=request.args.get("limit", 20),
    )
    return jsonify(results), 200


@bp.route("/api/market/tickers/<ticker>", methods=["GET"])
@token_required
def market_ticker_detail(current_user_id, ticker):
    entry = market_catalog.lookup(ticker)
    if not entry:
        return jsonify({"error": "Ativo nao encontrado na lista da B3."}), 404
    return jsonify(entry), 200
