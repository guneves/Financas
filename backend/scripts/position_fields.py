"""Que campos a Pluggy preenche nas posicoes da corretora, so lendo (Fase 3).

No servidor (padrao do DEPLOY.md), depois do deploy e de um pull:

    sudo docker compose exec -T -w /app/backend app python scripts/position_fields.py --email X

Para cada posicao guardada (`open_finance_positions.raw`, 056) imprime o tipo, o
subtipo e **quais chaves vem preenchidas** (nao nulas, nao vazias). Nenhum valor
sai daqui alem do tipo e do subtipo: nem nome, nem quantidade, nem saldo, nem
taxa. E o que diz se a renda fixa da BTG pode gravar sozinha
(`rate`, `rateType`, `fixedAnnualRate`, `dueDate`, `issuer`...;
services/open_finance_fixed_income.py).

Abre o SQLite somente leitura (`mode=ro`) e nunca importa `app` (que roda
init_db() e migra no import). Codigo de saida: 0 ok, 2 usuario nao encontrado.
"""

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_PATH  # noqa: E402

# Os campos que a renda fixa le, nesta ordem no resumo.
WATCHED = ("rateType", "rate", "fixedAnnualRate", "dueDate", "issuer", "issueDate", "isin")


def filled_keys(raw):
    """Puro: as chaves com valor (nao None, nao "", nao {} nem [])."""
    if not isinstance(raw, dict):
        return []
    return sorted(key for key, value in raw.items() if value not in (None, "", {}, []))


def report_lines(rows):
    """Puro: [(pluggy_type, subtype, raw_text)] -> as linhas impressas."""
    lines = []
    for pluggy_type, subtype, raw_text in rows:
        try:
            raw = json.loads(raw_text) if raw_text else None
        except ValueError:
            raw = None
        if raw is None:
            lines.append(f"{pluggy_type or '-'} / {subtype or '-'}: sem raw (ainda nao puxada depois do deploy)")
            continue
        keys = filled_keys(raw)
        watched = ", ".join(f"{key}={'sim' if key in keys else 'nao'}" for key in WATCHED)
        lines.append(f"{pluggy_type or '-'} / {subtype or '-'}: {', '.join(keys)}")
        lines.append(f"    renda fixa: {watched}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lista as chaves preenchidas de cada posicao da Pluggy.")
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
        rows = conn.execute(
            """
            SELECT pluggy_type, subtype, raw FROM open_finance_positions
            WHERE user_id = ? ORDER BY pluggy_type, subtype, id
            """,
            (user[0],),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        print("Nenhuma posicao da Pluggy.")
    for line in report_lines(rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
