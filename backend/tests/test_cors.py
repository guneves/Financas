"""O APK chama a API de outra origem (https://localhost), com Authorization.

Cada GET precisa de um preflight OPTIONS; sem Access-Control-Max-Age o Chrome
guarda a resposta por 5 s e quase todo pedido do celular vira duas idas ao PC.
"""


def test_preflight_fica_em_cache_no_navegador(client):
    response = client.options(
        "/api/accounts",
        headers={
            "Origin": "https://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("Access-Control-Max-Age") == "7200"
    assert "authorization" in response.headers.get("Access-Control-Allow-Headers", "").lower()
