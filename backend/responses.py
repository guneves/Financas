"""Respostas HTTP compartilhadas pelos blueprints (downloads)."""

from datetime import datetime

from flask import Response

import export_csv
import export_xlsx
from export_csv import ColumnError

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_FORMATS = {"csv", "xlsx"}


def download_response(body, mimetype, filename):
    """Resposta de download.

    Content-Disposition fica exposto no CORS para o navegador poder ler o nome
    do arquivo; o cliente busca com o Bearer no cabecalho, entao o download nao
    pode ser um link simples.
    """
    response = Response(body, mimetype=mimetype)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return response


def csv_response(text, filename):
    # mimetype sem charset: o Flask ja acrescenta "; charset=utf-8" a text/*.
    return download_response(text, "text/csv", filename)


def read_export_options(args, export_name):
    """(formato, colunas) de `?format=csv|xlsx&columns=a,b`.

    ColumnError (um ValueError) quando o pedido e invalido; a rota responde 400.
    """
    fmt = (args.get("format") or "csv").strip().lower()
    if fmt not in EXPORT_FORMATS:
        raise ColumnError("Formato deve ser csv ou xlsx.")
    columns = export_csv.select_columns(export_csv.EXPORTS[export_name], args.get("columns"))
    return fmt, columns


def export_response(fmt, columns, items, *, basename, sheet_name, context=None):
    """A mesma tabela em CSV (padrao) ou .xlsx, com a data de hoje no nome."""
    filename = f"{basename}-{datetime.now().strftime('%Y-%m-%d')}.{fmt}"
    if fmt == "xlsx":
        body = export_xlsx.table_xlsx(sheet_name, columns, items, context)
        return download_response(body, XLSX_MIMETYPE, filename)
    return csv_response(export_csv.table_csv(columns, items, context), filename)
