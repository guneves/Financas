"""Refaz os lancamentos do dono a partir da Pluggy (services/open_finance_rebuild.py).

Com o app parado, num container de uma vez so (nao importa app.py: nenhuma thread
de pull, cotacao ou Tesouro roda aqui; as migrations rodam no inicio):

    docker compose stop app
    docker compose run --rm --no-deps -T --entrypoint python -w /app/backend app \\
        scripts/rebuild_from_pluggy.py --email X                         # ensaio
    ... --email X --apply --app-stopped
    ... --email X --report-categories
    docker compose up -d app

Codigo de saida: 0 tudo confere, 1 falhou ou sobrou diferenca (o texto nomeia),
2 recusado antes de gravar (backup ou trava da carteira).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
from services import open_finance_rebuild as rebuild  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Refaz os lancamentos a partir da Pluggy.")
    parser.add_argument("--email", required=True, help="O e-mail exato do usuario.")
    parser.add_argument("--apply", action="store_true", help="Grava. Sem isto, so um ensaio.")
    parser.add_argument("--app-stopped", action="store_true",
                        help="Com --apply: confirma que o app esta parado (docker compose stop app).")
    parser.add_argument("--accept-balance-shift", action="store_true",
                        help="Aceita um saldo inicial que saltou numa conta que a Pluggy cobre inteira.")
    parser.add_argument("--report-categories", action="store_true", help="So o relatorio de categorias.")
    parser.add_argument("--month", default=rebuild.DEFAULT_RESET_MONTH, help="Mes das operacoes refeitas (AAAA-MM).")
    parser.add_argument("--keep-account", action="append", dest="keep_accounts",
                        help=f"Conta que fica intacta, pelo nome (padrao: {', '.join(rebuild.DEFAULT_KEEP_ACCOUNTS)}).")
    parser.add_argument("--register-item", help="Item da Pluggy a registrar antes (id).")
    parser.add_argument("--map", action="append", default=[], metavar="CONTA=DESTINO",
                        help="Conta da conexao registrada (nome, moeda ou id) = id da conta do app.")
    parser.add_argument("--ignore", action="append", default=[], metavar="CONTA",
                        help="Conta da conexao registrada que fica \"nao usar\".")
    parser.add_argument("--accept-investment-gaps", action="store_true", help="Segue com a trava da carteira aberta.")
    parser.add_argument("--allow-pending", action="store_true", help="Aceita item pendente no fim.")
    parser.add_argument("--mark-reviewed-before", metavar="AAAA-MM-DD",
                        help=f"Mais antigo que isto nao vai para a revisao (padrao: {rebuild.DEFAULT_REVIEW_DAYS} dias).")
    parser.add_argument("--from-step", choices=rebuild.STEPS, default=rebuild.STEPS[0], help="Retoma deste passo.")
    return parser.parse_args(argv)


def options_from(args):
    maps = {}
    for entry in args.map:
        key, separator, target = entry.partition("=")
        if not separator or not key or not target:
            raise SystemExit(f"--map espera CONTA=DESTINO: {entry}")
        maps[key] = target
    return rebuild.Options(
        month=args.month, keep_accounts=tuple(args.keep_accounts or rebuild.DEFAULT_KEEP_ACCOUNTS),
        register_item=args.register_item, maps=maps, ignores=tuple(args.ignore),
        accept_investment_gaps=args.accept_investment_gaps, allow_pending=args.allow_pending,
        accept_balance_shift=args.accept_balance_shift,
        reviewed_before=args.mark_reviewed_before, from_step=args.from_step,
    )


def main(argv=None):
    args = parse_args(argv)
    if args.apply and not args.app_stopped:
        print("RECUSADO: --apply roda com o app parado: docker compose stop app, depois --app-stopped.")
        return rebuild.EXIT_REFUSED
    # O container de uma vez so nao passa pelo boot do app.
    db.init_db()
    try:
        user_id = rebuild.find_user(args.email)
    except rebuild.RebuildRefused as exc:
        print(f"RECUSADO: {exc}")
        return rebuild.EXIT_REFUSED
    if args.report_categories:
        rebuild.print_category_report(rebuild.category_report(user_id))
        return rebuild.EXIT_OK
    options = options_from(args)
    return rebuild.apply(user_id, options) if args.apply else rebuild.dry_run(user_id, options)


if __name__ == "__main__":
    sys.exit(main())
