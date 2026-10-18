"""Ponto de entrada: cria o app Flask, registra os blueprints e prepara o banco.

As rotas moram em routes/ (um blueprint por area) e as regras em services/.
O trabalho de boot (migrations, backup, limpeza de comprovantes orfaos) roda na
importacao — os testes dependem disso: conftest.py configura o ambiente e so
entao importa este modulo.
"""

import os

from flask import Flask
from flask_cors import CORS

from applog import configure_logging
from config import CORS_ORIGINS
from db import init_db, run_startup_backup
from routes import (
    accounts as account_routes,
    app_bundle as app_bundle_routes,
    allocation as allocation_routes,
    attachments as attachment_routes,
    auth as auth_routes,
    budgets as budget_routes,
    cards as card_routes,
    frontend as frontend_routes,
    goals as goal_routes,
    imports as import_routes,
    inbox as inbox_routes,
    investments as investment_routes,
    market as market_routes,
    monthly_plan as monthly_plan_routes,
    proceeds as proceeds_routes,
    recurring as recurring_routes,
    system as system_routes,
    transactions as transaction_routes,
)
from services.attachments import prune_orphan_attachment_files

app = Flask(__name__)
cors_origins = "*" if CORS_ORIGINS == "*" else [
    origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()
] or "*"
# O APK (origem https://localhost) chama a API em outra origem com Authorization:
# cada GET precisa de um preflight OPTIONS. Sem Max-Age o Chrome guarda a
# resposta por 5 s, e quase todo pedido do celular virava duas idas ao PC.
# 7200 s e o teto do Chrome.
CORS_PREFLIGHT_MAX_AGE = 7200
CORS(app, resources={r"/api/*": {"origins": cors_origins}}, max_age=CORS_PREFLIGHT_MAX_AGE)

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
    app_bundle_routes,
    frontend_routes,
):
    app.register_blueprint(blueprint_module.bp)


configure_logging()
init_db()
run_startup_backup()
prune_orphan_attachment_files()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
