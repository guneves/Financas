package br.financas.app.rules

import java.math.BigDecimal

/**
 * A Conta investimento de Posicao (ContaInvestimento.jsx, 049): o servidor faz a conta (saldo
 * hoje, em transito, saldo depois de liquidar); aqui so o que a tela escolhe mostrar.
 */
object BrokerSettlement {

    private val CENT = BigDecimal("0.01")

    /** A dica de "Saldo hoje": confere com a corretora, o saldo da corretora com a diferenca, ou o nome da conta. */
    sealed interface Hint {
        data object Matches : Hint
        data class Broker(val balance: BigDecimal?, val difference: BigDecimal) : Hint
        data class Account(val name: String) : Hint
    }

    /** Sem a Pluggy, o nome da conta; com ela, "confere" quando |diferenca| < R$ 0,01 (null vale 0). */
    fun hint(pluggyPresent: Boolean, balance: BigDecimal?, difference: BigDecimal?, accountName: String?): Hint {
        if (!pluggyPresent) return Hint.Account(accountName.orEmpty())
        val diff = difference ?: BigDecimal.ZERO
        return if (diff.abs() < CENT) Hint.Matches else Hint.Broker(balance, diff)
    }

    enum class Tone { GAIN, LOSS, NEUTRAL }

    /** A cor do total em transito: neutra no modo privado ou em zero; verde entra, vermelho sai. */
    fun transitTone(total: BigDecimal?, hidden: Boolean): Tone = when {
        hidden || total == null || total.signum() == 0 -> Tone.NEUTRAL
        total.signum() > 0 -> Tone.GAIN
        else -> Tone.LOSS
    }

    /** Um provento anunciado e "Pagamento em"; o resto (operacao, outro lancamento) "Liquida em". */
    fun isPayment(kind: String?): Boolean = kind == "proceed"
}
