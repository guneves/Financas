"""Respostas HTTP compartilhadas pelos blueprints (downloads)."""

from flask import Response


def csv_response(text, filename):
    """Resposta de download de CSV.

    Content-Disposition fica exposto no CORS para o navegador poder ler o nome
    do arquivo; o cliente busca com o Bearer no cabecalho, entao o download nao
    pode ser um link simples.
    """
    # mimetype sem charset: o Flask ja acrescenta "; charset=utf-8" a text/*.
    response = Response(text, mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return response
