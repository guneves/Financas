"""Sem CORS: a tela e a API sao uma origem so (Vite com proxy em dev, Flask ou o
proxy de autenticacao em producao). Nenhuma outra origem pode ler a API."""

EVIL = "https://evil.example"


def test_preflight_de_outra_origem_nao_libera(client):
    response = client.options(
        "/api/accounts",
        headers={
            "Origin": EVIL,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert "Access-Control-Allow-Origin" not in response.headers


def test_get_de_outra_origem_nao_libera(client):
    response = client.get("/api/health", headers={"Origin": EVIL})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
