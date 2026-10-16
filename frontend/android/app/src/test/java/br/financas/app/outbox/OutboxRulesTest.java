package br.financas.app.outbox;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/** O lado nativo das regras de frontend/src/lib/outboxRules.test.js. */
public class OutboxRulesTest {

    @Test
    public void endpointsOfTheFourForms() {
        assertEquals("/api/transactions", OutboxRules.endpointFor("EXPENSE"));
        assertEquals("/api/transactions", OutboxRules.endpointFor("INCOME"));
        assertEquals("/api/transfers", OutboxRules.endpointFor("TRANSFER"));
        assertEquals("/api/cc-expenses/purchases", OutboxRules.endpointFor("CARD"));
        assertNull(OutboxRules.endpointFor("BUY"));
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
