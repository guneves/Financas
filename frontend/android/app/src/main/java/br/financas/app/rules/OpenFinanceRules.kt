package br.financas.app.rules

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Ajustes › Open Finance (043) no celular: so o estado das conexoes e o "Atualizar" — conectar
 * e mapear ficam na web. Port de `lib/openFinance.js` (itemStatus, itemProblem, accountLabel,
 * balanceCheck, syncSummary, syncHoursLabel, syncHoursChoices, checkSummary, itemBankName,
 * checkReasonLabel, balanceExplanation, autoRecordHint): mudou um, muda o outro, com um teste de cada lado
 * (OpenFinanceRulesTest.kt copia os casos de openFinance.test.js). Uma diferenca de proposito: o
 * celular nao tem a tela Aprovar (045), entao onde a web diz "no Revisar" aqui e "no Revisar" (o
 * Extrato, onde o que espera se resolve no celular).
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
    @JvmOverloads
    fun balanceCheck(type: String?, pluggyBalance: BigDecimal?, appBalance: BigDecimal?, awaitingCents: Long = 0): BalanceCheck {
        if (type == "CREDIT" || pluggyBalance == null || appBalance == null) return BalanceCheck("none", null)
        val difference = pluggyBalance.subtract(appBalance).setScale(2, RoundingMode.HALF_UP)
        val waiting = BigDecimal.valueOf(awaitingCents, 2)
        return BalanceCheck(if (difference.compareTo(waiting) == 0) "match" else "drift", difference)
    }

    /** O resumo de um "Atualizar" para o toast. Com "Gravar sozinho" (044), o gravado/ligado sai do
     *  "novo no Revisar" (so fica o que espera o dono). */
    @JvmStatic
    @JvmOverloads
    fun syncSummary(
        counts: Map<String, Int>?,
        removed: Int?,
        autoRecorded: Map<String, Int>? = null,
        investments: Map<String, Int>? = null,
    ): String {
        val recorded = autoRecorded?.get("recorded") ?: 0
        val linked = autoRecorded?.get("linked") ?: 0
        val fresh = maxOf((counts?.get("new") ?: 0) - recorded - linked, 0)
        val joined = counts?.get("merged") ?: 0
        val operations = investments?.get("recorded") ?: 0
        val gone = removed ?: 0
        val parts = mutableListOf<String>()
        if (recorded > 0) parts += if (recorded == 1) "1 lançamento gravado" else "$recorded lançamentos gravados"
        if (linked > 0) parts += if (linked == 1) "1 ligado ao que você lançou" else "$linked ligados ao que você lançou"
        if (fresh > 0) parts += if (fresh == 1) "1 movimento novo no Revisar" else "$fresh movimentos novos no Revisar"
        if (joined > 0) parts += if (joined == 1) "1 juntou-se a um aviso" else "$joined juntaram-se a avisos"
        if (operations > 0) parts += if (operations == 1) "1 operação na carteira" else "$operations operações na carteira"
        if (gone > 0) parts += if (gone == 1) "1 saiu (o banco desfez)" else "$gone saíram (o banco desfez)"
        return if (parts.isEmpty()) "Nada novo." else parts.joinToString(", ") + "."
    }

    /** "Busca automatica" (sync_hours no servidor): 0 desliga, nunca abaixo de 6 h (dono, 2026-10-27:
     *  a Pluggy so traz dado novo do banco de 6 a 24 h, e o app so le). */
    const val MIN_SYNC_HOURS = 6

    @JvmField
    val SYNC_HOURS_CHOICES: List<Int> = listOf(0, 6, 12, 24)

    @JvmStatic
    fun syncHoursLabel(hours: Int?): String = if (hours == null || hours == 0) "Desligada" else "A cada $hours h"

    /** As escolhas; um valor fora da lista (gravado pela API) aparece tambem, para nao sumir. */
    @JvmStatic
    fun syncHoursChoices(current: Int?): List<Pair<Int, String>> {
        val values = SYNC_HOURS_CHOICES.toMutableList()
        if (current != null && current in MIN_SYNC_HOURS..24 && current !in values) {
            values += current
            values.sort()
        }
        return values.map { it to syncHoursLabel(it) }
    }

    /** A conferencia de uma conta: "none" (sem conferencia), "match" ou "drift", e o texto. */
    data class CheckSummary(val state: String, val text: String)

    @JvmStatic
    fun checkSummary(present: Boolean, bankOnly: Int, appOnly: Int, awaiting: Int): CheckSummary {
        if (!present) return CheckSummary("none", "")
        val parts = mutableListOf<String>()
        if (bankOnly > 0) parts += if (bankOnly == 1) "1 só no banco" else "$bankOnly só no banco"
        if (appOnly > 0) parts += if (appOnly == 1) "1 só no app" else "$appOnly só no app"
        if (awaiting > 0) parts += if (awaiting == 1) "1 espera no Revisar" else "$awaiting esperam no Revisar"
        if (bankOnly == 0 && appOnly == 0) {
            return CheckSummary(
                "match",
                if (parts.isEmpty()) "Movimentos conferem" else "Movimentos conferem · " + parts.joinToString(" · "),
            )
        }
        return CheckSummary("drift", parts.joinToString(" · "))
    }

    /** O banco de uma conexao: o que os nomes das contas dizem (bank_name; o MeuPluggy nao diz). */
    @JvmStatic
    fun itemBankName(bankName: String?, connectorName: String?): String =
        bankName.orEmpty().ifEmpty { connectorName.orEmpty().ifEmpty { "Open Finance" } }

    private val CHECK_REASONS: Map<String, String> = mapOf(
        "awaiting" to "espera no Revisar",
        "denied" to "descartado no Revisar",
        "unmapped" to "a conta ainda sem destino",
        "changed_after_edit" to "o banco mudou o valor depois que você editou",
        "invoice_payment_missing" to "pagamento de fatura sem o pagamento no app",
        "invoice_payment_linked" to "pagamento de fatura",
        "different_amount_or_date" to "lançado com outro valor ou data",
        "not_in_bank" to "o banco não tem",
    )

    /** Por que um movimento esta so de um lado (o `reason` de cada linha da conferencia). */
    @JvmStatic
    fun checkReasonLabel(reason: String?): String = CHECK_REASONS[reason].orEmpty()

    /** De onde vem a diferenca de saldo (explanation do servidor, em centavos): linhas de texto, [] sem
     *  diferenca. `money` formata reais. */
    @JvmStatic
    fun balanceExplanation(
        difference: Long?,
        bankOnly: Long,
        awaiting: Long,
        appOnly: Long,
        before: Long,
        money: (BigDecimal) -> String,
    ): List<String> {
        if (difference == null || difference == 0L) return emptyList()
        val lines = mutableListOf<String>()
        fun part(cents: Long, text: String) {
            if (cents != 0L) lines += "${money(BigDecimal.valueOf(cents, 2))} $text"
        }
        part(bankOnly, "de movimentos só no banco")
        part(awaiting, "esperando no Revisar")
        part(appOnly, "de lançamentos só no app")
        part(before, "de antes da conferência (confira o saldo inicial da conta)")
        return lines
    }

    /** O texto de "Gravar sozinho": o que faz ligado, ou por que nao liga (auto_record_blockers). */
    @JvmStatic
    fun autoRecordHint(autoRecord: Boolean, blockers: List<String>): String = when {
        autoRecord -> "Os movimentos dos bancos conectados viram lançamentos sozinhos. O Revisar, no Extrato, fica " +
            "para o que só você decide (uma transferência sem a outra ponta, outra moeda)."
        blockers.isNotEmpty() -> blockers.joinToString(" ")
        else -> "Ligado, o que a Pluggy traz é lançado sozinho, para você só revisar; o que já espera vindo dela é " +
            "lançado na hora."
    }
}
