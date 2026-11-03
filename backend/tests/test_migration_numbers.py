"""Cada migration tem um numero proprio.

`init_db()` registra a migration pelo numero (`migration_version()`): duas com o
mesmo numero fazem a segunda ser pulada em silencio. Foi o que aconteceu com
052_open_finance_pending_on e 052_share_paid_by (2026-11-03): o deploy quebrou
com "no such column: share_paid_by".
"""

import collections
import os

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "database", "migrations"
)


def test_no_two_migrations_share_a_number():
    versions = collections.Counter(
        name.split("_", 1)[0]
        for name in os.listdir(MIGRATIONS_DIR)
        if name.lower().endswith(".sql")
    )
    repeated = sorted(version for version, count in versions.items() if count > 1)
    assert repeated == []


def test_every_migration_is_applied(db_module):
    conn = db_module.get_db()
    try:
        applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(transactions)")}
    finally:
        conn.close()
    on_disk = {name for name in db_module.migration_files()}
    assert on_disk - applied == set()
    assert "share_paid_by" in columns
