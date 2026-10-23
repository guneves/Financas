"""Cadastro fechado e chave dos tokens (revisao de 2026-10-18).

Sem JWT_SECRET no ambiente, os tokens eram assinados com o padrao publico
"dev-secret-change-me" e o app subia assim mesmo; e o /api/auth/signup era
aberto a qualquer um que alcancasse o servidor.
"""

import importlib
import os
import stat


def signup(client, email):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": "senha-de-teste-123", "username": "Fulano"},
    )


def test_signup_is_closed_once_the_owner_exists(client, app_module, monkeypatch):
    # O banco dos testes e um so na sessao: o dono e cadastrado com o cadastro
    # aberto, e entao ele fecha (o caso do banco vazio e o primeiro cadastro).
    auth_routes = importlib.import_module("routes.auth")
    first = signup(client, "dono@example.com")
    assert first.status_code == 201, first.get_data(as_text=True)
    monkeypatch.setattr(auth_routes, "ALLOW_SIGNUP", False)

    second = signup(client, "estranho@example.com")
    assert second.status_code == 403
    assert "fechado" in second.get_json()["error"]
    # O dono continua entrando.
    login = client.post("/api/auth/login", json={"email": "dono@example.com", "password": "senha-de-teste-123"})
    assert login.status_code == 200


def test_allow_signup_opens_it(client, app_module, monkeypatch):
    auth_routes = importlib.import_module("routes.auth")
    monkeypatch.setattr(auth_routes, "ALLOW_SIGNUP", True)
    assert signup(client, "um@example.com").status_code == 201
    assert signup(client, "dois@example.com").status_code == 201


def test_a_public_secret_is_replaced_by_a_stored_random_one(app_module, monkeypatch, tmp_path):
    config = importlib.import_module("config")
    secret_file = tmp_path / "dados" / ".jwt_secret"
    monkeypatch.setattr(config, "JWT_SECRET_FILE", str(secret_file))

    for public in ("", "dev-secret-change-me", "troque-esta-chave-em-producao"):
        monkeypatch.setenv("JWT_SECRET", public)
        secret = config.load_jwt_secret()
        assert secret not in config.PUBLIC_JWT_SECRETS
        assert len(secret) >= 32
    # Gerada uma vez: o proximo boot le a mesma (os aparelhos continuam logados).
    assert config.load_jwt_secret() == secret == secret_file.read_text().strip()
    if os.name == "posix":
        assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600


def test_a_real_secret_from_the_environment_wins(app_module, monkeypatch, tmp_path):
    config = importlib.import_module("config")
    monkeypatch.setattr(config, "JWT_SECRET_FILE", str(tmp_path / ".jwt_secret"))
    monkeypatch.setenv("JWT_SECRET", "uma-chave-longa-de-verdade")
    assert config.load_jwt_secret() == "uma-chave-longa-de-verdade"
    assert not (tmp_path / ".jwt_secret").exists()


def test_the_login_screen_can_ask_whether_signup_is_open(client, app_module, monkeypatch):
    # A tela de login so oferece "Criar acesso" quando o cadastro esta aberto.
    auth_routes = importlib.import_module("routes.auth")
    monkeypatch.setattr(auth_routes, "ALLOW_SIGNUP", False)
    assert signup(client, "primeiro@example.com").status_code in (201, 403)
    closed = client.get("/api/auth/signup")
    assert closed.status_code == 200
    assert closed.get_json() == {"open": False}
    monkeypatch.setattr(auth_routes, "ALLOW_SIGNUP", True)
    assert client.get("/api/auth/signup").get_json() == {"open": True}
