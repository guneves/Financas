"""Catalogo de ativos negociados na B3 (acoes do Ibovespa, ETFs, FIIs e BDRs).

O objetivo e simples: a busca de ativos da tela de lancamento so oferece papeis
que existem, e o backend recusa a compra de um ticker desconhecido. Isso evita o
erro classico de digitar "PETR5" e ficar com uma posicao fantasma que nenhuma
cotacao do yfinance consegue preencher.

A lista e estatica de proposito -- nao ha dependencia de rede no caminho da
busca. Ela e uma referencia, nao a verdade oficial da B3: quando um papel novo
entrar no indice, basta acrescentar uma linha aqui. Tickers antigos continuam na
lista mesmo apos mudanca de nome (CCRO3/MOTV3, ARZZ3/AZZA3), porque quem tem a
posicao antiga precisa poder lancar movimentos nela.
"""

# kind -> asset_class usado pelo restante do app.
KIND_ASSET_CLASS = {
    "ACAO": "STOCKS",
    "ETF": "STOCKS",
    "BDR": "STOCKS",
    "FII": "REIT",
}

KIND_LABELS = {
    "ACAO": "Acao",
    "ETF": "ETF",
    "BDR": "BDR",
    "FII": "FII",
}

# (ticker, nome, kind)
_RAW_CATALOG = [
    # --- Acoes (carteira do Ibovespa e large caps proximas) ---
    ("ABEV3", "Ambev", "ACAO"),
    ("ALOS3", "Allos", "ACAO"),
    ("ALPA4", "Alpargatas PN", "ACAO"),
    ("ASAI3", "Assai", "ACAO"),
    ("AURE3", "Auren Energia", "ACAO"),
    ("AZUL4", "Azul PN", "ACAO"),
    ("AZZA3", "Azzas 2154", "ACAO"),
    ("ARZZ3", "Arezzo (atual AZZA3)", "ACAO"),
    ("B3SA3", "B3", "ACAO"),
    ("BBAS3", "Banco do Brasil", "ACAO"),
    ("BBDC3", "Bradesco ON", "ACAO"),
    ("BBDC4", "Bradesco PN", "ACAO"),
    ("BBSE3", "BB Seguridade", "ACAO"),
    ("BEEF3", "Minerva", "ACAO"),
    ("BPAC11", "BTG Pactual Unit", "ACAO"),
    ("BRAP4", "Bradespar PN", "ACAO"),
    ("BRAV3", "Brava Energia", "ACAO"),
    ("BRFS3", "BRF", "ACAO"),
    ("BRKM5", "Braskem PNA", "ACAO"),
    ("CCRO3", "CCR (atual MOTV3)", "ACAO"),
    ("CMIG3", "Cemig ON", "ACAO"),
    ("CMIG4", "Cemig PN", "ACAO"),
    ("CMIN3", "CSN Mineracao", "ACAO"),
    ("COGN3", "Cogna Educacao", "ACAO"),
    ("CPFE3", "CPFL Energia", "ACAO"),
    ("CPLE3", "Copel ON", "ACAO"),
    ("CPLE6", "Copel PNB", "ACAO"),
    ("CRFB3", "Carrefour Brasil", "ACAO"),
    ("CSAN3", "Cosan", "ACAO"),
    ("CSNA3", "CSN Siderurgica Nacional", "ACAO"),
    ("CVCB3", "CVC Brasil", "ACAO"),
    ("CXSE3", "Caixa Seguridade", "ACAO"),
    ("CYRE3", "Cyrela", "ACAO"),
    ("DIRR3", "Direcional Engenharia", "ACAO"),
    ("EGIE3", "Engie Brasil", "ACAO"),
    ("ELET3", "Eletrobras ON", "ACAO"),
    ("ELET6", "Eletrobras PNB", "ACAO"),
    ("EMBR3", "Embraer", "ACAO"),
    ("ENEV3", "Eneva", "ACAO"),
    ("ENGI11", "Energisa Unit", "ACAO"),
    ("EQTL3", "Equatorial Energia", "ACAO"),
    ("FLRY3", "Fleury", "ACAO"),
    ("GGBR3", "Gerdau ON", "ACAO"),
    ("GGBR4", "Gerdau PN", "ACAO"),
    ("GMAT3", "Grupo Mateus", "ACAO"),
    ("GOAU4", "Metalurgica Gerdau PN", "ACAO"),
    ("HAPV3", "Hapvida", "ACAO"),
    ("HYPE3", "Hypera Pharma", "ACAO"),
    ("IGTI11", "Iguatemi Unit", "ACAO"),
    ("IRBR3", "IRB Brasil RE", "ACAO"),
    ("ISAE3", "ISA Energia ON", "ACAO"),
    ("ISAE4", "ISA Energia PN", "ACAO"),
    ("ITSA4", "Itausa PN", "ACAO"),
    ("ITUB3", "Itau Unibanco ON", "ACAO"),
    ("ITUB4", "Itau Unibanco PN", "ACAO"),
    ("KLBN4", "Klabin PN", "ACAO"),
    ("KLBN11", "Klabin Unit", "ACAO"),
    ("LREN3", "Lojas Renner", "ACAO"),
    ("LWSA3", "Locaweb", "ACAO"),
    ("MGLU3", "Magazine Luiza", "ACAO"),
    ("MOTV3", "Motiva (ex-CCR)", "ACAO"),
    ("MRFG3", "Marfrig", "ACAO"),
    ("MRVE3", "MRV Engenharia", "ACAO"),
    ("MULT3", "Multiplan", "ACAO"),
    ("NATU3", "Natura &Co", "ACAO"),
    ("PCAR3", "Grupo Pao de Acucar", "ACAO"),
    ("PETR3", "Petrobras ON", "ACAO"),
    ("PETR4", "Petrobras PN", "ACAO"),
    ("PETZ3", "Petz", "ACAO"),
    ("POMO4", "Marcopolo PN", "ACAO"),
    ("PRIO3", "PRIO", "ACAO"),
    ("PSSA3", "Porto Seguro", "ACAO"),
    ("RADL3", "Raia Drogasil", "ACAO"),
    ("RAIL3", "Rumo", "ACAO"),
    ("RAIZ4", "Raizen PN", "ACAO"),
    ("RDOR3", "Rede DOr Sao Luiz", "ACAO"),
    ("RECV3", "PetroReconcavo", "ACAO"),
    ("RENT3", "Localiza", "ACAO"),
    ("SANB11", "Santander Brasil Unit", "ACAO"),
    ("SBSP3", "Sabesp", "ACAO"),
    ("SLCE3", "SLC Agricola", "ACAO"),
    ("SMFT3", "Smart Fit", "ACAO"),
    ("SMTO3", "Sao Martinho", "ACAO"),
    ("STBP3", "Santos Brasil", "ACAO"),
    ("SUZB3", "Suzano", "ACAO"),
    ("TAEE11", "Taesa Unit", "ACAO"),
    ("TIMS3", "TIM Brasil", "ACAO"),
    ("TOTS3", "Totvs", "ACAO"),
    ("UGPA3", "Ultrapar", "ACAO"),
    ("USIM5", "Usiminas PNA", "ACAO"),
    ("VALE3", "Vale", "ACAO"),
    ("VAMO3", "Vamos", "ACAO"),
    ("VBBR3", "Vibra Energia", "ACAO"),
    ("VIVA3", "Vivara", "ACAO"),
    ("VIVT3", "Telefonica Brasil (Vivo)", "ACAO"),
    ("WEGE3", "WEG", "ACAO"),
    ("YDUQ3", "YDUQS", "ACAO"),

    # --- ETFs ---
    ("BOVA11", "iShares Ibovespa", "ETF"),
    ("BOVV11", "It Now Ibovespa", "ETF"),
    ("BOVB11", "BTG Ibovespa", "ETF"),
    ("PIBB11", "It Now IBrX-50", "ETF"),
    ("SMAL11", "iShares Small Cap", "ETF"),
    ("DIVO11", "It Now Dividendos IDIV", "ETF"),
    ("ECOO11", "iShares Indice Carbono Eficiente", "ETF"),
    ("ISUS11", "It Now ISE Sustentabilidade", "ETF"),
    ("GOVE11", "It Now Governanca IGCT", "ETF"),
    ("MATB11", "It Now Materiais Basicos", "ETF"),
    ("XFIX11", "Trend Fundos Imobiliarios IFIX", "ETF"),
    ("IVVB11", "iShares S&P 500", "ETF"),
    ("SPXI11", "It Now S&P 500", "ETF"),
    ("NASD11", "Trend Nasdaq-100", "ETF"),
    ("QBTC11", "Hashdex Bitcoin", "ETF"),
    ("HASH11", "Hashdex Crypto Index", "ETF"),
    ("BITH11", "Hashdex Bitcoin BITH11", "ETF"),
    ("ETHE11", "Hashdex Ethereum", "ETF"),
    ("QETH11", "QR Ethereum", "ETF"),
    ("WRLD11", "Trend MSCI World", "ETF"),
    ("ACWI11", "iShares MSCI ACWI", "ETF"),
    ("EURP11", "Trend Europa", "ETF"),
    ("XINA11", "Trend China", "ETF"),
    ("TECK11", "Trend Tecnologia EUA", "ETF"),
    ("USTK11", "Trend Acoes EUA", "ETF"),
    ("BDRX11", "It Now BDRX", "ETF"),
    ("GOLD11", "Trend Ouro", "ETF"),
    ("IMAB11", "It Now IMA-B Tesouro IPCA", "ETF"),
    ("IB5M11", "It Now IMA-B 5+", "ETF"),
    ("B5P211", "It Now IMA-B 5", "ETF"),
    ("IRFM11", "It Now IRF-M Prefixados", "ETF"),
    ("FIXA11", "Mirae Prefixado Futuro", "ETF"),
    ("DEBB11", "It Now Debentures Incentivadas", "ETF"),

    # --- Fundos Imobiliarios ---
    ("MXRF11", "Maxi Renda", "FII"),
    ("HGLG11", "CSHG Logistica", "FII"),
    ("KNRI11", "Kinea Renda Imobiliaria", "FII"),
    ("KNCR11", "Kinea Rendimentos Imobiliarios", "FII"),
    ("KNIP11", "Kinea Indices de Precos", "FII"),
    ("KNSC11", "Kinea Securities", "FII"),
    ("XPML11", "XP Malls", "FII"),
    ("XPLG11", "XP Log", "FII"),
    ("XPIN11", "XP Industrial", "FII"),
    ("XPCI11", "XP Credito Imobiliario", "FII"),
    ("HGRU11", "CSHG Renda Urbana", "FII"),
    ("HGRE11", "CSHG Real Estate", "FII"),
    ("HGBS11", "CSHG Brasil Shopping", "FII"),
    ("HGCR11", "CSHG Recebiveis Imobiliarios", "FII"),
    ("HGFF11", "CSHG Fundo de Fundos", "FII"),
    ("VISC11", "Vinci Shopping Centers", "FII"),
    ("VILG11", "Vinci Logistica", "FII"),
    ("VINO11", "Vinci Offices", "FII"),
    ("VGHF11", "Valora Hedge Fund", "FII"),
    ("VGIR11", "Valora CRI CDI", "FII"),
    ("BTLG11", "BTG Pactual Logistica", "FII"),
    ("BCFF11", "BTG Pactual Fundo de Fundos", "FII"),
    ("BRCO11", "Bresco Logistica", "FII"),
    ("LVBI11", "VBI Logistico", "FII"),
    ("PVBI11", "VBI Prime Properties", "FII"),
    ("IRDM11", "Iridium Recebiveis Imobiliarios", "FII"),
    ("RBRF11", "RBR Alpha Fundo de Fundos", "FII"),
    ("RBRR11", "RBR High Grade", "FII"),
    ("RBRP11", "RBR Properties", "FII"),
    ("RBRY11", "RBR Credito Imobiliario", "FII"),
    ("RECT11", "REC Renda Imobiliaria", "FII"),
    ("RZTR11", "Riza Terrax", "FII"),
    ("MALL11", "Malls Brasil Plural", "FII"),
    ("HSML11", "HSI Malls", "FII"),
    ("HSLG11", "HSI Logistica", "FII"),
    ("TRXF11", "TRX Real Estate", "FII"),
    ("ALZR11", "Alianza Trust Renda Imobiliaria", "FII"),
    ("GGRC11", "GGR Covepi Renda", "FII"),
    ("JSRE11", "JS Real Estate Multigestao", "FII"),
    ("MCCI11", "Maua Capital Recebiveis Imobiliarios", "FII"),
    ("CPTS11", "Capitania Securities", "FII"),
    ("CVBI11", "VBI CRI", "FII"),
    ("AFHI11", "AF Invest CRI", "FII"),
    ("SNCI11", "Suno Recebiveis Imobiliarios", "FII"),
    ("SNFF11", "Suno Fundo de Fundos", "FII"),
    ("VRTA11", "Fator Verita", "FII"),
    ("TGAR11", "TG Ativo Real", "FII"),
    ("FIIB11", "Industrial do Brasil", "FII"),
    ("KFOF11", "Kinea Fundo de Fundos", "FII"),
    ("HTMX11", "Hotel Maxinvest", "FII"),
    ("DEVA11", "Devant Recebiveis Imobiliarios", "FII"),
    ("HCTR11", "Hectare CE", "FII"),

    # --- BDRs mais negociados ---
    ("AAPL34", "Apple", "BDR"),
    ("MSFT34", "Microsoft", "BDR"),
    ("AMZO34", "Amazon", "BDR"),
    ("GOGL34", "Alphabet (Google)", "BDR"),
    ("META34", "Meta Platforms", "BDR"),
    ("TSLA34", "Tesla", "BDR"),
    ("NVDC34", "NVIDIA", "BDR"),
    ("NFLX34", "Netflix", "BDR"),
    ("ROXO34", "Nu Holdings (Nubank)", "BDR"),
    ("COCA34", "Coca-Cola", "BDR"),
    ("MCDC34", "McDonalds", "BDR"),
    ("SBUB34", "Starbucks", "BDR"),
    ("NIKE34", "Nike", "BDR"),
    ("WALM34", "Walmart", "BDR"),
    ("DISB34", "Walt Disney", "BDR"),
    ("JPMC34", "JPMorgan Chase", "BDR"),
    ("BOAC34", "Bank of America", "BDR"),
    ("GSGI34", "Goldman Sachs", "BDR"),
    ("VISA34", "Visa", "BDR"),
    ("MSCD34", "Mastercard", "BDR"),
    ("PYPL34", "PayPal", "BDR"),
    ("BERK34", "Berkshire Hathaway", "BDR"),
    ("JNJB34", "Johnson & Johnson", "BDR"),
    ("PFIZ34", "Pfizer", "BDR"),
    ("MRCK34", "Merck", "BDR"),
    ("ABBV34", "AbbVie", "BDR"),
    ("LILY34", "Eli Lilly", "BDR"),
    ("UNHH34", "UnitedHealth", "BDR"),
    ("PGCO34", "Procter & Gamble", "BDR"),
    ("EXXO34", "Exxon Mobil", "BDR"),
    ("CHVX34", "Chevron", "BDR"),
    ("BOEI34", "Boeing", "BDR"),
    ("CATP34", "Caterpillar", "BDR"),
    ("HONB34", "Honeywell", "BDR"),
    ("LMTB34", "Lockheed Martin", "BDR"),
    ("ORCL34", "Oracle", "BDR"),
    ("CSCO34", "Cisco", "BDR"),
    ("INTC34", "Intel", "BDR"),
    ("AMDD34", "AMD", "BDR"),
    ("QCOM34", "Qualcomm", "BDR"),
    ("ADBE34", "Adobe", "BDR"),
    ("CRMI34", "Salesforce", "BDR"),
    ("TSMC34", "TSMC", "BDR"),
    ("BABA34", "Alibaba", "BDR"),
    ("XPBR31", "XP Inc.", "BDR"),
]


def _build_entry(ticker, name, kind):
    return {
        "ticker": ticker,
        "name": name,
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "asset_class": KIND_ASSET_CLASS[kind],
    }


CATALOG = [_build_entry(*row) for row in _RAW_CATALOG]
CATALOG_BY_TICKER = {entry["ticker"]: entry for entry in CATALOG}


def normalize_ticker(value):
    """Aceita 'petr4', ' PETR4 ' e 'PETR4.SA' como o mesmo papel."""
    normalized = str(value or "").strip().upper()
    if normalized.endswith(".SA"):
        normalized = normalized[:-3]
    return normalized


def lookup(ticker):
    """Entrada do catalogo, ou None se o papel nao for conhecido."""
    return CATALOG_BY_TICKER.get(normalize_ticker(ticker))


def is_known(ticker):
    return normalize_ticker(ticker) in CATALOG_BY_TICKER


def _name_key(name):
    return str(name or "").strip().upper()


def search(query="", asset_class=None, kind=None, limit=20):
    """Busca por ticker ou nome.

    A ordenacao segue o que o usuario espera de um autocomplete: quem comeca com
    o que foi digitado vem primeiro (PETR3 antes de SPXI11 para "PET"), depois
    quem contem o texto no ticker, depois quem bate pelo nome da empresa.
    """
    needle = normalize_ticker(query)
    normalized_class = str(asset_class or "").strip().upper() or None
    normalized_kind = str(kind or "").strip().upper() or None

    results = []
    for entry in CATALOG:
        if normalized_class and entry["asset_class"] != normalized_class:
            continue
        if normalized_kind and entry["kind"] != normalized_kind:
            continue

        if not needle:
            rank = 3
        elif entry["ticker"].startswith(needle):
            rank = 0
        elif needle in entry["ticker"]:
            rank = 1
        elif needle in _name_key(entry["name"]):
            rank = 2
        else:
            continue

        results.append((rank, entry["ticker"], entry))

    results.sort(key=lambda item: (item[0], item[1]))

    try:
        max_results = int(limit)
    except (TypeError, ValueError):
        max_results = 20
    max_results = max(1, min(max_results, 100))

    return [entry for _, _, entry in results[:max_results]]
