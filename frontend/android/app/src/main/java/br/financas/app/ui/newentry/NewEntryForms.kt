// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: os handlers de frontend/src/components/NewEntrySheet.jsx (handleBankSubmit,
// handleTransferSubmit, handleCCExpenseSubmit, submitEntry e a abertura de um item da fila).
// Do lado web sao inline e sem teste; aqui: NewEntryFormsTest.kt. As mensagens sao as da web,
// letra por letra (inclusive as sem acento, que vieram assim do codigo).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.ui.newentry

import br.financas.app.core.MoneyInput
import br.financas.app.core.formatCurrency
import br.financas.app.core.getLocalDateString
import br.financas.app.core.moneyInputValue
import br.financas.app.core.parseLocalDate
import br.financas.app.core.parseMoneyInput
import br.financas.app.data.CreditCardDto
import br.financas.app.rules.Card
import br.financas.app.rules.CardFunctions
import br.financas.app.rules.CategoryOption
import br.financas.app.rules.DebitPurchase
import br.financas.app.rules.EntryOptions
import org.json.JSONObject
import java.math.BigDecimal

/** Os quatro tipos do "+ Novo" (o kind da fila; uma compra no debito vai como EXPENSE). */
object EntryType {
    const val EXPENSE = "EXPENSE"
    const val INCOME = "INCOME"
    const val TRANSFER = "TRANSFER"
    const val CARD = "CARD"

    val ALL: List<String> = listOf(EXPENSE, INCOME, TRANSFER, CARD)

    /** O tipo pedido ao abrir; qualquer outro (ou nenhum) e Despesa, como no Layout.jsx. */
    fun initial(requested: String?): String = if (requested != null && requested in ALL) requested else EXPENSE
}

/** Despesa e Receita dividem um formulario; `type` diz qual. Campos como texto, como na web. */
data class BankForm(
    val amount: String = "",
    val date: String = getLocalDateString(),
    val categoryId: String = "",
    val description: String = "",
    val type: String = EntryType.EXPENSE,
    val accountId: String = "",
)

data class TransferForm(
    val amount: String = "",
    val date: String = getLocalDateString(),
    val accountId: String = "",
    val transferAccountId: String = "",
    val description: String = "",
)

data class CardEntryForm(
    val cardId: String = "",
    val method: String = CardFunctions.CREDIT,
    val categoryId: String = "",
    val description: String = "",
    val totalAmount: String = "",
    val purchaseDate: String = getLocalDateString(),
    val installments: String = "1",
)

/** O resultado de um Salvar: o erro para a caixa vermelha, ou o envio pronto. */
sealed interface Submission {
    data class Invalid(val message: String) : Submission

    /**
     * [payload]: o corpo do POST na ordem da web; um valor null e uma chave que nao vai (o
     * `undefined` do JS). [label] abre os toasts ("Despesa de R$ 12,50"); [fallbackError] e o
     * texto quando a recusa do servidor nao traz mensagem.
     */
    data class Ready(
        val kind: String,
        val payload: Map<String, Any?>,
        val label: String,
        val fallbackError: String,
    ) : Submission
}

/** Um aviso ao fechar: o toast da web (tom e duracao). */
data class EntryNotice(val message: String, val tone: String = TONE_SUCCESS, val durationMs: Int = DEFAULT_DURATION_MS) {
    companion object {
        const val TONE_SUCCESS = "success"
        const val TONE_INFO = "info"
        const val DEFAULT_DURATION_MS = 4000
        const val LONG_DURATION_MS = 6000
    }
}

/** Os formularios de um item da fila aberto em Pendentes › Corrigir. */
data class EditedForms(
    val type: String,
    val bank: BankForm? = null,
    val transfer: TransferForm? = null,
    val card: CardEntryForm? = null,
    /** O nome guardado num item de antes do id, para achar o id quando as categorias chegarem. */
    val categoryName: String = "",
)

object NewEntryForms {

    const val BANK_AMOUNT_ERROR = "Informe um valor bancario valido."
    const val TRANSFER_AMOUNT_ERROR = "Informe um valor valido para a transferencia."
    const val SAME_ACCOUNT_ERROR = "Origem e destino devem ser contas diferentes."
    const val CARD_ERROR = "Preencha a compra no cartão com valores válidos."
    const val BANK_FALLBACK = "Não foi possível criar o lançamento."
    const val TRANSFER_FALLBACK = "Não foi possível registrar a transferência."
    const val DEBIT_FALLBACK = "Não foi possível registrar a compra no débito."
    const val CARD_FALLBACK = "Não foi possível criar a compra no cartão."

    /** Parcelas no aparelho: 1 a 48, como o min/max do campo na web (o servidor aceita ate 72). */
    const val MAX_INSTALLMENTS = 48

    // Os campos obrigatorios: na web e o `required` do navegador que segura o envio; aqui a
    // mesma frase do Chrome em portugues, com o nome do campo.
    fun requiredField(label: String) = "Preencha este campo: $label."
    fun requiredSelect(label: String) = "Selecione um item na lista: $label."

    /** Despesa ou receita. [defaultAccountId]: a conta padrao, usada quando nenhuma foi escolhida. */
    fun prepareBank(form: BankForm, options: List<CategoryOption>, defaultAccountId: String): Submission {
        val amount = positiveAmount(form.amount) ?: return Submission.Invalid(BANK_AMOUNT_ERROR)
        if (form.categoryId.isEmpty()) return Submission.Invalid(requiredSelect("Categoria"))
        if (form.description.isEmpty()) return Submission.Invalid(requiredField("Descrição"))
        if (parseLocalDate(form.date) == null) return Submission.Invalid(requiredField("Data"))
        val type = if (form.type == EntryType.INCOME) EntryType.INCOME else EntryType.EXPENSE
        // O id decide a categoria; o nome vai junto para a linha pendente do extrato.
        val payload = linkedMapOf<String, Any?>(
            "amount" to amount,
            "date" to form.date,
            "category_id" to form.categoryId,
            "category" to EntryOptions.categoryNameOf(options, form.categoryId),
            "description" to form.description,
            "type" to type,
            "account_id" to form.accountId.ifEmpty { defaultAccountId }.ifEmpty { null },
        )
        val word = if (type == EntryType.INCOME) "Receita" else "Despesa"
        return Submission.Ready(type, payload, "$word de ${formatCurrency(amount)}", BANK_FALLBACK)
    }

    fun prepareTransfer(form: TransferForm): Submission {
        val amount = positiveAmount(form.amount) ?: return Submission.Invalid(TRANSFER_AMOUNT_ERROR)
        if (form.accountId.isEmpty()) return Submission.Invalid(requiredSelect("De"))
        if (form.transferAccountId.isEmpty()) return Submission.Invalid(requiredSelect("Para"))
        if (parseLocalDate(form.date) == null) return Submission.Invalid(requiredField("Data"))
        if (form.accountId == form.transferAccountId) return Submission.Invalid(SAME_ACCOUNT_ERROR)
        val payload = linkedMapOf<String, Any?>(
            "amount" to amount,
            "date" to form.date,
            "account_id" to form.accountId,
            "transfer_account_id" to form.transferAccountId,
            "description" to form.description,
        )
        return Submission.Ready(EntryType.TRANSFER, payload, "Transferência de ${formatCurrency(amount)}", TRANSFER_FALLBACK)
    }

    /**
     * Compra no cartao. No metodo debito (cartao com debit_account_id) vira uma despesa na conta
     * do cartao, sem parcelas (CardFunctions.debitPurchasePayload).
     */
    fun prepareCard(form: CardEntryForm, cards: List<CreditCardDto>, options: List<CategoryOption>): Submission {
        val selected = cards.firstOrNull { it.id == form.cardId }
        val card = selected?.let { cardOf(it) }
        val method = CardFunctions.resolveCardMethod(card, form.method)
        val debit = method == CardFunctions.DEBIT
        val installments = if (debit) 1 else installmentsOf(form.installments)
        val date = parseLocalDate(form.purchaseDate)
        val amount = positiveAmount(form.totalAmount)
        if (card == null || date == null || amount == null || installments == null) {
            return Submission.Invalid(CARD_ERROR)
        }
        if (form.categoryId.isEmpty()) return Submission.Invalid(requiredSelect("Categoria"))
        if (form.description.isEmpty()) return Submission.Invalid(requiredField("Descrição"))
        val categoryName = EntryOptions.categoryNameOf(options, form.categoryId)
        if (debit) {
            val payload = CardFunctions.debitPurchasePayload(
                card,
                DebitPurchase(amount, date, form.categoryId, categoryName, form.description),
            )
            return Submission.Ready(EntryType.EXPENSE, payload, "Compra no débito de ${formatCurrency(amount)}", DEBIT_FALLBACK)
        }
        val payload = linkedMapOf<String, Any?>(
            "card_id" to form.cardId,
            "category_id" to form.categoryId,
            "category" to categoryName,
            "description" to form.description,
            "total_amount" to amount,
            "purchase_date" to form.purchaseDate,
            "installments" to installments,
        )
        val label = if (installments > 1) {
            "Compra no cartão de ${formatCurrency(amount)} em ${installments}x"
        } else {
            "Compra no cartão de ${formatCurrency(amount)}"
        }
        return Submission.Ready(EntryType.CARD, payload, label, CARD_FALLBACK)
    }

    /** So o erro (o validate(kind, form) da spec); null quando o formulario pode ser enviado. */
    fun validate(submission: Submission): String? = (submission as? Submission.Invalid)?.message

    /** O cartao do JSON visto pelas regras de CardFunctions. */
    fun cardOf(card: CreditCardDto): Card =
        Card(id = card.id, name = card.name, creditEnabled = card.creditEnabled, debitAccountId = card.debitAccountId)

    // Os toasts do NewEntrySheet.jsx (submitEntry).
    fun savedNotice(label: String) = EntryNotice("$label registrada.")

    fun queuedNotice(label: String) = EntryNotice(
        "Sem conexão: ${lowerFirst(label)} guardada neste aparelho. Ela é enviada quando o servidor responder.",
        EntryNotice.TONE_INFO,
        EntryNotice.LONG_DURATION_MS,
    )

    fun matchedNotice(message: String) = EntryNotice(message, EntryNotice.TONE_INFO, EntryNotice.LONG_DURATION_MS)

    fun updatedNotice(label: String) = EntryNotice("$label pendente atualizada.", EntryNotice.TONE_INFO)

    /**
     * Um item da fila no formulario do tipo dele (a abertura em modo de correcao do
     * NewEntrySheet.jsx). Um item sem category_id guarda o nome: o id sai de [options] agora ou,
     * se as categorias ainda nao chegaram, depois (EditedForms.categoryName).
     */
    fun formsFromItem(kind: String, payload: JSONObject, options: List<CategoryOption>): EditedForms {
        val categoryName = text(payload, "category")
        val categoryId = text(payload, "category_id").ifEmpty { EntryOptions.categoryIdForName(options, categoryName) }
        return when (kind) {
            EntryType.TRANSFER -> EditedForms(
                type = kind,
                transfer = TransferForm(
                    amount = amountText(payload.opt("amount")),
                    date = text(payload, "date").ifEmpty { getLocalDateString() },
                    accountId = text(payload, "account_id"),
                    transferAccountId = text(payload, "transfer_account_id"),
                    description = text(payload, "description"),
                ),
            )
            EntryType.CARD -> EditedForms(
                type = kind,
                card = CardEntryForm(
                    cardId = text(payload, "card_id"),
                    categoryId = categoryId,
                    description = text(payload, "description"),
                    totalAmount = amountText(payload.opt("total_amount")),
                    purchaseDate = text(payload, "purchase_date").ifEmpty { getLocalDateString() },
                    installments = amountText(payload.opt("installments")).ifEmpty { "1" },
                ),
                categoryName = if (categoryId.isEmpty()) categoryName else "",
            )
            else -> {
                // Uma compra no debito foi guardada como EXPENSE: reabre como Despesa.
                val type = if (kind == EntryType.INCOME) EntryType.INCOME else EntryType.EXPENSE
                EditedForms(
                    type = type,
                    bank = BankForm(
                        amount = amountText(payload.opt("amount")),
                        date = text(payload, "date").ifEmpty { getLocalDateString() },
                        categoryId = categoryId,
                        description = text(payload, "description"),
                        type = type,
                        accountId = text(payload, "account_id"),
                    ),
                    categoryName = if (categoryId.isEmpty()) categoryName else "",
                )
            }
        }
    }

    /** O corpo do POST: chave com valor null nao vai (o undefined do JS some no JSON.stringify). */
    fun payloadJson(payload: Map<String, Any?>): JSONObject {
        val json = JSONObject()
        for ((key, value) in payload) {
            if (value != null) json.put(key, value)
        }
        return json
    }

    // parseMoneyInput > 0, senao null (o `!Number.isFinite(amount) || amount <= 0` da web).
    private fun positiveAmount(text: String): BigDecimal? {
        val parsed = parseMoneyInput(text) as? MoneyInput.Amount ?: return null
        return parsed.value.takeIf { it.signum() > 0 }
    }

    // O Number() do campo de parcelas: inteiro de 1 a 48 ("3", " 3 ", "3.0"); senao null.
    private fun installmentsOf(text: String): Int? {
        val number = text.trim().toBigDecimalOrNull() ?: return null
        val whole = number.stripTrailingZeros()
        if (whole.scale() > 0) return null
        if (whole < BigDecimal.ONE || whole > BigDecimal(MAX_INSTALLMENTS)) return null
        return whole.intValueExact()
    }

    private fun lowerFirst(text: String): String =
        if (text.isEmpty()) text else text.substring(0, 1).lowercase() + text.substring(1)

    private fun text(payload: JSONObject, key: String): String {
        val value = payload.opt(key)
        return if (value == null || value == JSONObject.NULL) "" else value.toString()
    }

    // Um numero guardado no item (Double depois de ler o JSON) de volta ao campo: 42.9 -> "42,9".
    private fun amountText(value: Any?): String {
        if (value == null || value == JSONObject.NULL) return ""
        val number = value.toString().trim().toBigDecimalOrNull() ?: return value.toString()
        return moneyInputValue(number)
    }
}
