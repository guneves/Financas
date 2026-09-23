"""Banco SQLite: conexao, migrations versionadas e backups.

`init_db()` aplica, em ordem, os arquivos de `database/migrations` que ainda
nao constam em `schema_migrations`. Os backups automaticos seguem
`finance-AAAAMMDD-HHMMSS.*` e so esses entram na retencao.
"""

import json
import os
import re
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime, timezone

from config import (
    AUTO_BACKUP_MIN_INTERVAL_HOURS,
    AUTO_BACKUP_ON_BOOT,
    BACKUP_RETENTION_DAYS,
    DATABASE_BACKUP_DIR,
    DATABASE_PATH,
    MIGRATIONS_DIR,
    SQLITE_BUSY_TIMEOUT_MS,
)


# So os arquivos gerados automaticamente entram na rotacao. Backups com nome
# proprio (ex.: "finance-before-normalized-investments-*.db") sao marcos feitos
# a mao e nunca sao apagados pela retencao.
BACKUP_FILE_PATTERN = re.compile(r"^finance-\d{8}-\d{6}\.(db|sql|zip)$")


def get_db():
    database_dir = os.path.dirname(os.path.abspath(DATABASE_PATH))
    if database_dir:
        os.makedirs(database_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def configure_sqlite_database(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError as exc:
        print(f"Nao foi possivel ativar WAL no SQLite: {exc}")


def migration_version(filename):
    stem = filename.rsplit(".", 1)[0]
    return stem.split("_", 1)[0]


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def migration_files():
    if not os.path.isdir(MIGRATIONS_DIR):
        raise RuntimeError(f"Diretorio de migrations nao encontrado: {MIGRATIONS_DIR}")

    files = [
        filename
        for filename in os.listdir(MIGRATIONS_DIR)
        if filename.lower().endswith(".sql")
    ]
    return sorted(files)


def ensure_migrations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )


def applied_migration_versions(conn):
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def init_db():
    with get_db() as conn:
        configure_sqlite_database(conn)
        ensure_migrations_table(conn)
        applied_versions = applied_migration_versions(conn)

        for filename in migration_files():
            version = migration_version(filename)
            if version in applied_versions:
                continue

            migration_path = os.path.join(MIGRATIONS_DIR, filename)
            with open(migration_path, "r", encoding="utf-8") as file:
                sql = file.read()

            migration_script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT OR IGNORE INTO schema_migrations (version, name) VALUES "
                f"({sql_literal(version)}, {sql_literal(filename)});\n"
                "COMMIT;"
            )
            try:
                conn.executescript(migration_script)
            except sqlite3.DatabaseError:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.DatabaseError:
                    pass
                raise
            applied_versions.add(version)


def database_status():
    with get_db() as conn:
        configure_sqlite_database(conn)
        ensure_migrations_table(conn)
        migration_rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        wal_checkpoint = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()

    return {
        "path": DATABASE_PATH,
        "journal_mode": journal_mode,
        "foreign_keys": bool(foreign_keys),
        "busy_timeout_ms": SQLITE_BUSY_TIMEOUT_MS,
        "size_bytes": page_size * page_count,
        "wal_log_pages": wal_checkpoint[1] if wal_checkpoint else 0,
        "wal_checkpointed_pages": wal_checkpoint[2] if wal_checkpoint else 0,
        "migrations": [row_to_dict(row) for row in migration_rows],
    }


def create_database_backup():
    os.makedirs(DATABASE_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.db")

    with sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)

    dump_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.sql")
    with sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000) as source:
        with open(dump_path, "w", encoding="utf-8") as dump_file:
            for line in source.iterdump():
                dump_file.write(f"{line}\n")

    zip_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(backup_path, arcname=os.path.basename(backup_path))
        archive.write(dump_path, arcname=os.path.basename(dump_path))

    return {
        "database_path": backup_path,
        "dump_path": dump_path,
        "zip_path": zip_path,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def backup_files():
    """Backups automaticos (finance-AAAAMMDD-HHMMSS.*), do mais novo ao mais antigo."""
    if not os.path.isdir(DATABASE_BACKUP_DIR):
        return []

    entries = []
    for filename in os.listdir(DATABASE_BACKUP_DIR):
        if not BACKUP_FILE_PATTERN.match(filename):
            continue
        path = os.path.join(DATABASE_BACKUP_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            entries.append((path, os.path.getmtime(path)))
        except OSError:
            continue

    entries.sort(key=lambda entry: entry[1], reverse=True)
    return entries


def last_backup_age_hours():
    """Hours since the most recent backup, or None when there is none."""
    entries = backup_files()
    if not entries:
        return None
    return max(0.0, (time.time() - entries[0][1]) / 3600)


def prune_database_backups(retention_days=None):
    """Delete backup artifacts older than the retention window."""
    retention_days = BACKUP_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = time.time() - retention_days * 86400

    removed = []
    for path, modified_at in backup_files():
        if modified_at >= cutoff:
            continue
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except OSError as exc:
            print(f"Nao foi possivel remover o backup antigo {path}: {exc}")

    return removed


def run_startup_backup():
    """Back up the database on boot, then prune anything past retention.

    Skipped when AUTO_BACKUP_ON_BOOT is off, when there is no database file yet,
    or when a backup already ran inside AUTO_BACKUP_MIN_INTERVAL_HOURS - restarting
    the app repeatedly should not fill the backup directory.
    """
    if not AUTO_BACKUP_ON_BOOT:
        return None

    if not os.path.isfile(DATABASE_PATH) or os.path.getsize(DATABASE_PATH) == 0:
        return None

    age_hours = last_backup_age_hours()
    if age_hours is not None and age_hours < AUTO_BACKUP_MIN_INTERVAL_HOURS:
        prune_database_backups()
        return None

    try:
        backup = create_database_backup()
    except Exception as exc:
        print(f"Backup automatico de boot falhou: {exc}")
        return None

    removed = prune_database_backups()
    print(
        f"Backup automatico criado em {backup['zip_path']}"
        + (f" ({len(removed)} arquivo(s) antigo(s) removido(s))" if removed else "")
    )
    backup["pruned"] = removed
    return backup


def new_id():
    return str(uuid.uuid4())


def row_to_dict(row):
    return dict(row) if row else None


def parse_metadata_value(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def encode_metadata(value):
    if value in (None, ""):
        return None
    return json.dumps(value) if isinstance(value, dict) else value


def serialize_metadata_row(row):
    item = row_to_dict(row)
    if item and "metadata" in item:
        item["metadata"] = parse_metadata_value(item.get("metadata"))
    return item


def serialize_transaction(row):
    return serialize_metadata_row(row)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
