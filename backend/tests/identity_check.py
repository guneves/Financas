"""I1/I2 no fim de cada cenario.

`assert_identity(user_id)` falha com a lista de violacoes de
`identity_invariants.violations()`. Importa `db` so dentro da funcao: os testes
nunca importam `db` no topo (conftest.py troca o banco antes)."""

import importlib

from identity_invariants import violations


def assert_identity(user_id):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        found = violations(conn, user_id)
    assert found == [], "\n".join(found)
