"""Lancamentos recorrentes — secao 3.4 de docs/next-steps.md.

O que estes testes fixam:

- o molde vive em `recurring_transactions`, mas o dinheiro continua nascendo em
  `transactions` — materializado por POST /api/recurring/run;
- rodar duas vezes nao duplica nada (indice unico em source_type/source_id);
- mensal ancora no dia de `start_date`: dia 31 cai em 28/02 e VOLTA para 31/03,
  em vez de ficar preso no dia 28;
- `end_date` encerra a recorrencia (status FINISHED, next_run_date nulo) e
  `active = 0` a pausa;
- apagar o molde nao apaga os lancamentos ja gerados;
- a previsao nao grava nada e marca como `pending` o que ja venceu;
- nada de outro usuario aparece, nem pode ser lido, editado ou rodado.
"""

from datetime import datetime, timedelta

import pytest


def today_date():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def iso(date_value):
    return date_value.strftime("%Y-%m-%d")


def create_recurring(client, headers, **overrides):
    payload = {
        "amount": 1500,
        "type": "EXPENSE",
        "category": "Moradia",
        "description": "Aluguel",
        "frequency": "MONTHLY",
        "start_date": "2026-01-10",
    }
    payload.update(overrides)
    return client.post("/api/recurring", json=payload, headers=headers)


def create_ok(client, headers, **overrides):
    response = create_recurring(client, headers, **overrides)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def run(client, headers, **payload):
    response = client.post("/api/recurring/run", json=payload, headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def list_recurring(client, headers, **params):
    response = client.get("/api/recurring", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def get_recurring(client, headers, recurring_id):
    return next(
        item for item in list_recurring(client, headers)["items"] if item["id"] == recurring_id
    )


def transactions_of(client, headers):
    response = client.get("/api/transactions", headers=headers)
    assert response.status_code == 200
    return response.get_json()


def categories_of(client, headers):
    response = client.get("/api/categories", headers=headers)
    assert response.status_code == 200
    return {item["name"]: item for item in response.get_json()}


def pause_since(client, headers, db_module, recurring_id, paused_at):
    """Pausa e finge que a pausa comecou em `paused_at` (o relogio da rota e hoje).

    `paused_at=None` simula uma pausa anterior a migracao 019, que nao guardava o dia.
    """
    response = client.patch(
        f"/api/recurring/{recurring_id}", json={"active": False}, headers=headers
    )
    assert response.status_code == 200
    with db_module.get_db() as conn:
        conn.execute(
            "UPDATE recurring_transactions SET paused_at = ? WHERE id = ?",
            (iso(paused_at) if paused_at else None, recurring_id),
        )


def resume(client, headers, recurring_id, **extra):
    response = client.patch(
        f"/api/recurring/{recurring_id}", json={"active": True, **extra}, headers=headers
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


# --- criacao e validacao ----------------------------------------------------


def test_list_starts_empty(client, auth):
    body = list_recurring(client, auth)
    assert body["items"] == []
    assert body["pending_count"] == 0


def test_create_returns_the_template_with_next_run_on_the_start_date(client, auth):
    item = create_ok(client, auth)
    assert item["frequency"] == "MONTHLY"
    assert item["interval_count"] == 1
    assert item["next_run_date"] == "2026-01-10"
    assert item["status"] == "ACTIVE"
    assert item["active"] is True
    assert item["last_run_at"] is None


def test_create_links_the_category_by_name(client, auth):
    categories = categories_of(client, auth)
    item = create_ok(client, auth, category="Moradia")
    assert item["category"] == "Moradia"
    assert item["category_id"] == categories["Moradia"]["id"]


def test_create_accepts_a_category_id(client, auth):
    categories = categories_of(client, auth)
    item = create_ok(client, auth, category_id=categories["Lazer"]["id"], category=None)
    assert item["category"] == "Lazer"


def test_create_falls_back_to_the_default_account(client, auth):
    item = create_ok(client, auth)
    accounts = client.get("/api/accounts", headers=auth).get_json()
    assert item["account_id"] == accounts[0]["id"]


def test_create_rounds_the_amount_half_up(client, auth):
    item = create_ok(client, auth, amount=10.125)
    assert item["amount"] == 10.13


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 0},
        {"amount": -5},
        {"amount": "abc"},
        {"type": "TRANSFER"},
        {"type": "OUTRO"},
        {"frequency": "DAILY"},
        {"start_date": "10/01/2026"},
        {"interval_count": 0},
        {"interval_count": 1.5},
        {"category": ""},
    ],
)
def test_create_rejects_invalid_payloads(client, auth, payload):
    response = create_recurring(client, auth, **payload)
    assert response.status_code == 400, response.get_data(as_text=True)


def test_create_rejects_an_end_date_before_the_start(client, auth):
    response = create_recurring(client, auth, start_date="2026-03-01", end_date="2026-02-01")
    assert response.status_code == 400


def test_create_rejects_an_unknown_category_id(client, auth):
    response = create_recurring(client, auth, category_id="nao-existe")
    assert response.status_code == 400


def test_create_rejects_an_archived_category(client, auth):
    categories = categories_of(client, auth)
    assert client.delete(
        f"/api/categories/{categories['Lazer']['id']}", headers=auth
    ).status_code == 200
    response = create_recurring(client, auth, category_id=categories["Lazer"]["id"])
    assert response.status_code == 400


# --- materializacao ---------------------------------------------------------


def test_run_materializes_every_due_occurrence(client, auth):
    create_ok(client, auth, start_date="2026-01-10")
    result = run(client, auth, through="2026-04-15")
    assert result["created"] == 4
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-01-10", "2026-02-10", "2026-03-10", "2026-04-10"]


def test_generated_transactions_are_real_lancamentos(client, auth):
    create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    items = [item for item in transactions_of(client, auth) if item["date"] == "2026-01-10"]
    assert len(items) == 1
    assert items[0]["amount"] == 1500
    assert items[0]["type"] == "EXPENSE"
    assert items[0]["category"] == "Moradia"
    assert items[0]["description"] == "Aluguel"
    assert items[0]["source_type"] == "RECURRING_TRANSACTION"


def test_running_twice_creates_nothing_new(client, auth):
    create_ok(client, auth, start_date="2026-01-10")
    first = run(client, auth, through="2026-03-31")
    second = run(client, auth, through="2026-03-31")
    assert first["created"] == 3
    assert second["created"] == 0
    assert second["already_existed"] == 0
    assert len(transactions_of(client, auth)) == 3


def test_run_resumes_from_where_it_stopped(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-02-28")
    assert get_recurring(client, auth, recurring["id"])["next_run_date"] == "2026-03-10"
    second = run(client, auth, through="2026-04-30")
    assert second["created"] == 2
    assert get_recurring(client, auth, recurring["id"])["next_run_date"] == "2026-05-10"


def test_run_defaults_to_today(client, auth):
    start = today_date() - timedelta(days=40)
    create_ok(client, auth, start_date=iso(start), frequency="WEEKLY")
    result = run(client, auth)
    assert result["through"] == iso(today_date())
    assert result["created"] == 6
    assert all(item["date"] <= iso(today_date()) for item in result["transactions"])


def test_run_does_nothing_before_the_start_date(client, auth):
    create_ok(client, auth, start_date="2099-01-10")
    assert run(client, auth)["created"] == 0
    assert transactions_of(client, auth) == []


def test_run_can_target_a_single_recurrence(client, auth):
    rent = create_ok(client, auth, start_date="2026-01-10", description="Aluguel")
    create_ok(client, auth, start_date="2026-01-05", description="Internet")
    result = run(client, auth, through="2026-02-28", id=rent["id"])
    assert result["created"] == 2
    assert {item["description"] for item in result["transactions"]} == {"Aluguel"}


def test_run_with_an_unknown_id_is_a_404(client, auth):
    response = client.post("/api/recurring/run", json={"id": "nao-existe"}, headers=auth)
    assert response.status_code == 404


def test_run_rejects_an_invalid_through(client, auth):
    response = client.post("/api/recurring/run", json={"through": "31/12/2026"}, headers=auth)
    assert response.status_code == 400


def test_a_paused_recurrence_is_not_materialized(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    assert client.patch(
        f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth
    ).status_code == 200
    assert run(client, auth, through="2026-06-30")["created"] == 0
    assert get_recurring(client, auth, recurring["id"])["status"] == "PAUSED"


def test_a_paused_recurrence_is_not_run_even_when_named(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    assert run(client, auth, through="2026-06-30", id=recurring["id"])["created"] == 0


def test_resuming_skips_the_paused_period(client, auth, db_module):
    """Retomar nao pode cobrar a pausa.

    A assinatura ficou cancelada nesses meses: o dinheiro nao saiu, e
    materializar o periodo criaria despesas que nunca existiram — que o
    orcamento e o saldo por conta contariam como reais.
    """
    start = today_date() - timedelta(days=180)
    recurring = create_ok(client, auth, amount=50, start_date=iso(start))
    run(client, auth, through=iso(today_date() - timedelta(days=150)))
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=150))

    resumed = resume(client, auth, recurring["id"])
    assert resumed["next_run_date"] >= iso(today_date())
    assert resumed["paused_at"] is None

    created_before = len(transactions_of(client, auth))
    assert run(client, auth)["created"] == 0
    assert len(transactions_of(client, auth)) == created_before


def test_resuming_does_not_move_a_next_date_still_in_the_future(client, auth):
    future = iso(today_date() + timedelta(days=20))
    recurring = create_ok(client, auth, start_date=future)
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    resumed = client.patch(
        f"/api/recurring/{recurring['id']}", json={"active": True}, headers=auth
    ).get_json()
    assert resumed["next_run_date"] == future


def test_resuming_honours_an_explicit_next_run_date(client, auth):
    recurring = create_ok(client, auth, start_date=iso(today_date() - timedelta(days=90)))
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    resumed = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"active": True, "next_run_date": "2026-01-10"},
        headers=auth,
    ).get_json()
    assert resumed["next_run_date"] == "2026-01-10"


def test_resuming_after_the_end_date_finishes_the_recurrence(client, auth, db_module):
    recurring = create_ok(
        client,
        auth,
        start_date=iso(today_date() - timedelta(days=90)),
        end_date=iso(today_date() - timedelta(days=30)),
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=91))
    resumed = resume(client, auth, recurring["id"])
    assert resumed["next_run_date"] is None
    assert resumed["status"] == "FINISHED"


def test_resuming_and_extending_in_the_same_save_uses_the_new_end_date(client, auth, db_module):
    """Reativar e prorrogar no mesmo salvamento e o caso comum.

    Avaliar a retomada contra o end_date antigo encerraria justamente a
    recorrencia que o usuario acabou de estender.
    """
    recurring = create_ok(
        client,
        auth,
        start_date=iso(today_date() - timedelta(days=90)),
        end_date=iso(today_date() - timedelta(days=30)),
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=91))
    resumed = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"active": True, "end_date": iso(today_date() + timedelta(days=365))},
        headers=auth,
    ).get_json()
    assert resumed["status"] == "ACTIVE"
    assert resumed["next_run_date"] >= iso(today_date())


def test_resuming_with_a_new_frequency_uses_the_new_frequency(client, auth, db_module):
    recurring = create_ok(
        client, auth, start_date=iso(today_date() - timedelta(days=200)), frequency="MONTHLY"
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=201))
    resumed = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"active": True, "frequency": "WEEKLY"},
        headers=auth,
    ).get_json()
    assert resumed["frequency"] == "WEEKLY"
    assert resumed["next_run_date"] >= iso(today_date())
    assert resumed["next_run_date"] < iso(today_date() + timedelta(days=8))


def test_shrinking_the_end_date_past_the_next_occurrence_finishes_it(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    updated = client.patch(
        f"/api/recurring/{recurring['id']}", json={"end_date": "2026-01-31"}, headers=auth
    ).get_json()
    assert updated["next_run_date"] is None
    assert updated["status"] == "FINISHED"
    assert run(client, auth, through="2026-12-31")["created"] == 0


def finished_weekly(client, auth, db_module=None):
    """Semanal de -70 a -40 dias: gera -70, -63, -56, -49 e -42, e encerra.

    Com `db_module`, encerra sem gerar nada: pausada antes de 019 (sem
    paused_at) e retomada hoje, a retomada anda ate hoje e passa do fim.
    """
    recurring = create_ok(
        client,
        auth,
        frequency="WEEKLY",
        start_date=iso(today_date() - timedelta(days=70)),
        end_date=iso(today_date() - timedelta(days=40)),
    )
    if db_module is None:
        assert run(client, auth)["created"] == 5
    else:
        pause_since(client, auth, db_module, recurring["id"], None)
        resume(client, auth, recurring["id"])
    assert get_recurring(client, auth, recurring["id"])["status"] == "FINISHED"
    return recurring


def test_extending_the_end_date_revives_a_finished_recurrence(client, auth):
    """Prorrogar diz que o contrato continuou: o intervalo desde o fim fica pendente."""
    recurring = finished_weekly(client, auth)
    revived = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"end_date": iso(today_date() + timedelta(days=365))},
        headers=auth,
    ).get_json()
    assert revived["status"] == "ACTIVE"
    assert revived["next_run_date"] == iso(today_date() - timedelta(days=35))
    # -35, -28, -21, -14, -7 e hoje.
    assert revived["pending_count"] == 6
    assert run(client, auth)["created"] == 6
    assert get_recurring(client, auth, recurring["id"])["pending_count"] == 0


def test_clearing_the_end_date_revives_a_finished_recurrence(client, auth):
    recurring = finished_weekly(client, auth)
    revived = client.patch(
        f"/api/recurring/{recurring['id']}", json={"end_date": None}, headers=auth
    ).get_json()
    assert revived["status"] == "ACTIVE"
    assert revived["end_date"] is None
    assert revived["next_run_date"] == iso(today_date() - timedelta(days=35))
    assert revived["pending_count"] == 6


def test_extending_to_before_the_next_occurrence_stays_finished(client, auth):
    recurring = finished_weekly(client, auth)
    updated = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"end_date": iso(today_date() - timedelta(days=37))},
        headers=auth,
    ).get_json()
    assert updated["status"] == "FINISHED"
    assert updated["next_run_date"] is None
    assert updated["pending_count"] == 0


def test_a_finished_recurrence_that_never_ran_revives_from_the_start(client, auth, db_module):
    recurring = finished_weekly(client, auth, db_module)
    revived = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"end_date": iso(today_date() + timedelta(days=365))},
        headers=auth,
    ).get_json()
    assert revived["status"] == "ACTIVE"
    assert revived["next_run_date"] == recurring["start_date"]
    # -70 a hoje, de 7 em 7.
    assert revived["pending_count"] == 11


def test_extending_and_resuming_in_one_save_still_skips_the_pause(client, auth, db_module):
    """Reativar no mesmo salvamento aplica a retomada sobre a data revivida."""
    recurring = finished_weekly(client, auth)
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=38))
    revived = resume(
        client, auth, recurring["id"], end_date=iso(today_date() + timedelta(days=365))
    )
    assert revived["status"] == "ACTIVE"
    # -35 a -7 caem na pausa (-38 a hoje); hoje ja vale.
    assert revived["next_run_date"] == iso(today_date())
    assert revived["pending_count"] == 1


def test_reviving_does_not_bring_back_a_deleted_last_occurrence(client, auth):
    """O cursor guardado (019), e nao o ultimo lancamento que ainda existe.

    Antes, apagar o lancamento de -42 e prorrogar reconstruia o cursor a partir
    de -49 e gerava -42 de novo — o lancamento que o usuario acabou de apagar.
    """
    recurring = finished_weekly(client, auth)
    last = max(transactions_of(client, auth), key=lambda item: item["date"])
    assert last["date"] == iso(today_date() - timedelta(days=42))
    assert client.delete(f"/api/transactions/{last['id']}", headers=auth).status_code == 200

    revived = client.patch(
        f"/api/recurring/{recurring['id']}", json={"end_date": None}, headers=auth
    ).get_json()
    assert revived["next_run_date"] == iso(today_date() - timedelta(days=35))
    assert revived["last_occurrence_date"] == iso(today_date() - timedelta(days=42))
    assert revived["pending_count"] == 6
    created = run(client, auth)["transactions"]
    assert iso(today_date() - timedelta(days=42)) not in {item["date"] for item in created}


def test_run_records_the_last_occurrence_and_never_moves_it_back(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-03-31")
    assert get_recurring(client, auth, recurring["id"])["last_occurrence_date"] == "2026-03-10"

    client.patch(
        f"/api/recurring/{recurring['id']}", json={"next_run_date": "2026-01-10"}, headers=auth
    )
    run(client, auth, through="2026-01-31")
    assert get_recurring(client, auth, recurring["id"])["last_occurrence_date"] == "2026-03-10"


def test_an_explicit_next_date_after_the_end_date_is_refused(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10", end_date="2026-06-30")
    response = client.patch(
        f"/api/recurring/{recurring['id']}", json={"next_run_date": "2026-08-10"}, headers=auth
    )
    assert response.status_code == 400


def test_pausing_records_the_day_and_resuming_clears_it(client, auth):
    recurring = create_ok(client, auth, start_date=iso(today_date() - timedelta(days=5)))
    paused = client.patch(
        f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth
    ).get_json()
    assert paused["paused_at"] == iso(today_date())

    # Pausar de novo nao move o dia da pausa.
    again = client.patch(
        f"/api/recurring/{recurring['id']}", json={"active": False, "note": "x"}, headers=auth
    ).get_json()
    assert again["paused_at"] == iso(today_date())

    resumed = resume(client, auth, recurring["id"])
    assert resumed["paused_at"] is None
    assert resumed["pause_gaps"] == []


def test_an_occurrence_due_before_the_pause_survives_it(client, auth, db_module):
    """Decisao 2: pular so a janela da pausa, nao tudo ate hoje.

    Semanal de -10: -10 venceu antes da pausa (-8) e nao foi lancada — o
    dinheiro saiu, entao continua pendente. -3 caiu dentro da pausa e nao e
    devida. +4 e a seguinte.
    """
    recurring = create_ok(
        client, auth, frequency="WEEKLY", start_date=iso(today_date() - timedelta(days=10))
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=8))
    resumed = resume(client, auth, recurring["id"])

    assert resumed["next_run_date"] == iso(today_date() - timedelta(days=10))
    assert resumed["pending_count"] == 1
    assert resumed["pause_gaps"] == [[iso(today_date() - timedelta(days=8)), iso(today_date())]]

    result = run(client, auth)
    assert [item["date"] for item in result["transactions"]] == [
        iso(today_date() - timedelta(days=10))
    ]
    after = get_recurring(client, auth, recurring["id"])
    assert after["next_run_date"] == iso(today_date() + timedelta(days=4))

    # Depois que o /run passa da janela, ela sai da linha.
    run(client, auth, through=iso(today_date() + timedelta(days=4)))
    assert get_recurring(client, auth, recurring["id"])["pause_gaps"] == []


def test_pausing_and_resuming_the_same_day_skips_nothing(client, auth):
    recurring = create_ok(client, auth, start_date=iso(today_date() - timedelta(days=5)))
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    resumed = resume(client, auth, recurring["id"])
    assert resumed["pending_count"] == 1
    assert run(client, auth)["created"] == 1


def test_the_pause_day_and_the_resume_day_are_both_due(client, auth, db_module):
    """A janela e exclusiva nas duas pontas: o que vence no dia da pausa ja
    tinha vencido quando o usuario pausou, e o dia da retomada ja e ativo."""
    recurring = create_ok(
        client, auth, frequency="WEEKLY", start_date=iso(today_date() - timedelta(days=14))
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=14))
    resumed = resume(client, auth, recurring["id"])
    # -14 (dia da pausa) e hoje; -7 cai na pausa.
    assert resumed["pending_count"] == 2
    dates = [item["date"] for item in run(client, auth)["transactions"]]
    assert dates == [iso(today_date() - timedelta(days=14)), iso(today_date())]


def test_a_second_pause_keeps_the_first_window(client, auth, db_module):
    """Duas pausas antes de rodar: as duas janelas valem, o intervalo ativo entre elas nao."""
    recurring = create_ok(
        client, auth, frequency="WEEKLY", start_date=iso(today_date() - timedelta(days=35))
    )
    # Datas: -35, -28, -21, -14, -7, hoje.
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=30))
    with db_module.get_db() as conn:
        # Primeira pausa retomada em -20 (o relogio da rota e hoje, entao a
        # janela e escrita direto).
        conn.execute(
            "UPDATE recurring_transactions SET active = 1, paused_at = NULL, pause_gaps = ? "
            "WHERE id = ?",
            (
                f'[["{iso(today_date() - timedelta(days=30))}", '
                f'"{iso(today_date() - timedelta(days=20))}"]]',
                recurring["id"],
            ),
        )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=10))
    resume(client, auth, recurring["id"])

    dates = [item["date"] for item in run(client, auth)["transactions"]]
    assert dates == [
        iso(today_date() - timedelta(days=35)),
        iso(today_date() - timedelta(days=14)),
        iso(today_date()),
    ]


def test_an_explicit_next_date_drops_the_pause_windows(client, auth, db_module):
    recurring = create_ok(
        client, auth, frequency="WEEKLY", start_date=iso(today_date() - timedelta(days=10))
    )
    pause_since(client, auth, db_module, recurring["id"], today_date() - timedelta(days=8))
    resume(client, auth, recurring["id"])
    rewound = client.patch(
        f"/api/recurring/{recurring['id']}",
        json={"next_run_date": iso(today_date() - timedelta(days=10))},
        headers=auth,
    ).get_json()
    assert rewound["pause_gaps"] == []
    assert rewound["pending_count"] == 2


def test_a_pause_from_before_the_migration_still_skips_until_today(client, auth, db_module):
    """Sem paused_at (pausada antes de 019) nao ha como saber quando a pausa
    comecou: a retomada anda ate hoje, como antes, e a ocorrencia vencida se perde."""
    recurring = create_ok(client, auth, start_date=iso(today_date() - timedelta(days=5)))
    pause_since(client, auth, db_module, recurring["id"], None)
    resume(client, auth, recurring["id"])
    assert list_recurring(client, auth)["pending_count"] == 0
    assert run(client, auth)["created"] == 0


def test_rerunning_an_already_materialized_date_is_ignored(client, auth):
    """A rede de seguranca real da idempotencia: o indice unico em source_id.

    O teste acima ("rodar duas vezes") passa porque next_run_date ja andou.
    Aqui a recorrencia e rebobinada de proposito, que e o que aconteceria com
    duas chamadas de /run simultaneas.
    """
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-03-31")
    client.patch(
        f"/api/recurring/{recurring['id']}", json={"next_run_date": "2026-01-10"}, headers=auth
    )
    again = run(client, auth, through="2026-03-31")
    assert again["created"] == 0
    assert again["already_existed"] == 3
    assert len(transactions_of(client, auth)) == 3


def test_the_generated_transaction_can_be_edited(client, auth):
    create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    item = transactions_of(client, auth)[0]
    response = client.patch(
        f"/api/transactions/{item['id']}", json={"amount": 1600}, headers=auth
    )
    assert response.status_code == 200
    assert response.get_json()["amount"] == 1600


def test_the_generated_transaction_can_be_deleted_and_is_not_recreated(client, auth):
    create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    item = transactions_of(client, auth)[0]
    assert client.delete(f"/api/transactions/{item['id']}", headers=auth).status_code == 200
    assert run(client, auth, through="2026-01-31")["created"] == 0
    assert transactions_of(client, auth) == []


def test_generated_expenses_count_against_the_budget(client, auth):
    categories = categories_of(client, auth)
    assert client.post(
        "/api/budgets",
        json={
            "category_id": categories["Moradia"]["id"],
            "month": "2026-01",
            "planned_amount": 2000,
        },
        headers=auth,
    ).status_code == 201
    create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")

    month = client.get(
        "/api/budgets", headers=auth, query_string={"month": "2026-01"}
    ).get_json()
    moradia = next(item for item in month["items"] if item["category_name"] == "Moradia")
    assert moradia["spent"] == 1500
    assert moradia["remaining"] == 500


# --- calendario da recorrencia ----------------------------------------------


def test_monthly_keeps_the_anchor_day_after_a_short_month(client, auth):
    create_ok(client, auth, start_date="2026-01-31")
    result = run(client, auth, through="2026-04-30")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_monthly_anchor_survives_february_in_a_leap_year(client, auth):
    create_ok(client, auth, start_date="2028-01-30")
    result = run(client, auth, through="2028-03-31")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2028-01-30", "2028-02-29", "2028-03-30"]


def test_weekly_walks_seven_days_at_a_time(client, auth):
    create_ok(client, auth, start_date="2026-01-01", frequency="WEEKLY")
    result = run(client, auth, through="2026-01-29")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-01-01", "2026-01-08", "2026-01-15", "2026-01-22", "2026-01-29"]


def test_yearly_lands_on_the_same_day_next_year(client, auth):
    create_ok(client, auth, start_date="2026-03-15", frequency="YEARLY")
    result = run(client, auth, through="2028-12-31")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-03-15", "2027-03-15", "2028-03-15"]


def test_interval_count_skips_months(client, auth):
    create_ok(client, auth, start_date="2026-01-10", interval_count=3)
    result = run(client, auth, through="2026-12-31")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-01-10", "2026-04-10", "2026-07-10", "2026-10-10"]


def test_the_month_rolls_over_the_year(client, auth):
    create_ok(client, auth, start_date="2026-11-20")
    result = run(client, auth, through="2027-02-28")
    dates = sorted(item["date"] for item in result["transactions"])
    assert dates == ["2026-11-20", "2026-12-20", "2027-01-20", "2027-02-20"]


def test_end_date_finishes_the_recurrence(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10", end_date="2026-03-31")
    result = run(client, auth, through="2026-12-31")
    assert result["created"] == 3
    after = get_recurring(client, auth, recurring["id"])
    assert after["next_run_date"] is None
    assert after["status"] == "FINISHED"
    assert run(client, auth, through="2027-12-31")["created"] == 0


def test_end_date_on_an_occurrence_day_includes_that_occurrence(client, auth):
    create_ok(client, auth, start_date="2026-01-10", end_date="2026-03-10")
    assert run(client, auth, through="2026-12-31")["created"] == 3


# --- edicao e exclusao ------------------------------------------------------


def test_patch_updates_the_amount_and_keeps_the_schedule(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    response = client.patch(
        f"/api/recurring/{recurring['id']}", json={"amount": 1700}, headers=auth
    )
    assert response.status_code == 200
    assert response.get_json()["amount"] == 1700
    assert response.get_json()["next_run_date"] == "2026-02-10"


def test_patch_only_changes_the_fields_it_receives(client, auth):
    recurring = create_ok(client, auth, description="Aluguel", note="contrato 2026")
    updated = client.patch(
        f"/api/recurring/{recurring['id']}", json={"description": "Aluguel novo"}, headers=auth
    ).get_json()
    assert updated["description"] == "Aluguel novo"
    assert updated["note"] == "contrato 2026"
    assert updated["amount"] == 1500


def test_moving_the_start_date_before_the_first_run_moves_the_next_occurrence(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    updated = client.patch(
        f"/api/recurring/{recurring['id']}", json={"start_date": "2026-02-05"}, headers=auth
    ).get_json()
    assert updated["next_run_date"] == "2026-02-05"


def test_moving_the_start_date_after_a_run_does_not_rewind_the_recurrence(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    updated = client.patch(
        f"/api/recurring/{recurring['id']}", json={"start_date": "2026-01-20"}, headers=auth
    ).get_json()
    assert updated["next_run_date"] == "2026-02-10"
    assert run(client, auth, through="2026-02-28")["created"] == 1


def test_next_run_date_can_be_set_explicitly(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-01-31")
    updated = client.patch(
        f"/api/recurring/{recurring['id']}", json={"next_run_date": "2026-05-10"}, headers=auth
    ).get_json()
    assert updated["next_run_date"] == "2026-05-10"
    assert run(client, auth, through="2026-05-31")["created"] == 1


def test_patch_rejects_an_empty_payload(client, auth):
    recurring = create_ok(client, auth)
    response = client.patch(f"/api/recurring/{recurring['id']}", json={}, headers=auth)
    assert response.status_code == 400


def test_patch_rejects_an_end_date_before_the_start(client, auth):
    recurring = create_ok(client, auth, start_date="2026-03-01")
    response = client.patch(
        f"/api/recurring/{recurring['id']}", json={"end_date": "2026-01-01"}, headers=auth
    )
    assert response.status_code == 400


def test_patch_on_an_unknown_recurrence_is_a_404(client, auth):
    assert client.patch("/api/recurring/nao-existe", json={"amount": 1}, headers=auth).status_code == 404


def test_delete_removes_the_template_and_keeps_the_transactions(client, auth):
    recurring = create_ok(client, auth, start_date="2026-01-10")
    run(client, auth, through="2026-03-31")
    response = client.delete(f"/api/recurring/{recurring['id']}", headers=auth)
    assert response.status_code == 200
    assert response.get_json() == {"deleted": True, "kept_transactions": 3}
    assert list_recurring(client, auth)["items"] == []
    assert len(transactions_of(client, auth)) == 3


def test_delete_on_an_unknown_recurrence_is_a_404(client, auth):
    assert client.delete("/api/recurring/nao-existe", headers=auth).status_code == 404


def test_include_inactive_false_hides_paused_recurrences(client, auth):
    recurring = create_ok(client, auth)
    create_ok(client, auth, description="Internet")
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    body = list_recurring(client, auth, include_inactive="0")
    assert [item["description"] for item in body["items"]] == ["Internet"]


def test_pending_count_reports_what_run_would_create(client, auth):
    start = today_date() - timedelta(days=70)
    create_ok(client, auth, start_date=iso(start))
    body = list_recurring(client, auth)
    assert body["pending_count"] == body["items"][0]["pending_count"] == 3
    run(client, auth)
    assert list_recurring(client, auth)["pending_count"] == 0


def test_a_finished_recurrence_has_nothing_pending(client, auth):
    """Encerrada (next_run_date nulo) nao pode recontar o historico como vencido."""
    start = today_date() - timedelta(days=200)
    create_ok(client, auth, start_date=iso(start), end_date=iso(start + timedelta(days=100)))
    run(client, auth)
    body = list_recurring(client, auth)
    assert body["items"][0]["status"] == "FINISHED"
    assert body["pending_count"] == body["items"][0]["pending_count"] == 0

    forecast = client.get("/api/recurring/forecast?days=90", headers=auth).get_json()
    assert forecast["occurrences"] == []
    assert forecast["pending_count"] == 0


# --- previsao de caixa ------------------------------------------------------


def test_forecast_projects_without_writing_anything(client, auth):
    create_ok(client, auth, start_date=iso(today_date() + timedelta(days=5)))
    body = client.get(
        "/api/recurring/forecast", headers=auth, query_string={"days": 90}
    ).get_json()
    assert body["days"] == 90
    assert len(body["occurrences"]) == 3
    assert transactions_of(client, auth) == []


def test_forecast_totals_income_against_expense(client, auth):
    create_ok(
        client,
        auth,
        amount=5000,
        type="INCOME",
        category="Receita",
        description="Salario",
        start_date=iso(today_date() + timedelta(days=2)),
    )
    create_ok(client, auth, amount=1500, start_date=iso(today_date() + timedelta(days=3)))
    body = client.get(
        "/api/recurring/forecast", headers=auth, query_string={"days": 30}
    ).get_json()
    assert body["totals"] == {"income": 5000, "expense": 1500, "net": 3500}
    assert body["windows"]["30"]["net"] == 3500


def test_forecast_windows_grow_with_the_horizon(client, auth):
    create_ok(client, auth, amount=100, start_date=iso(today_date() + timedelta(days=1)))
    body = client.get(
        "/api/recurring/forecast", headers=auth, query_string={"days": 90}
    ).get_json()
    assert body["windows"]["30"]["expense"] == 100
    assert body["windows"]["60"]["expense"] == 200
    assert body["windows"]["90"]["expense"] == 300


def test_forecast_marks_overdue_occurrences_as_pending(client, auth):
    create_ok(client, auth, start_date=iso(today_date() - timedelta(days=40)))
    body = client.get("/api/recurring/forecast", headers=auth).get_json()
    assert body["pending_count"] == 2
    assert body["occurrences"][0]["pending"] is True


def test_forecast_ignores_paused_recurrences(client, auth):
    recurring = create_ok(client, auth, start_date=iso(today_date() + timedelta(days=1)))
    client.patch(f"/api/recurring/{recurring['id']}", json={"active": False}, headers=auth)
    body = client.get("/api/recurring/forecast", headers=auth).get_json()
    assert body["occurrences"] == []
    assert body["totals"] == {"income": 0, "expense": 0, "net": 0}


def test_forecast_rejects_a_non_numeric_horizon(client, auth):
    response = client.get("/api/recurring/forecast", headers=auth, query_string={"days": "abc"})
    assert response.status_code == 400


# --- isolamento por usuario -------------------------------------------------


def test_recurrences_of_another_user_do_not_appear(client, auth, other_user):
    create_ok(client, auth, description="Aluguel")
    create_ok(client, other_user["headers"], description="Aluguel do outro")
    items = list_recurring(client, auth)["items"]
    assert [item["description"] for item in items] == ["Aluguel"]


def test_cannot_patch_a_recurrence_of_another_user(client, auth, other_user):
    theirs = create_ok(client, other_user["headers"])
    response = client.patch(f"/api/recurring/{theirs['id']}", json={"amount": 1}, headers=auth)
    assert response.status_code == 404


def test_cannot_delete_a_recurrence_of_another_user(client, auth, other_user):
    theirs = create_ok(client, other_user["headers"])
    assert client.delete(f"/api/recurring/{theirs['id']}", headers=auth).status_code == 404
    assert len(list_recurring(client, other_user["headers"])["items"]) == 1


def test_running_does_not_materialize_another_users_recurrence(client, auth, other_user):
    create_ok(client, other_user["headers"], start_date="2026-01-10")
    assert run(client, auth, through="2026-12-31")["created"] == 0
    assert transactions_of(client, other_user["headers"]) == []


def test_cannot_run_a_recurrence_of_another_user_by_id(client, auth, other_user):
    theirs = create_ok(client, other_user["headers"], start_date="2026-01-10")
    response = client.post("/api/recurring/run", json={"id": theirs["id"]}, headers=auth)
    assert response.status_code == 404


def test_forecast_of_another_user_is_not_visible(client, auth, other_user):
    create_ok(client, other_user["headers"], start_date=iso(today_date() + timedelta(days=1)))
    body = client.get("/api/recurring/forecast", headers=auth).get_json()
    assert body["occurrences"] == []


def test_recurring_endpoints_require_authentication(client):
    assert client.get("/api/recurring").status_code == 401
    assert client.post("/api/recurring", json={}).status_code == 401
    assert client.post("/api/recurring/run", json={}).status_code == 401
    assert client.get("/api/recurring/forecast").status_code == 401


def test_a_recurrence_in_an_archived_account_does_not_post(client, auth):
    """Revisao de 2026-10-18: lancava numa conta que saiu das telas."""
    account = client.post("/api/accounts", json={"name": "Velha", "type": "CHECKING"}, headers=auth).get_json()
    item = create_ok(client, auth, account_id=account["id"], start_date=iso(today_date()))
    assert client.delete(f"/api/accounts/{account['id']}", headers=auth).status_code == 200

    result = run(client, auth)
    assert result["created"] == 0
    assert [blocked["id"] for blocked in result["blocked"]] == [item["id"]]
    assert result["blocked"][0]["account_name"] == "Velha"
    assert transactions_of(client, auth) == []

    # Trocada a conta, a ocorrencia que esperava e lancada.
    principal = next(a for a in client.get("/api/accounts", headers=auth).get_json() if a["is_default"])
    client.patch(f"/api/recurring/{item['id']}", json={"account_id": principal["id"]}, headers=auth)
    result = run(client, auth)
    assert result["created"] == 1
    assert result["blocked"] == []
    assert transactions_of(client, auth)[0]["account_id"] == principal["id"]
