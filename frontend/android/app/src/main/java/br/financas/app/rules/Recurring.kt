// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de frontend/src/lib/recurring.js (testes: recurring.test.js e
// RecurringTest.kt): a frequencia em texto e a edicao de valor e conta de uma recorrencia.
// O calendario (proxima data, pausas, pendentes) e so do servidor (services/recurring.py).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import br.financas.app.core.parseMoneyInput
import java.math.BigDecimal

object Recurring {

    private val FREQUENCY_LABELS = mapOf("WEEKLY" to "Semanal", "MONTHLY" to "Mensal", "YEARLY" to "Anual")

    /** "Mensal", "Semanal", "Anual"; com intervalo, "A cada 2 meses" etc. */
    fun frequencyLabel(frequency: String, intervalCount: Int?): String {
        val base = FREQUENCY_LABELS[frequency] ?: frequency
        val interval = intervalCount?.takeIf { it != 0 } ?: 1
        if (interval <= 1) return base
        return when (frequency) {
            "WEEKLY" -> "A cada $interval semanas"
            "YEARLY" -> "A cada $interval anos"
            else -> "A cada $interval meses"
        }
    }

    /** Uma opcao do seletor de conta da edicao. */
    data class AccountOption(val id: String, val label: String, val disabled: Boolean)

    /** As contas ativas e, se a da recorrencia nao esta entre elas, "Conta arquivada" no topo, so para mostrar. */
    fun accountOptions(currentAccountId: String?, accounts: List<Pair<String, String>>): List<AccountOption> {
        val options = accounts.map { (id, name) -> AccountOption(id, name, false) }
        if (!currentAccountId.isNullOrEmpty() && accounts.none { it.first == currentAccountId }) {
            return listOf(AccountOption(currentAccountId, "Conta arquivada", true)) + options
        }
        return options
    }

    /** O PATCH so com o que mudou; a conta so quando outra foi escolhida (nunca ""). */
    fun editPatch(amount: BigDecimal?, accountId: String?, draftAmount: String, draftAccountId: String): Map<String, Any?> {
        val patch = linkedMapOf<String, Any?>()
        when (val parsed = parseMoneyInput(draftAmount)) {
            is MoneyInput.Amount -> if (amount == null || parsed.value.compareTo(amount) != 0) patch["amount"] = parsed.value
            // NaN !== Number(item.amount) no JS: um valor invalido vai e o servidor recusa.
            MoneyInput.Invalid -> patch["amount"] = null
            MoneyInput.Empty -> Unit
        }
        if (draftAccountId.isNotEmpty() && draftAccountId != (accountId ?: "")) patch["account_id"] = draftAccountId
        return patch
    }
}
