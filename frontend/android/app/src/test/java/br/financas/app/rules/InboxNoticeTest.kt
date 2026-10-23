// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de matchedInboxNotice em frontend/src/lib/inboxRules.test.js, mais o da compra no
// cartao (a primeira parcela diz).
package br.financas.app.rules

import br.financas.app.rules.InboxNotice.matchedInboxNotice
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class InboxNoticeTest {

    @Test
    fun aMatchedCreationSaysSo() {
        assertTrue(matchedInboxNotice(JSONObject().put("matched_inbox", true), "Despesa").startsWith("Despesa: já esperava"))
        assertEquals("", matchedInboxNotice(JSONArray().put(JSONObject().put("id", "x")), "Compra"))
    }

    @Test
    fun theWholeText() {
        assertEquals(
            "Despesa de R\$ 10: já esperava em Aprovar (do celular ou do banco). Ficou um lançamento só.",
            matchedInboxNotice(JSONObject().put("matched_inbox", true), "Despesa de R\$ 10"),
        )
    }

    @Test
    fun aCardPurchaseReadsTheFirstInstallment() {
        val rows = JSONArray()
            .put(JSONObject().put("id", "1").put("matched_inbox", true))
            .put(JSONObject().put("id", "2"))
        assertTrue(matchedInboxNotice(rows, "Compra").isNotEmpty())
        assertEquals("", matchedInboxNotice(JSONArray(), "Compra"))
    }

    @Test
    fun nothingWhenNotMatched() {
        assertEquals("", matchedInboxNotice(JSONObject().put("matched_inbox", false), "Despesa"))
        assertEquals("", matchedInboxNotice(JSONObject(), "Despesa"))
        assertEquals("", matchedInboxNotice(null, "Despesa"))
        assertEquals("", matchedInboxNotice("texto", "Despesa"))
    }
}
