"""O nome e a categoria de uma transacao da Pluggy (puro, como market_catalog.py).

O Open Finance gravado sozinho (044) categoriza nesta ordem (quem chama:
open_finance_inbox.category_decision()): a regra de importacao do dono; a
tabela de comerciantes (`keyword_categories()`, pelo comerciante, pelo outro
lado do Pix e pela descricao limpa); o CNAE do comerciante (`cnae_categories()`);
a categoria que a Pluggy deu (`pluggy_category_names()`); a padrao do app
("Outros" na despesa, "Receita" na receita — o que o app chama de sem
categoria). As tabelas dao so NOMES, em ordem de preferencia: quem usa fica com
o primeiro que o dono tem ativo (nunca inventa categoria), e nenhum cai no passo
seguinte.

`clean_description()` / `display_name()`: o nome legivel do lancamento, sem o
prefixo do banco, datas e marcas de parcela. A descricao crua fica em
open_finance_transactions (as regras do dono casam com ela).

Os ids da Pluggy tem 8 digitos em arvore (01000000 Income, 01010000 Salary...):
vale o mais especifico que estiver aqui — o id inteiro, depois os 4 primeiros
digitos, depois os 2.
"""

import re
import unicodedata

# Os nomes das categorias que o app cria para todo usuario (services/accounts.py).
RECEITA = "Receita"
ALIMENTACAO = "Alimentação"
MORADIA = "Moradia"
TRANSPORTE = "Transporte"
SAUDE = "Saúde"
EDUCACAO = "Educação"
LAZER = "Lazer"
SERVICOS = "Serviços"
OUTROS = "Outros"
# Do dono (2026-10-30); nem todo usuario tem: sempre com uma alternativa.
COMPRAS = "Compras"

PLUGGY_CATEGORY_NAMES = {
    # 01 Income: salario, aposentadoria, renda de autonomo, auxilio, eventuais.
    "01": RECEITA,
    # 02 Loans and financing; 06 Legal obligations; 13 Donations; 15 Taxes.
    "02": OUTROS,
    "06": OUTROS,
    "13": OUTROS,
    "15": OUTROS,
    # 03 Investments: so o provento chega como receita; o resto e carteira (039).
    "0306": RECEITA,
    # 07 Services.
    "07": SERVICOS,
    "0701": SERVICOS,   # Telecommunications
    "0702": EDUCACAO,   # Education
    "0703": SAUDE,      # Wellness and fitness
    "0704": LAZER,      # Tickets
    # 08 Shopping.
    "08": OUTROS,
    # 09 Digital services (streaming, apps).
    "09": SERVICOS,
    # 10 Groceries; 11 Food and drinks (restaurante, delivery).
    "10": ALIMENTACAO,
    "11": ALIMENTACAO,
    # 12 Travel; 14 Gambling; 21 Leisure.
    "12": LAZER,
    "14": LAZER,
    "21": LAZER,
    # 16 Bank fees; 20 Insurance.
    "16": SERVICOS,
    "20": SERVICOS,
    # 17 Housing (aluguel, agua, luz, gas, casa).
    "17": MORADIA,
    # 18 Healthcare (farmacia, hospital, dentista).
    "18": SAUDE,
    # 19 Transportation (app de corrida, onibus, combustivel, pedagio).
    "19": TRANSPORTE,
}


def pluggy_category_name(category_id):
    """O nome da categoria do dono para o id da Pluggy, ou None (transferencias,
    pagamento de fatura, investimento, id desconhecido)."""
    text = "".join(ch for ch in str(category_id or "") if ch.isdigit())
    if len(text) != 8:
        return None
    for key in (text, text[:4], text[:2]):
        if key in PLUGGY_CATEGORY_NAMES:
            return PLUGGY_CATEGORY_NAMES[key]
    return None


# Onde ha uma categoria melhor que a do nome acima, ou o dono nao tem aquela.
PLUGGY_PREFERENCES = {
    "08": (COMPRAS, OUTROS),
    "17": (MORADIA, SERVICOS),
}


def pluggy_category_names(category_id):
    """Os nomes para o id da Pluggy, em ordem de preferencia."""
    name = pluggy_category_name(category_id)
    if not name:
        return ()
    prefix = "".join(ch for ch in str(category_id or "") if ch.isdigit())[:2]
    return PLUGGY_PREFERENCES.get(prefix, (name,))


def expected_type(name):
    """Receita so vale para entradas; as outras, para saidas."""
    return "INCOME" if name == RECEITA else "EXPENSE"


# ---------------------------------------------------------------------------
# Comerciantes
# ---------------------------------------------------------------------------

UTILITIES = (MORADIA, SERVICOS)
SHOPPING = (COMPRAS, OUTROS)

# Na ordem: o primeiro grupo que casa decide, entao o composto vem antes do termo
# geral ("uber eats" antes de "uber", "mercado livre" antes de "mercado"). Casam
# palavras inteiras do texto sem acento e em minusculas; palavra comum ("extra",
# "big", "dia", "bar") fica de fora: casaria errado.
MERCHANT_KEYWORDS = (
    ((ALIMENTACAO,), ("uber eats", "ifood", "ifd", "rappi", "ze delivery", "aiqfome", "james delivery")),
    ((LAZER,), ("amazon prime", "prime video", "primevideo", "youtube premium", "youtubepremium")),
    (SHOPPING, ("mercado livre", "mercadolivre", "mercadolibre", "shopee", "shein", "aliexpress", "amazon",
                "magazine luiza", "magalu", "americanas", "casas bahia", "ponto frio", "kabum", "renner",
                "riachuelo", "zara", "centauro", "decathlon", "netshoes", "leroy merlin", "telhanorte", "kalunga",
                "havan", "ikea", "tok stok", "tokstok", "livraria")),
    ((SAUDE,), ("posto de saude", "drogaria", "drogarias", "drogasil", "droga raia", "drogaraia", "raia",
                "pague menos", "panvel", "farmacia", "farmacias", "drogao", "ultrafarma", "nissei", "onofre",
                "unimed", "amil", "bradesco saude", "sulamerica", "hapvida", "notredame", "hospital", "clinica",
                "laboratorio", "fleury", "dentista", "odonto", "odontologia", "psicologo", "psicologa",
                "smart fit", "smartfit", "bluefit", "gympass", "wellhub", "totalpass", "academia")),
    ((ALIMENTACAO,), ("mcdonald", "mcdonalds", "burger king", "subway", "habibs", "outback", "starbucks", "padaria",
                      "panificadora", "restaurante", "lanchonete", "pizzaria", "churrascaria", "sushi", "cafeteria",
                      "sorveteria", "acougue", "hortifruti", "hortifrutti", "carrefour", "pao de acucar", "assai",
                      "atacadao", "bretas", "supermercado", "supermercados", "mercado", "mercadinho", "mercearia",
                      "sams club", "zaffari", "mambo", "st marche", "savegnago", "angeloni", "muffato", "prezunic")),
    ((TRANSPORTE,), ("uber", "ubertrip", "99app", "99 app", "99pop", "99 pop", "99 taxi", "99 tecnologia",
                     "99tecnologia", "cabify", "indriver", "sem parar", "semparar", "conectcar", "veloe",
                     "ipiranga", "shell", "petrobras", "posto", "auto posto", "combustivel", "combustiveis",
                     "estacionamento", "estapar", "pedagio", "metro", "cptm", "bilhete unico", "sptrans")),
    ((LAZER,), ("netflix", "spotify", "disney", "disneyplus", "hbo", "hbomax", "globoplay", "deezer", "apple tv",
                "paramount", "crunchyroll", "twitch", "steam", "playstation", "xbox", "nintendo", "cinema", "cinemark",
                "ingresso", "ingressos", "sympla", "ticketmaster", "eventim", "airbnb", "booking", "decolar",
                "latam", "gol linhas", "azul linhas", "hotel", "pousada")),
    ((EDUCACAO,), ("escola", "colegio", "faculdade", "universidade", "udemy", "alura", "coursera", "duolingo",
                   "curso")),
    (UTILITIES, ("enel", "cemig", "cpfl", "coelba", "celesc", "energisa", "neoenergia", "equatorial", "sabesp",
                 "copasa", "sanepar", "cedae", "embasa", "comgas", "naturgy", "aluguel", "condominio")),
    ((SERVICOS,), ("vivo", "claro", "tim", "telefonica", "algar", "sky", "apple com", "icloud", "google", "microsoft",
                   "openai", "anthropic", "github", "dropbox", "porto seguro", "seguro", "tarifa", "anuidade",
                   "barbearia", "lavanderia")),
)


def plain_text(text):
    """Minusculas, sem acento, so letras e numeros separados por um espaco."""
    folded = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", folded).strip()


_KEYWORD_PATTERNS = tuple(
    (names, re.compile(r"\b(?:" + "|".join(re.escape(term) for term in terms) + r")\b"))
    for names, terms in MERCHANT_KEYWORDS
)


def keyword_categories(*texts):
    """Os nomes do primeiro comerciante conhecido nos textos, ou ()."""
    plain = " ".join(plain_text(text) for text in texts if text)
    if not plain:
        return ()
    for names, pattern in _KEYWORD_PATTERNS:
        if pattern.search(plain):
            return names
    return ()


# CNAE (so os digitos): vale o prefixo mais longo que estiver aqui.
CNAE_CATEGORIES = {
    "4711": (ALIMENTACAO,), "4712": (ALIMENTACAO,), "472": (ALIMENTACAO,), "56": (ALIMENTACAO,),
    "4731": (TRANSPORTE,), "49": (TRANSPORTE,), "5223": (TRANSPORTE,), "5229": (TRANSPORTE,),
    "4771": (SAUDE,), "86": (SAUDE,), "87": (SAUDE,), "9313": (SAUDE,),
    "85": (EDUCACAO,),
    "55": (LAZER,), "59": (LAZER,), "79": (LAZER,), "90": (LAZER,), "91": (LAZER,), "93": (LAZER,),
    "35": UTILITIES, "36": UTILITIES,
    "61": (SERVICOS,), "62": (SERVICOS,), "63": (SERVICOS,), "65": (SERVICOS,), "95": (SERVICOS,), "96": (SERVICOS,),
    "45": SHOPPING, "47": SHOPPING,
}


def cnae_categories(cnae):
    digits = "".join(ch for ch in str(cnae or "") if ch.isdigit())
    for size in (4, 3, 2):
        if len(digits) >= size and digits[:size] in CNAE_CATEGORIES:
            return CNAE_CATEGORIES[digits[:size]]
    return ()


# ---------------------------------------------------------------------------
# O nome legivel
# ---------------------------------------------------------------------------

_BANK_PREFIX = re.compile(
    r"^\s*(?:"
    r"compra\s+(?:com\s+|no\s+|de\s+)?cart[aã]o(?:\s+(?:de\s+)?(?:d[eé]bito|cr[eé]dito))?"
    r"|compra\s+(?:no\s+)?(?:d[eé]bito|cr[eé]dito)"
    r"|compra\s+internacional|compra\s+a\s+vista|compra\s+aprovada|compra"
    r"|d[eé]bito\s+autom[aá]tico|cart[aã]o"
    r"|pix\s+(?:enviado|recebido|transf(?:er[eê]ncia)?|qrs|qr\s+code|agendado)(?:\s+(?:para|de))?|pix(?:\s+(?:para|de))?"
    r"|transfer[eê]ncia\s+(?:enviada|recebida)(?:\s+(?:para|de))?|ted|doc"
    r"|pagto|pag(?:amento)?\s+(?:de|com)\s+boleto"
    r"|pag\s*\*|pg\s*\*|mp\s*\*|ec\s*\*|sumup\s*\*|ifd\s*\*"
    r")(?:(?<=\*)|(?=[\s*:\-]|$))[\s*:\-]*",
    re.IGNORECASE,
)
_INSTALLMENT = re.compile(
    r"\bparc(?:ela)?\.?\s*\d{1,2}\s*(?:/|de)\s*\d{1,2}\b|\b\d{1,2}\s*/\s*\d{1,2}\b(?!/)", re.IGNORECASE,
)
_DATE = re.compile(r"\b\d{2}[/-]\d{2}[/-]\d{2,4}\b|\b\d{2}[/-]\d{2}\b")
_TIME = re.compile(r"\b\d{2}:\d{2}(?::\d{2})?\b")
_TRAILING_COUNTRY = re.compile(r"\s+(?:BR|BRA)$")
_LOWER_WORDS = {"de", "da", "do", "das", "dos", "e", "para"}


def readable_case(text):
    """Um texto todo em maiusculas fica legivel; o resto, como veio."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters or sum(ch.isupper() for ch in letters) < len(letters) * 0.8:
        return text
    words = text.lower().split(" ")
    return " ".join(
        word if index and word in _LOWER_WORDS else word[:1].upper() + word[1:]
        for index, word in enumerate(words)
    )


def clean_description(text):
    """A descricao do banco sem prefixo, datas e parcela; a original (so com o
    caso arrumado) se nao sobra nada."""
    original = re.sub(r"\s+", " ", str(text or "")).strip()
    if not original:
        return None
    current = _DATE.sub(" ", _TIME.sub(" ", _INSTALLMENT.sub(" ", original)))
    for _ in range(3):
        stripped = _BANK_PREFIX.sub("", current, count=1)
        if stripped == current:
            break
        current = stripped
    current = re.sub(r"\s*\*+\s*", " ", current)
    current = re.sub(r"\s+", " ", current).strip(" -:/.")
    current = _TRAILING_COUNTRY.sub("", current).strip()
    return readable_case(current if len(plain_text(current)) >= 2 else original)


def display_name(description, merchant_name=None, counterparty=None, movement=None, direction=None):
    """O nome do lancamento: o comerciante; no Pix/TED para alguem, quem esta do
    outro lado; senao a descricao limpa."""
    if merchant_name:
        return readable_case(re.sub(r"\s+", " ", merchant_name).strip())
    if counterparty and movement in ("TRANSFER", "SELF_TRANSFER"):
        kind = "Pix" if "pix" in plain_text(description).split() else "Transferência"
        return f"{kind} {'para' if direction == 'OUT' else 'de'} {readable_case(counterparty.strip())}"
    return clean_description(description)
