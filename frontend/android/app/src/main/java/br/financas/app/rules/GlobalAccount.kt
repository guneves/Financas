// Porte: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de frontend/src/lib/globalAccount.js (testes: globalAccount.test.js e GlobalAccountTest.kt).
//
// Conta global (dono, 2026-10-27): a conta em dolar (Wise) e a unica tela do app fora de reais.
// Saldo e extrato na moeda da conta, e embaixo um "~ R$" pelo cambio de hoje (PTAX) ou "sem
// cambio hoje". Fora dela tudo e real: o Inicio soma a conta convertida no saldo em contas.
//
// O Pix de uma conta em reais para ela e UMA transferencia (047): `amount` e o que saiu em reais,
// `transfer_amount` o que entrou em dolar; sem ele, o dolar e "a conferir" e fica fora do saldo.
// Puro: nada de Android nem de Compose.
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.TransactionDto
import br.financas.app.core.MoneyInput
import br.financas.app.core.parseMoneyInput
import java.math.BigDecimal
import java.math.RoundingMode

object GlobalAccount {

    fun currencyOf(account: AccountDto?): String = (account?.currency ?: "BRL").ifBlank { "BRL" }.uppercase()

    fun isGlobal(account: AccountDto?): Boolean = account != null && currencyOf(account) != "BRL"

    /** As contas globais ativas, na ordem da lista de contas. */
    fun globalAccounts(accounts: List<AccountDto>): List<AccountDto> = accounts.filter { isGlobal(it) && !it.isArchived }

    /** Uma linha do extrato vista da conta global: valor na moeda dela, com sentido (+1 entra, -1 sai). */
    data class Row(
        val transaction: TransactionDto,
        val direction: Int,
        /** null = o dolar de uma transferencia de reais ainda nao chegou ("a conferir"). */
        val native: BigDecimal?,
        val pending: Boolean,
        /** O que saiu da conta em reais (so na transferencia de la para ca). */
        val sourceAmount: BigDecimal?,
        /** A outra conta da transferencia. */
        val counterpart: String?,
    )

    fun row(transaction: TransactionDto, accountId: String, namesById: Map<String, String>): Row {
        if (transaction.type == "TRANSFER") {
            if (transaction.transferAccountId == accountId) {
                val received = transaction.transferAmount
                return Row(transaction, 1, received, received == null, transaction.amount, namesById[transaction.accountId])
            }
            return Row(transaction, -1, transaction.amount, false, null, namesById[transaction.transferAccountId])
        }
        return Row(transaction, if (transaction.type == "INCOME") 1 else -1, transaction.amount, false, null, null)
    }

    fun statement(transactions: List<TransactionDto>, accountId: String, namesById: Map<String, String>): List<Row> =
        transactions
            .filter { it.accountId == accountId || it.transferAccountId == accountId }
            .map { row(it, accountId, namesById) }

    data class Totals(val incoming: BigDecimal, val outgoing: BigDecimal, val pending: Int)

    /** Entradas e saidas do extrato carregado, na moeda da conta (sem o "a conferir"). */
    fun totals(rows: List<Row>): Totals {
        var incoming = BigDecimal.ZERO
        var outgoing = BigDecimal.ZERO
        rows.forEach { row ->
            val value = row.native ?: return@forEach
            if (row.direction > 0) incoming += value else outgoing += value
        }
        return Totals(incoming.setScale(2, RoundingMode.HALF_UP), outgoing.setScale(2, RoundingMode.HALF_UP), rows.count { it.pending })
    }

    /** O "~ R$": o saldo que o servidor ja converteu (balance_brl, PTAX de hoje), ou null sem cambio. */
    fun brlHint(account: AccountDto?): BigDecimal? = if (isGlobal(account)) account?.balanceBrl else null

    /** O cambio do Pix (reais por unidade), quatro casas; null sem os dois lados. */
    fun impliedRate(row: Row): BigDecimal? {
        val native = row.native ?: return null
        val source = row.sourceAmount ?: return null
        if (row.pending || native.signum() == 0 || source.signum() == 0) return null
        return source.divide(native, 4, RoundingMode.HALF_UP)
    }

    // ---- "Pix para ca" (pages/ContaGlobal.jsx, savePix) ----

    /** O formulario do Pix de uma conta em reais para a conta global: os dois valores, como texto. */
    data class PixForm(
        val accountId: String = "",
        val amount: String = "",
        val transferAmount: String = "",
        val date: String = "",
        val description: String = "",
    )

    /** As contas de onde sai o Pix: ativas, em reais, nunca a Corretora. */
    fun pixSources(accounts: List<AccountDto>): List<AccountDto> =
        accounts.filter { !it.isArchived && currencyOf(it) == "BRL" && it.type != "BROKERAGE" }

    private fun positive(text: String): BigDecimal? =
        (parseMoneyInput(text) as? MoneyInput.Amount)?.value?.takeIf { it.signum() > 0 }

    /** O que falta, com as frases da web; "" quando da para salvar. */
    fun pixMissing(form: PixForm, currency: String): String = when {
        form.accountId.isEmpty() -> "Escolha a conta em reais de onde saiu o Pix."
        positive(form.amount) == null -> "Informe quanto saiu em reais."
        positive(form.transferAmount) == null -> "Informe quanto entrou em $currency."
        form.date.isEmpty() -> "Informe a data."
        else -> ""
    }

    /**
     * POST /api/transfers: uma transferencia so (047), `amount` o que saiu em reais e
     * `transfer_amount` o que entrou na conta global. O client_id faz a repeticao voltar a mesma.
     */
    fun pixBody(form: PixForm, account: AccountDto, clientId: String): Map<String, Any?> = linkedMapOf(
        "account_id" to form.accountId,
        "transfer_account_id" to account.id,
        "amount" to positive(form.amount),
        "transfer_amount" to positive(form.transferAmount),
        "date" to form.date,
        "description" to form.description.trim().ifEmpty { "Pix para ${account.name}" },
        "client_id" to clientId,
    )
}
