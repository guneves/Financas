// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: matchedInboxNotice() de frontend/src/lib/inboxRules.js (teste em inboxRules.test.js);
// aqui: InboxNoticeTest.kt. O texto do celular nao diz "Aprovar" (a tela saiu do celular, 045).
package br.financas.app.rules

import org.json.JSONArray
import org.json.JSONObject

object InboxNotice {

    /**
     * O aviso quando a criacao fechou um item dos avisos do celular ou do banco (a resposta traz
     * matched_inbox: true; na compra no cartao, a primeira parcela). "" quando nao fechou.
     * [data] e a resposta lida com JSONTokener: JSONObject (lancamento) ou JSONArray (parcelas).
     */
    @JvmStatic
    fun matchedInboxNotice(data: Any?, label: String): String {
        val row = if (data is JSONArray) data.optJSONObject(0) else data as? JSONObject
        if (row == null || !truthy(row.opt("matched_inbox"))) return ""
        return "$label: já tinha chegado pelo celular ou pelo banco. Ficou um lançamento só."
    }

    // O `row?.matched_inbox` do JS: true, 1, "x"... valem; false, 0, "", null nao.
    private fun truthy(value: Any?): Boolean = when (value) {
        null, JSONObject.NULL -> false
        is Boolean -> value
        is Number -> value.toDouble() != 0.0 && !value.toDouble().isNaN()
        is String -> value.isNotEmpty()
        else -> true
    }
}
