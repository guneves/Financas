// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/autoDecisions.test.js que o celular usa, na mesma ordem.
package br.financas.app.rules

import br.financas.app.data.ApiJson
import br.financas.app.data.AutoDecisionDto
import br.financas.app.data.AutoDecisionsDto
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutoDecisionsTest {
    private fun detail(json: String): JsonObject = ApiJson.parseToJsonElement(json).jsonObject

    private fun decision(kind: String = "auto_confirm", undoneAt: String? = null, undoable: Boolean = true) =
        AutoDecisionDto(id = "a", kind = kind, undoneAt = undoneAt, undoable = undoable)

    // node: 'a confirmacao automatica nao aparece na lista: nao ha Revisar para onde voltar'
    @Test
    fun aConfirmacaoAutomaticaNaoApareceNaLista() {
        val items = listOf(decision(kind = "auto_confirm"), decision(kind = "pluggy_category").copy(id = "b"))
        assertEquals(listOf("b"), AutoDecisions.shownDecisions(items).map { it.id })
        assertEquals(emptyList<AutoDecisionDto>(), AutoDecisions.shownDecisions(emptyList()))
    }

    // node: 'o texto de cada decisao'
    @Test
    fun oTextoDeCadaDecisao() {
        assertEquals("Categoria da Pluggy", AutoDecisions.decisionTitle("pluggy_category"))
        assertEquals("Decisão automática", AutoDecisions.decisionTitle("nova"))
        assertEquals(
            "Outros → Alimentação",
            AutoDecisions.decisionDetail("pluggy_category", detail("""{"before": ["Outros", "a"], "after": ["Alimentação", "b"]}""")),
        )
        assertEquals("Ficou em Lazer", AutoDecisions.decisionDetail("auto_confirm", detail("""{"category": ["Lazer", "x"]}""")))
        assertTrue(
            Regex("45,90.*49,90").containsMatchIn(
                AutoDecisions.decisionDetail("conflict_changed", detail("""{"before_cents": 4590, "after_cents": 4990}""")),
            ),
        )
        assertEquals("PTAX de 09/10/2026", AutoDecisions.decisionDetail("fx_fallback", detail("""{"rate_date": "2026-10-09"}""")))
        assertEquals("", AutoDecisions.decisionDetail("auto_confirm", JsonObject(emptyMap())))
    }

    // node: 'desfazer: so a que nao foi desfeita, e o aviso de cada uma'
    @Test
    fun desfazerSoAQueNaoFoiDesfeita() {
        assertTrue(AutoDecisions.canUndo(decision()))
        assertFalse(AutoDecisions.canUndo(decision(undoneAt = "2026-11-18")))
        assertEquals("Desfeito.", AutoDecisions.undoToast("transfer_guess"))
        assertTrue(AutoDecisions.undoToast("conflict_vanished").contains("voltou"))
    }

    // node: 'a carteira (fase 2): o texto e o que se desfaz aqui'
    @Test
    fun aCarteiraOTextoEOQueSeDesfazAqui() {
        assertEquals("Custódia da corretora: o app já tinha", AutoDecisions.decisionTitle("investment_custody"))
        assertEquals("ITSA4", AutoDecisions.decisionDetail("investment_proceed_link", detail("""{"code": "ITSA4"}""")))
        assertEquals(
            "LCA ORIGINAL · R$ 1.000,00",
            AutoDecisions.decisionDetail("investment_custody_in", detail("""{"name": "LCA ORIGINAL", "cost": 1000}""")),
        )
        assertEquals(
            "CDB C6 · 13,5% a.a.",
            AutoDecisions.decisionDetail("investment_rate_deduced", detail("""{"name": "CDB C6", "fixedAnnualRate": 13.5}""")),
        )
        assertFalse(AutoDecisions.canUndo(decision(kind = "investment_custody_in", undoable = false)))
        assertEquals("Apague no Extrato para desfazer", AutoDecisions.noUndoLabel(decision(undoable = false)))
        assertEquals("Desfeito", AutoDecisions.noUndoLabel(decision(undoneAt = "2026-11-19")))
        assertTrue(AutoDecisions.undoToast("investment_custody").contains("Conferência"))
        assertEquals("BB RF LP HIGH", AutoDecisions.decisionDetail("investment_closed_fund", detail("""{"name": "BB RF LP HIGH"}""")))
    }

    // So o celular: a resposta do servidor lida como chega (um antigo sem `undoable` vale sim).
    @Test
    fun aRespostaDoServidor() {
        val body = """{"items": [{"id": "d1", "kind": "conflict_vanished", "table": "transactions", "target_id": "t",
            "detail": {"row": {"description": "PADARIA", "date": "2026-11-15"}}, "created_at": "2026-11-19T10:00:00Z",
            "undone_at": null}], "counts": {"conflict_vanished": 1}}"""
        val parsed = ApiJson.decodeFromString(AutoDecisionsDto.serializer(), body)
        val first = parsed.items.single()
        assertTrue(first.undoable)
        assertEquals("PADARIA", AutoDecisions.decisionDetail(first))
        assertEquals(1, parsed.counts["conflict_vanished"])
        assertEquals("14% a.a.", AutoDecisions.decisionDetail("investment_rate_deduced", detail("""{"fixedAnnualRate": 14.0}""")))
    }
}
