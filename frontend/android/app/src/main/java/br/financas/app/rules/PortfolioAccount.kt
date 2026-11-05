// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/portfolioAccount.js (portfolioAccount.test.js); aqui
// PortfolioAccountTest.kt, os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js

/**
 * A conta da carteira (dono, 2026-10-17): uma conta do tipo Corretora em reais e a conta de onde
 * as operacoes saem (e para onde a venda e o resgate voltam). Toda operacao nova vai para o Extrato
 * nessa conta, a nao ser que o dono marque "Não descontar de nenhuma conta". O backend tem a mesma
 * regra (`portfolio_cash_account_id()`) para quem nao manda a chave; a tela manda sempre.
 */
object PortfolioAccount {
    const val PORTFOLIO_ACCOUNT_TYPE = "BROKERAGE"

    const val NO_PORTFOLIO_ACCOUNT_MESSAGE =
        "Vincule uma conta à carteira antes: cadastre uma conta do tipo Corretora em Ajustes › Contas."
    const val PICK_ACCOUNT_MESSAGE = "Escolha a conta da carteira, ou marque “Não descontar de nenhuma conta”."

    /** Uma conta de GET /api/accounts, so o que estas regras leem. */
    data class Account(
        val id: String,
        val type: String?,
        val currency: String? = null,
        val archivedAt: String? = null,
        /** Alimentada pela Pluggy (`pluggy` de GET /api/accounts, Fase 3). */
        val pluggy: Boolean = false,
    )

    /**
     * O valor do campo: [enabled] falso e a marca "não descontar de nenhuma conta"; [missing] diz
     * que o dono ainda nao tem conta da carteira (a tela preenche quando a lista de contas chega).
     */
    data class CashLink(val enabled: Boolean, val accountId: String, val missing: Boolean, val fresh: Boolean = false)

    /** Uma recusa do campo, com o texto para a tela (o `throw new Error` da web). */
    class CashLinkError(message: String) : IllegalArgumentException(message)

    /** O lancamento ligado e sempre em reais. */
    fun isBrlAccount(account: Account): Boolean =
        account.currency.isNullOrEmpty() || account.currency.uppercase() == "BRL"

    /** As contas da carteira, na ordem da lista de contas (a do backend), so as ativas em reais. */
    fun portfolioAccounts(accounts: List<Account>?): List<Account> =
        (accounts ?: emptyList()).filter { account ->
            account.type == PORTFOLIO_ACCOUNT_TYPE && account.archivedAt.isNullOrEmpty() && isBrlAccount(account)
        }

    fun pickPortfolioAccountId(accounts: List<Account>?): String = portfolioAccounts(accounts).firstOrNull()?.id ?: ""

    /** [CashLink.fresh]: ainda nao passou pela lista de contas ([cashLinkWithAccounts] decide o padrao). */
    fun emptyCashLink(): CashLink = CashLink(enabled = true, accountId = "", missing = false, fresh = true)

    /**
     * Investimentos so pela Pluggy (Fase 3): a Corretora alimentada pela Pluggy recebe sozinha o que
     * a corretora faz, e o servidor recusa uma operacao digitada com o caixa nela. Por isso o padrao,
     * ali, e "Não descontar de nenhuma conta", nunca a Corretora.
     */
    const val PLUGGY_FED_NOTE = "A Corretora é atualizada pela Pluggy: o que a corretora faz entra sozinho. " +
        "Aqui só o que ela não vê (cripto, outra instituição), sem descontar da Corretora."

    fun pluggyFedPortfolio(accounts: List<Account>?): Boolean = portfolioAccounts(accounts).firstOrNull()?.pluggy == true

    /**
     * O valor do campo quando a lista de contas chega: a falta de conta da carteira, o padrao de uma
     * operacao nova (desligado na Corretora da Pluggy) e a conta da carteira quando ligado.
     */
    fun cashLinkWithAccounts(value: CashLink, accounts: List<Account>?): CashLink {
        val portfolio = portfolioAccounts(accounts)
        var next = value.copy(missing = portfolio.isEmpty())
        if (next.fresh) {
            next = next.copy(fresh = false)
            if (portfolio.firstOrNull()?.pluggy == true) next = next.copy(enabled = false)
        }
        val first = portfolio.firstOrNull()
        if (next.enabled && next.accountId.isEmpty() && first != null) next = next.copy(accountId = first.id)
        return next
    }

    fun isPluggyFedAccount(accounts: List<Account>?, accountId: String?): Boolean =
        !accountId.isNullOrEmpty() && accounts.orEmpty().firstOrNull { it.id == accountId }?.pluggy == true

    /** O campo a partir do metadata salvo: so `cash_account_id` texto conta. */
    fun cashLinkFromMetadata(metadata: Map<String, Any?>?): CashLink {
        val raw = metadata?.get("cash_account_id")
        val accountId = if (raw is String) Js.trim(raw) else ""
        return CashLink(enabled = accountId.isNotEmpty(), accountId = accountId, missing = false)
    }

    /**
     * O pedaco do metadata, sempre explicito: a conta, ou `null` para nao descontar de lugar nenhum
     * (sem a chave o backend usaria a conta da carteira). Uma operacao nova sem conta da carteira e
     * recusada aqui ([CashLinkError] com a mensagem que leva a Ajustes); a edicao ([editing]) de
     * uma operacao antiga nao.
     */
    fun cashLinkMetadata(value: CashLink?, editing: Boolean = false): Map<String, Any?> {
        if (!editing && value?.missing == true) throw CashLinkError(NO_PORTFOLIO_ACCOUNT_MESSAGE)
        if (value?.enabled != true) return mapOf("cash_account_id" to null)
        if (value.accountId.isEmpty()) throw CashLinkError(PICK_ACCOUNT_MESSAGE)
        return mapOf("cash_account_id" to value.accountId)
    }
}
