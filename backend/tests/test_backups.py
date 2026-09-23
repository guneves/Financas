"""Automatic backup on boot and 7-day retention (Phase 1's last item).

`run_startup_backup()` runs at import time in the real app. The test session
disables it via `AUTO_BACKUP_ON_BOOT=0` (see `conftest.py`) and re-enables it
here with monkeypatch, so the boot behaviour is exercised deliberately instead
of as a side effect of importing the module.
"""

import os
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture()
def test_dir(db_module):
    """Diretorio de trabalho ao lado do banco de teste.

    Deliberadamente nao usa a fixture de diretorio temporario do pytest: a base
    dela fica em `%TEMP%/pytest-of-<user>`, que nem sempre e acessivel aqui.
    """
    return Path(tempfile.mkdtemp(dir=os.path.dirname(db_module.DATABASE_PATH)))


@pytest.fixture()
def backup_dir(db_module, monkeypatch, test_dir):
    """Aponta os backups para um diretorio proprio a cada teste."""
    target = test_dir / "backups"
    monkeypatch.setattr(db_module, "DATABASE_BACKUP_DIR", str(target))
    return target


def age_file(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def touch_backup(directory, name, days_old=0):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("backup", encoding="utf-8")
    if days_old:
        age_file(path, days_old)
    return path


# --- pruning -----------------------------------------------------------------

def test_prune_removes_backups_past_retention(db_module, backup_dir):
    stale = touch_backup(backup_dir, "finance-20260101-000000.zip", days_old=9)
    fresh = touch_backup(backup_dir, "finance-20260914-000000.zip", days_old=1)

    removed = db_module.prune_database_backups(retention_days=7)

    assert removed == [stale.name]
    assert not stale.exists()
    assert fresh.exists()


def test_prune_keeps_a_backup_on_the_retention_boundary(db_module, backup_dir):
    edge = touch_backup(backup_dir, "finance-20260909-000000.db", days_old=6)

    assert db_module.prune_database_backups(retention_days=7) == []
    assert edge.exists()


def test_prune_ignores_files_it_did_not_create(db_module, backup_dir):
    foreign = touch_backup(backup_dir, "notas-fiscais.zip", days_old=90)
    wrong_suffix = touch_backup(backup_dir, "finance-20260101-000000.txt", days_old=90)

    assert db_module.prune_database_backups(retention_days=7) == []
    assert foreign.exists()
    assert wrong_suffix.exists()


def test_prune_never_touches_a_hand_named_milestone_backup(db_module, backup_dir):
    """Backups com nome proprio sao marcos manuais e ficam fora da rotacao.

    A retencao so remove o que o proprio app gera no formato
    `finance-AAAAMMDD-HHMMSS.*`. Um `finance-before-<coisa>-*.db` de meses atras
    permanece — foi gravado de proposito antes de uma migracao.
    """
    milestone = touch_backup(
        backup_dir, "finance-before-normalized-investments-20260702-234230.db", days_old=200
    )
    automatic = touch_backup(backup_dir, "finance-20260702-234230.db", days_old=200)

    removed = db_module.prune_database_backups(retention_days=7)

    assert removed == [automatic.name]
    assert milestone.exists()


def test_prune_handles_a_missing_backup_directory(db_module, backup_dir):
    assert not backup_dir.exists()
    assert db_module.prune_database_backups(retention_days=7) == []


def test_prune_covers_every_artifact_of_one_backup(db_module, backup_dir):
    names = [
        "finance-20260101-000000.db",
        "finance-20260101-000000.sql",
        "finance-20260101-000000.zip",
    ]
    for name in names:
        touch_backup(backup_dir, name, days_old=30)

    assert sorted(db_module.prune_database_backups(retention_days=7)) == sorted(names)
    assert list(backup_dir.iterdir()) == []


def test_last_backup_age_reports_the_newest_file(db_module, backup_dir):
    assert db_module.last_backup_age_hours() is None

    touch_backup(backup_dir, "finance-20260101-000000.zip", days_old=10)
    touch_backup(backup_dir, "finance-20260914-000000.zip", days_old=1)

    age = db_module.last_backup_age_hours()
    assert age == pytest.approx(24, abs=1)


# --- boot --------------------------------------------------------------------

def test_startup_backup_writes_the_three_artifacts(db_module, backup_dir, monkeypatch):
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", True)
    monkeypatch.setattr(db_module, "AUTO_BACKUP_MIN_INTERVAL_HOURS", 0)

    backup = db_module.run_startup_backup()

    assert backup is not None
    for key in ("database_path", "dump_path", "zip_path"):
        assert os.path.isfile(backup[key]), key
    assert backup["pruned"] == []


def test_startup_backup_prunes_while_it_runs(db_module, backup_dir, monkeypatch):
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", True)
    monkeypatch.setattr(db_module, "AUTO_BACKUP_MIN_INTERVAL_HOURS", 0)
    monkeypatch.setattr(db_module, "BACKUP_RETENTION_DAYS", 7)
    stale = touch_backup(backup_dir, "finance-20250101-000000.zip", days_old=30)

    backup = db_module.run_startup_backup()

    assert backup["pruned"] == [stale.name]
    assert not stale.exists()


def test_startup_backup_is_skipped_when_disabled(db_module, backup_dir, monkeypatch):
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", False)

    assert db_module.run_startup_backup() is None
    assert not backup_dir.exists()


def test_restarting_soon_after_a_backup_does_not_create_another(db_module, backup_dir, monkeypatch):
    """Reiniciar o app varias vezes no dia nao deve encher o diretorio."""
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", True)
    monkeypatch.setattr(db_module, "AUTO_BACKUP_MIN_INTERVAL_HOURS", 12)
    touch_backup(backup_dir, "finance-20260915-000000.zip")

    assert db_module.run_startup_backup() is None
    assert len(list(backup_dir.iterdir())) == 1


def test_a_stale_backup_triggers_a_new_one_on_boot(db_module, backup_dir, monkeypatch):
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", True)
    monkeypatch.setattr(db_module, "AUTO_BACKUP_MIN_INTERVAL_HOURS", 12)
    touch_backup(backup_dir, "finance-20260914-000000.zip", days_old=1)

    assert db_module.run_startup_backup() is not None


def test_startup_backup_is_skipped_without_a_database_file(db_module, backup_dir, monkeypatch, test_dir):
    monkeypatch.setattr(db_module, "AUTO_BACKUP_ON_BOOT", True)
    monkeypatch.setattr(db_module, "DATABASE_PATH", str(test_dir / "inexistente.db"))

    assert db_module.run_startup_backup() is None
    assert not backup_dir.exists()


# --- endpoint ----------------------------------------------------------------

def test_backup_endpoint_also_prunes(client, auth, db_module, backup_dir, monkeypatch):
    monkeypatch.setattr(db_module, "BACKUP_RETENTION_DAYS", 7)
    stale = touch_backup(backup_dir, "finance-20250101-000000.zip", days_old=30)

    response = client.post("/api/database/backups", headers=auth)

    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["pruned"] == [stale.name]
    assert not stale.exists()


def test_backup_endpoint_requires_authentication(client):
    assert client.post("/api/database/backups").status_code == 401


# --- espelho dos comprovantes ------------------------------------------------

@pytest.fixture()
def attachments_dir(db_module, monkeypatch, test_dir):
    target = test_dir / "attachments"
    monkeypatch.setattr(db_module, "ATTACHMENTS_DIR", str(target))
    return target


def write_receipt(directory, user_id, name, content=b"%PDF-1.4 recibo"):
    folder = directory / user_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(content)
    return path


def test_mirror_copies_new_receipts_once(db_module, backup_dir, attachments_dir):
    write_receipt(attachments_dir, "u1", "a.pdf")
    first = db_module.mirror_attachments()
    second = db_module.mirror_attachments()

    assert first["copied"] == 1
    assert second["copied"] == 0
    assert (backup_dir / "attachments" / "u1" / "a.pdf").read_bytes() == b"%PDF-1.4 recibo"


def test_a_deleted_receipt_moves_to_a_dated_folder(db_module, backup_dir, attachments_dir):
    receipt = write_receipt(attachments_dir, "u1", "a.pdf")
    db_module.mirror_attachments()
    receipt.unlink()

    result = db_module.mirror_attachments()

    assert result["removed"] == 1
    assert not (backup_dir / "attachments" / "u1" / "a.pdf").exists()
    removed = list((backup_dir / "attachments-removed").glob("*/u1/a.pdf"))
    assert len(removed) == 1


def test_removed_receipts_expire_after_retention(db_module, backup_dir, attachments_dir):
    old_day = backup_dir / "attachments-removed" / "20200101" / "u1"
    old_day.mkdir(parents=True)
    (old_day / "velho.pdf").write_bytes(b"x")

    result = db_module.mirror_attachments(retention_days=7)

    assert result["expired_days"] == ["20200101"]
    assert not (backup_dir / "attachments-removed" / "20200101").exists()


def test_backup_runs_the_mirror(db_module, backup_dir, attachments_dir):
    write_receipt(attachments_dir, "u1", "a.pdf")
    backup = db_module.create_database_backup()
    assert backup["attachments"]["copied"] == 1
    assert (backup_dir / "attachments" / "u1" / "a.pdf").exists()
    # O espelho nao entra na retencao dos zips.
    assert all("attachments" not in os.path.basename(path) for path, _ in db_module.backup_files())
