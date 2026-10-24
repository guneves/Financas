// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/sharing.js (testes em sharing.test.js): SHARE_OPTIONS, othersAmount,
// ownAmount, shareSummary, settlePayload,
// shareFormFrom, shareFormError e sharePayload (e o toCents que elas usam);
// aqui: SharingTest.kt, os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import br.financas.app.core.formatCurrency
import java.math.BigDecimal
import java.math.BigInteger
import java.math.RoundingMode

/** Um item do seletor "De quem e" (SHARE_OPTIONS). */
data class ShareOption(val value: String, val label: String)

/**
 * A linha gravada (lancamento ou compra no cartao), so o que shareFormFrom le.
 * `shareOthersAmount` e o numero do JSON (null = ausente ou null).
 */
data class ShareItem(
    val shareMode: String? = null,
    val sharePerson: String? = null,
    val shareOthersAmount: BigDecimal? = null,
)

/** Uma linha com a divisao (lancamento ou parcela), o que othersAmount/shareSummary leem. */
data class SharedRow(
    val amount: BigDecimal? = null,
    val shareMode: String? = null,
    val sharePerson: String? = null,
    val shareOthersAmount: BigDecimal? = null,
)

/**
 * Os campos do formulario, como texto (o que o campo digitado guarda). null e o
 * campo ausente do JS (undefined): para sharePayload, `share_others_amount`
 * ausente e NaN (vai null no JSON), e "" e 0.
 */
data class ShareForm(
    val shareMode: String? = null,
    val sharePerson: String? = null,
    val shareOthersAmount: String? = null,
)

/**
 * De quem e o gasto (032, backend/services/sharing.py): so minha, dividida
 * (SPLIT, com a parte dos outros) ou de outra pessoa (OTHERS), sempre com o nome.
 */
object Sharing {
    const val SPLIT = "SPLIT"
    const val OTHERS = "OTHERS"

    @JvmField
    val SHARE_OPTIONS: List<ShareOption> = listOf(
        ShareOption("", "Só minha"),
        ShareOption(SPLIT, "Dividida"),
        ShareOption(OTHERS, "De outra pessoa"),
    )

    /** Os campos do formulario a partir da linha gravada. */
    @JvmStatic
    fun shareFormFrom(item: ShareItem?): ShareForm = ShareForm(
        shareMode = item?.shareMode.orEmpty(),
        sharePerson = item?.sharePerson.orEmpty(),
        shareOthersAmount = if (item?.shareMode == SPLIT) item?.shareOthersAmount?.let(::numberString).orEmpty() else "",
    )

    /**
     * Confere o formulario contra o valor total; devolve a mensagem ou "".
     * `amount` null e o `Number(undefined) || 0` do JS: 0.
     */
    @JvmStatic
    fun shareFormError(form: ShareForm?, amount: BigDecimal?): String {
        if (form == null || form.shareMode.isNullOrEmpty()) return ""
        if (Js.trim(form.sharePerson.orEmpty()).isEmpty()) return "Informe o nome da pessoa."
        if (form.shareMode == SPLIT) {
            // Number(texto): null e o NaN e o Infinity do JS (nao finitos).
            val others = jsNumber(form.shareOthersAmount)
            if (others == null || others.signum() <= 0) return "Informe a parte da outra pessoa."
            if (toCents(others) >= toCents(amount ?: BigDecimal.ZERO)) {
                return "A parte da outra pessoa deve ser menor que o valor. Se é tudo dela, escolha \"De outra pessoa\"."
            }
        }
        return ""
    }

    /**
     * O que vai no PATCH. "So minha" manda share_mode null, que limpa tudo. As chaves
     * na ordem do JS; `share_others_amount` so no SPLIT, null quando o Number do JS
     * daria NaN ou Infinity (o JSON.stringify os escreve como null).
     */
    @JvmStatic
    fun sharePayload(form: ShareForm?): Map<String, Any?> {
        if (form == null || form.shareMode.isNullOrEmpty()) return linkedMapOf("share_mode" to null)
        val payload = linkedMapOf<String, Any?>(
            "share_mode" to form.shareMode,
            "share_person" to Js.trim(form.sharePerson.orEmpty()),
        )
        if (form.shareMode == SPLIT) payload["share_others_amount"] = jsNumber(form.shareOthersAmount)
        return payload
    }

    /** Quanto da linha e de outra pessoa, em reais (othersAmount). */
    @JvmStatic
    fun othersAmount(item: SharedRow?): BigDecimal = when (item?.shareMode) {
        OTHERS -> item.amount ?: BigDecimal.ZERO
        SPLIT -> item.shareOthersAmount ?: BigDecimal.ZERO
        else -> BigDecimal.ZERO
    }

    /** A parte do dono, em centavos e de volta (ownAmount). */
    @JvmStatic
    fun ownAmount(item: SharedRow?): BigDecimal {
        val cents = toCents(item?.amount ?: BigDecimal.ZERO) - toCents(othersAmount(item))
        return BigDecimal(cents).movePointLeft(2)
    }

    @JvmStatic
    fun isShared(item: SharedRow?): Boolean = !item?.shareMode.isNullOrEmpty()

    /** "Dividida com Ana · sua parte R$ 40,00" / "De Ana" / "" (shareSummary). */
    @JvmStatic
    fun shareSummary(item: SharedRow?): String {
        if (item == null || !isShared(item)) return ""
        val person = item.sharePerson?.takeIf { it.isNotEmpty() } ?: "outra pessoa"
        if (item.shareMode == OTHERS) return "De $person"
        return "Dividida com $person · sua parte ${formatCurrency(ownAmount(item))}"
    }

    /** Um item de "A receber" que settlePayload le: TRANSACTION ou CARD_PURCHASE e o id. */
    data class ReceivableRef(val kind: String, val id: String)

    /** Os ids que POST /api/receivables/settle espera (settlePayload). */
    @JvmStatic
    fun settlePayload(items: List<ReceivableRef> = emptyList(), settled: Boolean = true): Map<String, Any?> = linkedMapOf(
        "transaction_ids" to items.filter { it.kind == "TRANSACTION" }.map { it.id },
        "cc_expense_ids" to items.filter { it.kind == "CARD_PURCHASE" }.map { it.id },
        "settled" to settled,
    )

    /**
     * `Math.round(value * 100)` do JS, em centavos, sobre o valor decimal exato: o .5
     * vai para +infinito (-0,005 -> -0, nao -1, que seria o HALF_UP). Diferenca
     * conhecida: o JS multiplica em binario, e um valor com 3 ou mais casas perto do
     * meio centavo pode cair do outro lado (1.005 * 100 = 100.49999999999999 -> 100 no JS,
     * 101 aqui). Com ate 2 casas os dois dao o mesmo.
     */
    @JvmStatic
    fun toCents(value: BigDecimal): BigInteger =
        value.movePointRight(2).add(HALF).setScale(0, RoundingMode.FLOOR).toBigIntegerExact()

    private val HALF = BigDecimal("0.5")
    private val MAX_DOUBLE = BigDecimal(Double.MAX_VALUE)
    private val DECIMAL = Regex("^[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?$")
    private val RADIX = Regex("^0([xXoObB])([0-9a-fA-F]+)$")

    /**
     * `Number(texto)` do JS como BigDecimal exato: null quando o JS daria NaN ou um
     * valor infinito (undefined, "abc", "Infinity", "1e400"); "" e brancos sao 0.
     * Sem zeros finais e sem expoente, como o JS le o numero ("12.50" -> 12.5).
     */
    private fun jsNumber(value: String?): BigDecimal? {
        if (value == null) return null
        val text = Js.trim(value)
        if (text.isEmpty()) return BigDecimal.ZERO
        val number = RADIX.matchEntire(text)?.let { match ->
            val radix = when (match.groupValues[1].lowercase()) { "x" -> 16; "o" -> 8; else -> 2 }
            match.groupValues[2].toBigIntegerOrNull(radix)?.toBigDecimal() ?: return null
        } ?: run {
            if (!DECIMAL.matches(text)) return null
            try {
                BigDecimal(text)
            } catch (_: NumberFormatException) {
                return null
            }
        }
        if (number.abs() > MAX_DOUBLE) return null
        return plain(number)
    }

    private fun plain(value: BigDecimal): BigDecimal {
        if (value.signum() == 0) return BigDecimal.ZERO
        val stripped = value.stripTrailingZeros()
        return if (stripped.scale() < 0) stripped.setScale(0) else stripped
    }

    // String(numero) do JS para um valor em reais: 40.10 -> "40.1", 40 -> "40".
    private fun numberString(value: BigDecimal): String = plain(value).toPlainString()
}
