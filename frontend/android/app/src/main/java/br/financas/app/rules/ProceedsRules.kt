// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/proceedsRules.js (proceedsRules.test.js); aqui ProceedsRulesTest.kt,
// os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

/**
 * Registrar provento: que tipo cada ativo recebe e que campos cada tipo pede. A categoria vem do
 * servidor (`category` de /api/assets): ACAO, ETF, BDR, FII, RENDA_FIXA, TESOURO, CRIPTO, OTHER.
 * O servidor recusa so o que a classe nunca recebe; aqui o filtro e mais fino:
 * - JCP e de sociedade anonima (Lei 9.249/1995, art. 9o): so acoes, nunca ETF, BDR ou FII;
 * - dividendos: acoes, ETFs que distribuem, BDRs e os rendimentos de FII;
 * - amortizacao: FII, acao, renda fixa e, no Tesouro, so Renda+ e Educa+;
 * - juros (cupom): renda fixa e, no Tesouro, so os com juros semestrais (NTN-B, NTN-F). Um titulo
 *   do Tesouro cujo nome nao diz o produto fica nos dois.
 */
object ProceedsRules {
    data class Choice(val value: String, val label: String)

    /** Um ativo de /api/assets (ou da carteira), so o que estas regras leem. */
    data class Asset(
        val id: String,
        val ticker: String? = null,
        val name: String? = null,
        val category: String? = null,
        /** `asset_class` de /api/assets ou `class` da carteira. */
        val assetClass: String? = null,
    )

    /** O campo de IR do formulario. */
    data class TaxField(val label: String, val hint: String)

    val PROCEEDS_TYPES = listOf(
        Choice("DIVIDEND", "Dividendos"),
        Choice("JCP", "JCP"),
        Choice("AMORTIZATION", "Amortização"),
        Choice("INTEREST", "Juros (cupom)"),
    )

    val CATEGORY_LABELS = mapOf(
        "ACAO" to "Ações",
        "ETF" to "ETFs",
        "BDR" to "BDRs",
        "FII" to "FIIs",
        "RENDA_FIXA" to "Renda fixa",
        "TESOURO" to "Tesouro Direto",
        "CRIPTO" to "Cripto",
        "OTHER" to "Outros",
    )

    /** Abaixo do tipo, no formulario: quem pode ter este provento. */
    val TYPE_HINTS = mapOf(
        "DIVIDEND" to "Ações, ETFs, BDRs e FIIs (rendimentos).",
        "JCP" to "Só ações: ETF, BDR e FII não pagam JCP.",
        "AMORTIZATION" to "FIIs, ações, renda fixa e Tesouro Renda+/Educa+.",
        "INTEREST" to "Renda fixa e Tesouro com juros semestrais.",
    )

    private val TYPE_CATEGORIES = mapOf(
        "DIVIDEND" to listOf("ACAO", "ETF", "BDR", "FII"),
        "JCP" to listOf("ACAO"),
        "AMORTIZATION" to listOf("ACAO", "FII", "RENDA_FIXA", "TESOURO"),
        "INTEREST" to listOf("RENDA_FIXA", "TESOURO"),
    )

    private val FIXED_INCOME_CATEGORIES = listOf("RENDA_FIXA", "TESOURO")

    private val CLASS_CATEGORY = mapOf("STOCKS" to "ACAO", "REIT" to "FII", "FIXED_INCOME" to "RENDA_FIXA", "OTHER" to "OTHER")

    /** A categoria do ativo; sem ela (resposta antiga), a da classe. */
    fun assetCategory(asset: Asset?): String? {
        if (asset == null) return null
        return asset.category.takeUnless { it.isNullOrEmpty() }
            ?: CLASS_CATEGORY[asset.assetClass]
            ?: "OTHER"
    }

    fun categoryLabel(asset: Asset?): String = CATEGORY_LABELS[assetCategory(asset)] ?: ""

    fun isFixedIncomeCategory(category: String?): Boolean = category in FIXED_INCOME_CATEGORIES

    private val INSTALLMENTS = Regex("RENDA ?\\+|EDUCA ?\\+")
    private val NTN_F = Regex("\\bNTN-?F\\b")
    private val NTN_B = Regex("\\bNTN-?B\\b")
    private val BULLET = Regex("SELIC|PREFIXADO|PRE-FIXADO|IPCA|\\bLFT\\b|\\bLTN\\b")

    /**
     * O produto do Tesouro pelo nome: COUPON (juros semestrais), INSTALLMENTS (Renda+, Educa+),
     * BULLET (Selic, Prefixado, IPCA+ sem juros) ou null quando o nome nao diz.
     */
    fun treasuryProduct(name: String?): String? {
        val text = AssetSearch.normalizeSearchText(name)
        if (text.isEmpty()) return null
        if (INSTALLMENTS.containsMatchIn(text)) return "INSTALLMENTS"
        if (text.contains("JUROS SEMESTRAIS") || NTN_F.containsMatchIn(text)) return "COUPON"
        if (NTN_B.containsMatchIn(text)) return if (text.contains("PRINCIPAL")) "BULLET" else "COUPON"
        if (BULLET.containsMatchIn(text)) return "BULLET"
        return null
    }

    private fun assetName(asset: Asset?): String =
        asset?.ticker.takeUnless { it.isNullOrEmpty() } ?: asset?.name.takeUnless { it.isNullOrEmpty() } ?: ""

    fun proceedsTypeFitsAsset(type: String?, asset: Asset?): Boolean {
        val category = assetCategory(asset)
        if (category !in (TYPE_CATEGORIES[type] ?: emptyList())) return false
        if (category != "TESOURO") return true
        val product = treasuryProduct(assetName(asset))
        if (type == "INTEREST") return product == "COUPON" || product == null
        if (type == "AMORTIZATION") return product == "INSTALLMENTS" || product == null
        return true
    }

    /** Os ativos que podem ter este tipo; [keepId] (o da edicao) fica mesmo que nao caiba. */
    fun assetsForProceedsType(assets: List<Asset>?, type: String?, keepId: String = ""): List<Asset> =
        (assets ?: emptyList()).filter { asset ->
            proceedsTypeFitsAsset(type, asset) || (keepId.isNotEmpty() && asset.id == keepId)
        }

    /**
     * FIXED: renda fixa e Tesouro — so pagamento e valor bruto, com "repetir". MARKET: acao, ETF,
     * BDR, FII — data com, valor por cota, quantidade na data com.
     */
    fun proceedsLayout(type: String?, asset: Asset?): String =
        if (isFixedIncomeCategory(assetCategory(asset)) && type in listOf("INTEREST", "AMORTIZATION")) "FIXED" else "MARKET"

    /** O campo de IR: null quando o tipo nao tem IR (a amortizacao devolve capital). */
    fun proceedsTaxField(type: String?): TaxField? = when (type) {
        "AMORTIZATION" -> null
        "INTEREST" -> TaxField(
            "IR retido (R$)",
            "Em branco: tabela regressiva desde a aplicação (22,5% a 15%), zero em título isento.",
        )
        "JCP" -> TaxField("IR retido (R$)", "Em branco: 15% retido na fonte (17,5% com data com desde 2026).")
        else -> TaxField(
            "IR retido (R$)",
            "Em branco: sem IR (dividendos e rendimentos de FII). Preencha só se houve retenção na fonte.",
        )
    }

    /** O tipo atual se vale para o ativo; senao o primeiro que vale (ou o atual, quando nenhum vale). */
    fun typeForAsset(asset: Asset?, current: String): String {
        if (asset == null || proceedsTypeFitsAsset(current, asset)) return current
        return PROCEEDS_TYPES.firstOrNull { proceedsTypeFitsAsset(it.value, asset) }?.value ?: current
    }

    fun typeLabel(value: String): String = PROCEEDS_TYPES.firstOrNull { it.value == value }?.label ?: value

    // Uma cotacao (atualizar precos, preco manual) nao muda posicao nenhuma.
    private val QUOTE_ONLY_WRITE = Regex("^/api/investments/(update-prices|price-by-asset)(/|\\?|$)")
    private val POSITION_WRITE = Regex("^/api/(investments|corporate-actions)(/|\\?|$)")

    /**
     * Escritas que mudam a posicao de um ativo em alguma data, e com ela os proventos automaticos
     * (a sincronizacao roda logo depois).
     */
    fun changesPositions(path: String?): Boolean {
        val value = path ?: ""
        return POSITION_WRITE.containsMatchIn(value) && !QUOTE_ONLY_WRITE.containsMatchIn(value)
    }
}
