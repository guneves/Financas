"""Nome de usuario: escolhido no cadastro, trocado em Ajustes, nunca o e-mail."""

import uuid


def _email():
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


def _signup(client, **overrides):
    body = {"email": _email(), "password": "senha-de-teste-123", "username": "Guilherme"}
    body.update(overrides)
    return client.post("/api/auth/signup", json=body)


def test_signup_stores_username(client):
    response = _signup(client, username="  Guilherme   Neves ")
    assert response.status_code == 201
    assert response.get_json()["user"]["username"] == "Guilherme Neves"


def test_signup_requires_username(client):
    response = _signup(client, username="")
    assert response.status_code == 400
    assert "nome de usuario" in response.get_json()["error"]


def test_signup_rejects_email_as_username(client):
    response = _signup(client, username="eu@example.com")
    assert response.status_code == 400


def test_signup_rejects_long_username(client):
    response = _signup(client, username="x" * 41)
    assert response.status_code == 400


def test_login_and_me_return_username(client):
    email = _email()
    assert _signup(client, email=email, username="Ana").status_code == 201

    login = client.post("/api/auth/login", json={"email": email, "password": "senha-de-teste-123"})
    assert login.status_code == 200
    assert login.get_json()["user"]["username"] == "Ana"

    headers = {"Authorization": f"Bearer {login.get_json()['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.get_json()["user"]["username"] == "Ana"


def test_patch_me_changes_username(client, user, auth):
    response = client.patch("/api/auth/me", headers=auth, json={"username": "Novo Nome"})
    assert response.status_code == 200
    assert response.get_json()["user"]["username"] == "Novo Nome"
    assert client.get("/api/auth/me", headers=auth).get_json()["user"]["username"] == "Novo Nome"


def test_patch_me_validates_username(client, auth):
    response = client.patch("/api/auth/me", headers=auth, json={"username": " "})
    assert response.status_code == 400
    assert client.get("/api/auth/me", headers=auth).get_json()["user"]["username"] == "Usuario de teste"


def test_patch_me_only_touches_own_user(client, user, other_user):
    client.patch("/api/auth/me", headers=user["headers"], json={"username": "Primeiro"})
    other = client.get("/api/auth/me", headers=other_user["headers"]).get_json()["user"]
    assert other["username"] == "Usuario de teste"


def test_patch_me_requires_auth(client):
    assert client.patch("/api/auth/me", json={"username": "Alguem"}).status_code == 401
