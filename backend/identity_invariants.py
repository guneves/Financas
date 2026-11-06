"""Um movimento, uma linha: as invariantes I1/I2.

Puro: recebe uma conexao sqlite3 (qualquer uma, ate somente leitura) e um
user_id, e devolve as violacoes em texto. Nao importa `db` nem `services`, para
o script do servidor (scripts/check_identity.py) abrir o banco sem migrar, e o
teste (tests/identity_check.py) chamar no fim de cada cenario.

Uma violacao e:
1. um lancamento apontado por duas transacoes vivas da Pluggy da MESMA direcao
   (a transferencia tem uma por ponta; a linha do caixa da corretora e dela);
2. um lancamento apontado por duas notificacoes vivas do mesmo canal (app do
   banco, ou Samsung Wallet) e da mesma direcao (o repost do mesmo aviso, PAIRED
   com uma do mesmo app, e a mesma observacao);
3. um item com duas transacoes da Pluggy vivas como fonte (SOURCE) na mesma
   direcao.
"""

SAMSUNG_WALLET = "com.samsung.android.spay"
BROKER_PREFIX = "broker:"
IN_KINDS = ("PIX_IN", "TRANSFER_IN", "REFUND")

LIVE_PLUGGY = "o.role <> 'REMOVED' AND COALESCE(o.conflict, '') <> 'vanished'"


def _rows(conn, sql, params):
    return [tuple(row) for row in conn.execute(sql, params).fetchall()]


def violations(conn, user_id):
    found = []
    for table, target_id, direction, count in _rows(
        conn,
        f"""
        SELECT o.target_table, o.target_id, o.direction, COUNT(*) FROM open_finance_transactions o
        WHERE o.user_id = ? AND o.target_id IS NOT NULL AND o.target_id NOT LIKE '{BROKER_PREFIX}%'
          AND {LIVE_PLUGGY}
        GROUP BY o.target_table, o.target_id, o.direction HAVING COUNT(*) > 1
        """,
        (user_id,),
    ):
        found.append(f"I2 pluggy: {table} {target_id} tem {count} transacoes vivas da Pluggy ({direction})")

    in_kinds = ", ".join(f"'{kind}'" for kind in IN_KINDS)
    for table, target_id, channel, direction, count in _rows(
        conn,
        f"""
        SELECT d.target_table, d.target_id,
               CASE WHEN d.app = '{SAMSUNG_WALLET}' THEN 'wallet' ELSE 'bank' END AS channel,
               CASE WHEN d.kind IN ({in_kinds}) THEN 'IN' ELSE 'OUT' END AS direction,
               COUNT(*)
        FROM notify_detections d
        WHERE d.user_id = ? AND d.target_id IS NOT NULL AND d.role IN ('SOURCE', 'PAIRED', 'MATCHED')
          AND d.kind <> 'DECLINED'
          AND NOT EXISTS (
              SELECT 1 FROM notify_detections r
              WHERE r.user_id = d.user_id AND r.id = d.paired_with AND r.app = d.app
          )
        GROUP BY d.target_table, d.target_id, channel, direction HAVING COUNT(*) > 1
        """,
        (user_id,),
    ):
        found.append(f"I2 {channel}: {table} {target_id} tem {count} notificacoes vivas ({direction})")

    for item_id, direction, count in _rows(
        conn,
        f"""
        SELECT o.item_id, o.direction, COUNT(*) FROM open_finance_transactions o
        WHERE o.user_id = ? AND o.item_id IS NOT NULL AND o.role = 'SOURCE' AND {LIVE_PLUGGY}
        GROUP BY o.item_id, o.direction HAVING COUNT(*) > 1
        """,
        (user_id,),
    ):
        found.append(f"I1 item: {item_id} tem {count} fontes vivas da Pluggy ({direction})")
    return found
