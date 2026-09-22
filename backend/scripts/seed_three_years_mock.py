"""Semeia 3 anos de dados ficticios para UM usuario, pelo proprio app.

Uso (de dentro de backend/):
    ..\\.venv\\Scripts\\python.exe scripts/seed_three_years_mock.py wgrrodrigues6@gmail.com

DESTRUTIVO para o usuario informado: apaga todas as linhas dele (contas,
categorias, lancamentos, cartoes, orcamentos, recorrencias, investimentos) e
recria tudo. Outros usuarios nao sao tocados. Antes de apagar, grava uma copia
do banco em backend/backups/finance-pre-mock-<timestamp>.db.

Tudo e gravado pelas rotas da API (Flask test client com um token do usuario),
nao por INSERT direto: assim a fatura de cada parcela, o caixa ligado aos
investimentos, o FIFO, as posicoes e os resultados realizados saem exatamente
como sairiam do app.
"""

import calendar
import os
import random
import sqlite3
import sys
from datetime import date, datetime, timedelta

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
os.environ.setdefault("AUTO_BACKUP_ON_BOOT", "0")

import app as finance_app  # noqa: E402

TODAY = date.today()
START = date(TODAY.year - 3, TODAY.month, 1)
RNG = random.Random(20260922)

# Ordem importa: filhos antes dos pais por causa das FKs.
USER_TABLES = [
    "price_quotes",
    "investment_proceeds",
    "investment_realized_results",
    "investment_positions",
    "investment_transactions",
    "investments",
    "assets",
    "cc_expenses",
    "credit_cards",
    "budgets",
    "recurring_transactions",
    "transactions",
    "categories",
    "accounts",
]


# ---------------------------------------------------------------- utilidades

def money(value):
    return float(finance_app.rounded_money(value))


def months_between(start, end):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            year, month = year + 1, 1


def day_in(year, month, day):
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def in_range(value):
    return START <= value <= TODAY


def iso(value):
    return value.isoformat()


class Api:
    def __init__(self, user_id):
        self.client = finance_app.app.test_client()
        self.headers = {"Authorization": f"Bearer {finance_app.create_token(user_id)}"}
        self.calls = 0

    def _check(self, response, method, path, payload, allow_fail):
        self.calls += 1
        if response.status_code >= 400:
            if allow_fail:
                return None
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.get_json()} | {payload}")
        return response.get_json()

    def post(self, path, payload, allow_fail=False):
        response = self.client.post(path, json=payload, headers=self.headers)
        return self._check(response, "POST", path, payload, allow_fail)

    def patch(self, path, payload):
        response = self.client.patch(path, json=payload, headers=self.headers)
        return self._check(response, "PATCH", path, payload, False)

    def get(self, path):
        response = self.client.get(path, headers=self.headers)
        return self._check(response, "GET", path, None, False)


# ---------------------------------------------------------------- preparo

def backup_and_wipe(user_id):
    db_path = finance_app.DATABASE_PATH
    backup_dir = os.path.join(BACKEND_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(
        backup_dir, f"finance-pre-mock-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
    )
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    print(f"Backup: {backup_path}")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in USER_TABLES:
            deleted = conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,)).rowcount
            if deleted:
                print(f"  apagado {table}: {deleted}")
        finance_app.seed_default_categories(conn, user_id)
        conn.commit()


# ---------------------------------------------------------------- cadastros

def create_accounts(api):
    accounts = {a["name"]: a for a in api.get("/api/accounts")}  # cria a Conta Principal
    principal = accounts["Conta Principal"]["id"]
    api.patch(f"/api/accounts/{principal}", {"institution": "Itaú", "initial_balance": 18500})
    savings = api.post("/api/accounts", {
        "name": "Poupança", "type": "SAVINGS", "institution": "Itaú", "initial_balance": 6000,
    })["id"]
    wallet = api.post("/api/accounts", {
        "name": "Carteira", "type": "CASH", "initial_balance": 250,
    })["id"]
    return {"principal": principal, "savings": savings, "wallet": wallet}


def create_categories(api):
    for name, kind in [
        ("Salário", "INCOME"),
        ("Freelance", "INCOME"),
        ("Assinaturas", "EXPENSE"),
        ("Mercado", "EXPENSE"),
        ("Restaurantes", "EXPENSE"),
        ("Pets", "EXPENSE"),
        ("Presentes", "EXPENSE"),
    ]:
        api.post("/api/categories", {"name": name, "kind": kind})
    return {c["name"]: c["id"] for c in api.get("/api/categories")}


def create_cards(api):
    nubank = api.post("/api/credit-cards", {"name": "Nubank", "due_day": 10, "closing_day": 3})
    itau = api.post("/api/credit-cards", {"name": "Itaú Visa", "due_day": 20, "closing_day": 13})
    return {"Nubank": nubank, "Itaú Visa": itau}


# ---------------------------------------------------------------- recorrencias

def create_recurrences(api, accounts):
    """Contas fixas viram recorrencias; /api/recurring/run materializa o historico."""

    def recurrence(description, category, amount, start, end=None, type_="EXPENSE", day=None, **extra):
        payload = {
            "type": type_,
            "description": description,
            "category": category,
            "amount": amount,
            "frequency": extra.pop("frequency", "MONTHLY"),
            "start_date": iso(start),
            "end_date": iso(end) if end else None,
            "account_id": accounts["principal"],
        }
        payload.update(extra)
        api.post("/api/recurring", payload)

    first = START
    # Salario: reajuste todo marco.
    salary_steps = [(9500.00, None), (10450.00, 3), (11600.00, 3), (12750.00, 3)]
    period_start = day_in(first.year, first.month, 5)
    for index, (amount, _) in enumerate(salary_steps):
        next_raise = date(period_start.year + (1 if period_start.month >= 3 else 0), 3, 5)
        end = next_raise - timedelta(days=1) if index < len(salary_steps) - 1 else None
        recurrence("Salário - Empresa X", "Salário", amount, period_start, end, type_="INCOME")
        period_start = next_raise

    # Aluguel: reajuste anual no aniversario do contrato (mes de inicio).
    rents = [2400.00, 2550.00, 2690.00]
    for year_index, amount in enumerate(rents):
        start = day_in(first.year + year_index, first.month, 8)
        end = day_in(first.year + year_index + 1, first.month, 7) if year_index < 2 else None
        recurrence("Aluguel apartamento", "Moradia", amount, start, end)

    recurrence("Condomínio", "Moradia", 640.00, day_in(first.year, first.month, 10))
    recurrence("Internet fibra", "Serviços", 119.90, day_in(first.year, first.month, 15))
    recurrence("Plano de saúde", "Saúde", 489.00, day_in(first.year, first.month, 12),
               date(2024, 12, 31))
    recurrence("Plano de saúde", "Saúde", 562.00, date(2025, 1, 12))
    recurrence("Curso de inglês", "Educação", 390.00, day_in(first.year, first.month, 20),
               date(2025, 6, 30))
    recurrence("Academia", "Saúde", 129.90, date(2024, 2, 5))
    recurrence("Seguro do carro", "Transporte", 2380.00, date(first.year, 11, 15),
               frequency="YEARLY")

    return api.post("/api/recurring/run", {"through": iso(TODAY)})["created"]


# ---------------------------------------------------------------- conta corrente

def seed_account_movements(api, accounts):
    count = 0

    def movement(when, category, amount, description, account="principal", type_="EXPENSE"):
        nonlocal count
        if not in_range(when):
            return
        api.post("/api/transactions", {
            "type": type_, "date": iso(when), "category": category,
            "amount": money(amount), "description": description,
            "account_id": accounts[account],
        })
        count += 1

    for year, month in months_between(START, TODAY):
        # Contas de consumo variaveis (verao = mais energia).
        energy = RNG.uniform(210, 330) if month in (12, 1, 2, 3) else RNG.uniform(150, 240)
        movement(day_in(year, month, 18), "Serviços", energy, "Conta de luz - Enel")
        movement(day_in(year, month, 22), "Serviços", RNG.uniform(75, 125), "Conta de água - Sabesp")
        movement(day_in(year, month, 9), "Serviços", 64.99, "Plano de celular")

        # Feira/padaria no debito e dinheiro vivo.
        for _ in range(RNG.randint(2, 4)):
            movement(day_in(year, month, RNG.randint(1, 28)), "Mercado", RNG.uniform(35, 180),
                    RNG.choice(["Feira", "Padaria", "Hortifruti", "Açougue"]))
        for _ in range(RNG.randint(1, 3)):
            movement(day_in(year, month, RNG.randint(1, 28)), "Lazer", RNG.uniform(20, 60),
                    RNG.choice(["Feira de rua", "Estacionamento", "Pastel", "Gorjeta"]), account="wallet")

        # Freelance em ~45% dos meses.
        if RNG.random() < 0.45:
            movement(day_in(year, month, RNG.randint(12, 26)), "Freelance",
                    RNG.choice([850, 1200, 1800, 2400, 3500]),
                    RNG.choice(["Projeto landing page", "Consultoria", "Manutenção de site", "Dashboard BI"]),
                    type_="INCOME")

        # Rendimento da poupanca.
        movement(day_in(year, month, 28), "Receita", RNG.uniform(35, 95), "Rendimento poupança",
                account="savings", type_="INCOME")

        # Transferencia para a poupanca e reforco da carteira.
        when = day_in(year, month, 6)
        if in_range(when):
            api.post("/api/transfers", {
                "account_id": accounts["principal"], "transfer_account_id": accounts["savings"],
                "amount": RNG.choice([300, 400, 500, 600]), "date": iso(when),
                "description": "Reserva de emergência",
            })
            count += 1
        when = day_in(year, month, 14)
        if in_range(when):
            api.post("/api/transfers", {
                "account_id": accounts["principal"], "transfer_account_id": accounts["wallet"],
                "amount": 100, "date": iso(when), "description": "Saque",
            })
            count += 1

        # Eventos anuais.
        if month == 2:
            movement(date(year, 2, 10), "Transporte", 1860.00 + (year - 2024) * 95, "IPVA")
            movement(date(year, 2, 15), "Moradia", 1240.00, "IPTU (cota única)")
            movement(date(year, 2, 1), "Educação", RNG.uniform(420, 680), "Material escolar / livros")
        if month == 11:
            movement(date(year, 11, 28), "Salário", 5200.00 + (year - 2023) * 550, "13º salário - 1ª parcela",
                    type_="INCOME")
        if month == 12:
            movement(date(year, 12, 18), "Salário", 4100.00 + (year - 2023) * 450, "13º salário - 2ª parcela",
                    type_="INCOME")
        if month == 1:
            movement(date(year, 1, 5), "Salário", 3200.00 + (year - 2024) * 350, "Adicional de férias (1/3)",
                    type_="INCOME")
        if month == 4:
            movement(date(year, 4, 28), "Receita", RNG.uniform(600, 1900), "Restituição IR", type_="INCOME")

    # Resgate da poupanca para a viagem.
    api.post("/api/transfers", {
        "account_id": accounts["savings"], "transfer_account_id": accounts["principal"],
        "amount": 4000, "date": "2025-01-05", "description": "Resgate para viagem",
    })
    return count + 1


# ---------------------------------------------------------------- cartoes

CARD_ONE_OFFS = [
    # (data, cartao, categoria, descricao, valor, parcelas)
    ("2023-11-24", "Nubank", "Outros", "Black Friday - fone de ouvido", 899.00, 3),
    ("2023-12-15", "Itaú Visa", "Presentes", "Presentes de Natal", 1480.00, 4),
    ("2024-02-10", "Itaú Visa", "Educação", "Curso online de dados", 1188.00, 12),
    ("2024-04-18", "Nubank", "Outros", "Smartphone novo", 4799.00, 10),
    ("2024-07-06", "Itaú Visa", "Lazer", "Passagens - férias de julho", 2640.00, 6),
    ("2024-07-20", "Itaú Visa", "Lazer", "Hospedagem Florianópolis", 1950.00, 3),
    ("2024-09-02", "Nubank", "Saúde", "Tratamento dentário", 2400.00, 6),
    ("2024-11-29", "Nubank", "Moradia", "Geladeira frost free", 3899.00, 12),
    ("2024-12-12", "Itaú Visa", "Presentes", "Presentes de Natal", 1720.00, 5),
    ("2025-01-08", "Itaú Visa", "Lazer", "Viagem Chile - pacote", 7800.00, 10),
    ("2025-03-15", "Nubank", "Transporte", "Revisão do carro + pneus", 2280.00, 4),
    ("2025-05-10", "Nubank", "Presentes", "Dia das Mães", 420.00, 1),
    ("2025-06-21", "Itaú Visa", "Educação", "Pós-graduação - matrícula", 1350.00, 1),
    ("2025-08-30", "Nubank", "Outros", "Notebook de trabalho", 6499.00, 12),
    ("2025-10-11", "Itaú Visa", "Moradia", "Sofá novo", 3200.00, 8),
    ("2025-11-28", "Nubank", "Outros", "Black Friday - smart TV", 2899.00, 10),
    ("2025-12-10", "Itaú Visa", "Presentes", "Presentes de Natal", 1890.00, 5),
    ("2026-01-15", "Itaú Visa", "Lazer", "Viagem Nordeste", 5400.00, 6),
    ("2026-03-08", "Nubank", "Saúde", "Óculos de grau", 1150.00, 3),
    ("2026-05-02", "Nubank", "Pets", "Castração + vacinas do gato", 780.00, 2),
    ("2026-07-19", "Itaú Visa", "Lazer", "Show + ingressos", 690.00, 2),
    ("2026-08-25", "Nubank", "Moradia", "Máquina de lavar", 2799.00, 10),
]


def seed_card_purchases(api, cards):
    count = 0

    def buy(when, card, category, description, amount, installments=1):
        nonlocal count
        if not in_range(when):
            return
        api.post("/api/cc-expenses/purchases", {
            "card_id": cards[card]["id"], "category": category, "description": description,
            "total_amount": money(amount), "purchase_date": iso(when), "installments": installments,
        })
        count += 1

    for year, month in months_between(START, TODAY):
        # Assinaturas fixas.
        buy(day_in(year, month, 7), "Nubank", "Assinaturas", "Netflix", 44.90 if year < 2025 else 59.90)
        buy(day_in(year, month, 11), "Nubank", "Assinaturas", "Spotify Família", 34.90 if year < 2025 else 40.90)
        buy(day_in(year, month, 16), "Itaú Visa", "Assinaturas", "iCloud 200 GB", 14.90)
        if (year, month) >= (2024, 6):
            buy(day_in(year, month, 3), "Itaú Visa", "Assinaturas", "Amazon Prime", 19.90)

        # Supermercado semanal.
        for week in range(4):
            buy(day_in(year, month, 2 + week * 7 + RNG.randint(0, 2)),
                RNG.choice(["Nubank", "Nubank", "Itaú Visa"]), "Mercado",
                RNG.choice(["Supermercado Pão de Açúcar", "Carrefour", "Assaí Atacadista", "Oxxo"]),
                RNG.uniform(180, 520))

        # Combustivel.
        for _ in range(RNG.randint(2, 3)):
            buy(day_in(year, month, RNG.randint(1, 28)), "Itaú Visa", "Transporte",
                RNG.choice(["Posto Shell", "Posto Ipiranga", "Posto BR"]), RNG.uniform(180, 290))
        if RNG.random() < 0.7:
            buy(day_in(year, month, RNG.randint(1, 28)), "Nubank", "Transporte", "Uber",
                RNG.uniform(18, 75))

        # Restaurantes e delivery.
        for _ in range(RNG.randint(3, 7)):
            buy(day_in(year, month, RNG.randint(1, 28)), "Nubank", "Restaurantes",
                RNG.choice(["iFood", "iFood", "Restaurante japonês", "Hamburgueria", "Pizzaria", "Café"]),
                RNG.uniform(35, 190))

        # Farmacia, pet, lazer.
        if RNG.random() < 0.65:
            buy(day_in(year, month, RNG.randint(1, 28)), "Nubank", "Saúde", "Drogasil",
                RNG.uniform(30, 160))
        if (year, month) >= (2024, 3):
            buy(day_in(year, month, RNG.randint(1, 28)), "Itaú Visa", "Pets", "Petz - ração e areia",
                RNG.uniform(140, 260))
        if RNG.random() < 0.5:
            buy(day_in(year, month, RNG.randint(1, 28)), "Itaú Visa", "Lazer",
                RNG.choice(["Cinema", "Livraria", "Steam", "Bar com amigos"]), RNG.uniform(45, 240))
        if RNG.random() < 0.3:
            buy(day_in(year, month, RNG.randint(1, 28)), "Nubank", "Outros",
                RNG.choice(["Renner", "Amazon", "Mercado Livre", "Leroy Merlin"]), RNG.uniform(90, 480))

    for when, card, category, description, amount, installments in CARD_ONE_OFFS:
        buy(date.fromisoformat(when), card, category, description, amount, installments)
    return count


def pay_past_invoices(api, cards, accounts):
    """Paga toda fatura vencida, como o botao 'Pagar fatura' de Cartoes."""
    expenses = api.get("/api/cc-expenses")
    totals = {}
    for item in expenses:
        key = (item["card_id"], item["invoice_year"], item["invoice_month"])
        totals[key] = totals.get(key, 0) + float(item["amount"])

    names = {card["id"]: name for name, card in cards.items()}
    paid = 0
    for (card_id, year, month), total in sorted(totals.items(), key=lambda kv: kv[0][1:]):
        due = day_in(year, month, cards[names[card_id]]["due_day"])
        if due > TODAY:
            continue
        api.post("/api/transactions", {
            "type": "EXPENSE", "date": iso(due), "amount": money(total),
            "category": f"Pagamento Fatura {names[card_id]}",
            "description": f"Fatura {month:02d}/{year}",
            "account_id": accounts["principal"],
        })
        api.patch("/api/cc-expenses/invoice-status", {
            "card_id": card_id, "invoice_month": month, "invoice_year": year,
            "status": "PAID", "current_status": "OPEN",
        })
        paid += 1
    return paid


# ---------------------------------------------------------------- orcamento

BUDGET_PLAN = {
    "Moradia": 3300, "Mercado": 350, "Serviços": 480, "Saúde": 700,
    "Educação": 450, "Lazer": 250, "Transporte": 300,
}


def seed_budgets(api, category_ids):
    count = 0
    budget_start = date(TODAY.year - 1, TODAY.month, 1)
    for year, month in months_between(budget_start, TODAY):
        for name, planned in BUDGET_PLAN.items():
            api.post("/api/budgets", {
                "category_id": category_ids[name], "month": f"{year:04d}-{month:02d}",
                "planned_amount": planned, "rollover": name == "Lazer",
            })
            count += 1
    return count


# ---------------------------------------------------------------- investimentos

STOCKS = {
    # ticker: (classe, preco inicial, deriva anual, volatilidade mensal)
    "ITUB4": ("STOCKS", 27.5, 0.14, 0.05),
    "PETR4": ("STOCKS", 34.0, 0.03, 0.07),
    "WEGE3": ("STOCKS", 37.0, 0.06, 0.06),
    "TAEE11": ("STOCKS", 34.5, 0.03, 0.03),
    "BBAS3": ("STOCKS", 25.0, -0.02, 0.06),
    "HGLG11": ("REIT", 162.0, 0.00, 0.03),
    "MXRF11": ("REIT", 10.6, -0.02, 0.02),
    "KNRI11": ("REIT", 139.0, 0.02, 0.025),
}

# Provento mensal por cota (FII) ou trimestral/semestral (acoes).
PROCEEDS = {
    "HGLG11": ("DIVIDEND", 1.10, range(1, 13)),
    "MXRF11": ("DIVIDEND", 0.10, range(1, 13)),
    "KNRI11": ("DIVIDEND", 1.00, range(1, 13)),
    "ITUB4": ("JCP", 0.40, (3, 6, 9, 12)),
    "TAEE11": ("DIVIDEND", 1.20, (5, 11)),
    "BBAS3": ("JCP", 0.55, (3, 6, 9, 12)),
    "PETR4": ("DIVIDEND", 1.05, (2, 5, 8, 11)),
}

FIXED_INCOME = [
    # (data, nome, valor, metadata)
    ("2023-10-10", "CDB Banco Inter 2026", 5000.00,
     {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.10}),
    ("2024-01-15", "LCI Itaú 2026", 8000.00,
     {"fixed_income_type": "LCI", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0.95,
      "is_tax_free": True}),
    ("2024-06-20", "CDB XP Pré 2027", 6000.00,
     {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 0.118}),
    ("2025-02-12", "CRA Raízen IPCA+ 2030", 7000.00,
     {"fixed_income_type": "CRA", "rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.068,
      "is_tax_free": True}),
    ("2025-09-18", "LCA BTG 2027", 10000.00,
     {"fixed_income_type": "LCA", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0.93,
      "is_tax_free": True}),
    ("2026-04-08", "CDB Nubank CDI+ 2028", 9000.00,
     {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI_PLUS", "annual_rate": 0.015}),
]

# Resgate (data, nome, valor recebido)
FIXED_INCOME_REDEMPTIONS = [
    ("2025-12-22", "CDB Banco Inter 2026", 3000.00, 3786.00),
]

# Vendas (data, ticker, quantidade)
SALES = [
    ("2024-05-20", "PETR4", 100),
    ("2025-07-14", "WEGE3", 100),
    ("2026-06-10", "BBAS3", 200),
]


def price_path():
    """Preco mensal por ticker: passeio aleatorio com deriva."""
    paths = {}
    for ticker, (_, price, drift, vol) in STOCKS.items():
        series = {}
        for year, month in months_between(START, TODAY):
            series[(year, month)] = price
            price = max(price * (1 + drift / 12 + RNG.gauss(0, vol)), price * 0.6)
        paths[ticker] = series
    return paths


def seed_investments(api):
    prices = price_path()
    events = []

    # Aporte mensal: um papel por mes, rotativo, lote de 100 (FII em lotes menores).
    rotation = ["ITUB4", "HGLG11", "TAEE11", "MXRF11", "WEGE3", "KNRI11", "PETR4", "BBAS3"]
    for index, (year, month) in enumerate(months_between(START, TODAY)):
        ticker = rotation[index % len(rotation)]
        when = day_in(year, month, 7)
        if not in_range(when):
            continue
        price = prices[ticker][(year, month)]
        quantity = {"HGLG11": 10, "KNRI11": 12, "MXRF11": 150}.get(ticker, 100)
        events.append((when, "buy", ticker, quantity, price))

    for when, ticker, quantity in SALES:
        when = date.fromisoformat(when)
        events.append((when, "sell", ticker, quantity, prices[ticker][(when.year, when.month)] * 1.04))

    for when, name, amount, metadata in FIXED_INCOME:
        events.append((date.fromisoformat(when), "fixed", name, amount, metadata))
    for when, name, cost, received in FIXED_INCOME_REDEMPTIONS:
        events.append((date.fromisoformat(when), "redeem", name, cost, received))

    events.sort(key=lambda event: event[0])
    fixed_buy_ids = {}
    count = 0
    for event in events:
        when, kind = event[0], event[1]
        if not in_range(when):
            continue
        if kind == "buy":
            _, _, ticker, quantity, price = event
            fee = money(4.90)
            api.post("/api/investments", [{
                "asset_class": STOCKS[ticker][0], "ticker_or_name": ticker,
                "quantity": quantity,
                "average_price": round((quantity * money(price) + fee) / quantity, 6),
                "current_price": money(price),
                "metadata": {"purchase_date": iso(when), "other_costs": fee},
            }])
        elif kind == "sell":
            _, _, ticker, quantity, price = event
            api.post("/api/investments", [{
                "asset_class": STOCKS[ticker][0], "ticker_or_name": ticker,
                "quantity": -quantity, "average_price": money(price), "current_price": money(price),
                "metadata": {"sale_date": iso(when), "sale_price": money(price), "other_costs": 4.90},
            }])
        elif kind == "fixed":
            _, _, name, amount, metadata = event
            fixed_buy_ids[name] = api.post("/api/investments", [{
                "asset_class": "FIXED_INCOME", "ticker_or_name": name, "quantity": 1,
                "average_price": amount, "current_price": amount,
                "metadata": {**metadata, "purchase_date": iso(when), "other_costs": 0},
            }])[0]["id"]
        elif kind == "redeem":
            _, _, name, cost, received = event
            api.post("/api/investments", [{
                "asset_class": "FIXED_INCOME", "ticker_or_name": name, "quantity": -1,
                "average_price": cost, "current_price": received,
                "metadata": {"is_redemption": True, "affects_position": True,
                             "related_id": fixed_buy_ids[name], "redemption_date": iso(when)},
            }])
        count += 1

    # Cotacao atual: o ultimo preco simulado de cada papel.
    assets = {a["ticker"]: a for a in api.get("/api/assets")}
    for ticker in STOCKS:
        if ticker in assets:
            api.patch(f"/api/investments/price-by-asset/{assets[ticker]['id']}", {
                "asset_class": STOCKS[ticker][0],
                "current_price": money(prices[ticker][(TODAY.year, TODAY.month)]),
            })

    # Proventos.
    proceeds = 0
    for ticker, (proceeds_type, per_unit, months) in PROCEEDS.items():
        asset = assets.get(ticker)
        if not asset:
            continue
        for year, month in months_between(START, TODAY):
            if month not in months:
                continue
            record = day_in(year, month, 1) - timedelta(days=1)
            payment = day_in(year, month, 14)
            if record < START or payment > TODAY:
                continue
            value = per_unit * RNG.uniform(0.9, 1.1)
            created = api.post("/api/investment-proceeds", {
                "asset_id": asset["id"], "proceeds_type": proceeds_type,
                "record_date": iso(record), "ex_date": iso(record + timedelta(days=1)),
                "payment_date": iso(payment), "amount_per_unit": round(value, 4),
            }, allow_fail=True)
            proceeds += 1 if created else 0
    return count, proceeds


# ---------------------------------------------------------------- main

def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python scripts/seed_three_years_mock.py <email>")
    email = sys.argv[1].strip().lower()

    with sqlite3.connect(finance_app.DATABASE_PATH) as conn:
        row = conn.execute("SELECT id FROM users WHERE lower(email) = ?", (email,)).fetchone()
    if not row:
        raise SystemExit(f"Usuario {email} nao encontrado.")
    user_id = row[0]

    print(f"Periodo: {START} a {TODAY} | usuario {email}")
    backup_and_wipe(user_id)
    api = Api(user_id)

    accounts = create_accounts(api)
    category_ids = create_categories(api)
    cards = create_cards(api)
    print(f"Recorrencias materializadas: {create_recurrences(api, accounts)}")
    print(f"Movimentacoes em conta: {seed_account_movements(api, accounts)}")
    print(f"Compras no cartao: {seed_card_purchases(api, cards)}")
    print(f"Faturas pagas: {pay_past_invoices(api, cards, accounts)}")
    print(f"Orcamentos: {seed_budgets(api, category_ids)}")
    operations, proceeds = seed_investments(api)
    print(f"Operacoes de investimento: {operations} | proventos: {proceeds}")

    for account in api.get("/api/accounts"):
        print(f"  saldo {account['name']}: {account.get('balance')}")
    print(f"Chamadas a API: {api.calls}")


if __name__ == "__main__":
    main()
