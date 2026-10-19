"""GET nos servicos do governo: o SGS do Banco Central e o Tesouro Transparente.

Os dois falhavam no servidor e funcionavam no navegador. A imagem roda Python
3.14, e desde o 3.13 `ssl.create_default_context()` liga `VERIFY_X509_STRICT`,
que recusa certificados fora da RFC 5280 (sem Authority Key Identifier, uma CA
intermediaria sem keyUsage) -- defeito comum nas cadeias dos sites gov.br, que
navegadores e curl aceitam. Aqui a cadeia e o nome do host continuam
verificados; so a checagem estrita sai.

Tambem aqui: uma nova tentativa para falhas passageiras (sem conexao, tempo
esgotado, 429/502/503/504) e um erro que diz a causa ("certificado recusado",
"sem resposta em 15 s") em vez do repr do urllib, para o healthcheck mostrar.

Os testes trocam `urllib.request.urlopen`; a funcao e lida na hora da chamada.
"""

import socket
import ssl
import time
import urllib.error
import urllib.request

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
RETRY_STATUS = {429, 502, 503, 504}
# Espera antes de cada nova tentativa (segundos); uma tentativa a mais por item.
RETRY_DELAYS_SECONDS = (1.5,)


def ssl_context():
    """Contexto com a cadeia verificada, sem o modo estrito do Python 3.13+."""
    context = ssl.create_default_context()
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict:
        context.verify_flags &= ~strict
    return context


_context = None


def _shared_context():
    global _context
    if _context is None:
        _context = ssl_context()
    return _context


def describe_error(exc, timeout):
    """O motivo de uma falha de rede em portugues, curto (vai para a tela)."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"respondeu HTTP {exc.code}"
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError) or isinstance(exc, ssl.SSLCertVerificationError):
        detail = getattr(reason, "verify_message", None) or str(reason)
        return f"certificado recusado ({detail})"
    if isinstance(reason, ssl.SSLError):
        return f"erro de TLS ({reason})"
    if isinstance(reason, (socket.timeout, TimeoutError)) or "timed out" in str(reason):
        return f"sem resposta em {timeout:g} s"
    if isinstance(reason, socket.gaierror):
        return "endereco nao encontrado (DNS)"
    if isinstance(reason, ConnectionRefusedError):
        return "conexao recusada"
    return str(reason) or exc.__class__.__name__


def _retryable(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in RETRY_STATUS
    reason = getattr(exc, "reason", exc)
    # Certificado recusado nao melhora tentando de novo.
    return not isinstance(reason, ssl.SSLError)


def get(url, timeout, accept="*/*"):
    """Os bytes da resposta. HTTPError sobe como esta (quem chama le o corpo);
    qualquer outra falha vira RuntimeError com o motivo legivel."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    delays = list(RETRY_DELAYS_SECONDS)
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=_shared_context()) as response:
                return response.read()
        except (urllib.error.URLError, OSError) as exc:
            if delays and _retryable(exc):
                time.sleep(delays.pop(0))
                continue
            if isinstance(exc, urllib.error.HTTPError):
                raise
            raise RuntimeError(describe_error(exc, timeout)) from exc
