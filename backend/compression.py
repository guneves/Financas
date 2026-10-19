"""Respostas JSON comprimidas com gzip, quando o cliente aceita.

O Extrato e os Cartoes leem centenas de KB de JSON (`/api/transactions`,
`/api/cc-expenses`), e o celular os busca pela VPN do Tailscale: comprimido, o
mesmo JSON cai para perto de um decimo. O navegador e o WebView do APK
descomprimem sozinhos (`Accept-Encoding: gzip`). Arquivos (o frontend, os
comprovantes, as exportacoes) ficam como estao: so o JSON da API passa aqui.
"""

import gzip

# Abaixo disso o cabecalho e o tempo de CPU custam mais do que economizam.
MIN_COMPRESS_BYTES = 1024
# Nivel 6 (o padrao do zlib e do nginx) comprime quase tanto quanto o 9 em
# bem menos tempo.
COMPRESS_LEVEL = 6


def accepts_gzip(accept_encoding):
    for part in (accept_encoding or "").split(","):
        token, _, params = part.strip().partition(";")
        if token.strip().lower() not in ("gzip", "*"):
            continue
        quality = params.strip().replace(" ", "")
        if quality.startswith("q=") and quality[2:] in ("0", "0.0", "0.00", "0.000"):
            return False
        return True
    return False


def compress_response(request, response):
    """`after_request`: comprime a resposta JSON se valer a pena."""
    if response.direct_passthrough or response.is_streamed:
        return response
    if response.status_code < 200 or response.status_code >= 300 or response.status_code == 204:
        return response
    if response.mimetype != "application/json" or "Content-Encoding" in response.headers:
        return response
    response.vary.add("Accept-Encoding")
    if not accepts_gzip(request.headers.get("Accept-Encoding")):
        return response
    body = response.get_data()
    if len(body) < MIN_COMPRESS_BYTES:
        return response
    response.set_data(gzip.compress(body, compresslevel=COMPRESS_LEVEL, mtime=0))
    response.headers["Content-Encoding"] = "gzip"
    return response
