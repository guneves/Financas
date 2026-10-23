package br.financas.app.outbox;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

import java.util.HashSet;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Port: mudou um, muda o outro, com um teste de cada lado.
 * O lado nativo das regras de frontend/src/lib/outboxRules.test.js.
 */
public class OutboxRulesTest {

    @Test
    public void endpointsOfTheFourForms() {
        assertEquals("/api/transactions", OutboxRules.endpointFor("EXPENSE"));
        assertEquals("/api/transactions", OutboxRules.endpointFor("INCOME"));
        assertEquals("/api/transfers", OutboxRules.endpointFor("TRANSFER"));
        assertEquals("/api/cc-expenses/purchases", OutboxRules.endpointFor("CARD"));
        assertNull(OutboxRules.endpointFor("BUY"));
    }

    // "o client_id tem o formato que o servidor aceita"
    @Test
    public void clientIdFormat() {
        Pattern pattern = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$");
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < 50; i += 1) {
            String id = OutboxRules.newClientId();
            assertTrue(id, pattern.matcher(id).matches());
            seen.add(id);
        }
        assertEquals(50, seen.size());
    }

    // "o item leva o client_id dentro do payload, e mantem o que ja veio"
    @Test
    public void keepsAnExistingClientId() throws Exception {
        JSONObject built = OutboxRules.buildItem("EXPENSE", new JSONObject().put("amount", 10), "u1", 0L);
        assertEquals(built.getString("client_id"), built.getJSONObject("payload").getString("client_id"));
        assertEquals("pending", built.getString("status"));
        assertEquals("u1", built.getString("user_id"));
        assertEquals("", built.getString("last_error"));
        assertEquals("EXPENSE", built.getString("kind"));
        assertFalse(built.has("edited"));

        JSONObject kept = OutboxRules.buildItem(
            "EXPENSE", new JSONObject().put("amount", 10).put("client_id", "ja-existia-123"), null, 0L);
        assertEquals("ja-existia-123", kept.getString("client_id"));
        assertEquals("ja-existia-123", kept.getJSONObject("payload").getString("client_id"));
        assertEquals("", kept.getString("user_id"));
    }

    @Test
    public void createdAtIsTheJsIsoString() throws Exception {
        assertEquals("2026-10-22T14:03:11.512Z", OutboxRules.isoInstant(1792677791512L));
        assertEquals("1970-01-01T00:00:00.000Z", OutboxRules.buildItem("CARD", new JSONObject(), "u", 0L).getString("created_at"));
    }

    @Test(expected = IllegalArgumentException.class)
    public void buildItemRefusesAnUnknownKind() throws Exception {
        OutboxRules.buildItem("BUY", new JSONObject(), "u1", 0L);
    }

    // "item corrigido: mesmo client_id, de volta a pendente, marcado como editado"
    @Test
    public void editedItemKeepsTheClientId() throws Exception {
        JSONObject current = new JSONObject()
            .put("client_id", "abc12345")
            .put("user_id", "u1")
            .put("kind", "EXPENSE")
            .put("payload", new JSONObject().put("amount", 10).put("client_id", "abc12345"))
            .put("status", "needs_attention")
            .put("last_error", "Categoria nao encontrada.")
            .put("created_at", "2026-10-12T10:00:00.000Z");
        JSONObject next = OutboxRules.editedItem(
            current, "INCOME", new JSONObject().put("amount", 12.5).put("client_id", "outro-id-99"));
        assertEquals("abc12345", next.getString("client_id"));
        assertEquals("abc12345", next.getJSONObject("payload").getString("client_id"));
        assertEquals(12.5, next.getJSONObject("payload").getDouble("amount"), 0.0);
        assertEquals("INCOME", next.getString("kind"));
        assertEquals("pending", next.getString("status"));
        assertEquals("", next.getString("last_error"));
        assertTrue(next.getBoolean("edited"));
        assertEquals("u1", next.getString("user_id"));
        assertEquals("2026-10-12T10:00:00.000Z", next.getString("created_at"));
        assertEquals("EXPENSE", OutboxRules.editedItem(current, null, new JSONObject().put("amount", 1)).getString("kind"));
        // O item de origem nao muda (a tela pode ainda estar com ele).
        assertEquals("needs_attention", current.getString("status"));
    }

    @Test
    public void outcomeOfEachResponse() {
        assertEquals(OutboxRules.Outcome.DONE, OutboxRules.outcomeOf(false, 201));
        assertEquals(OutboxRules.Outcome.DONE, OutboxRules.outcomeOf(false, 200));
        assertEquals(OutboxRules.Outcome.RETRY, OutboxRules.outcomeOf(true, 0));
        assertEquals(OutboxRules.Outcome.RETRY, OutboxRules.outcomeOf(false, 502));
        assertEquals(OutboxRules.Outcome.RETRY, OutboxRules.outcomeOf(false, 408));
        assertEquals(OutboxRules.Outcome.RETRY, OutboxRules.outcomeOf(false, 429));
        assertEquals(OutboxRules.Outcome.STOP, OutboxRules.outcomeOf(false, 401));
        assertEquals(OutboxRules.Outcome.ATTENTION, OutboxRules.outcomeOf(false, 400));
        assertEquals(OutboxRules.Outcome.ATTENTION, OutboxRules.outcomeOf(false, 409));
    }

    @Test
    public void onlyTheCreatedRowsProveDelivery() throws Exception {
        assertTrue(OutboxRules.isCreationResponse("EXPENSE", new JSONObject().put("id", 1)));
        assertTrue(OutboxRules.isCreationResponse("CARD", new JSONArray()));
        // Um portal de Wi-Fi responde 200 com HTML: nao e entrega.
        assertFalse(OutboxRules.isCreationResponse("EXPENSE", null));
        assertFalse(OutboxRules.isCreationResponse("CARD", new JSONObject().put("id", 1)));
        assertFalse(OutboxRules.isCreationResponse("TRANSFER", new JSONArray()));
    }

    @Test
    public void centsRoundHalfUp() {
        assertEquals(1235, OutboxRules.cents("12.345"));
        assertEquals(1000, OutboxRules.cents(10));
        assertEquals(1999, OutboxRules.cents(19.99));
        assertEquals(0, OutboxRules.cents(JSONObject.NULL));
    }

    @Test
    public void editedExpenseMatchingWhatWasDelivered() throws Exception {
        JSONObject item = item("EXPENSE", new JSONObject().put("amount", "50.00").put("date", "2026-10-16").put("account_id", 3));
        JSONObject delivered = new JSONObject().put("amount", 50).put("date", "2026-10-16").put("type", "EXPENSE").put("account_id", 3);
        assertFalse(OutboxRules.deliveredDiffers(item, delivered));
    }

    @Test
    public void editedExpenseWhoseOldVersionHadArrived() throws Exception {
        JSONObject item = item("EXPENSE", new JSONObject().put("amount", "55.00").put("date", "2026-10-16"));
        JSONObject delivered = new JSONObject().put("amount", 50).put("date", "2026-10-16").put("type", "EXPENSE");
        assertTrue(OutboxRules.deliveredDiffers(item, delivered));
    }

    @Test
    public void transferComparesBothAccounts() throws Exception {
        JSONObject item = item("TRANSFER", new JSONObject()
            .put("amount", 100).put("date", "2026-10-16").put("account_id", 1).put("transfer_account_id", 2));
        JSONObject swapped = new JSONObject()
            .put("amount", 100).put("date", "2026-10-16").put("account_id", 2).put("transfer_account_id", 1);
        assertTrue(OutboxRules.deliveredDiffers(item, swapped));
    }

    @Test
    public void cardPurchaseComparesTotalAndInstallments() throws Exception {
        JSONObject item = item("CARD", new JSONObject()
            .put("total_amount", "100.00").put("installments", 2).put("purchase_date", "2026-10-16").put("card_id", 7));
        JSONArray same = new JSONArray()
            .put(new JSONObject().put("amount", 50).put("purchase_date", "2026-10-16").put("card_id", 7))
            .put(new JSONObject().put("amount", 50).put("purchase_date", "2026-10-16").put("card_id", 7));
        assertFalse(OutboxRules.deliveredDiffers(item, same));
        JSONArray single = new JSONArray()
            .put(new JSONObject().put("amount", 100).put("purchase_date", "2026-10-16").put("card_id", 7));
        assertTrue(OutboxRules.deliveredDiffers(item, single));
    }

    @Test
    public void nothingDeliveredIsNotADifference() throws Exception {
        assertFalse(OutboxRules.deliveredDiffers(item("EXPENSE", new JSONObject().put("amount", 1)), null));
    }

    private static JSONObject item(String kind, JSONObject payload) throws Exception {
        return new JSONObject().put("client_id", "c1").put("kind", kind).put("payload", payload).put("edited", true);
    }
}
