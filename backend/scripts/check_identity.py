"""Confere I1/I2 (um movimento, uma linha) no banco, so lendo.

No servidor (padrao do DEPLOY.md):

    sudo docker compose exec -T -w /app/backend app python scripts/check_identity.py --email X

Abre o SQLite somente leitura (`mode=ro`) e nunca importa `app` (que roda
init_db() e migra no import). Em uso normal nao imprime nada. Codigo de saida:
0 nada a apontar, 1 ha violacoes, 2 usuario nao encontrado.
"""

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH  # noqa: E402
from identity_invariants import violations  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lista lancamentos que duas observacoes de um canal reclamam.")
    parser.add_argument("--email", required=True, help="O e-mail exato do usuario.")
    parser.add_argument("--database", default=DATABASE_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    path = os.path.abspath(args.database).replace("\\", "/")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (args.email,)).fetchone()
        if not user:
            print(f"Usuario nao encontrado: {args.email}", file=sys.stderr)
            return 2
        found = violations(conn, user[0])
    finally:
        conn.close()
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
