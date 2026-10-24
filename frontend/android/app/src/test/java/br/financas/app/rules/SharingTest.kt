// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/sharing.test.js que tocam shareFormError e sharePayload,
// na mesma ordem; o nome do teste do node vai no comentario de cada um. O ultimo teste
// (shareFormFrom e os centavos) nao tem par no node: sharing.test.js nao os testa.
package br.financas.app.rules

import br.financas.app.rules.Sharing.SHARE_OPTIONS
import br.financas.app.rules.Sharing.shareFormError
import br.financas.app.rules.Sharing.shareFormFrom
import br.financas.app.rules.Sharing.sharePayload
import br.financas.app.rules.Sharing.toCents
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.math.BigInteger

class SharingTest {
    private val pizza = SharedRow(amount = BigDecimal(80), shareMode = "SPLIT", shareOthersAmount = BigDecimal("40.1"), sharePerson = "Ana")

    private fun assertMoney(expected: String, actual: BigDecimal) =
        assertEquals("$actual", 0, BigDecimal(expected).compareTo(actual))

    // node: 'the owner part of a split, an all-others and a plain row'
    @Test
    fun theOwnerPartOfASplitAnAllOthersAndAPlainRow() {
        assertMoney("40.1", Sharing.othersAmount(pizza))
        assertMoney("39.9", Sharing.ownAmount(pizza))
        assertMoney("0", Sharing.ownAmount(SharedRow(amount = BigDecimal(50), shareMode = "OTHERS")))
        assertMoney("50", Sharing.ownAmount(SharedRow(amount = BigDecimal(50))))
        assertMoney("0", Sharing.othersAmount(SharedRow(amount = BigDecimal(50))))
    }

    // node: 'the list line says who and the owner part'
    @Test
    fun theListLineSaysWhoAndTheOwnerPart() {
        assertEquals("Dividida com Ana · sua parte R$ 39,90", Sharing.shareSummary(pizza))
        assertEquals("De Bruno", Sharing.shareSummary(SharedRow(amount = BigDecimal(10), shareMode = "OTHERS", sharePerson = "Bruno")))
        assertEquals("", Sharing.shareSummary(SharedRow(amount = BigDecimal(10))))
    }

    // node: 'receivables group by person, case and spaces aside, biggest first' (a parte do settlePayload)
    @Test
    fun settlePayloadSplitsTheIdsByKind() {
        val items = listOf(Sharing.ReceivableRef("TRANSACTION", "t1"), Sharing.ReceivableRef("TRANSACTION", "t2"))
        assertEquals(
            listOf("transaction_ids" to listOf("t1", "t2"), "cc_expense_ids" to emptyList<String>(), "settled" to true),
            Sharing.settlePayload(items).toList(),
        )
        val card = Sharing.settlePayload(listOf(Sharing.ReceivableRef("CARD_PURCHASE", "c1")), settled = false)
        assertEquals(listOf("c1"), card["cc_expense_ids"])
        assertEquals(false, card["settled"])
    }
    private fun assertMatches(pattern: String, text: String?) =
        assertTrue("\"$text\" contem /$pattern/", text != null && Regex(pattern).containsMatchIn(text))

    // node: 'the form needs a name, and a split smaller than the total'
    @Test
    fun theFormNeedsANameAndASplitSmallerThanTheTotal() {
        val eighty = BigDecimal(80)
        assertEquals("", shareFormError(ShareForm(shareMode = ""), eighty))
        assertMatches("nome", shareFormError(ShareForm(shareMode = "OTHERS", sharePerson = " "), eighty))
        assertMatches("parte", shareFormError(ShareForm(shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = ""), eighty))
        assertMatches("menor", shareFormError(ShareForm(shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = "80"), eighty))
        assertEquals("", shareFormError(ShareForm(shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = "40"), eighty))
    }

    // node: 'the payload clears with null and trims the name'
    @Test
    fun thePayloadClearsWithNullAndTrimsTheName() {
        assertEquals(mapOf("share_mode" to null), sharePayload(ShareForm(shareMode = "")))
        assertEquals(
            listOf("share_mode" to "OTHERS", "share_person" to "Ana"),
            sharePayload(ShareForm(shareMode = "OTHERS", sharePerson = " Ana ", shareOthersAmount = "9")).toList(),
        )
        assertEquals(
            listOf("share_mode" to "SPLIT", "share_person" to "Ana", "share_others_amount" to BigDecimal("12.5")),
            sharePayload(ShareForm(shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = "12.5")).toList(),
        )
    }

    // Sem par no node: shareFormFrom, SHARE_OPTIONS e o arredondamento dos centavos.
    @Test
    fun theFormFromARowAndTheCents() {
        assertEquals(ShareForm("", "", ""), shareFormFrom(null))
        assertEquals(
            ShareForm("SPLIT", "Ana", "40.1"),
            shareFormFrom(ShareItem(shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = BigDecimal("40.10"))),
        )
        assertEquals(
            ShareForm("OTHERS", "Bruno", ""),
            shareFormFrom(ShareItem(shareMode = "OTHERS", sharePerson = "Bruno", shareOthersAmount = BigDecimal(5))),
        )
        assertEquals(ShareForm("SPLIT", "", ""), shareFormFrom(ShareItem(shareMode = "SPLIT")))
        assertEquals(listOf("", "SPLIT", "OTHERS"), SHARE_OPTIONS.map { it.value })
        // Math.round: o meio centavo vai para +infinito, tambem nos negativos.
        assertEquals(BigInteger.valueOf(4001), toCents(BigDecimal("40.005")))
        assertEquals(BigInteger.ZERO, toCents(BigDecimal("-0.005")))
        assertEquals(BigInteger.valueOf(-1), toCents(BigDecimal("-0.006")))
        // Number(): "12,5" e NaN (a parte digitada com virgula e recusada), "Infinity" tambem.
        assertMatches("parte", shareFormError(ShareForm("SPLIT", "Ana", "12,5"), BigDecimal(80)))
        assertMatches("parte", shareFormError(ShareForm("SPLIT", "Ana", "Infinity"), BigDecimal(80)))
        assertEquals(null, sharePayload(ShareForm("SPLIT", "Ana", null))["share_others_amount"])
        assertTrue(sharePayload(ShareForm("SPLIT", "Ana", null)).containsKey("share_others_amount"))
    }
}
