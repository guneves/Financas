"""Os numeros do Inicio, lidos do servidor, para comparar o Inicio nativo com o da web.

Uso (Python 3, so a biblioteca padrao; a senha e pedida, ou vem de FINANCAS_PASSWORD):

    python mobile/inicio-snapshot.py --url https://<servidor> --email voce@exemplo.com

So faz GET (e o login). Os mesmos GETs que o Inicio faz ao abrir, entao, como abrir o app,
lancam um debito automatico ou um provento que ja venceram. Imprime cada valor com o rotulo
da tela; as duas telas (APK de debug e navegador) devem mostrar exatamente isso, sem itens
pendentes no aparelho e com o olho aberto.
"""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]


def brl(value):
    if value is None:
        return "sem câmbio hoje"
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}R$ {'.'.join(groups)},{cents}"


def signed(value):
    amount = Decimal(str(value))
    return ("+" if amount >= 0 else "-") + brl(abs(amount))


def month_label(key):
    year, month = key.split("-")
    return f"{MONTHS[int(month) - 1]} de {year}"


def day_month(iso):
    return date.fromisoformat(iso).strftime("%d/%m") if iso else "—"


def call(base, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers=headers,
                                     method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode(), parse_float=Decimal)
    except urllib.error.HTTPError as error:
        sys.exit(f"{path}: HTTP {error.code} {error.read().decode(errors='replace')[:300]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True, help="endereco do servidor, sem / no fim")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    password = os.environ.get("FINANCAS_PASSWORD") or getpass.getpass("Senha: ")
    token = call(base, "/api/auth/login", body={"email": args.email, "password": password})["access_token"]

    home = call(base, "/api/home?months=12", token)
    attention = call(base, "/api/attention", token)
    budgets = call(base, f"/api/budgets?month={home['month']}", token)

    print(f"Hoje no servidor: {home['today']}  ·  mês {month_label(home['month'])}\n")
    print("SALDO EM CONTA")
    print(f"  Total: {brl(home['consolidated_balance'])}")
    for account in home["accounts"]:
        if account.get("archived_at") or account.get("type") == "BROKERAGE":
            continue
        print(f"  {account['name']}: {brl(account.get('balance_brl'))}")

    s = home["summary"]
    print("\nRESUMO DO MÊS")
    print(f"  Resultado do mês: {signed(s['result'])}")
    print(f"  Entrou: {brl(s['income'])}")
    print(f"  Saiu: {brl(s['expense'])}")
    if Decimal(str(s["invested"])) or Decimal(str(s["redeemed"])):
        print(f"  Investido: {signed(s['investment_net'])}  (Aportes {brl(s['invested'])} · Resgates {brl(s['redeemed'])})")
    others = Decimal(str(s["others_net"]))
    if others:
        label = "Outras pessoas te pagaram" if others > 0 else "Você pagou para outras pessoas"
        print(f"  {label}: {brl(abs(others))}")

    print("\nPRÓXIMA FATURA")
    invoices = home["next_invoices"]
    print(f"  Total: {brl(home['next_invoices_total'])}  ({len(invoices)} fatura(s))")
    for invoice in invoices:
        state = "Fechada" if invoice["closed"] else f"fecha {day_month(invoice['closing_date'])}"
        print(f"  {invoice['card_name']}: {brl(invoice['total'])}, vence {day_month(invoice['due_date'])}, {state}")
    if home.get("next_closing_date"):
        print(f"  Próximo fechamento: {day_month(home['next_closing_date'])}")

    print(f"\nPRECISA DE ATENÇÃO (o sino lista todos: {len(attention['items'])})")
    for item in attention["items"]:
        numbers = {k: v for k, v in item.items() if k not in ("key", "kind", "tone")}
        print(f"  {item['kind']} [{item['tone']}] {json.dumps(numbers, default=str, ensure_ascii=False)}")
    if not attention["items"]:
        print("  Nada pendente agora.")

    totals = budgets.get("totals") or {}
    if budgets.get("items"):
        print("\nORÇAMENTO DO MÊS")
        print(f"  {brl(totals.get('spent', 0))} gasto de {brl(totals.get('available', 0))}")
        for item in budgets["items"]:
            if item.get("status") in ("OVER", "WARNING"):
                name = f"{item['parent_name']} › {item['category_name']}" if item.get("parent_name") else item["category_name"]
                print(f"  {item['status']}: {name} {brl(item['spent'])} / {brl(item['available'])}")

    print("\nFLUXO DE CAIXA (12 meses) e EVOLUÇÃO DO SALDO")
    print(f"  {'mês':8} {'receitas':>14} {'despesas':>14} {'investido':>14} {'resultado':>14} {'saldo no fim':>16}")
    for month in home["flow"]:
        invested = Decimal(str(month["invested"])) - Decimal(str(month["redeemed"]))
        result = Decimal(str(month["income"])) - Decimal(str(month["expense"]))
        print(f"  {month['month']:8} {brl(month['income']):>14} {brl(month['expense']):>14} "
              f"{brl(invested):>14} {brl(result):>14} {brl(month['balance']):>16}")


if __name__ == "__main__":
    main()
