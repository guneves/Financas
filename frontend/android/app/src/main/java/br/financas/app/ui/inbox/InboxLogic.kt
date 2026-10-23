// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: o que frontend/src/pages/lancamentos/Aprovar.jsx monta inline (os corpos de approve/"É este"/
// split, as linhas de fonte, candidato e decidido, o "Usada N vezes", as opcoes de categoria da
// edicao, os cartoes e contas dos seletores). As regras com teste no node estao em
// rules/InboxRules.kt; aqui o resto, testado em InboxLogicTest.kt.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.ui.inbox

import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatSignedCurrency
import br.financas.app.core.getLocalDateString
import br.financas.app.data.AccountDto
import br.financas.app.data.CreditCardDto
import br.financas.app.data.InboxCandidateDto
import br.financas.app.data.InboxHintDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.InboxSourceDto
import br.financas.app.rules.Card
import br.financas.app.rules.CardFunctions
import br.financas.app.rules.CategoryOption
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.InboxRules
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeParseException

object InboxLogic {

    /** A lista pendente se rele sozinha com a tela aberta (REFRESH_MS de Aprovar.jsx). */
    const val REFRESH_MS = 20_000L

    /** A chave do botao ocupado: "<id>:<acao>" (o busyKey da web). */
    fun busyKey(id: String, action: String): String = "$id:$action"

    const val BUSY_READY = "ready"

    /** "Aprovar": { version, remember }. */
    fun approveBody(item: InboxItemDto, remember: Boolean): Map<String, Any?> =
        withVersion(item).apply { this["remember"] = remember }

    /** "É este": { version, remember, candidate: { table, id } }. */
    fun matchBody(item: InboxItemDto, candidate: InboxCandidateDto, remember: Boolean): Map<String, Any?> =
        withVersion(item).apply {
            this["remember"] = remember
            this["candidate"] = linkedMapOf("table" to candidate.table, "id" to candidate.id)
        }

    /** "Não é a mesma: separar": { version, source, source_id }. */
    fun splitBody(item: InboxItemDto, source: InboxSourceDto): Map<String, Any?> =
        withVersion(item).apply {
            this["source"] = source.source
            this["source_id"] = source.id
        }

    /**
     * O item que voltou de uma decisao, na lista da vista: na de pendentes fica (trocado) se ainda
     * esta pendente e sai se foi decidido; na de decididos, o contrario ("Voltar para aprovar").
     * Um item pendente que nao estava na lista entra no alto. null (lista nao lida) fica null.
     */
    fun applyDecision(items: List<InboxItemDto>?, updated: InboxItemDto, pendingView: Boolean): List<InboxItemDto>? {
        if (items == null) return null
        val belongs = updated.isPending == pendingView
        val present = items.any { it.id == updated.id }
        return when {
            !belongs -> items.filter { it.id != updated.id }
            present -> items.map { if (it.id == updated.id) updated else it }
            pendingView -> listOf(updated) + items
            else -> items
        }
    }

    /** O valor da lista: com sinal (sai, entra), a transferencia sem. */
    fun amountText(item: InboxItemDto): String {
        val sign = InboxRules.amountSign(item.rule)
        return if (sign != 0) formatSignedCurrency(item.amount, sign) else formatCurrency(item.amount)
    }

    /** "Aprovar como novo" quando ha lancamentos parecidos. */
    fun approvesAsNew(item: InboxItemDto): Boolean = item.candidates.isNotEmpty()

    /** O "⋯" so aparece quando ha alguma fonte a separar (alem de "Editar antes de aprovar"). */
    fun showsMenu(item: InboxItemDto): Boolean = InboxRules.splittableSources(item.rule).isNotEmpty()

    /** As fontes que o "⋯" oferece separar, com o DTO (o corpo do split leva source e id). */
    fun splittable(item: InboxItemDto): List<InboxSourceDto> {
        val ids = InboxRules.splittableSources(item.rule).map { it.source to it.id }.toSet()
        return item.sources.filter { (it.source to it.id) in ids }
    }

    /** Uma linha de fonte: "Notificação Itaú · compra no crédito · final 1234 · 17/10/2026 às 22:30 · mesma compra". */
    fun sourceLine(source: InboxSourceDto): String {
        val whenPart = if (source.source == "notification") InboxRules.whenText(source.occurredAt) else formatDateBR(source.date)
        val paired = if (source.role == "PAIRED") " · mesma compra" else ""
        return "${InboxRules.sourceLabel(source.rule)} · $whenPart$paired"
    }

    fun candidateTitle(candidate: InboxCandidateDto): String =
        candidate.description.orEmpty()
            .ifEmpty { candidate.category.orEmpty() }
            .ifEmpty { InboxRules.candidateKindLabel(candidate.kind) }

    /** "Compra no cartão · 17/10/2026 · R$ 45,90 · parcela 1/3 · Itaú Visa". */
    fun candidateLine(candidate: InboxCandidateDto): String {
        val where = candidate.cardName.orEmpty().ifEmpty { candidate.accountName.orEmpty() }
        val transferTo = if (!candidate.transferAccountName.isNullOrEmpty()) " → ${candidate.transferAccountName}" else ""
        val installment = if (!candidate.installmentInfo.isNullOrEmpty()) " · parcela ${candidate.installmentInfo}" else ""
        val place = if (where.isNotEmpty()) " · $where$transferTo" else ""
        return "${InboxRules.candidateKindLabel(candidate.kind)} · ${formatDateBR(candidate.date)} · " +
            "${formatCurrency(candidate.amount)}$installment$place"
    }

    /** O titulo de um item: a descricao, senao o tipo. */
    fun itemTitle(item: InboxItemDto): String =
        item.description.orEmpty().ifEmpty { InboxRules.entryTypeLabel(item.entryType) }

    /** A linha de um decidido: "Aprovado · 17/10/2026 às 22:30 · R$ 45,90 · lançado em 18/10/2026". */
    fun decidedLine(item: InboxItemDto): String {
        val targetDate = item.target?.date.orEmpty()
        val launched = if (targetDate.isNotEmpty() && targetDate != item.occurredAt.orEmpty().take(10)) {
            " · lançado em ${formatDateBR(targetDate)}"
        } else {
            ""
        }
        return "${InboxRules.decisionText(item.rule)} · ${InboxRules.whenText(item.occurredAt)} · " +
            "${formatCurrency(item.amount)}$launched"
    }

    /** "Voltar para aprovar" so num recusado. */
    fun restorable(item: InboxItemDto): Boolean = item.state == InboxItemDto.STATE_DENIED

    /** "Usada 3 vezes · desde 17/10/2026" (a data local de created_at, um instante UTC). */
    fun hintUsage(hint: InboxHintDto, zone: ZoneId = ZoneId.systemDefault()): String =
        "Usada ${hint.uses} ${if (hint.uses == 1) "vez" else "vezes"} · desde ${hintDate(hint.createdAt, zone)}"

    fun hintDate(createdAt: String?, zone: ZoneId = ZoneId.systemDefault()): String {
        if (createdAt.isNullOrEmpty()) return formatDateBR(null)
        val local = try {
            getLocalDateString(Instant.parse(createdAt).atZone(zone).toLocalDate())
        } catch (error: DateTimeParseException) {
            createdAt.take(10)
        }
        return formatDateBR(local)
    }

    /**
     * As opcoes do seletor de categoria da edicao, depois de "Sugerida pelas regras" (valor ""):
     * a categoria do proprio item quando ela nao esta na lista, depois as do tipo. Pares
     * (valor, rotulo).
     */
    fun editCategoryOptions(
        options: List<CategoryOption>,
        draftType: String,
        item: InboxItemDto,
    ): List<Pair<String, String>> {
        val categories = EntryOptions.filterCategoryOptions(options, if (draftType == "INCOME") "INCOME" else "EXPENSE")
        val fallback = InboxRules.itemCategoryOption(item.rule, categories.map { it.id })
        val list = mutableListOf<Pair<String, String>>()
        if (fallback != null) list.add(fallback.value to fallback.label.orEmpty())
        categories.forEach { list.add(it.id to it.label) }
        return list
    }

    /** O seletor de cartao: so os de credito (041); a compra num so-debito vira despesa na conta. */
    fun pickerCards(cards: List<CreditCardDto>): List<CreditCardDto> =
        cards.filter { CardFunctions.hasCredit(Card(id = it.id, name = it.name, creditEnabled = it.creditEnabled, debitAccountId = it.debitAccountId)) }

    /** As contas dos seletores: so as ativas. */
    fun activeAccounts(accounts: List<AccountDto>): List<AccountDto> = accounts.filter { !it.isArchived }

    /** O destino da transferencia: qualquer ativa menos a de origem. */
    fun destinationAccounts(accounts: List<AccountDto>, originId: String?): List<AccountDto> =
        accounts.filter { it.id != originId }

    /** Onde rolar a lista para o item que a notificacao abriu; -1 se nao esta nela. */
    fun indexOf(items: List<InboxItemDto>?, id: String?): Int =
        if (id.isNullOrEmpty() || items == null) -1 else items.indexOfFirst { it.id == id }

    private fun withVersion(item: InboxItemDto): LinkedHashMap<String, Any?> {
        val body = linkedMapOf<String, Any?>()
        if (item.version != null) body["version"] = item.version
        return body
    }
}
