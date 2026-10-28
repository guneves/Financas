// Ajustes (pages/ajustes/): o que as secoes fazem inline, sem teste no node — os rotulos, o saldo
// em reais da conta, o saldo inicial com sinal, o que o menu de uma conta oferece, o fechamento
// sugerido do cartao, o aviso do debito automatico, o nome de usuario —, aqui com testes
// (SettingsTest.kt). O corpo do cartao e CardFunctions.cardFormPayload.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import br.financas.app.core.parseMoneyInput
import java.math.BigDecimal

object Settings {

    /** ACCOUNT_TYPE_LABELS de ContasSection.jsx, na ordem do seletor. */
    val ACCOUNT_TYPES: List<Pair<String, String>> = listOf(
        "CHECKING" to "Conta corrente",
        "SAVINGS" to "Poupança",
        "BROKERAGE" to "Corretora",
        "CASH" to "Dinheiro",
        "OTHER" to "Outra",
    )

    fun accountTypeLabel(type: String?): String = ACCOUNT_TYPES.firstOrNull { it.first == type }?.second ?: type.orEmpty()

    /**
     * A Conta global (2026-10-27): o unico lugar onde uma moeda aparece e este tipo do seletor de
     * "Nova conta"; no servidor ela e CHECKING em USD (GLOBAL_TYPE de ContasSection.jsx).
     */
    const val GLOBAL_TYPE = "GLOBAL_USD"
    val NEW_ACCOUNT_TYPES: List<Pair<String, String>> = ACCOUNT_TYPES + (GLOBAL_TYPE to "Conta global (US$)")

    /** O rotulo da linha: "Conta global (USD)" na conta em outra moeda, senao o do tipo. */
    fun accountLabel(type: String?, currency: String?): String {
        val code = (currency ?: "BRL").ifBlank { "BRL" }.uppercase()
        return if (code != "BRL") "Conta global ($code)" else accountTypeLabel(type)
    }

    /** O corpo do POST /api/accounts da "Nova conta" (o que handleCreateAccount manda). */
    fun newAccountBody(name: String, type: String, institution: String, initialBalance: BigDecimal): Map<String, Any?> {
        val global = type == GLOBAL_TYPE
        val body = linkedMapOf<String, Any?>(
            "name" to name,
            "type" to if (global) "CHECKING" else type,
            "institution" to institution,
            "initial_balance" to initialBalance,
        )
        if (global) body["currency"] = "USD"
        return body
    }

    /** KIND_LABELS de CategoriasSection.jsx. */
    val CATEGORY_KINDS: List<Pair<String, String>> = listOf("EXPENSE" to "Despesa", "INCOME" to "Receita", "BOTH" to "Ambos")

    fun categoryKindLabel(kind: String?): String = CATEGORY_KINDS.firstOrNull { it.first == kind }?.second ?: kind.orEmpty()

    /**
     * O saldo da conta em reais (accountBalanceBrl): GET /api/accounts manda balance_brl, null
     * numa conta em moeda estrangeira sem cambio hoje ("sem câmbio hoje"). Numa conta em reais
     * sem o campo vale o balance.
     */
    fun accountBalanceBrl(balance: BigDecimal?, balanceBrl: BigDecimal?, currency: String?): BigDecimal? {
        val brl = currency.isNullOrEmpty() || currency.uppercase() == "BRL"
        return balanceBrl ?: if (brl) balance ?: BigDecimal.ZERO else null
    }

    /** O saldo inicial lido (parseBalanceInput): o "-" na frente vale (cheque especial). */
    fun parseBalanceInput(value: String?): MoneyInput {
        val text = (value ?: "").trim()
        val negative = text.startsWith("-")
        val parsed = parseMoneyInput(if (negative) text.substring(1) else text)
        return if (negative && parsed is MoneyInput.Amount) MoneyInput.Amount(parsed.value.negate()) else parsed
    }

    /** O que o "⋯" de uma conta ativa oferece (accountMenuItems). */
    data class AccountMenu(val makeDefault: Boolean, val linkToPortfolio: Boolean, val unlinkFromPortfolio: Boolean)

    fun accountMenu(type: String?, isDefault: Boolean, currency: String?): AccountMenu {
        val portfolio = type == "BROKERAGE"
        val brl = currency.isNullOrEmpty() || currency.uppercase() == "BRL"
        return AccountMenu(
            // A conta global (outra moeda) nunca e a padrao: o lancamento sem conta e em reais.
            makeDefault = !isDefault && !portfolio && brl,
            linkToPortfolio = !portfolio && !isDefault && brl,
            unlinkFromPortfolio = portfolio,
        )
    }

    /** O fechamento sugerido ao digitar o vencimento: 7 dias antes, dando a volta em 30. "" sem numero. */
    fun suggestedClosingDay(dueText: String): String {
        // parseInt() do JS: o numero do comeco ("10a" = 10).
        val due = Regex("^\\s*[+-]?\\d+").find(dueText)?.value?.trim()?.toIntOrNull() ?: return ""
        var closing = due - 7
        if (closing <= 0) closing += 30
        return closing.toString()
    }

    /** O toast do seletor "Débito automático" de um cartao. */
    fun autopayNotice(cardName: String, dueDay: Int?, accountName: String?): String =
        if (accountName != null) {
            "Débito automático do \"$cardName\" ligado: a fatura será paga no vencimento, dia $dueDay, com saldo de $accountName."
        } else {
            "Débito automático do \"$cardName\" desligado."
        }

    /** "Vence dia 10 • Fecha dia 3 • Débito em Itaú" (credito e/ou debito). */
    fun cardDetail(credit: Boolean, dueDay: Int?, closingDay: Int?, debitAccountName: String?): String =
        listOfNotNull(
            if (credit) "Vence dia $dueDay • Fecha dia $closingDay" else null,
            debitAccountName?.let { "Débito em $it" },
        ).joinToString(" • ")

    /** O Salvar do nome de usuario: mudou e tem ao menos 2 letras (o servidor confere o resto). */
    fun canSaveUsername(typed: String, current: String?): Boolean {
        val trimmed = typed.trim()
        return trimmed != (current ?: "") && trimmed.length >= 2
    }
}
