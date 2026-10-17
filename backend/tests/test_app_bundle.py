"""A tela do APK servida para o celular se atualizar (services/app_bundle.py)."""

import hashlib
import importlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest

VERSION = "0123456789abcdef"


@pytest.fixture()
def bundle_dir(app_module, db_module, monkeypatch):
    # Ao lado do banco de teste, como test_frontend_serving.py: a pasta temporaria
    # do proprio pytest nem sempre e acessivel nesta maquina.
    directory = Path(tempfile.mkdtemp(dir=os.path.dirname(db_module.DATABASE_PATH)))
    module = importlib.import_module("services.app_bundle")
    # Patch onde o nome e lido.
    monkeypatch.setattr(module, "APP_BUNDLE_DIR", str(directory))
    module.reset_cache()
    yield directory
    module.reset_cache()


def write_bundle(directory, version=VERSION, native_level=1, api_base="https://servidor.exemplo"):
    (directory / "assets").mkdir(exist_ok=True)
    (directory / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (directory / "assets" / "index-abc.js").write_text("console.log('tela')", encoding="utf-8")
    (directory / "bundle.json").write_text(
        json.dumps({"version": version, "native_level": native_level, "api_base": api_base}),
        encoding="utf-8",
    )


def test_no_bundle_is_a_404(client, bundle_dir):
    response = client.get("/api/app-bundle")
    assert response.status_code == 404
    assert response.get_json()["error"]


def test_manifest_describes_the_zip_it_serves(client, bundle_dir):
    write_bundle(bundle_dir)

    manifest = client.get("/api/app-bundle").get_json()
    assert manifest["version"] == VERSION
    assert manifest["native_level"] == 1
    assert manifest["api_base"] == "https://servidor.exemplo"
    assert manifest["url"] == f"/api/app-bundle/{VERSION}.zip"

    response = client.get(manifest["url"])
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    data = response.get_data()
    assert len(data) == manifest["size"]
    assert hashlib.sha256(data).hexdigest() == manifest["sha256"]

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(archive.namelist())
        assert names == ["assets/index-abc.js", "bundle.json", "index.html"]
        assert json.loads(archive.read("bundle.json"))["version"] == VERSION


def test_same_content_gives_the_same_bytes(client, bundle_dir, app_module):
    """O SHA-256 do manifesto precisa valer depois de um reboot do servidor."""
    write_bundle(bundle_dir)
    first = client.get(f"/api/app-bundle/{VERSION}.zip").get_data()
    importlib.import_module("services.app_bundle").reset_cache()
    second = client.get(f"/api/app-bundle/{VERSION}.zip").get_data()
    assert first == second


def test_only_the_current_version_downloads(client, bundle_dir):
    write_bundle(bundle_dir)
    assert client.get("/api/app-bundle/fedcba9876543210.zip").status_code == 404


def test_a_new_build_is_picked_up_without_a_restart(client, bundle_dir):
    write_bundle(bundle_dir)
    client.get("/api/app-bundle")
    write_bundle(bundle_dir, version="1111111111111111")
    (bundle_dir / "index.html").write_text("<!doctype html>nova", encoding="utf-8")

    manifest = client.get("/api/app-bundle").get_json()
    assert manifest["version"] == "1111111111111111"
    data = client.get(manifest["url"]).get_data()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.read("index.html") == b"<!doctype html>nova"


@pytest.mark.parametrize("manifest", [
    {"version": "curta", "native_level": 1, "api_base": "https://x"},
    {"version": VERSION, "native_level": 0, "api_base": "https://x"},
    {"version": VERSION, "native_level": True, "api_base": "https://x"},
    {"version": VERSION, "native_level": "1", "api_base": "https://x"},
    {"version": VERSION, "native_level": 1, "api_base": "http://x"},
    {"version": VERSION, "native_level": 1},
])
def test_an_invalid_manifest_serves_nothing(client, bundle_dir, manifest):
    write_bundle(bundle_dir)
    (bundle_dir / "bundle.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert client.get("/api/app-bundle").status_code == 404


def test_a_build_without_index_serves_nothing(client, bundle_dir):
    write_bundle(bundle_dir)
    (bundle_dir / "index.html").unlink()
    assert client.get("/api/app-bundle").status_code == 404


def test_no_token_needed(client, bundle_dir):
    """Um app deslogado tambem se atualiza: a tela e a mesma que `/` serve a qualquer um."""
    write_bundle(bundle_dir)
    assert client.get("/api/app-bundle").status_code == 200
