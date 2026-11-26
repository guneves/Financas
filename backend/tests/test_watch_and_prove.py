"""Tudo automatico, Fase 3 (automation-prompt): vigiar e provar.

- `GET /api/review/auto` filtra por regra (`kinds`, `conference` = o que a
  Conferencia mostra em "Resolvido automaticamente") e por dias (`days`);
- uma linha por semana no log com quantas decisoes de cada regra
  (`auto_decisions.log_weekly()`, chamada pela thread da Pluggy);
- `scripts/review_breakdown.py` conta as decisoes pela data do lancamento
  decidido, nunca pela data em que o app decidiu (a reconstrucao de 2026-10-27
  regravou um ano de uma vez).
"""

import importlib
import logging
from datetime import date

from test_attachments import create_transaction
from test_review_breakdown import _run


def _decisions():
    return importlib.import_module("services.auto_decisions")


def _record(user_id, kind, table, target_id, detail=None, created_at=None, undone=False):
    db = importlib.import_module("db")
    decisions = _decisions()
    with db.get_db() as conn:
        decision_id = decisions.record(conn, user_id, kind, table, target_id, detail)
        if created_at:
            conn.execute("UPDATE auto_decisions SET created_at = ? WHERE id = ?", (created_at, decision_id))
        if undone:
            decisions.mark_undone(conn, user_id, decision_id)
    return decision_id


class TestTheFilters:
    def test_conference_lists_only_conflicts_and_the_portfolio(self, client, auth, user):
        row = create_transaction(client, auth)
        _record(user["id"], "auto_confirm", "transactions", row["id"])
        changed = _record(user["id"], "conflict_changed", "transactions", row["id"], {"before_cents": 100})
        custody = _record(user["id"], "investment_custody", "open_finance_investment_operations", "op-1",
                          {"code": "BBAS3"})
        body = client.get("/api/review/auto?kinds=conference", headers=auth).get_json()
        assert {item["id"] for item in body["items"]} == {changed, custody}
        assert body["counts"] == {"conflict_changed": 1, "investment_custody": 1}
        everything = client.get("/api/review/auto", headers=auth).get_json()
        assert len(everything["items"]) == 3

    def test_a_named_kind_and_an_unknown_one(self, client, auth, user):
        row = create_transaction(client, auth)
        _record(user["id"], "auto_confirm", "transactions", row["id"])
        _record(user["id"], "pluggy_category", "transactions", row["id"])
        body = client.get("/api/review/auto?kinds=pluggy_category", headers=auth).get_json()
        assert [item["kind"] for item in body["items"]] == ["pluggy_category"]
        refused = client.get("/api/review/auto?kinds=pluggy_category,inventada", headers=auth)
        assert refused.status_code == 400
        assert "inventada" in refused.get_json()["error"]

    def test_days_cuts_by_when_the_app_decided(self, client, auth, user):
        row = create_transaction(client, auth)
        _record(user["id"], "auto_confirm", "transactions", row["id"])
        _record(user["id"], "pluggy_category", "transactions", row["id"], created_at="2001-01-01T00:00:00Z")
        body = client.get("/api/review/auto?days=30", headers=auth).get_json()
        assert [item["kind"] for item in body["items"]] == ["auto_confirm"]
        assert body["counts"] == {"auto_confirm": 1}
        for bad in ("0", "366", "x"):
            assert client.get(f"/api/review/auto?days={bad}", headers=auth).status_code == 400

    def test_another_users_decisions_never_show(self, client, auth, user, other_user):
        _record(other_user["id"], "conflict_changed", "transactions", "outro")
        body = client.get("/api/review/auto?kinds=conference", headers=auth).get_json()
        assert body["items"] == [] and body["counts"] == {}


class TestTheWeeklyLine:
    def _log(self, user_id, today):
        db = importlib.import_module("db")
        with db.get_db() as conn:
            return _decisions().log_weekly(conn, user_id, today=today)

    def test_one_line_a_week_with_counts_per_kind(self, user, caplog):
        _record(user["id"], "auto_confirm", "transactions", "a", created_at="2030-01-08T10:00:00Z")
        _record(user["id"], "auto_confirm", "transactions", "b", created_at="2030-01-09T10:00:00Z")
        _record(user["id"], "conflict_changed", "transactions", "c", created_at="2030-01-09T11:00:00Z", undone=True)
        _record(user["id"], "pluggy_category", "transactions", "d", created_at="2029-12-01T10:00:00Z")
        with caplog.at_level(logging.INFO):
            report = self._log(user["id"], date(2030, 1, 10))
        assert report["since"] == "2030-01-03"
        assert report["total"] == 2 and report["undone"] == 1
        assert report["n_auto_confirm"] == 2
        assert report["n_pluggy_category"] == 0  # antes da semana
        assert report["n_conflict_changed"] == 0 and report["undone_conflict_changed"] == 1
        [line] = [record for record in caplog.records if record.getMessage() == "Decisoes automaticas da semana"]
        assert line.n_auto_confirm == 2 and line.user_id == user["id"]

    def test_not_again_inside_the_week(self, user):
        assert self._log(user["id"], date(2030, 1, 10)) is not None
        assert self._log(user["id"], date(2030, 1, 16)) is None
        assert self._log(user["id"], date(2030, 1, 17)) is not None

    def test_the_refresh_round_writes_it_for_every_user_with_pluggy(self, user, monkeypatch, caplog):
        refresh = importlib.import_module("services.open_finance_refresh")
        monkeypatch.setattr(refresh, "user_ids_with_items", lambda: [user["id"]])
        with caplog.at_level(logging.INFO):
            refresh.log_weekly_decisions()
            refresh.log_weekly_decisions()
        lines = [record for record in caplog.records if record.getMessage() == "Decisoes automaticas da semana"]
        assert len(lines) == 1

    def test_a_failing_user_does_not_stop_the_round(self, user, monkeypatch, caplog):
        refresh = importlib.import_module("services.open_finance_refresh")
        monkeypatch.setattr(refresh, "user_ids_with_items", lambda: ["quebrado", user["id"]])
        real = refresh.auto_decisions.log_weekly

        def flaky(conn, current_user_id, today=None):
            if current_user_id == "quebrado":
                raise RuntimeError("falhou")
            return real(conn, current_user_id, today)
        monkeypatch.setattr(refresh.auto_decisions, "log_weekly", flaky)
        with caplog.at_level(logging.INFO):
            refresh.log_weekly_decisions()
        messages = [record.getMessage() for record in caplog.records]
        assert "Decisoes automaticas da semana" in messages
        assert any("Resumo semanal das decisoes falhou" in message for message in messages)


class TestTheBreakdown:
    def test_decisions_count_by_the_rows_own_date(self, client, auth, user, tmp_path):
        recent = create_transaction(client, auth, date="2026-11-10")
        old = create_transaction(client, auth, date="2025-01-15")
        undone = create_transaction(client, auth, date="2026-11-12")
        # Todas decididas hoje; so a data do lancamento decide a janela.
        _record(user["id"], "auto_confirm", "transactions", recent["id"])
        _record(user["id"], "auto_confirm", "transactions", old["id"])
        _record(user["id"], "pluggy_category", "transactions", undone["id"], undone=True)
        # O conflito que apagou a linha guarda a data dela no detail.
        _record(user["id"], "conflict_vanished", "transactions", "apagada", {"row": {"date": "2026-11-15"}})
        _record(user["id"], "conflict_vanished", "transactions", "apagada-antiga", {"row": {"date": "2024-03-01"}})

        result = _run(user, tmp_path, "--days", "30")
        assert result.returncode == 0, result.stderr
        out = result.stdout
        assert "Decididos sozinhos (lancamentos desde 2026-10-18): 2, desfeitos pelo dono: 1" in out
        ficaram = out.split("ficaram, por regra:")[1].split("desfeitos, por regra:")[0]
        assert "    1  auto_confirm" in ficaram
        assert "    1  conflict_vanished" in ficaram
        assert "    1  pluggy_category" in out.split("desfeitos, por regra:")[1]
