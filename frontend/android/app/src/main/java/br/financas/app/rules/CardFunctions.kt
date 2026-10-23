// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/cardFunctions.js (testes em cardFunctions.test.js);
// aqui: CardFunctionsTest.kt, os mesmos casos na mesma ordem.
package br.financas.app.rules

import java.math.BigDecimal
import java.time.LocalDate

/**
 * Um cartao como vem de GET /api/credit-cards, so o que as regras leem.
 *
 * `creditEnabled`: null = sem a coluna (cartao de antes da 041), que e credito;
 * so `false` (o 0 ou false do JSON) desliga o credito, como no JS.
 * `debitAccountId`: null ou "" = sem debito (o JS testa `Boolean(...)`).
 */
data class Card(
    val id: String? = null,
    val name: String? = null,
    val creditEnabled: Boolean? = null,
    val debitAccountId: String? = null,
)

/** Um item do seletor de funcoes de Ajustes (CARD_FUNCTION_ITEMS). */
data class CardFunctionItem(val value: String, val label: String)

/**
 * O formulario de Ajustes > Cartoes, com os campos como texto, como no JS.
 *
 * `autopayAccountId` so entra no corpo quando o campo existe no formulario
 * (`'autopay_account_id' in form`): `autopayAccountIdSet` diz se existe, e por
 * padrao e "veio um valor". Para "existe e vale null" passe `autopayAccountIdSet = true`.
 */
data class CardForm(
    val name: String? = null,
    val functions: String? = null,
    val debitAccountId: String? = null,
    val dueDay: String? = null,
    val closingDay: String? = null,
    val autopayAccountId: String? = null,
    val autopayAccountIdSet: Boolean = autopayAccountId != null,
)

/** `{ payload }` ou `{ error }`: exatamente um dos dois e nao nulo. */
data class CardFormResult(val payload: Map<String, Any?>? = null, val error: String? = null)

/** Os campos da compra no debito do "+ Novo" (o segundo argumento de debitPurchasePayload). */
data class DebitPurchase(
    val amount: BigDecimal?,
    val date: LocalDate?,
    val categoryId: String?,
    val category: String?,
    val description: String?,
)

/**
 * As funcoes de um cartao (migration 041): credito, debito ou os dois.
 *
 * Credito e o de sempre: fatura, parcelas, debito automatico. Debito e uma conta
 * (`debit_account_id`): a compra no debito e uma despesa comum nessa conta, sem
 * fatura. Um cartao so debito (o Flash) tem `credit_enabled` 0 e nao aparece onde
 * se escolhe cartao de credito. Puro: nada de Android, testado na JVM.
 */
object CardFunctions {
    const val CREDIT = "CREDIT"
    const val DEBIT = "DEBIT"
    const val BOTH = "BOTH"

    @JvmField
    val CARD_FUNCTION_ITEMS: List<CardFunctionItem> = listOf(
        CardFunctionItem(CREDIT, "Crédito"),
        CardFunctionItem(DEBIT, "Débito"),
        CardFunctionItem(BOTH, "Os dois"),
    )

    @JvmStatic
    fun hasCredit(card: Card?): Boolean = card != null && card.creditEnabled != false

    @JvmStatic
    fun hasDebit(card: Card?): Boolean = !card?.debitAccountId.isNullOrEmpty()

    /** Os cartoes onde uma compra vai para a fatura. */
    @JvmStatic
    fun creditCards(cards: List<Card>?): List<Card> = (cards ?: emptyList()).filter { hasCredit(it) }

    /** 'CREDIT' | 'DEBIT' | 'BOTH' de um cartao gravado (o valor do seletor de Ajustes). */
    @JvmStatic
    fun cardFunctionOf(card: Card?): String {
        if (hasCredit(card) && hasDebit(card)) return BOTH
        return if (hasDebit(card) && !hasCredit(card)) DEBIT else CREDIT
    }

    @JvmStatic
    fun cardFunctionLabel(card: Card?): String = when (cardFunctionOf(card)) {
        BOTH -> "Crédito e débito"
        DEBIT -> "Débito"
        else -> "Crédito"
    }

    /** Como a compra pode ser feita neste cartao, na ordem do seletor do "+ Novo". */
    @JvmStatic
    fun cardMethods(card: Card?): List<String> {
        if (card == null) return emptyList()
        val methods = mutableListOf<String>()
        if (hasCredit(card)) methods.add(CREDIT)
        if (hasDebit(card)) methods.add(DEBIT)
        return methods
    }

    /** O metodo que vale: o escolhido, se o cartao o tem; senao o primeiro dele. */
    @JvmStatic
    fun resolveCardMethod(card: Card?, chosen: String?): String {
        val methods = cardMethods(card)
        return if (chosen != null && chosen in methods) chosen else (methods.firstOrNull() ?: CREDIT)
    }

    /**
     * O corpo de POST/PATCH /api/credit-cards a partir do formulario de Ajustes, ou o
     * erro com o que falta. O mapa tem as chaves do JSON do JS, na mesma ordem; uma
     * chave ausente no JS e ausente aqui, um null do JS e um valor null aqui.
     */
    @JvmStatic
    fun cardFormPayload(form: CardForm?): CardFormResult {
        val name = jsTrim(form?.name ?: "")
        if (form == null || name.isEmpty()) return CardFormResult(error = "Informe o nome do cartão.")
        val functions = form.functions?.takeIf { it.isNotEmpty() } ?: CREDIT
        val credit = functions != DEBIT
        val debit = functions != CREDIT
        val debitAccountId = if (debit) form.debitAccountId?.takeIf { it.isNotEmpty() } else null
        val payload = linkedMapOf<String, Any?>(
            "name" to name,
            "credit_enabled" to credit,
            "debit_account_id" to debitAccountId,
        )
        if (debit && debitAccountId == null) {
            return CardFormResult(error = "Escolha a conta de onde sai a compra no débito.")
        }
        if (credit) {
            val dueDay = dayOf(form.dueDay)
            val closingDay = dayOf(form.closingDay)
            if (dueDay == null || closingDay == null) {
                return CardFormResult(error = "Informe o vencimento e o fechamento do cartão (dia de 1 a 31).")
            }
            payload["due_day"] = dueDay
            payload["closing_day"] = closingDay
        }
        if (form.autopayAccountIdSet) {
            payload["autopay_account_id"] = if (credit) form.autopayAccountId?.takeIf { it.isNotEmpty() } else null
        }
        return CardFormResult(payload = payload)
    }

    /**
     * A compra no debito vira uma despesa na conta do cartao (POST /api/transactions).
     * As sete chaves estao sempre no mapa (no JS um campo `undefined` sumiria do JSON;
     * aqui ele vai como null). `date` sai como texto AAAA-MM-DD.
     */
    @JvmStatic
    fun debitPurchasePayload(card: Card, purchase: DebitPurchase): Map<String, Any?> = linkedMapOf(
        "amount" to purchase.amount,
        "date" to purchase.date?.toString(),
        "category_id" to purchase.categoryId,
        "category" to purchase.category,
        "description" to purchase.description,
        "type" to "EXPENSE",
        "account_id" to card.debitAccountId,
    )

    /** O dia do formulario: `Number(value)` do JS, inteiro de 1 a 31, senao null. */
    @JvmStatic
    fun dayOf(value: String?): Int? {
        val number = jsNumber(value) ?: return null
        if (number.signum() == 0 || number.stripTrailingZeros().scale() > 0) return null
        return if (number >= BigDecimal.ONE && number <= BigDecimal(31)) number.intValueExact() else null
    }

    // Os brancos que o trim() do JS (e o Number()) tiram.
    private fun isJsWhitespace(c: Char): Boolean =
        c == ' ' || c in '\t'..'\r' || c == ' ' || c == ' ' || c in ' '..' ' ||
            c == ' ' || c == ' ' || c == ' ' || c == ' ' || c == '　' || c == '﻿'

    private fun jsTrim(text: String): String = text.trim { isJsWhitespace(it) }

    private val DECIMAL = Regex("""[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?""")
    private val PREFIXED = Regex("""0([xXoObB])([0-9a-fA-F]+)""")

    /**
     * `Number(text)` do JS para o que interessa a um dia: o valor finito exato, ou
     * null para NaN e Infinity. null (undefined) e NaN; "" e "  " sao 0.
     */
    private fun jsNumber(value: String?): BigDecimal? {
        if (value == null) return null
        val text = jsTrim(value)
        if (text.isEmpty()) return BigDecimal.ZERO
        PREFIXED.matchEntire(text)?.let { match ->
            val radix = when (match.groupValues[1][0].lowercaseChar()) { 'x' -> 16; 'o' -> 8; else -> 2 }
            return match.groupValues[2].toBigIntegerOrNull(radix)?.toBigDecimal()
        }
        if (!DECIMAL.matches(text)) return null
        return try {
            BigDecimal(text)
        } catch (_: NumberFormatException) {
            null
        }
    }
}
