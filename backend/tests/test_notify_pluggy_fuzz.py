"""Notificacoes + Pluggy por cenarios gerados (06-verify-and-fix.md §4).

Os testes de matriz cobrem os casos que alguem pensou; este gera mundos com
`random.Random(seed)` e confere invariantes (teste baseado em propriedades:
Claessen & Hughes, "QuickCheck", ICFP 2000). Cada semente:

1. **A verdade**: 5 a 15 movimentos reais numa semana, no Itau, no BB, no
   cartao do BTG e na Corretora: compras (algumas gemeas, algumas com outro
   valor no banco: gorjeta ou internacional), Pix a terceiros, transferencias
   entre contas do dono e para a Corretora, e pre-autorizacoes que o banco
   soltou (notificadas, nunca postadas, fora do saldo).
2. **O que cada canal ve**: cada movimento notificado ou nao (as vezes duas
   vezes, o repost do BTG 24 ms depois), as pontas de uma transferencia em 0, 1
   ou 2 avisos, no mesmo envio ou em outro, as vezes depois da Pluggy (celular
   sem rede); a Pluggy mostra postado, ou pendente e depois postado com a mesma
   id ou outra, em pulls de conexoes em ordem aleatoria; a compra internacional
   "em processamento" (o Claude do dono, 2026-11-04) esta no saldo do banco
   desde o dia 0 e a Pluggy so a lista 5 a 30 dias depois, com a data da compra
   ou a do lancamento. O dono as vezes diz "E meu" ou muda a categoria de uma
   compra entre os passos.
3. **Depois do ultimo pull**: `assert_identity()`; uma linha por movimento real
   (gemeas sao duas, a transferencia e uma TRANSFER); o saldo de cada conta e o
   total do cartao iguais aos da verdade; nada esperando em `GET /api/inbox`.

As notificacoes passam pela porta de verdade (`notification_wanted()` com
`bank_notifications` ligado por padrao): este arquivo nunca usa
`any_bank_notifications`, e cada mundo manda tambem avisos que ela deve ignorar
(ordem da corretora, Samsung com cartao do banco, Pix ao Tesouro, app fora da
lista), que nao deixam rastro. A transferencia com as duas pontas sai do Revisar
sozinha, e `review_count` e o tamanho do Revisar. A semente vai na mensagem de
cada falha.

Cada conta ganha uma linha antiga antes da semana: em producao toda conta tem
historico, e sem ele a janela do pull de uma conta nova e so OVERLAP_DAYS (a
compra internacional postada semanas depois com a data da compra nao entraria).
A semana e em setembro, antes do relogio real: `last_sync_at` e a hora de
verdade e o app so "leu" o banco depois de `pluggy_updated_at`.
"""

import importlib
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import pytest

from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, day_iso, fake_pluggy, open_finance_module, pluggy_id  # noqa: F401
from test_auto_record import confirm, notifications_on
from test_inbox import BB, ITAU, detection, send
from test_open_finance_auto import meupluggy, pin_today

BRT = timezone(timedelta(hours=-3))
BTG_BANK = "com.btg.pactual.banking"
BROKERAGE = "com.btg.pactual.digital.mobile"
SELF_TRANSFER = "04000000"
PIX_CATEGORY = "05000000"
# Antes do relogio real: last_sync_at e a hora de verdade, e o app so "leu" o
# banco se last_sync_at >= pluggy_updated_at (bank_refreshed_since()).
START = date(2026, 9, 14)
SEEDS = range(200)

MERCHANTS = [
    "PADARIA BOM PAO", "MERCADO EXTRA", "FARMACIA SAO JOAO", "POSTO IPIRANGA", "RESTAURANTE SABOR",
    "LIVRARIA CULTURA", "CINEMARK", "ACADEMIA FORMA", "PETSHOP AMIGO", "OTICA VISAO", "SORVETERIA GELATO",
    "PIZZARIA FORNO", "HORTIFRUTI VERDE", "PAPELARIA ARTE", "BARBEARIA NAVALHA", "LAVANDERIA LIMPA",
]
FOREIGN = ["CLAUDE.AI", "NETFLIX.COM", "SPOTIFY AB", "STEAM GAMES"]
PEOPLE = ["Maria Silva", "Joao Pereira", "Ana Costa", "Pedro Souza", "Carla Lima"]


def _ms(moment):
    return int(moment.timestamp() * 1000)


def _at(day, minute):
    return datetime(day.year, day.month, day.day, 8, 0, tzinfo=BRT) + timedelta(minutes=minute)


class Movement:
    """Um movimento real e o que cada canal ve dele."""

    def __init__(self, kind, day, minute, amount, **extra):
        self.kind = kind          # debit | card | pix | own | broker | preauth
        self.day = day
        self.minute = minute
        self.amount = amount      # centavos que o banco tira/poe (a verdade)
        self.notified_amount = amount
        self.international = False
        self.merchant = None
        self.account = None       # conta de onde sai (ou o cartao)
        self.to_account = None    # destino de uma transferencia
        self.counterparty = None
        self.notices = []         # [(dia de envio, grupo, [deteccoes])]
        self.sides = []           # o que a Pluggy lista: dicts por conta
        self.__dict__.update(extra)


class Scenario:
    def __init__(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.movements = []
        self.used_cents = set()
        self.merchants = list(MERCHANTS)
        self.rng.shuffle(self.merchants)

    def cents(self, low=1500, high=60000):
        while True:
            value = self.rng.randint(low, high)
            # Um valor so por movimento (os gemeos repetem de proposito), a mais
            # de R$ 2 de qualquer outro (o arredondamento do BB). O par
            # aproximado nao confunde movimentos: cada compra tem seu comerciante.
            if all(abs(value - other) > 200 for other in self.used_cents):
                self.used_cents.add(value)
                return value

    def generate(self):
        rng = self.rng
        count = rng.randint(5, 15)
        while len(self.movements) < count:
            day = START + timedelta(days=rng.randint(0, 6))
            minute = rng.randint(0, 600)
            kind = rng.choices(
                ["debit", "card", "pix", "own", "broker", "preauth", "twins"],
                weights=[4, 4, 2, 2, 1, 1, 2],
            )[0]
            if kind == "twins":
                base = self._purchase(rng.choice(["debit", "card"]), day, minute, twin=True)
                if base is None:
                    continue
                twin = self._purchase(base.kind, day, minute + rng.randint(1, 30), twin_of=base)
                self.movements += [base, twin]
                continue
            if kind in ("debit", "card", "preauth"):
                movement = self._purchase(kind, day, minute)
                if movement is None:
                    continue
            elif kind == "pix":
                movement = Movement("pix", day, minute, self.cents(), account=rng.choice(["itau", "bb"]),
                                    counterparty=rng.choice(PEOPLE))
            elif kind == "own":
                source = rng.choice(["itau", "bb"])
                movement = Movement("own", day, minute, self.cents(), account=source,
                                    to_account="bb" if source == "itau" else "itau", counterparty="Fulano Dono")
            else:
                movement = Movement("broker", day, minute, self.cents(), account="itau", to_account="corretora",
                                    counterparty="Fulano Dono")
            self.movements.append(movement)
        for movement in self.movements:
            self._channels(movement)
        self.noise = []
        for _ in range(rng.randint(0, 3)):
            day = START + timedelta(days=rng.randint(0, 6))
            at = _ms(_at(day, rng.randint(0, 600)))
            self.noise.append((day, rng.choice([
                # A corretora: so Pix/TED; uma ordem nunca e compra no cartao.
                detection("PURCHASE", self.cents(), at=at, app=BROKERAGE, merchant="ORDEM DE COMPRA PETR4"),
                # Samsung Wallet com cartao que nao e o do Flash.
                detection("CREDIT_PURCHASE", self.cents(), at=at, app="com.samsung.android.spay",
                          merchant="LOJA SAMSUNG", card_name="BTG Pactual Banking"),
                # Pix de investimento de um banco.
                detection("PIX_OUT", self.cents(), at=at, app=ITAU, merchant=None, counterparty="TESOURO DIRETO"),
                # Um app que a politica nao ouve.
                detection("PIX_OUT", self.cents(), at=at, app="com.nubank", merchant=None, counterparty="Maria"),
            ])))
        return self

    def _purchase(self, kind, day, minute, twin=False, twin_of=None):
        rng = self.rng
        if twin_of is not None:
            movement = Movement(twin_of.kind, day, minute, twin_of.amount, account=twin_of.account,
                                merchant=twin_of.merchant)
            return movement
        if not self.merchants:
            return None
        account = "card" if kind == "card" else "itau"
        movement = Movement("preauth" if kind == "preauth" else kind, day, minute, self.cents(), account=account,
                            merchant=self.merchants.pop())
        if twin or kind == "preauth":
            return movement
        shape = rng.random()
        if shape < 0.15:
            # Internacional: o banco avisa uma estimativa e posta convertido (IOF).
            movement.international = True
            movement.merchant = rng.choice(FOREIGN) + f" {len(self.movements)}"
            movement.notified_amount = movement.amount
            movement.amount = self._near(movement.amount, rng.randint(0, 8))
        elif shape < 0.3:
            # Gorjeta: postado ate 25% acima do aviso.
            movement.notified_amount = movement.amount
            movement.amount = self._near(movement.amount, rng.randint(5, 25))
        return movement

    def _near(self, cents, percent):
        """O valor postado, `percent`% acima do aviso, tambem unico."""
        value = cents + cents * percent // 100
        while value != cents and any(abs(value - other) <= 200 for other in self.used_cents - {cents}):
            value += 1
        self.used_cents.add(value)
        return value

    # -- os canais ---------------------------------------------------------

    def _notice(self, movement, app, kind, amount, counterparty=None, merchant=None, international=False):
        body = detection(kind, amount, at=_ms(_at(movement.day, movement.minute)), app=app,
                         merchant=merchant, counterparty=counterparty)
        if international:
            body["international"] = True
        if counterparty is None:
            body.pop("counterparty")
        return body

    def _send_day(self, movement, posted_day):
        """O dia do envio: o do movimento ou, sem rede, depois da Pluggy."""
        if self.rng.random() < 0.15:
            return posted_day + timedelta(days=1)
        return movement.day

    def _channels(self, movement):
        rng = self.rng
        app_of = {"itau": ITAU, "bb": BB}
        if movement.kind in ("debit", "card", "preauth"):
            posted_day = self._pluggy_side(movement, movement.account, -1) if movement.kind != "preauth" else movement.day
            notified = movement.kind == "preauth" or rng.random() < 0.75
            if notified:
                if movement.kind == "card":
                    notice = self._notice(movement, BTG_BANK, "CREDIT_PURCHASE", movement.notified_amount,
                                          merchant=movement.merchant, international=movement.international)
                else:
                    notice = self._notice(movement, ITAU, "DEBIT_PURCHASE", movement.notified_amount,
                                          merchant=movement.merchant, international=movement.international)
                self._schedule(movement, posted_day, [notice])
        elif movement.kind == "pix":
            posted_day = self._pluggy_side(movement, movement.account, -1)
            if rng.random() < 0.75:
                notice = self._notice(movement, app_of[movement.account], "PIX_OUT", movement.amount,
                                      counterparty=movement.counterparty)
                self._schedule(movement, posted_day, [notice])
        else:
            out_day = self._pluggy_side(movement, movement.account, -1)
            in_day = self._pluggy_side(movement, movement.to_account, +1)
            out_notice = self._notice(movement, app_of[movement.account], "PIX_OUT", movement.amount,
                                      counterparty=movement.counterparty)
            if movement.kind == "broker":
                in_notice = self._notice(movement, BROKERAGE, "TRANSFER_IN", movement.amount)
            else:
                in_notice = self._notice(movement, app_of[movement.to_account], "PIX_IN", movement.amount,
                                         counterparty=movement.counterparty)
            in_notice["posted_ms"] += rng.randint(1, 120) * 1000
            seen = [notice for notice in (out_notice, in_notice) if rng.random() < 0.6]
            if len(seen) == 2 and rng.random() < 0.5:
                self._schedule(movement, max(out_day, in_day), seen)
            else:
                for notice, posted_day in zip(seen, (out_day, in_day)):
                    self._schedule(movement, posted_day, [notice])

    def _schedule(self, movement, posted_day, notices):
        day = self._send_day(movement, posted_day)
        group = [*notices]
        if self.rng.random() < 0.15:
            # O repost (BTG: o mesmo aviso de novo, 24 ms depois, outra chave).
            again = dict(notices[0])
            again["key"] = again["key"][::-1]
            again["posted_ms"] += 24
            if self.rng.random() < 0.5:
                group.append(again)
            else:
                movement.notices.append((day, [again]))
        movement.notices.append((day, group))

    def _pluggy_side(self, movement, account, sign):
        """Como a Pluggy lista esta ponta; devolve o dia em que fica postada."""
        rng = self.rng
        if movement.international:
            delay = rng.randint(5, 30)
            posted_day = movement.day + timedelta(days=delay)
            side = {
                "account": account, "sign": sign, "pending_day": None, "posted_day": posted_day,
                "date": rng.choice([movement.day, posted_day]), "pending_amount": movement.amount,
                "same_id": True, "ids": (pluggy_id(), pluggy_id()),
            }
        else:
            pending = rng.random() < 0.5
            posted_day = movement.day + timedelta(days=rng.randint(0, 1) if pending else rng.choice([0, 0, 1]))
            side = {
                "account": account, "sign": sign, "pending_day": movement.day if pending else None,
                "posted_day": posted_day, "date": movement.day if rng.random() < 0.7 else posted_day,
                # A pendente de uma gorjeta e o valor do aviso; a postada, o do banco.
                "pending_amount": movement.notified_amount if account != "corretora" else movement.amount,
                "same_id": rng.random() < 0.5, "ids": (pluggy_id(), pluggy_id()),
            }
        movement.sides.append(side)
        return posted_day

    # -- a verdade ---------------------------------------------------------

    def real(self):
        return [movement for movement in self.movements if movement.kind != "preauth"]

    def last_day(self):
        days = [side["posted_day"] for movement in self.movements for side in movement.sides]
        days += [day for movement in self.movements for day, _group in movement.notices]
        return max([*days, START + timedelta(days=6)])

    def describe(self):
        lines = [f"seed={self.seed}"]
        for movement in self.movements:
            lines.append(
                f"  {movement.kind} {movement.account}->{movement.to_account} {movement.day} +{movement.minute}min "
                f"bank={movement.amount} notified={movement.notified_amount} intl={movement.international} "
                f"merchant={movement.merchant} notices={[(str(d), [(n['app'].split('.')[-1], n['kind'], n['posted_ms'] % 100000) for n in g]) for d, g in movement.notices]} "
                f"sides={[(s['account'], str(s['pending_day']), str(s['posted_day']), str(s['date']), s['same_id']) for s in movement.sides]}"
            )
        return "\n".join(lines)


def _bank_row(movement, side, status, amount_cents, day):
    amount = side["sign"] * amount_cents / 100
    tx_id = side["ids"][0] if status == "PENDING" or side["same_id"] else side["ids"][1]
    if side["account"] == "card":
        raw = card_tx(amount_cents / 100, day.isoformat(), movement.merchant, tx_id=tx_id, status=status, docs_sign=True)
        return raw
    if movement.kind in ("own", "broker"):
        text = "RECEBIMENTO TRANSFERÊNCIA" if side["sign"] > 0 else "PIX ENVIADO"
        return bank_tx(amount, day.isoformat(), text, category_id=SELF_TRANSFER, tx_id=tx_id, status=status,
                       counterparty=movement.counterparty if side["account"] != "corretora" else None)
    if movement.kind == "pix":
        return bank_tx(amount, day.isoformat(), f"PIX ENVIADO {movement.counterparty.upper()}", category_id=PIX_CATEGORY,
                       tx_id=tx_id, status=status, counterparty=movement.counterparty)
    return bank_tx(amount, day.isoformat(), f"COMPRA CARTAO DEB {movement.merchant}", tx_id=tx_id, status=status)


class Run:
    def __init__(self, world, scenario, monkeypatch, invoices_module, user):
        self.world = world
        self.scenario = scenario
        self.monkeypatch = monkeypatch
        self.invoices_module = invoices_module
        self.user = user

    def today(self, day):
        pin_today(self.monkeypatch, self.invoices_module, day)
        self.day = day

    def setup(self):
        self.today(START - timedelta(days=1))
        world = self.world
        self.made = made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
        self.pluggy = {
            "itau": made["itau:0001/1-1"][0], "bb": made["bb:0003/3-3"][0],
            "card": made["btg:4321"][0], "corretora": made["btg:0002/2-2X"][0],
        }
        self.app = {
            "itau": made["itau:0001/1-1"][2], "bb": made["bb:0003/3-3"][2],
            "card": made["btg:4321"][2], "corretora": made["corretora"],
        }
        self.items = {bank: made["items"][bank] for bank in ("itau", "btg", "bb")}
        # Uma linha antiga em cada conta: em producao toda conta tem historico, e
        # a janela do pull de uma conta sem linha nenhuma e so OVERLAP_DAYS.
        old_day = (START - timedelta(days=25)).isoformat()
        self.history = {
            "itau": bank_tx(-1.0, old_day, "TARIFA PACOTE"), "bb": bank_tx(-1.0, old_day, "TARIFA PACOTE"),
            "card": card_tx(1.0, old_day, "ANUIDADE", docs_sign=True),
        }
        self.publish(START - timedelta(days=1))
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE open_finance_accounts SET synced_until = NULL WHERE user_id = ?", (self.user["id"],))
        self.pull(["itau", "btg", "bb"])
        self.pluggy_items = {}
        for pluggy_item, accounts in world.fake.accounts.items():
            for raw in accounts:
                self.pluggy_items[raw["id"]] = pluggy_item

    def bank_state(self, day):
        """O que a Pluggy lista e o saldo do banco no dia `day`."""
        listed = {account: [] for account in self.pluggy}
        for account, raw in self.history.items():
            listed[account].append(dict(raw))
        balance = {"itau": -100, "bb": -100}
        for movement in self.scenario.movements:
            if movement.kind != "preauth" and movement.day <= day:
                # O saldo do banco ja conta o que esta em processamento/pendente.
                for side in movement.sides:
                    if side["account"] in balance:
                        balance[side["account"]] += side["sign"] * movement.amount
            for side in movement.sides:
                if side["posted_day"] <= day:
                    listed[side["account"]].append(_bank_row(movement, side, "POSTED", movement.amount, side["date"]))
                elif side["pending_day"] is not None and side["pending_day"] <= day:
                    listed[side["account"]].append(
                        _bank_row(movement, side, "PENDING", side["pending_amount"], movement.day))
        return listed, balance

    def publish(self, day):
        listed, balance = self.bank_state(day)
        fake = self.world.fake
        for account, rows in listed.items():
            fake.transactions[self.pluggy[account]] = rows
        for accounts in fake.accounts.values():
            for raw in accounts:
                for name, value in balance.items():
                    if raw["id"] == self.pluggy[name]:
                        raw["balance"] = value / 100
        stamp = f"{day.isoformat()}T12:00:00.000Z"
        for pluggy_item in fake.items.values():
            pluggy_item["lastUpdatedAt"] = stamp

    def pull(self, banks):
        for bank in banks:
            self.world.sync(self.items[bank])

    def owner_touches(self):
        rng = self.scenario.rng
        if rng.random() < 0.3:
            queue = self.world.call("get", "/api/review")
            rows = queue.get("rows") or queue.get("items") or []
            if rows:
                row = rng.choice(rows)
                table = row.get("table") or ("cc_expenses" if row.get("card_id") else "transactions")
                confirm(self.world.client, self.world.auth, {"table": table, "id": row["id"]})
        if rng.random() < 0.15:
            purchases = {movement.amount for movement in self.scenario.movements if movement.kind == "debit"}
            purchases |= {movement.notified_amount for movement in self.scenario.movements if movement.kind == "debit"}
            rows = [row for row in self.world.transactions(self.app["itau"])
                    if row["type"] == "EXPENSE" and round(row["amount"] * 100) in purchases]
            if rows:
                row = rng.choice(rows)
                response = self.world.client.patch(
                    f"/api/transactions/{row['id']}", json={"category_id": self.lazer()}, headers=self.world.auth,
                )
                assert response.status_code == 200, response.get_data(as_text=True)

    def lazer(self):
        if not hasattr(self, "_lazer"):
            self._lazer = self.world.category_id("Lazer")
        return self._lazer

    def play(self):
        rng = self.scenario.rng
        self.setup()
        last = self.scenario.last_day()
        final = max(last + timedelta(days=1), START + timedelta(days=13))
        notices = sorted(
            ((day, group) for movement in self.scenario.movements for day, group in movement.notices),
            key=lambda entry: (entry[0], min(notice["posted_ms"] for notice in entry[1])),
        )
        day = START
        while day <= final:
            self.today(day)
            self.publish(day)
            todays = [group for send_day, group in notices if send_day == day]
            todays += [[noise] for noise_day, noise in self.scenario.noise if noise_day == day]
            banks = [bank for bank in self.items if rng.random() < 0.6]
            rng.shuffle(banks)
            # Avisos e pulls em ordem aleatoria dentro do dia.
            steps = [("notice", group) for group in todays] + [("pull", bank) for bank in banks]
            rng.shuffle(steps)
            for step, payload in steps:
                if step == "notice":
                    results = send(self.world.client, self.world.auth, *payload)
                    for notice, result in zip(payload, results):
                        if any(notice is noise for _day, noise in self.scenario.noise):
                            assert result["status"] == "ignored", (self.scenario.describe(), notice, result)
                else:
                    self.pull([payload])
            self.owner_touches()
            day += timedelta(days=1)
        # O ultimo dia: todas as conexoes, duas voltas (cada uma ve as outras lidas).
        self.today(final)
        self.publish(final)
        self.pull(["itau", "btg", "bb"])
        self.pull(["bb", "btg", "itau"])

    # -- as conferencias ---------------------------------------------------

    def check(self):
        message = self.scenario.describe()
        app = self.app
        names = {value: key for key, value in app.items()}
        rows = self.world.transactions()
        got = Counter()
        for row in rows:
            got[(row["type"], names.get(row["account_id"], row["account_id"]),
                 names.get(row.get("transfer_account_id")), round(row["amount"] * 100))] += 1
        expected = Counter({("EXPENSE", "itau", None, 100): 1, ("EXPENSE", "bb", None, 100): 1})
        card_expected = Counter({100: 1})
        for movement in self.scenario.real():
            if movement.kind in ("debit", "pix"):
                expected[("EXPENSE", movement.account, None, movement.amount)] += 1
            elif movement.kind in ("own", "broker"):
                expected[("TRANSFER", movement.account, movement.to_account, movement.amount)] += 1
            else:
                card_expected[movement.amount] += 1
        kinds = {}
        for movement in self.scenario.movements:
            label = movement.kind + ("-intl" if movement.international else "") + (
                "-near" if movement.notified_amount != movement.amount else "")
            kinds[movement.amount] = kinds[movement.notified_amount] = label

        def labelled(counter):
            return sorted((kinds.get(key[3], "?"), key[0], str(key[1])[:8], str(key[2])[:8], key[3], count)
                          for key, count in counter.items())

        assert got == expected, (
            f"{message}\nextra: {labelled(got - expected)}\nmissing: {labelled(expected - got)}"
        )
        card = Counter(round(row["amount"] * 100) for row in self.world.card_rows(app["card"]))
        assert card == card_expected, f"{message}\ncard: {card}\nexpected: {card_expected}"
        balances = {row["id"]: round(row["balance"] * 100) for row in self.world.call("get", "/api/accounts")}
        _listed, truth = self.bank_state(self.day)
        for name in ("itau", "bb"):
            assert balances[app[name]] == truth[name], f"{message}\n{name}: {balances[app[name]]} != {truth[name]}"
        # A transferencia com as duas pontas, uma da Pluggy, sai do Revisar sozinha (Fase 4).
        stuck = [row for row in rows if row["type"] == "TRANSFER" and row["needs_review"]]
        assert stuck == [], f"{message}\nTRANSFER still in review: {stuck}"
        home = self.world.call("get", "/api/home")
        queue = self.world.call("get", "/api/review")
        listed = queue.get("rows") or queue.get("items") or []
        assert home["review_count"] == len(listed), f"{message}\nreview_count {home['review_count']} != {len(listed)}"
        # A porta: nenhum aviso ignorado deixou rastro.
        db = importlib.import_module("db")
        with db.get_db() as conn:
            for _day, noise in self.scenario.noise:
                found = conn.execute(
                    "SELECT COUNT(*) FROM notify_detections WHERE user_id = ? AND amount_cents = ?",
                    (self.user["id"], noise["amount_cents"]),
                ).fetchone()[0]
                assert found == 0, f"{message}\nignored notice left a trace: {noise}"
        waiting = self.world.pending()
        assert waiting == [], f"{message}\nwaiting: {waiting}"
        try:
            assert_identity(self.user["id"])
        except AssertionError as exc:
            raise AssertionError(f"{message}\n{exc}") from None


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    return World(client, auth, fake_pluggy)


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_world(world, user, monkeypatch, invoices_module, seed):
    scenario = Scenario(seed).generate()
    run = Run(world, scenario, monkeypatch, invoices_module, user)
    run.play()
    run.check()
