// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/cardPurchase.js (purchaseInstallments, refundPrefillAmount; testes em
// cardPurchase.test.js), formatInvoiceLabel de pages/lancamentos/helpers.js e as regras inline de
// pages/lancamentos/Cartoes.jsx (getInvoiceStatus, paymentHint, a conta sugerida, os textos de
// excluir), CardRefundSheet.jsx (a mensagem do estorno) e CardShareSheet.jsx (o total e a divisao
// atual, em centavos). Aqui: CardRulesTest.kt. As faturas, o total, "Próxima", fechada/paga e
// atrasada vem prontos de GET /api/cc-invoices: nada disso e calculado aqui.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.data.AccountDto
import br.financas.app.data.CardInvoiceDto
import br.financas.app.data.InvoiceCardDto
import br.financas.app.data.PurchaseInstallmentDto
import java.math.BigDecimal
import java.math.BigInteger

/** O selo de uma fatura que nao e futura. */
enum class InvoiceStatus { CREDIT, PAST_DUE, CLOSED, OPEN }

/** A compra como os sheets a leem: o valor desta parcela e quantas parcelas tem. */
data class PurchaseRef(val amount: BigDecimal, val installmentTotal: Int = 1)

object CardRules {

    private fun toCents(value: BigDecimal?): BigInteger = Sharing.toCents(value ?: BigDecimal.ZERO)

    private fun fromCents(cents: BigInteger): BigDecimal = BigDecimal(cents).movePointLeft(2)

    private fun installmentCount(info: String?): Int {
        val total = info.orEmpty().split("/").getOrNull(1)?.trim()?.toIntOrNull()
        return if (total != null && total > 0) total else 1
    }

    /**
     * As parcelas desta compra entre as candidatas: a 1 centavo do valor desta parcela e com a
     * mesma quantidade de parcelas (uma linha antiga sem client_id cai na chave antiga).
     */
    fun purchaseInstallments(candidates: List<PurchaseInstallmentDto>?, purchase: PurchaseRef): List<PurchaseInstallmentDto> {
        val purchaseCents = toCents(purchase.amount)
        val total = purchase.installmentTotal.takeIf { it > 0 } ?: 1
        return candidates.orEmpty().filter { item ->
            (toCents(item.amount) - purchaseCents).abs() <= BigInteger.ONE && installmentCount(item.installmentInfo) == total
        }
    }

    /** O estorno comeca pelo total da compra: a soma das parcelas, em centavos; sem elas, a estimativa. */
    fun refundPrefillAmount(purchase: PurchaseRef, candidates: List<PurchaseInstallmentDto>?): BigDecimal {
        val found = purchaseInstallments(candidates, purchase)
        val cents = if (found.isNotEmpty()) {
            found.fold(BigInteger.ZERO) { sum, item -> sum + toCents(item.amount) }
        } else {
            toCents(purchase.amount) * BigInteger.valueOf((purchase.installmentTotal.takeIf { it > 0 } ?: 1).toLong())
        }
        return fromCents(cents)
    }

    /** "MM/AAAA". */
    fun formatInvoiceLabel(month: Int, year: Int): String = "${month.toString().padStart(2, '0')}/$year"

    /** O selo: credito (total < 0), em atraso (depois do vencimento), fechada ou aberta. */
    fun invoiceStatus(invoice: CardInvoiceDto): InvoiceStatus = when {
        invoice.total.signum() < 0 -> InvoiceStatus.CREDIT
        invoice.pastDue -> InvoiceStatus.PAST_DUE
        invoice.closed -> InvoiceStatus.CLOSED
        else -> InvoiceStatus.OPEN
    }

    /** Por que o Pagar esta (ou nao) ali, numa linha; null sem nada a dizer. */
    fun paymentHint(invoice: CardInvoiceDto, autopayAccountId: String?, future: Boolean = false): String? {
        if (invoice.total.signum() < 0) return "O crédito do estorno abate a próxima fatura"
        if (!invoice.closed) {
            val closing = invoice.closingDate
            if (closing.isNullOrEmpty()) return "Pagamento liberado após o fechamento"
            return if (future) "Fecha em ${formatDateBR(closing)}" else "Fecha em ${formatDateBR(closing)} · pagamento liberado depois"
        }
        if (!autopayAccountId.isNullOrEmpty() && !invoice.dueDate.isNullOrEmpty()) {
            return "Débito automático em ${formatDateBR(invoice.dueDate)}"
        }
        return null
    }

    /** O Pagar: so numa fatura fechada e sem credito (o servidor confere de novo). */
    fun canPay(invoice: CardInvoiceDto): Boolean = invoice.payable

    /**
     * A conta sugerida no sheet: a do debito automatico do cartao, se ativa; senao a padrao;
     * senao a primeira ativa — a mesma que o servidor usa sem account_id.
     */
    fun suggestedPayAccountId(accounts: List<AccountDto>, autopayAccountId: String?): String {
        val active = accounts.filter { !it.isArchived }
        if (!autopayAccountId.isNullOrEmpty() && active.any { it.id == autopayAccountId }) return autopayAccountId
        return (active.firstOrNull { it.isDefault } ?: active.firstOrNull())?.id.orEmpty()
    }

    /** A fatura marcada "Próxima" pelo servidor e o cartao dela; null sem nenhuma. */
    fun nearest(cards: List<InvoiceCardDto>): Pair<InvoiceCardDto, CardInvoiceDto>? {
        for (card in cards) {
            val invoice = card.invoices.firstOrNull { it.nearest }
            if (invoice != null) return card to invoice
        }
        return null
    }

    /** A descricao do cabecalho de Cartoes. */
    fun headerDescription(cards: List<InvoiceCardDto>, openTotal: BigDecimal): String {
        val (card, invoice) = nearest(cards) ?: return "Faturas em aberto por cartão."
        return "Próxima fatura: ${card.cardName} ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} · " +
            "${formatCurrency(invoice.total)} · ${formatCurrency(openTotal)} em aberto nos cartões"
    }

    /** "Fecha dia N · vence dia M" (+ " · débito automático em <conta>"). */
    fun cardSubtitle(card: InvoiceCardDto, autopayAccountName: String?): String {
        val base = "Fecha dia ${card.closingDay ?: "-"} · vence dia ${card.dueDay ?: "-"}"
        return if (!card.autopayAccountId.isNullOrEmpty()) "$base · débito automático em ${autopayAccountName ?: "—"}" else base
    }

    /** O rotulo das faturas futuras dobradas: "Fatura seguinte" / "Próximas N faturas". */
    fun futureLabel(future: List<CardInvoiceDto>): String =
        if (future.size == 1) "Fatura seguinte" else "Próximas ${future.size} faturas"

    /** A soma das faturas futuras (os totais do servidor), em centavos. */
    fun futureTotal(future: List<CardInvoiceDto>): BigDecimal =
        fromCents(future.fold(BigInteger.ZERO) { sum, item -> sum + toCents(item.total) })

    /** O texto da confirmacao de excluir uma compra: as abertas saem, as pagas ficam. */
    fun deletePurchaseMessage(openCount: Int, paidCount: Int): String {
        if (paidCount <= 0) return "Todas as parcelas dela saem das faturas."
        val openText = if (openCount == 1) "A parcela em aberto sai da fatura." else "As $openCount parcelas em aberto saem das faturas."
        val paidText = if (paidCount == 1) {
            "A parcela já paga fica: saiu com o pagamento da fatura. Para tirá-la também, desfaça esse pagamento no Extrato."
        } else {
            "As $paidCount parcelas já pagas ficam: saíram com o pagamento das faturas. Para tirá-las também, desfaça esses pagamentos no Extrato."
        }
        return "$openText $paidText"
    }

    /** "Excluir compra e parcelas" numa parcelada. */
    fun deletePurchaseLabel(installmentTotal: Int): String =
        if (installmentTotal > 1) "Excluir compra e parcelas" else "Excluir compra"

    /** O toast do estorno: "Estorno de R$ X lançado na fatura MM/AAAA." */
    fun refundNotice(amount: BigDecimal, invoiceMonth: Int?, invoiceYear: Int?): String {
        val invoice = if (invoiceMonth != null && invoiceYear != null) " na fatura ${formatInvoiceLabel(invoiceMonth, invoiceYear)}" else ""
        return "Estorno de ${formatCurrency(amount)} lançado$invoice."
    }

    /** O toast do pagamento: "... paga — R$ X saiu de <conta>." ou "... foi debitado." */
    fun paidNotice(cardName: String, invoice: CardInvoiceDto, accountName: String?): String {
        val payer = if (accountName != null) " saiu de $accountName" else " foi debitado"
        return "Fatura $cardName ${formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear)} paga — ${formatCurrency(invoice.total)}$payer."
    }

    /** O total da compra inteira e a divisao atual, para "De quem é?" (somas em centavos). */
    data class ShareStart(val total: BigDecimal, val form: ShareForm, val installments: Int)

    fun shareStart(rows: List<PurchaseInstallmentDto>): ShareStart {
        val total = fromCents(rows.fold(BigInteger.ZERO) { sum, row -> sum + toCents(row.amount) })
        val first = rows.firstOrNull { !it.shareMode.isNullOrEmpty() } ?: rows.firstOrNull()
        val othersTotal = fromCents(
            rows.fold(BigInteger.ZERO) { sum, row ->
                sum + toCents(Sharing.othersAmount(SharedRow(row.amount, row.shareMode, row.sharePerson, row.shareOthersAmount)))
            },
        )
        val item = first?.let {
            ShareItem(it.shareMode, it.sharePerson, if (it.shareMode == Sharing.SPLIT) othersTotal else it.shareOthersAmount)
        }
        return ShareStart(total, Sharing.shareFormFrom(item), rows.size)
    }
}
