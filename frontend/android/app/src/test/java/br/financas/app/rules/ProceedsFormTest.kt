// O buildPayload/handleEdit de pages/Proventos.jsx (sem teste do lado web): os casos sao o
// comportamento da web hoje.
package br.financas.app.rules

import br.financas.app.rules.ProceedsForm.Form
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.math.BigDecimal

class ProceedsFormTest {
    private val cdb = ProceedsRules.Asset("a1", ticker = "CDB X", category = "RENDA_FIXA", assetClass = "FIXED_INCOME")
    private val stock = ProceedsRules.Asset("a2", ticker = "PETR4", category = "ACAO", assetClass = "STOCKS")

    private fun error(block: () -> Unit) = assertThrows(ProceedsForm.FormError::class.java, block).message

    @Test
    fun aCouponIsFixedWithPaymentDateAsRecordDate() {
        val form = Form(assetId = "a1", proceedsType = "INTEREST", paymentDate = "2027-01-15", grossAmount = "1.234,56", notes = "1o cupom")
        val body = ProceedsForm.payload(form, cdb, editing = false)
        assertEquals("2027-01-15", body["record_date"])
        assertEquals(BigDecimal("1234.56"), body["gross_amount"])
        assertNull(body["tax_amount"])
        assertNull(body["amount_per_unit"])
        assertFalse(body.containsKey("repeat"))
        assertEquals(listOf("asset_id", "proceeds_type", "declared_date", "record_date", "ex_date", "payment_date", "amount_per_unit", "eligible_quantity", "gross_amount", "tax_amount", "notes"), body.keys.toList())
    }

    @Test
    fun aRepeatedCouponSendsTheSeriesOnlyOnCreate() {
        val form = Form(assetId = "a1", proceedsType = "INTEREST", paymentDate = "2027-01-15", grossAmount = "80", taxAmount = "12", repeatEvery = "6", repeatCount = "4")
        val body = ProceedsForm.payload(form, cdb, editing = false)
        assertEquals(mapOf("every_months" to 6, "count" to 4), body["repeat"])
        assertEquals(BigDecimal("12"), body["tax_amount"])
        assertFalse(ProceedsForm.payload(form, cdb, editing = true).containsKey("repeat"))
        assertEquals("Informe quantos pagamentos (de 1 a 120).", error { ProceedsForm.payload(form.copy(repeatCount = "121"), cdb, false) })
        assertEquals("Informe quantos pagamentos (de 1 a 120).", error { ProceedsForm.payload(form.copy(repeatCount = "2.5"), cdb, false) })
        assertEquals(3, (ProceedsForm.payload(form.copy(repeatCount = "3.0"), cdb, false)["repeat"] as Map<*, *>)["count"])
    }

    @Test
    fun anAmortizationHasNoTax() {
        val form = Form(assetId = "a1", proceedsType = "AMORTIZATION", paymentDate = "2027-01-15", grossAmount = "500", taxAmount = "x")
        assertNull(ProceedsForm.payload(form, cdb, editing = false)["tax_amount"])
    }

    @Test
    fun fixedRefusals() {
        val form = Form(assetId = "a1", proceedsType = "INTEREST", paymentDate = "2027-01-15", grossAmount = "80")
        assertEquals("Selecione o ativo na lista.", error { ProceedsForm.payload(form.copy(assetId = ""), cdb, false) })
        assertEquals("Informe a data de pagamento.", error { ProceedsForm.payload(form.copy(paymentDate = ""), cdb, false) })
        assertEquals("Informe o valor bruto do pagamento.", error { ProceedsForm.payload(form.copy(grossAmount = "0"), cdb, false) })
        assertEquals("Informe o valor bruto do pagamento.", error { ProceedsForm.payload(form.copy(grossAmount = ""), cdb, false) })
        assertEquals("Informe um IR válido.", error { ProceedsForm.payload(form.copy(taxAmount = "abc"), cdb, false) })
    }

    @Test
    fun aDividendIsMarketWithBlanksAsNull() {
        val form = Form(assetId = "a2", proceedsType = "DIVIDEND", recordDate = "2026-10-01", paymentDate = "2026-10-20", amountPerUnit = "0,45")
        val body = ProceedsForm.payload(form, stock, editing = false)
        assertEquals(BigDecimal("0.45"), body["amount_per_unit"])
        assertNull(body["eligible_quantity"])
        assertNull(body["declared_date"])
        assertNull(body["ex_date"])
        assertEquals("2026-10-01", body["record_date"])
        assertEquals("Informe a data com.", error { ProceedsForm.payload(form.copy(recordDate = ""), stock, false) })
        assertEquals("Informe valores numéricos válidos.", error { ProceedsForm.payload(form.copy(eligibleQuantity = "dez"), stock, false) })
        // Cupom num ativo de bolsa nao e FIXED: pede a data com.
        assertEquals("Informe a data com.", error { ProceedsForm.payload(form.copy(proceedsType = "INTEREST", recordDate = ""), stock, false) })
    }

    @Test
    fun editFormFromASavedProceed() {
        val form = ProceedsForm.editForm("a2", null, null, null, "2026-09-30", "2026-10-20", BigDecimal("0.4500"), BigDecimal("100"), null, null, null, "2026-10-24")
        assertEquals("DIVIDEND", form.proceedsType)
        assertEquals("2026-10-24", form.recordDate)
        assertEquals("0,45", form.amountPerUnit)
        assertEquals("100", form.eligibleQuantity)
        assertEquals("", form.grossAmount)
        assertEquals("", form.repeatEvery)
    }

    @Test
    fun texts() {
        assertEquals("PETR4, pago em 20/10/2026.", ProceedsForm.deleteMessage("PETR4", "20/10/2026", automatic = false))
        assertEquals("Ativo, pago em 20/10/2026. Ele foi calculado automaticamente e não volta nas próximas atualizações.", ProceedsForm.deleteMessage(null, "20/10/2026", automatic = true))
        assertEquals("Proventos atualizados: 2 novo(s), 0 corrigido(s), 1 removido(s).", ProceedsForm.syncToast(2, 0, 1))
        assertEquals("Proventos já estavam em dia.", ProceedsForm.syncToast(0, 0, 0))
        assertEquals(listOf("2025-12", "2026-01"), ProceedsForm.chartRows(listOf("2026-01", "2025-12")) { it })
    }
}
