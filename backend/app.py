"""Ponto de entrada: cria o app Flask, registra os blueprints e prepara o banco.

As rotas moram em routes/ (um blueprint por area) e as regras em services/.
O trabalho de boot (migrations, backup, limpeza de comprovantes orfaos) roda na
importacao — os testes dependem disso: conftest.py configura o ambiente e so
entao importa este modulo.
"""

import os

from flask import Flask, request

import tesouro_client
from services import open_finance_refresh, quote_refresh
from gzip_responses import compress_response
from applog import configure_logging
from db import init_db, run_startup_backup
from routes import (
    accounts as account_routes,
    allocation as allocation_routes,
    attachments as attachment_routes,
    auth as auth_routes,
    budgets as budget_routes,
    cards as card_routes,
    frontend as frontend_routes,
    goals as goal_routes,
    home as home_routes,
    imports as import_routes,
    inbox as inbox_routes,
    review as review_routes,
    investments as investment_routes,
    market as market_routes,
    monthly_plan as monthly_plan_routes,
    open_finance as open_finance_routes,
    proceeds as proceeds_routes,
    receivables as receivable_routes,
    recurring as recurring_routes,
    system as system_routes,
    transactions as transaction_routes,
)
from services.attachments import prune_orphan_attachment_files

app = Flask(__name__)
# Sem CORS: a tela e a API sao uma origem so (o build servido aqui, o Vite
# com proxy de /api em desenvolvimento, o APK nativo nao e um navegador).

for blueprint_module in (
    system_routes,
    auth_routes,
    budget_routes,
    recurring_routes,
    import_routes,
    card_routes,
    account_routes,
    transaction_routes,
    attachment_routes,
    investment_routes,
    proceeds_routes,
    market_routes,
    allocation_routes,
    goal_routes,
    monthly_plan_routes,
    inbox_routes,
    review_routes,
    open_finance_routes,
    receivable_routes,
    home_routes,
    frontend_routes,
):
    app.register_blueprint(blueprint_module.bp)

# JSON grande (Extrato, Cartoes) vai comprimido: gzip_responses.py.
app.after_request(lambda response: compress_response(request, response))


configure_logging()
init_db()
run_startup_backup()
prune_orphan_attachment_files()
# Precos do Tesouro Direto baixados no boot e conferidos de hora em hora.
tesouro_client.start_auto_refresh()
# Cotacoes da renda variavel de hora em hora (QUOTE_AUTO_REFRESH_SECONDS).
quote_refresh.start_auto_refresh()
# Open Finance puxado de tempos em tempos (OPEN_FINANCE_SYNC_SECONDS; sem credenciais, nada).
open_finance_refresh.start_auto_refresh()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
