// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/goals.test.js, na mesma ordem; o ultimo (o corpo do sheet) nao
// tem par no node: payloadFromForm segue inline em pages/Metas.jsx.
package br.financas.app.rules

import br.financas.app.rules.Goals.badge
import br.financas.app.rules.Goals.forecastHint
import br.financas.app.rules.Goals.forecastText
import br.financas.app.rules.Goals.shortMonthYear
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class GoalsTest {

    // node: 'shortMonthYear: mes curto sem ponto e o ano inteiro'
    @Test
    fun shortMonthYearMesCurtoEAnoInteiro() {
        assertEquals("out/2028", shortMonthYear("2028-10"))
        assertEquals("mai/2027", shortMonthYear("2027-05"))
        assertEquals("jan/2030", shortMonthYear("2030-01"))
    }

    // node: 'forecastText: alcancada, renda, sem previsao ou o mes'
    @Test
    fun forecastTextAlcancadaRendaSemPrevisaoOuOMes() {
        assertEquals("Alcançada", forecastText(true, "NET_WORTH", "2028-10"))
        assertEquals("—", forecastText(false, "MONTHLY_INCOME", null))
        assertEquals("Sem previsão", forecastText(false, "PORTFOLIO", null))
        assertEquals("dez/2028", forecastText(false, "PORTFOLIO", "2028-12"))
    }

    // node: 'forecastHint: anos e meses, no singular quando e um'
    @Test
    fun forecastHintAnosEMeses() {
        fun hint(months: Int) = forecastHint(false, "NET_WORTH", "2030-01", months)
        assertEquals("em 2 anos e 3 meses", hint(27))
        assertEquals("em 1 ano e 1 mês", hint(13))
        assertEquals("em 2 anos", hint(24))
        assertEquals("em 5 meses", hint(5))
        assertEquals("", hint(0))
        assertEquals("Informe um aporte mensal", forecastHint(false, "NET_WORTH", null, null))
        assertEquals("", forecastHint(true, "NET_WORTH", "2030-01", 3))
        assertEquals("", forecastHint(false, "MONTHLY_INCOME", null, null))
    }

    // node: 'goalBadge: alcancada vence o prazo; sem data, nenhum selo'
    @Test
    fun goalBadgeAlcancadaVenceOPrazo() {
        assertEquals(Goals.GoalBadge("Alcançada", Goals.BadgeTone.SUCCESS), badge(true, false))
        assertEquals(Goals.GoalBadge("Fora do prazo", Goals.BadgeTone.WARNING), badge(false, false))
        assertEquals(Goals.GoalBadge("No prazo", Goals.BadgeTone.NEUTRAL), badge(false, true))
        assertNull(badge(false, null))
    }

    @Test
    fun payloadLimpaOQueOTipoEsconde() {
        val dated = Goals.GoalForm(name = "Reserva", kind = "NET_WORTH", targetAmount = "100.000", monthlyContribution = "2.000", annualReturnPercent = "8,5", targetDate = "2030-01-31")
        val body = Goals.payload(dated)
        assertNull(body["asset_class"])
        assertEquals(0, BigDecimal(100000).compareTo(body["target_amount"] as BigDecimal))
        assertEquals(0, BigDecimal(2000).compareTo(body["monthly_contribution"] as BigDecimal))
        assertEquals(0, BigDecimal("8.5").compareTo(body["annual_return_percent"] as BigDecimal))
        assertEquals("2030-01-31", body["target_date"])

        // A mesma meta trocada para Renda: nada do que ficou escondido vai.
        val income = Goals.payload(dated.copy(kind = "MONTHLY_INCOME"))
        assertEquals(0, BigDecimal.ZERO.compareTo(income["monthly_contribution"] as BigDecimal))
        assertNull(income["annual_return_percent"])
        assertNull(income["target_date"])

        val klass = Goals.payload(Goals.GoalForm(name = "Ações", kind = "ASSET_CLASS", assetClass = "REIT", targetAmount = "50000", annualReturnPercent = "-5"))
        assertEquals("REIT", klass["asset_class"])
        assertEquals(0, BigDecimal(-5).compareTo(klass["annual_return_percent"] as BigDecimal))
        assertEquals(0, BigDecimal.ZERO.compareTo(klass["monthly_contribution"] as BigDecimal))
        assertNull(klass["target_date"])
        assertNull(Goals.payload(Goals.GoalForm(targetAmount = ""))["target_amount"])
        assertEquals("abc", Goals.payload(Goals.GoalForm(targetAmount = "abc"))["target_amount"])
    }

    @Test
    fun classLabelComoGetClassLabel() {
        assertEquals("Ações", Goals.classLabel("STOCKS"))
        assertEquals("Fundos Imobiliários", Goals.classLabel("REIT"))
        assertEquals("Renda Fixa", Goals.classLabel("FIXED_INCOME"))
        assertEquals("Outros", Goals.classLabel("OTHER"))
        assertEquals("CRYPTO", Goals.classLabel("CRYPTO"))
    }
}
