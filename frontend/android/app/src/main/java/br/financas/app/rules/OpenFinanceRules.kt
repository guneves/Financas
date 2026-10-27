package br.financas.app.rules

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Ajustes › Open Finance (043) no celular: so o estado das conexoes e o "Atualizar" — conectar
 * e mapear ficam na web. Port de `lib/openFinance.js` (itemStatus, itemProblem, accountLabel,
 * balanceCheck, syncSummary): mudou um, muda o outro, com um teste de cada lado
 * (OpenFinanceRulesTest.kt copia os casos de openFinance.test.js).
 */
object OpenFinanceRules {

    /** O estado como o Badge mostra: o texto e o tom ("success", "info", "warning", "danger", "neutral"). */
    data class Status(val label: String, val tone: String)

    private val STATUS: Map<String, Status> = mapOf(
        "UPDATED" to Status("Atualizada", "success"),
        "UPDATING" to Status("Atualizando no banco…", "info"),
        "OUTDATED" to Status("Desatualizada", "warning"),
        "LOGIN_ERROR" to Status("Precisa entrar de novo", "danger"),
        "WAITING_USER_INPUT" to Status("Esperando um código seu", "warning"),
    )

    @JvmStatic
    fun itemStatus(status: String?, needsOwner: Boolean): Status {
        val known = STATUS[status]
        // Um item "atualizado" pode ainda esperar o dono (executionStatus): o aviso vence.
        if (needsOwner && (known == null || known.tone == "success" || known.tone == "info")) {
            return Status("Precisa de você no banco", "warning")
        }
        return known ?: Status(status.orEmpty().ifEmpty { "Sem estado" }, "neutral")
    }

    /** A mensagem da Pluggy vence; depois o que o dono faz; depois a ultima falha. */
    @JvmStatic
    fun itemProblem(errorMessage: String?, needsOwner: Boolean, lastSyncError: String?): String = when {
        !errorMessage.isNullOrEmpty() -> errorMessage
        needsOwner -> "A conexão espera uma ação sua (senha, código ou um aceite no banco). Use \"Reconectar\"."
        !lastSyncError.isNullOrEmpty() -> "A última atualização falhou: $lastSyncError"
        else -> ""
    }

    /** "Conta Corrente · 0001/12345-0" / "Mastercard Black · final 9437". */
    @JvmStatic
    fun accountLabel(type: String?, name: String?, number: String?): String {
        val title = name.orEmpty().ifEmpty { if (type == "CREDIT") "Cartão" else "Conta" }
        val digits = number.orEmpty().filter { it.isDigit() }
        if (digits.isEmpty()) return title
        return if (type == "CREDIT") "$title · final ${digits.takeLast(4)}" else "$title · $number"
    }

    /** Conferir o saldo, nunca ajustar: "match", "drift" ou "none" (cartao, ou sem mapeamento). */
    data class BalanceCheck(val state: String, val difference: BigDecimal?)

    @JvmStatic
    fun balanceCheck(type: String?, pluggyBalance: BigDecimal?, appBalance: BigDecimal?): BalanceCheck {
        if (type == "CREDIT" || pluggyBalance == null || appBalance == null) return BalanceCheck("none", null)
        val difference = pluggyBalance.subtract(appBalance).setScale(2, RoundingMode.HALF_UP)
        return BalanceCheck(if (difference.signum() == 0) "match" else "drift", difference)
    }

    /** O resumo de um "Atualizar" para o toast. */
    @JvmStatic
    fun syncSummary(counts: Map<String, Int>?, removed: Int?): String {
        val fresh = counts?.get("new") ?: 0
        val joined = counts?.get("merged") ?: 0
        val gone = removed ?: 0
        val parts = mutableListOf<String>()
        if (fresh > 0) parts += if (fresh == 1) "1 movimento novo no Aprovar" else "$fresh movimentos novos no Aprovar"
        if (joined > 0) parts += if (joined == 1) "1 juntou-se a um aviso" else "$joined juntaram-se a avisos"
        if (gone > 0) parts += if (gone == 1) "1 saiu (o banco desfez)" else "$gone saíram (o banco desfez)"
        return if (parts.isEmpty()) "Nada novo." else parts.joinToString(", ") + "."
    }
}
