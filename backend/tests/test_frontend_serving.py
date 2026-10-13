"""O Flask serve o build do frontend em `/` (mobile-docs/steps-to-production.md, fase 1).

Uma origem so: a tela e a API no mesmo endereco. O que estes testes seguram e
a fronteira — uma rota de tela cai no index.html, uma rota de API que nao
existe continua sendo erro em JSON, e nada fora da pasta do build e servido.
"""

import importlib
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_path(db_module):
    # Ao lado do banco de teste, como test_backups.py: a pasta temporaria do
    # proprio pytest nem sempre e acessivel nesta maquina.
    return Path(tempfile.mkdtemp(dir=tempfile.mkdtemp(dir=os.path.dirname(db_module.DATABASE_PATH))))


@pytest.fixture()
def dist(tmp_path, monkeypatch, app_module):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path.parent / "segredo.txt").write_text("fora do build", encoding="utf-8")
    # Patch onde o nome e lido: o blueprint importa FRONTEND_DIST_DIR pelo nome.
    monkeypatch.setattr(importlib.import_module("routes.frontend"), "FRONTEND_DIST_DIR", str(tmp_path))
    return tmp_path


def test_root_serves_the_built_index(client, dist):
    response = client.get("/")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "<html>app</html>"
    assert response.headers["Cache-Control"] == "no-cache"


def test_a_build_file_is_served_as_itself(client, dist):
    response = client.get("/assets/app.js")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "console.log(1)"


@pytest.mark.parametrize("path", ["/lancamentos", "/investimentos/posicao", "/ajustes/contas"])
def test_a_screen_route_falls_back_to_the_index(client, dist, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "<html>app</html>"


@pytest.mark.parametrize("path", ["/api", "/api/nao-existe", "/api/transactions/x/y/z"])
def test_an_unknown_api_path_is_a_json_404_not_the_app(client, dist, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "error" in response.get_json()


def test_the_api_still_answers_and_still_asks_for_a_token(client, dist):
    assert client.get("/api/health").get_json()["status"] == "ok"
    assert client.get("/api/transactions").status_code == 401


@pytest.mark.parametrize("path", ["/../segredo.txt", "/assets/../../segredo.txt", "/%2e%2e/segredo.txt"])
def test_nothing_outside_the_build_is_served(client, dist, path):
    response = client.get(path)
    assert "fora do build" not in response.get_data(as_text=True)


def test_without_a_build_the_answer_says_so(client, tmp_path, monkeypatch, app_module):
    monkeypatch.setattr(importlib.import_module("routes.frontend"), "FRONTEND_DIST_DIR", str(tmp_path))
    response = client.get("/")
    assert response.status_code == 404
    assert "npm run build" in response.get_json()["error"]
