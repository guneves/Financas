// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/inboxRules.js (testes em inboxRules.test.js), tudo menos
// matchedInboxNotice (esse esta em InboxNotice.kt); mais as regras soltas de
// frontend/src/pages/lancamentos/Aprovar.jsx (CONFLICT_MESSAGE, openPickers, o "alreadyOpen" do
// "Trocar", o rotulo da conta, o aviso da caixa de escolhas e a categoria do proprio item na
// edicao), que nao tem teste no node. Aqui: InboxRulesTest.kt, os casos do node na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import br.financas.app.core.MoneyInput
import br.financas.app.core.formatCurrency
import br.financas.app.core.parseMoneyInput
import java.math.BigDecimal

/**
 * Uma fonte do item (`sources[]` de serialize_item, backend/services/inbox.py), so o que as
 * regras leem. Os textos ausentes do JSON sao null; "" vale o mesmo que null (falso no JS).
 */
data class InboxSource(
    val source: String? = null,
    val id: String? = null,
    val role: String? = null,
    val app: String? = null,
    val appLabel: String? = null,
    val kind: String? = null,
    val occurredAt: String? = null,
    val cardLast4: String? = null,
    val cardName: String? = null,
    val counterparty: String? = null,
    // Open Finance (043): o banco, a conta, a descricao do banco, a parcela.
    val connectorName: String? = null,
    /** O banco da conta (044): no MeuPluggy o conector e "MeuPluggy" para todos. */
    val bankName: String? = null,
    val accountName: String? = null,
    val description: String? = null,
    val installmentNumber: Int? = null,
    val totalInstallments: Int? = null,
)

/** A ocorrencia de recorrencia que aprovar da como feita (034), `item.recurring`. */
data class InboxRecurring(
    val description: String? = null,
    val category: String? = null,
    val date: String? = null,
    val amount: BigDecimal? = null,
    /** So `false` diz "valor diferente do previsto"; null (ausente) nao, como no JS (=== false). */
    val exactAmount: Boolean? = null,
    val settled: Boolean = false,
)

/**
 * Um item de GET /api/inbox, so o que as regras leem. `version` null e o item sem versao: a
 * chave nao vai no corpo (o JSON.stringify do JS omite undefined).
 */
data class InboxItem(
    val id: String? = null,
    val version: Int? = null,
    val state: String? = null,
    val reason: String? = null,
    val entryType: String? = null,
    val direction: String? = null,
    val amount: BigDecimal? = null,
    val occurredAt: String? = null,
    val description: String? = null,
    val category: String? = null,
    val categoryId: String? = null,
    val accountId: String? = null,
    val accountName: String? = null,
    val cardId: String? = null,
    val cardName: String? = null,
    val transferAccountId: String? = null,
    val transferAccountName: String? = null,
    val installments: Int? = null,
    val needs: List<String>? = null,
    val confirm: List<String>? = null,
    val ready: Boolean = false,
    val ambiguous: Boolean = false,
    val recurring: InboxRecurring? = null,
    val recurringOff: Boolean = false,
    val sources: List<InboxSource>? = null,
)

/** Uma escolha lembrada de GET /api/inbox/hints, so o que hintText le. */
data class InboxHint(
    val hintKey: String? = null,
    val label: String? = null,
    val entryType: String? = null,
    val accountName: String? = null,
    val cardName: String? = null,
    val transferAccountName: String? = null,
)

/** Um item que "Aprovar prontos" deixou: `{id, reason, error?}`. */
data class ApproveReadySkip(val id: String? = null, val reason: String? = null, val error: String? = null)

/** A resposta de POST /api/inbox/approve-ready (null = a chave ausente, conta 0). */
data class ApproveReadyResult(
    val approved: List<String>? = null,
    val skipped: List<ApproveReadySkip>? = null,
)

/**
 * O formulario de edicao, com os campos como texto (o que o campo da tela guarda). "" e o
 * campo vazio do JS; `installments` e texto porque o campo numerico do web devolve texto.
 */
data class InboxDraft(
    val entryType: String = "",
    val amount: String = "",
    val date: String = "",
    val time: String = "",
    val description: String = "",
    val categoryId: String = "",
    val accountId: String = "",
    val cardId: String = "",
    val transferAccountId: String = "",
    val installments: String = "1",
)

/**
 * Uma escolha rapida no cartao do item. Cada destino so entra no corpo quando foi escolhido
 * (`choice.card_id !== undefined` no JS): o `...Set` diz se foi, e por padrao e "veio um valor".
 * Para "escolheu vazio" (vai null) passe "" ou `cardIdSet = true`.
 */
data class QuickChoice(
    val method: String? = null,
    val cardId: String? = null,
    val accountId: String? = null,
    val transferAccountId: String? = null,
    val cardIdSet: Boolean = cardId != null,
    val accountIdSet: Boolean = accountId != null,
    val transferAccountIdSet: Boolean = transferAccountId != null,
)

/** A opcao extra do seletor de categoria da edicao: o valor e o rotulo (`item.category`). */
data class CategoryFallbackOption(val value: String, val label: String?)

/**
 * Aprovar (Lancamentos > Aprovar): os textos e os pedidos da tela. As regras de verdade (o que
 * junta com o que, o que fica lembrado, o que vira lancamento) estao no servidor
 * (backend/services/inbox.py e inbox_decisions.py); aqui so se diz isso em portugues e se monta
 * o pedido. Os corpos sao mapas na ordem das chaves do JS, prontos para virar JSON.
 */
object InboxRules {

    @JvmField
    val ENTRY_TYPE_LABELS: Map<String, String> = linkedMapOf(
        "EXPENSE" to "Despesa",
        "INCOME" to "Receita",
        "TRANSFER" to "Transferência",
        "CARD" to "Cartão de crédito",
    )

    @JvmStatic
    fun entryTypeLabel(type: String?): String = ENTRY_TYPE_LABELS[type].orEmpty().ifEmpty { "Crédito ou débito?" }

    private val KIND_LABELS: Map<String, String> = mapOf(
        "CREDIT_PURCHASE" to "compra no crédito",
        "DEBIT_PURCHASE" to "compra no débito",
        "PURCHASE" to "compra (sem crédito/débito)",
        "PIX_OUT" to "Pix enviado",
        "PIX_IN" to "Pix recebido",
        "TRANSFER_OUT" to "transferência enviada",
        "TRANSFER_IN" to "transferência recebida",
        "REFUND" to "estorno",
        "DECLINED" to "compra negada",
    )

    /** De onde veio cada fonte do item, numa linha. */
    @JvmStatic
    fun sourceLabel(source: InboxSource?): String {
        if (source == null) return ""
        if (source.source == "open_finance") return openFinanceSourceLabel(source)
        val app = source.appLabel.orEmpty().ifEmpty { source.app.orEmpty() }.ifEmpty { "Notificação" }
        val kind = KIND_LABELS[source.kind].orEmpty()
        val card = if (!source.cardLast4.isNullOrEmpty()) "final ${source.cardLast4}" else source.cardName.orEmpty()
        return listOf("Notificação $app", kind, card, source.counterparty.orEmpty())
            .filter { it.isNotEmpty() }
            .joinToString(" · ")
    }

    /** Uma transacao do Open Finance (043): o banco, a conta, a descricao do banco,
     *  a parcela; "saiu do banco" quando a Pluggy a desfez antes da aprovacao. */
    private fun openFinanceSourceLabel(source: InboxSource): String {
        val name = source.bankName.orEmpty().ifEmpty { source.connectorName.orEmpty() }
        val bank = if (name.isNotEmpty()) "Open Finance $name" else "Open Finance"
        val total = source.totalInstallments ?: 0
        val installment = if (source.installmentNumber != null && total > 1) "parcela ${source.installmentNumber}/$total" else ""
        return listOf(
            bank,
            source.accountName.orEmpty(),
            source.description.orEmpty(),
            installment,
            source.counterparty.orEmpty(),
            if (source.role == "REMOVED") "saiu do banco" else "",
        ).filter { it.isNotEmpty() }.joinToString(" · ")
    }

    private const val SAMSUNG_WALLET = "com.samsung.android.spay"

    /** "via Samsung Wallet" quando so o Samsung avisou: o banco nao notificou. */
    @JvmStatic
    fun onlySamsung(item: InboxItem?): Boolean {
        val notifications = item?.sources.orEmpty().filter { it.source == "notification" }
        return notifications.isNotEmpty() && notifications.all { it.app == SAMSUNG_WALLET }
    }

    /** A data e a hora de [splitOccurredAt]. */
    data class OccurredAt(val date: String, val time: String)

    /**
     * A hora como a fonte disse, sem converter fuso: "2026-10-17T22:30:00-03:00" e 17/10/2026
     * as 22:30 em qualquer aparelho. So a data, quando a fonte nao tem hora.
     */
    @JvmStatic
    fun splitOccurredAt(occurredAt: String?): OccurredAt {
        val text = occurredAt.orEmpty()
        val date = text.take(10)
        // slice(11, 16) do JS: fora do texto da "".
        val time = if (text.length > 11) text.substring(11, minOf(16, text.length)) else ""
        return OccurredAt(date, time)
    }

    private val ISO_DATE = Regex("^\\d{4}-\\d{2}-\\d{2}$")

    @JvmStatic
    fun whenText(occurredAt: String?): String {
        val (date, time) = splitOccurredAt(occurredAt)
        if (!ISO_DATE.matches(date)) return ""
        val (year, month, day) = date.split('-')
        val dayText = "$day/$month/$year"
        return if (time.isNotEmpty()) "$dayText às $time" else dayText
    }

    /**
     * O que o dono corrigiu na data/hora, para o PATCH. Hora vazia: so a data. O fuso fica o do
     * item (o servidor completa).
     */
    @JvmStatic
    fun composeOccurredAt(date: String?, time: String?): String {
        if (date.isNullOrEmpty()) return ""
        return if (!time.isNullOrEmpty()) "${date}T$time" else date
    }

    /** O sinal do valor na lista: sai (-1), entra (1), transferencia sem sinal (0). */
    @JvmStatic
    fun amountSign(item: InboxItem?): Int {
        if (item?.entryType == "TRANSFER") return 0
        return if (item?.direction == "IN") 1 else -1
    }

    @JvmField
    val NEED_TEXTS: Map<String, String> = linkedMapOf(
        "method" to "Foi no crédito ou no débito?",
        "card" to "Qual cartão?",
        "account" to "Qual conta?",
        "transfer_account" to "Para qual conta?",
        "amount" to "Confira o valor em reais (compra em outra moeda).",
    )

    @JvmStatic
    fun needText(need: String?): String = NEED_TEXTS[need].orEmpty().ifEmpty { "Falta escolher algo." }

    @JvmField
    val CONFIRM_TEXTS: Map<String, String> = linkedMapOf(
        "card" to "Cartão preenchido por palpite: confirme.",
        "account" to "Conta preenchida por palpite: confirme.",
        "transfer_account" to "Conta de destino preenchida por palpite: confirme.",
    )

    /** Por que o item espera (alem do normal "aprovar ou recusar"). */
    @JvmStatic
    fun reasonText(item: InboxItem?): String = when (item?.reason) {
        "several_candidates" ->
            "Há mais de um lançamento parecido já gravado. Se um deles for este, toque em \"É este\"; se não, aprove para lançar."
        "possible_duplicate" ->
            "Parece um lançamento que já está no app. Se for, toque em \"É este\" para não contar duas vezes."
        "installments_differ" ->
            "Há uma compra de mesmo total com outro número de parcelas. Se for a mesma, toque em \"É este\"."
        "out_of_reach" ->
            "Parece uma transferência, um pagamento de fatura ou um movimento da carteira que já está no app. Se for, toque em \"É este\"."
        "own_transfer" ->
            "Entre suas contas: entra como transferência e não conta como entrada nem saída."
        "external_transfer" ->
            "Com outra pessoa: entra como despesa ou receita. Se foi entre suas contas, troque para transferência — o app lembra da próxima vez."
        else -> ""
    }

    @JvmField
    val DECISION_LABELS: Map<String, String> = linkedMapOf(
        "APPROVED" to "Aprovado",
        "MATCHED" to "Já estava lançado",
        "DENIED" to "Recusado",
        "REMOVED" to "Saiu",
    )

    @JvmStatic
    fun decisionText(item: InboxItem?): String {
        if (item?.state == "REMOVED") {
            return if (item?.reason == "declined") "Compra negada pelo banco" else "Saiu da lista"
        }
        if (item?.state == "MATCHED" && item?.reason == "created_elsewhere") return "Lançado pelo \"+ Novo\""
        return DECISION_LABELS[item?.state].orEmpty()
    }

    /** Fontes que podem ser separadas ("nao e a mesma"): toda notificacao ligada ao item. */
    @JvmStatic
    fun splittableSources(item: InboxItem?): List<InboxSource> {
        val sources = item?.sources.orEmpty().filter {
            it.source in setOf("notification", "open_finance") && it.role in setOf("SOURCE", "PAIRED")
        }
        return if (sources.size > 1) sources else emptyList()
    }

    @JvmStatic
    fun readyIds(items: List<InboxItem>? = null): List<String?> = items.orEmpty().filter { it.ready }.map { it.id }

    /** Que tipo de lancamento parecido ja gravado e cada candidato. */
    @JvmField
    val CANDIDATE_KIND_LABELS: Map<String, String> = linkedMapOf(
        "entry" to "Lançamento",
        "card_purchase" to "Compra no cartão",
        "transfer" to "Transferência",
        "invoice_payment" to "Pagamento de fatura",
        "investment_cash" to "Pela carteira",
        "proceed" to "Provento",
    )

    @JvmStatic
    fun candidateKindLabel(kind: String?): String = CANDIDATE_KIND_LABELS[kind].orEmpty().ifEmpty { "Lançamento" }

    /** A categoria do proprio item quando ela so tem nome (sem id): fica como esta. */
    const val ITEM_CATEGORY = "__item__"

    /**
     * O formulario de edicao a partir do item. A categoria e pelo id: o nome se repete
     * ("Outros" na raiz e em "Lazer > Outros"). O valor vira o texto que o campo mostraria
     * (String(numero) do JS: 45.90 -> "45.9").
     */
    @JvmStatic
    fun draftFromItem(item: InboxItem?): InboxDraft {
        val (date, time) = splitOccurredAt(item?.occurredAt)
        return InboxDraft(
            entryType = item?.entryType.orEmpty(),
            amount = item?.amount?.let(::numberString).orEmpty(),
            date = date,
            time = time,
            description = item?.description.orEmpty(),
            categoryId = item?.categoryId.orEmpty().ifEmpty { if (item?.category.isNullOrEmpty()) "" else ITEM_CATEGORY },
            accountId = item?.accountId.orEmpty(),
            cardId = item?.cardId.orEmpty(),
            transferAccountId = item?.transferAccountId.orEmpty(),
            installments = (item?.installments?.takeIf { it != 0 } ?: 1).toString(),
        )
    }

    /**
     * O PATCH/approve: so o que mudou em relacao ao item, mais a versao. As chaves na ordem do
     * JS. `amount` e BigDecimal, ou null quando o campo esta vazio ou invalido (o JS manda null
     * ou NaN, que o JSON.stringify escreve null). `installments` e Long (ou Double quando o
     * texto nao e inteiro, como o Number do JS).
     */
    @JvmStatic
    fun changesFromDraft(item: InboxItem?, draft: InboxDraft): Map<String, Any?> {
        val original = draftFromItem(item)
        val changes = linkedMapOf<String, Any?>()
        if (draft.entryType.isNotEmpty() && draft.entryType != original.entryType) changes["entry_type"] = draft.entryType
        // "45,90", "45.90" e "1.234,56": o campo e texto, para aceitar os dois teclados.
        val amount = parseMoneyInput(draft.amount)
        // Number(original.amount): '' (sem valor) e 0.
        val originalAmount = item?.amount ?: BigDecimal.ZERO
        if (amount !is MoneyInput.Amount || amount.value.compareTo(originalAmount) != 0) {
            changes["amount"] = (amount as? MoneyInput.Amount)?.value
        }
        if (draft.date != original.date || draft.time != original.time) {
            changes["occurred_at"] = composeOccurredAt(draft.date, draft.time)
        }
        val description = Js.trim(draft.description)
        if (description != original.description) changes["description"] = description.ifEmpty { null }
        if (draft.categoryId != original.categoryId) {
            // Vazio e "sugerida pelas regras": o servidor escolhe ao aprovar.
            if (draft.categoryId.isEmpty()) {
                changes["category"] = null
                changes["category_id"] = null
            } else if (draft.categoryId != ITEM_CATEGORY) {
                changes["category_id"] = draft.categoryId
            }
        }
        if (draft.accountId != original.accountId) changes["account_id"] = draft.accountId.ifEmpty { null }
        if (draft.cardId != original.cardId) changes["card_id"] = draft.cardId.ifEmpty { null }
        if (draft.transferAccountId != original.transferAccountId) {
            changes["transfer_account_id"] = draft.transferAccountId.ifEmpty { null }
        }
        // Number(draft.installments || 1) !== Number(original.installments || 1); null e o NaN.
        val typed = Js.number(draft.installments.ifEmpty { "1" })
        val originalInstallments = Js.number(original.installments.ifEmpty { "1" })
        if (typed == null || typed != originalInstallments) {
            // Number(draft.installments) || 1: vazio, 0 e NaN viram 1.
            val value = Js.number(draft.installments)
            changes["installments"] = jsonNumber(if (value != null && Js.truthy(value)) value else 1.0)
        }
        return withVersion(item, changes)
    }

    /**
     * Uma escolha rapida no cartao do item (credito/debito, qual cartao, qual conta): o pedido
     * que a grava, ja com o tipo certo.
     */
    @JvmStatic
    fun quickChoice(item: InboxItem?, choice: QuickChoice): Map<String, Any?> {
        val body = withVersion(item, linkedMapOf())
        if (choice.method == "CARD") body["entry_type"] = "CARD"
        if (choice.method == "DEBIT") body["entry_type"] = if (item?.direction == "IN") "INCOME" else "EXPENSE"
        if (choice.cardIdSet) body["card_id"] = choice.cardId?.ifEmpty { null }
        if (choice.accountIdSet) body["account_id"] = choice.accountId?.ifEmpty { null }
        if (choice.transferAccountIdSet) body["transfer_account_id"] = choice.transferAccountId?.ifEmpty { null }
        return body
    }

    /**
     * Lembrar so faz sentido quando havia o que decidir — e nunca quando o caso e ambiguo (o
     * servidor nao guarda: pergunta toda vez).
     */
    @JvmStatic
    fun offersRemember(item: InboxItem?): Boolean {
        if (item?.ambiguous == true) return false
        return !item?.needs.isNullOrEmpty() || !item?.confirm.isNullOrEmpty()
    }

    /** Mais de uma conta (ou cartao) no banco e a notificacao sem o final. */
    @JvmStatic
    fun ambiguousText(item: InboxItem?): String {
        if (item == null || !item.ambiguous) return ""
        val what = if (item.entryType == "CARD") "um cartão" else "uma conta"
        return "Você tem mais de $what neste banco e o aviso não diz o final: o app pergunta toda vez."
    }

    /** Os seletores de destino que o tipo do item usa (o "Trocar" abre estes). */
    @JvmStatic
    fun targetFields(item: InboxItem?): List<String> = when (item?.entryType) {
        "CARD" -> listOf("card")
        "EXPENSE", "INCOME" -> listOf("account")
        "TRANSFER" -> listOf("account", "transfer_account")
        else -> emptyList()
    }

    /**
     * Para onde o item vai, numa linha ("Itau Conta corrente", "Itau Visa · 3x", "Itau -> BTG").
     * Vazio enquanto falta escolher: o seletor ja esta aberto.
     */
    @JvmStatic
    fun targetText(item: InboxItem?): String {
        if (item == null || item.entryType.isNullOrEmpty()) return ""
        if (item.entryType == "CARD") {
            if (item.cardId.isNullOrEmpty()) return ""
            val parts = mutableListOf(item.cardName.orEmpty().ifEmpty { "Cartão" })
            if ((item.installments ?: 0) > 1) parts.add("${item.installments}x")
            return parts.joinToString(" · ")
        }
        if (item.accountId.isNullOrEmpty()) return ""
        if (item.entryType == "TRANSFER") {
            if (item.transferAccountId.isNullOrEmpty()) return ""
            return "${item.accountName.orEmpty().ifEmpty { "Conta" }} → ${item.transferAccountName.orEmpty().ifEmpty { "Conta" }}"
        }
        return item.accountName.orEmpty().ifEmpty { "Conta" }
    }

    /** O aviso do Extrato e do cabecalho. */
    @JvmStatic
    fun pendingNoticeText(count: Int?): String {
        if (count == null || count == 0) return ""
        return if (count == 1) {
            "1 movimento do celular ou do banco espera sua aprovação."
        } else {
            "$count movimentos do celular ou do banco esperam sua aprovação."
        }
    }

    /** O resultado de "Aprovar prontos". */
    @JvmStatic
    fun approveReadySummary(result: ApproveReadyResult?): String {
        val approved = result?.approved?.size ?: 0
        val skipped = result?.skipped?.size ?: 0
        if (approved == 0 && skipped == 0) return "Nada para aprovar."
        val parts = mutableListOf("$approved ${if (approved == 1) "aprovado" else "aprovados"}")
        if (skipped > 0) parts.add("$skipped ${if (skipped == 1) "ficou" else "ficaram"} para você decidir")
        return "${parts.joinToString(", ")}."
    }

    /** Uma escolha lembrada, numa linha: "Samsung Wallet · sem credito/debito · final 1234 -> Itau Visa". */
    @JvmStatic
    fun hintText(hint: InboxHint?): String {
        if (hint == null) return ""
        val target = when (hint.entryType) {
            "TRANSFER" -> "transferência para ${hint.transferAccountName.orEmpty().ifEmpty { "?" }}"
            "CARD" -> hint.cardName.orEmpty().ifEmpty { "cartão removido" }
            else -> hint.accountName.orEmpty().ifEmpty { "conta removida" } + if (hint.entryType == "INCOME") " (receita)" else ""
        }
        // `hint.label || hint.hint_key`: sem os dois, o JS escreve "undefined".
        return "${hint.label.orEmpty().ifEmpty { hint.hintKey ?: "undefined" }} → $target"
    }

    // "2026-10-05" -> "05/10"; sem mes ou dia, "".
    private fun shortDate(date: String?): String {
        val parts = date.orEmpty().split('-')
        val month = parts.getOrNull(1).orEmpty()
        val day = parts.getOrNull(2).orEmpty()
        return if (day.isNotEmpty() && month.isNotEmpty()) "$day/$month" else ""
    }

    /**
     * A recorrencia que aprovar da como feita (034): Netflix de 05/10, salario do mes. O
     * servidor escolhe; aqui so se diz em portugues.
     */
    @JvmStatic
    fun recurringText(item: InboxItem?): String {
        if (item == null) return ""
        val occurrence = item.recurring ?: return ""
        val name = occurrence.description.orEmpty().ifEmpty { occurrence.category.orEmpty() }.ifEmpty { "recorrência" }
        val whenDay = shortDate(occurrence.date)
        if (occurrence.settled) return "Marcou \"$name\" de $whenDay como feita em Recorrentes."
        if (item.recurringOff) return "Não marca \"$name\" de $whenDay em Recorrentes."
        val amount = if (occurrence.exactAmount == false) " (previsto ${formatCurrency(occurrence.amount)})" else ""
        return "Recorrente: ao aprovar, \"$name\" de $whenDay$amount fica como feita em Recorrentes — não será lançada de novo."
    }

    /** "Nao e esta" (false) e desfazer (true): fica no item, vale para o "Aprovar todos". */
    @JvmStatic
    fun recurringToggle(item: InboxItem?, on: Boolean): Map<String, Any?> =
        withVersion(item, linkedMapOf()).apply { this["recurring"] = on }

    // ---- As regras soltas de Aprovar.jsx (sem teste no node) ----

    /** O 409 de qualquer decisao: a lista e relida e o dono confere. */
    const val CONFLICT_MESSAGE = "Este item mudou em outro aparelho. A lista foi atualizada: confira antes de decidir."

    /**
     * Os seletores que o item mostra aberto: o que falta, o palpite a confirmar e, depois de
     * "Trocar" ([changing]), todos os do tipo.
     */
    @JvmStatic
    fun openPickers(item: InboxItem?, changing: Boolean): List<String> {
        val needs = item?.needs.orEmpty()
        val confirm = item?.confirm.orEmpty()
        return targetFields(item).filter { changing || it in needs || it in confirm }
    }

    /**
     * O "Trocar" some quando todos os seletores do tipo ja estao abertos (o que falta ou o
     * palpite). A linha de destino so aparece quando [targetText] nao e vazio.
     */
    @JvmStatic
    fun alreadyOpen(item: InboxItem?, changing: Boolean): Boolean {
        val fields = targetFields(item)
        return !changing && fields.isNotEmpty() && openPickers(item, false).size == fields.size
    }

    /** A caixa de escolhas aparece quando pede credito/debito ou tem um seletor aberto. */
    @JvmStatic
    fun showsDecisions(item: InboxItem?, changing: Boolean): Boolean =
        item?.needs.orEmpty().contains("method") || openPickers(item, changing).isNotEmpty()

    /** A caixa e ambar (aviso) quando falta algo ou ha palpite; depois de "Trocar", neutra. */
    @JvmStatic
    fun decisionsWarn(item: InboxItem?, changing: Boolean): Boolean {
        val needs = item?.needs.orEmpty()
        val confirm = item?.confirm.orEmpty()
        return "method" in needs || openPickers(item, changing).any { it in needs || it in confirm }
    }

    /** O rotulo do seletor de conta: a origem na transferencia. */
    @JvmStatic
    fun accountPickerLabel(item: InboxItem?): String =
        if (item?.entryType == "TRANSFER") "De qual conta?" else needText("account")

    /**
     * A categoria que o item ja tem, quando nao esta na lista do seletor da edicao (so o nome,
     * arquivada ou de outro tipo): fica como opcao, com o nome do item. [shownCategoryIds] sao
     * os ids das opcoes da lista (filterCategoryOptions do tipo). null quando nao ha opcao extra.
     */
    @JvmStatic
    fun itemCategoryOption(item: InboxItem?, shownCategoryIds: Collection<String>): CategoryFallbackOption? {
        val itemCategory = draftFromItem(item).categoryId
        if (itemCategory.isEmpty() || itemCategory in shownCategoryIds) return null
        return CategoryFallbackOption(itemCategory, item?.category)
    }

    // { version: item?.version, ... }: sem versao a chave nao vai (undefined some no JSON).
    private fun withVersion(item: InboxItem?, changes: Map<String, Any?>): LinkedHashMap<String, Any?> {
        val body = linkedMapOf<String, Any?>()
        val version = item?.version
        if (version != null) body["version"] = version
        body.putAll(changes)
        return body
    }

    // O Number do JS no corpo: inteiro como Long, o resto como esta; Infinity vira null, como
    // no JSON.stringify.
    private fun jsonNumber(value: Double): Number? = when {
        !value.isFinite() -> null
        value == Math.floor(value) && Math.abs(value) < 9.0e15 -> value.toLong()
        else -> value
    }

    // String(numero) do JS para um valor em reais: 45.90 -> "45.9", 50 -> "50".
    private fun numberString(value: BigDecimal): String {
        if (value.signum() == 0) return "0"
        val stripped = value.stripTrailingZeros()
        return (if (stripped.scale() < 0) stripped.setScale(0) else stripped).toPlainString()
    }
}
