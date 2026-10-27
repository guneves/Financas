"""A categoria da Pluggy -> a categoria do dono (puro, como market_catalog.py).

O Open Finance gravado sozinho (044) categoriza nesta ordem: a regra de
importacao do dono que casa com a descricao; senao esta tabela, pela categoria
que a Pluggy deu; senao a padrao do app ("Outros" na despesa, "Receita" na
receita — o que o app chama de sem categoria). A tabela da so o NOME: quem usa
resolve o id nas categorias do dono, e um nome que ele nao tem (apagou,
renomeou) cai na padrao.

Os ids da Pluggy tem 8 digitos em arvore (01000000 Income, 01010000 Salary...):
vale o mais especifico que estiver aqui — o id inteiro, depois os 4 primeiros
digitos, depois os 2.
"""

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


def expected_type(name):
    """Receita so vale para entradas; as outras, para saidas."""
    return "INCOME" if name == RECEITA else "EXPENSE"
