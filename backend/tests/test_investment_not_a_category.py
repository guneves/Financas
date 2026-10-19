"""Investimento deixa de ser categoria (039, dono 2026-10-19).

O que estes testes fixam:

- a despesa/receita digitada em "Investimento" vira transferencia com a
  Corretora da carteira (a despesa vai para ela, a receita volta dela) e o
  saldo da conta do banco nao muda;
- quem nao tem Corretora ganha uma, saldo inicial 0, sem tomar a padrao;
- a linha que ja esta na propria Corretora, ou numa conta que nao e em reais,
  fica como esta;
- o caixa das operacoes e o provento pago viram "Aporte" / "Resgate" /
  "Provento", sem category_id;
- a categoria e arquivada, a regra de importacao que a escolhia e desligada e
  o item pendente do Aprovar volta para a categoria padrao;
- nada de outro usuario.
"""

import os
import sqlite3

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "database", "migrations")


def migrated_up_to(path, last_version):
    """Um banco como o de quem parou na migration `last_version` (db.init_db)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL)")
    for filename in sorted(os.listdir(MIGRATIONS_DIR)):
        version = filename.split("_", 1)[0]
        if filename.endswith(".sql") and version <= last_version:
            with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as file:
                conn.executescript(file.read())
            conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)", (version, filename))
    conn.commit()
    return conn


def apply_039(conn):
    [filename] = [name for name in os.listdir(MIGRATIONS_DIR) if name.startswith("039_")]
    with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as file:
        conn.executescript(file.read())


SEED = """
    INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.c', 'x'), ('u2', 'd@e.f', 'x');
    INSERT INTO categories (id, user_id, name, kind) VALUES
        ('cat:u1:investimento', 'u1', 'Investimento', 'BOTH'),
        ('cat:u1:outros', 'u1', 'Outros', 'EXPENSE'),
        ('cat:u1:receita', 'u1', 'Receita', 'INCOME'),
        ('cat:u2:investimento', 'u2', 'Investimento', 'BOTH');
    INSERT INTO accounts (id, user_id, name, type, currency, initial_balance, is_default) VALUES
        ('banco', 'u1', 'Banco', 'CHECKING', 'BRL', 1000, 1),
        ('usd', 'u1', 'Conta USD', 'CHECKING', 'USD', 0, 0),
        ('btg', 'u1', 'BTG', 'BROKERAGE', 'BRL', 0, 0),
        ('nubank', 'u2', 'Nubank', 'CHECKING', 'BRL', 0, 1),
        ('corretora-velha', 'u2', 'Corretora', 'BROKERAGE', 'BRL', 0, 0);
    UPDATE accounts SET archived_at = '2026-01-01' WHERE id = 'corretora-velha';
    INSERT INTO transactions (id, user_id, account_id, amount, date, category, category_id, type, source_type, source_id, share_mode, share_person) VALUES
        ('aporte', 'u1', 'banco', 500, '2026-03-01', 'Investimento', 'cat:u1:investimento', 'EXPENSE', NULL, NULL, 'OTHERS', 'Ana'),
        ('resgate', 'u1', 'banco', 200, '2026-03-02', 'Investimento', NULL, 'INCOME', NULL, NULL, NULL, NULL),
        ('importado', 'u1', 'banco', 50, '2026-03-03', 'Investimento', 'cat:u1:investimento', 'EXPENSE', 'STATEMENT_IMPORT', 'h1', NULL, NULL),
        ('na-corretora', 'u1', 'btg', 70, '2026-03-04', 'Investimento', 'cat:u1:investimento', 'EXPENSE', NULL, NULL, NULL, NULL),
        ('em-dolar', 'u1', 'usd', 10, '2026-03-05', 'Investimento', 'cat:u1:investimento', 'EXPENSE', NULL, NULL, NULL, NULL),
        ('mercado', 'u1', 'banco', 30, '2026-03-06', 'Outros', 'cat:u1:outros', 'EXPENSE', NULL, NULL, NULL, NULL),
        ('cash:compra', 'u1', 'btg', 900, '2026-03-07', 'Investimento', 'cat:u1:investimento', 'EXPENSE', 'INVESTMENT_TRANSACTION', 'compra', NULL, NULL),
        ('cash:venda', 'u1', 'btg', 400, '2026-03-08', 'Investimento', NULL, 'INCOME', 'INVESTMENT_TRANSACTION', 'venda', NULL, NULL),
        ('proceed:p1', 'u1', 'btg', 12, '2026-03-09', 'Investimento', NULL, 'INCOME', 'INVESTMENT_PROCEED', 'p1', NULL, NULL),
        ('dele', 'u2', 'nubank', 80, '2026-03-01', 'Investimento', 'cat:u2:investimento', 'EXPENSE', NULL, NULL, NULL, NULL);
    INSERT INTO import_rules (id, user_id, pattern, category, category_id) VALUES
        ('regra-btg', 'u1', 'btg', 'Investimento', 'cat:u1:investimento'),
        ('regra-uber', 'u1', 'uber', 'Outros', 'cat:u1:outros');
    INSERT INTO inbox_items (id, user_id, state, direction, amount, occurred_at, source_occurred_at, category, category_id) VALUES
        ('pendente', 'u1', 'PENDING', 'OUT', 500, '2026-03-10', '2026-03-10', 'Investimento', 'cat:u1:investimento'),
        ('aprovado', 'u1', 'APPROVED', 'OUT', 500, '2026-03-01', '2026-03-01', 'Investimento', 'cat:u1:investimento');
"""


def balance(conn, account_id):
    row = conn.execute(
        """
        SELECT a.initial_balance
          + COALESCE(SUM(CASE
              WHEN t.type = 'INCOME' AND t.account_id = a.id THEN t.amount
              WHEN t.type = 'EXPENSE' AND t.account_id = a.id THEN -t.amount
              WHEN t.type = 'TRANSFER' AND t.account_id = a.id THEN -t.amount
              WHEN t.type = 'TRANSFER' AND t.transfer_account_id = a.id THEN t.amount
              ELSE 0 END), 0) AS balance
        FROM accounts a
        LEFT JOIN transactions t ON t.user_id = a.user_id
          AND (t.account_id = a.id OR t.transfer_account_id = a.id)
        WHERE a.id = ?
        """,
        (account_id,),
    ).fetchone()
    return row["balance"]


def migrated(tmp_path):
    conn = migrated_up_to(str(tmp_path / "old.db"), "038")
    conn.executescript(SEED)
    conn.commit()
    before = {account: balance(conn, account) for account in ("banco", "usd", "nubank")}
    apply_039(conn)
    rows = {row["id"]: row for row in conn.execute("SELECT * FROM transactions")}
    return conn, rows, before


def test_typed_aportes_become_transfers_with_the_portfolio_account(tmp_path):
    conn, rows, before = migrated(tmp_path)

    aporte = rows["aporte"]
    assert (aporte["type"], aporte["account_id"], aporte["transfer_account_id"]) == ("TRANSFER", "banco", "btg")
    assert (aporte["category"], aporte["category_id"]) == ("Transferencia", None)
    assert aporte["share_mode"] is None and aporte["share_person"] is None

    resgate = rows["resgate"]
    assert (resgate["type"], resgate["account_id"], resgate["transfer_account_id"]) == ("TRANSFER", "btg", "banco")
    # Importada tambem: o source_id fica, reimportar continua sem duplicar.
    assert rows["importado"]["type"] == "TRANSFER"
    assert rows["importado"]["source_id"] == "h1"

    # O saldo das contas do banco nao muda.
    assert balance(conn, "banco") == before["banco"]
    # O que ja estava na Corretora, ou fora do real, fica como estava.
    assert rows["na-corretora"]["type"] == "EXPENSE"
    assert rows["em-dolar"]["type"] == "EXPENSE"
    assert rows["mercado"]["type"] == "EXPENSE"
    conn.close()


def test_a_user_without_a_portfolio_account_gets_one(tmp_path):
    conn, rows, before = migrated(tmp_path)
    [created] = conn.execute(
        "SELECT * FROM accounts WHERE user_id = 'u2' AND archived_at IS NULL AND type = 'BROKERAGE'"
    ).fetchall()
    # "Corretora" ja e o nome da arquivada.
    assert created["name"] == "Corretora (carteira)"
    assert (created["currency"], created["initial_balance"], created["is_default"]) == ("BRL", 0, 0)
    assert rows["dele"]["type"] == "TRANSFER"
    assert rows["dele"]["transfer_account_id"] == created["id"]
    assert balance(conn, "nubank") == before["nubank"]
    # u1 ja tinha a dele: nenhuma conta nova.
    assert conn.execute("SELECT COUNT(*) FROM accounts WHERE user_id = 'u1'").fetchone()[0] == 3
    conn.close()


def test_portfolio_rows_are_labelled_not_categorized(tmp_path):
    conn, rows, _ = migrated(tmp_path)
    assert (rows["cash:compra"]["category"], rows["cash:compra"]["category_id"]) == ("Aporte", None)
    assert rows["cash:venda"]["category"] == "Resgate"
    assert rows["proceed:p1"]["category"] == "Provento"
    assert rows["cash:compra"]["type"] == "EXPENSE"
    conn.close()


def test_the_category_is_archived_and_what_pointed_to_it_moves_on(tmp_path):
    conn, _, _ = migrated(tmp_path)
    archived = {row["id"]: row["archived_at"] for row in conn.execute("SELECT id, archived_at FROM categories")}
    assert archived["cat:u1:investimento"] and archived["cat:u2:investimento"]
    assert archived["cat:u1:outros"] is None

    rules = {row["id"]: row["active"] for row in conn.execute("SELECT id, active FROM import_rules")}
    assert rules == {"regra-btg": 0, "regra-uber": 1}

    items = {row["id"]: row for row in conn.execute("SELECT * FROM inbox_items")}
    assert (items["pendente"]["category"], items["pendente"]["category_id"]) == ("Outros", "cat:u1:outros")
    assert items["aprovado"]["category"] == "Investimento"
    conn.close()


def test_new_users_are_not_seeded_with_it(client, auth):
    names = {item["name"] for item in client.get("/api/categories", headers=auth).get_json()}
    assert "Investimento" not in names
