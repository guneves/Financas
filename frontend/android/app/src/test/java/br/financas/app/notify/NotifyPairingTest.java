package br.financas.app.notify;

import static br.financas.app.notify.NotifyPairing.CANCELLED;
import static br.financas.app.notify.NotifyPairing.CONFIRMED;
import static br.financas.app.notify.NotifyPairing.CREDIT_PURCHASE;
import static br.financas.app.notify.NotifyPairing.DEBIT_PURCHASE;
import static br.financas.app.notify.NotifyPairing.DECLINED;
import static br.financas.app.notify.NotifyPairing.DISCARDED;
import static br.financas.app.notify.NotifyPairing.HELD;
import static br.financas.app.notify.NotifyPairing.MATCHED;
import static br.financas.app.notify.NotifyPairing.PIX_OUT;
import static br.financas.app.notify.NotifyPairing.REFUND;
import static br.financas.app.notify.NotifyPairing.REFUSED;
import static br.financas.app.notify.NotifyPairing.SUGGESTED;
import static br.financas.app.notify.NotifyPairing.SUPERSEDED;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

import org.junit.Before;
import org.junit.Test;

/** O pareamento banco x Samsung Wallet (NotifyPairing): uma compra, um lancamento. */
public class NotifyPairingTest {

    private static final String SAMSUNG = NotifyPairing.SAMSUNG_WALLET;
    private static final String ITAU = "com.itau";
    private static final String BB = "br.com.bb.android";
    private static final long W = NotifyPairing.DEFAULT_WINDOW_MS;
    private static final long MIN = 60_000L;
    private static final long T = 1_760_000_000_000L;
    // backend/validators.py: o client_id que o servidor aceita.
    private static final Pattern CLIENT_ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$");

    /** O aparelho: as deteccoes guardadas, na ordem de chegada. */
    private List<NotifyPairing.Detection> stored;
    private long nextId;

    @Before
    public void setUp() {
        stored = new ArrayList<>();
        nextId = 1;
    }

    private NotifyPairing.Detection detection(String pkg, String kind, long cents, long postedAt) {
        NotifyPairing.Detection row = new NotifyPairing.Detection();
        row.id = nextId++;
        row.sourcePackage = pkg;
        row.kind = kind;
        row.amountCents = cents;
        row.postedAt = postedAt;
        row.dedupKey = NotifyRules.dedupKey(pkg, "0|" + pkg + "|" + row.id, postedAt);
        return row;
    }

    /** Chega e fica guardada, como o leitor faria. */
    private NotifyPairing.Detection arrive(String pkg, String kind, long cents, long postedAt) {
        return arrive(detection(pkg, kind, cents, postedAt));
    }

    private NotifyPairing.Detection arrive(NotifyPairing.Detection row) {
        List<NotifyPairing.Detection> changed = NotifyPairing.arrive(row, stored, W);
        assertEquals(row, changed.get(0));
        stored.add(row);
        return row;
    }

    private int countIn(String state) {
        int count = 0;
        for (NotifyPairing.Detection row : stored) {
            if (state.equals(row.state)) count++;
        }
        return count;
    }

    @Test
    public void aBankDetectionIsASuggestionAtOnce() {
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 4590, T);
        assertEquals(SUGGESTED, bank.state);
        assertEquals(bank.dedupKey, bank.groupClientId);
        assertEquals("itau", bank.issuer);
        assertTrue(CLIENT_ID.matcher(bank.groupClientId).matches());
    }

    @Test
    public void bankFirstThenSamsungLeavesOneSuggestion() {
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 4590, T);
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 4590, T + 40_000);

        assertEquals(SUGGESTED, bank.state);
        assertEquals(SUPERSEDED, samsung.state);
        assertEquals(bank.id, samsung.pairedWith);
        assertEquals(bank.groupClientId, samsung.groupClientId);
        assertEquals(1, countIn(SUGGESTED));
    }

    @Test
    public void samsungFirstIsHeldThenTheBankTakesItsPlace() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 4590, T);
        assertEquals(HELD, samsung.state);
        assertEquals(samsung.dedupKey, samsung.groupClientId);

        NotifyPairing.Detection bank = detection(ITAU, CREDIT_PURCHASE, 4590, T + 3 * MIN);
        List<NotifyPairing.Detection> changed = NotifyPairing.arrive(bank, stored, W);
        stored.add(bank);

        assertEquals(2, changed.size());
        assertEquals(SUGGESTED, bank.state);
        assertEquals(SUPERSEDED, samsung.state);
        assertEquals(bank.id, samsung.pairedWith);
        // Um client_id por compra: o da primeira deteccao do grupo.
        assertEquals(samsung.dedupKey, bank.groupClientId);
        assertEquals(1, countIn(SUGGESTED));
        // Nada mais a promover: a retida ja foi superada.
        assertTrue(NotifyPairing.promoteDue(stored, T + W + MIN, W).isEmpty());
    }

    @Test
    public void samsungAloneIsPromotedWhenTheWindowCloses() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 1250, T);

        assertTrue(NotifyPairing.promoteDue(stored, T + 5 * MIN, W).isEmpty());
        // No limite exato a janela ainda esta aberta: um banco postado agora pareia.
        assertTrue(NotifyPairing.promoteDue(stored, T + W, W).isEmpty());
        assertEquals(HELD, samsung.state);
        assertEquals(T + W + 1, NotifyPairing.promoteAt(samsung, W));

        List<NotifyPairing.Detection> promoted = NotifyPairing.promoteDue(stored, T + W + 1, W);
        assertEquals(1, promoted.size());
        assertEquals(SUGGESTED, samsung.state);
        assertEquals(samsung.dedupKey, samsung.groupClientId);
        // Idempotente: rodar de novo nao muda nada.
        assertTrue(NotifyPairing.promoteDue(stored, T + 2 * W, W).isEmpty());
    }

    @Test
    public void aLateBankAfterThePromotionReplacesTheUnconfirmedSuggestion() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 8800, T);
        NotifyPairing.promoteDue(stored, T + W + 1, W);
        assertEquals(SUGGESTED, samsung.state);

        // Postada 4 min depois, lida so quando o leitor religou e leu a bandeja.
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 8800, T + 4 * MIN);

        assertEquals(SUGGESTED, bank.state);
        assertEquals(SUPERSEDED, samsung.state);
        assertEquals(samsung.groupClientId, bank.groupClientId);
        assertEquals(1, countIn(SUGGESTED));
    }

    @Test
    public void aLateBankAfterTheOwnerConfirmedIsMatchedNotASecondEntry() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 8800, T);
        NotifyPairing.promoteDue(stored, T + W + 1, W);
        assertTrue(NotifyPairing.confirm(samsung));

        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 8800, T + 4 * MIN);

        assertEquals(MATCHED, bank.state);
        assertEquals(samsung.id, bank.pairedWith);
        assertEquals(samsung.groupClientId, bank.groupClientId);
        assertEquals(CONFIRMED, samsung.state);
        assertEquals(0, countIn(SUGGESTED));
    }

    @Test
    public void aLateBankAfterTheOwnerDiscardedStaysDiscarded() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 8800, T);
        NotifyPairing.promoteDue(stored, T + W + 1, W);
        assertTrue(NotifyPairing.discard(samsung));

        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 8800, T + 2 * MIN);

        assertEquals(DISCARDED, bank.state);
        assertEquals(samsung.id, bank.pairedWith);
        assertEquals(0, countIn(SUGGESTED));
    }

    @Test
    public void aSamsungAfterAConfirmedBankDoesNotComeBack() {
        NotifyPairing.Detection bank = arrive(BB, DEBIT_PURCHASE, 3000, T);
        assertTrue(NotifyPairing.confirm(bank));

        NotifyPairing.Detection samsung = arrive(SAMSUNG, DEBIT_PURCHASE, 3000, T + MIN);

        assertEquals(SUPERSEDED, samsung.state);
        assertEquals(bank.groupClientId, samsung.groupClientId);
        assertTrue(NotifyPairing.promoteDue(stored, T + 2 * W, W).isEmpty());
    }

    @Test
    public void twoSameAmountPurchasesStayTwo() {
        // Duas compras de R$ 12,00 na mesma padaria; o banco so notificou a segunda.
        NotifyPairing.Detection first = arrive(SAMSUNG, CREDIT_PURCHASE, 1200, T);
        NotifyPairing.Detection second = arrive(SAMSUNG, CREDIT_PURCHASE, 1200, T + 2 * MIN);
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 1200, T + 3 * MIN);

        assertEquals(SUPERSEDED, second.state);
        assertEquals(bank.id, second.pairedWith);
        assertEquals(HELD, first.state);

        NotifyPairing.promoteDue(stored, T + W + 1, W);
        assertEquals(SUGGESTED, first.state);
        assertEquals(2, countIn(SUGGESTED));
        assertNotEquals(first.groupClientId, bank.groupClientId);
    }

    @Test
    public void twoBankPurchasesAndOneSamsungPairOnlyOnce() {
        NotifyPairing.Detection early = arrive(ITAU, CREDIT_PURCHASE, 1200, T);
        NotifyPairing.Detection late = arrive(ITAU, CREDIT_PURCHASE, 1200, T + 5 * MIN);
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 1200, T + 4 * MIN);

        assertEquals(late.id, samsung.pairedWith);
        assertEquals(SUGGESTED, early.state);
        assertEquals(SUGGESTED, late.state);

        // Um segundo Samsung do mesmo valor pareia com o banco que sobrou, nao com o ja pareado.
        NotifyPairing.Detection again = arrive(SAMSUNG, CREDIT_PURCHASE, 1200, T + 5 * MIN);
        assertEquals(SUPERSEDED, again.state);
        assertEquals(early.id, again.pairedWith);
        assertEquals(2, countIn(SUGGESTED));
    }

    @Test
    public void twoBankDetectionsNeverPairWithEachOther() {
        arrive(ITAU, CREDIT_PURCHASE, 5000, T);
        arrive(ITAU, CREDIT_PURCHASE, 5000, T + MIN);
        assertEquals(2, countIn(SUGGESTED));
    }

    @Test
    public void twoSamsungDetectionsNeverPairWithEachOther() {
        arrive(SAMSUNG, CREDIT_PURCHASE, 5000, T);
        arrive(SAMSUNG, CREDIT_PURCHASE, 5000, T + MIN);
        assertEquals(2, countIn(HELD));
    }

    @Test
    public void aDeclinedPurchaseFromTheBankCancelsTheHeldSamsung() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 9990, T);
        NotifyPairing.Detection declined = arrive(ITAU, DECLINED, 9990, T + 20_000);

        assertEquals(REFUSED, declined.state);
        assertEquals(CANCELLED, samsung.state);
        assertEquals(declined.id, samsung.pairedWith);
        assertTrue(NotifyPairing.promoteDue(stored, T + 2 * W, W).isEmpty());
        assertEquals(0, countIn(SUGGESTED));
    }

    @Test
    public void aDeclinedPurchaseFromTheBankCancelsAPromotedSuggestion() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 9990, T);
        NotifyPairing.promoteDue(stored, T + W + 1, W);
        arrive(ITAU, DECLINED, 9990, T + MIN);
        assertEquals(CANCELLED, samsung.state);
    }

    @Test
    public void aSamsungAfterTheBanksDeclinedIsCancelledOnArrival() {
        NotifyPairing.Detection declined = arrive(BB, DECLINED, 9990, T);
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 9990, T + 30_000);

        assertEquals(CANCELLED, samsung.state);
        assertEquals(declined.id, samsung.pairedWith);
        // A negada so cancela uma: a nova tentativa aprovada segue o caminho dela.
        NotifyPairing.Detection retry = arrive(SAMSUNG, CREDIT_PURCHASE, 9990, T + MIN);
        assertEquals(HELD, retry.state);
    }

    @Test
    public void aDeclinedPurchaseNeverTouchesAConfirmedEntry() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 9990, T);
        NotifyPairing.promoteDue(stored, T + W + 1, W);
        NotifyPairing.confirm(samsung);

        arrive(ITAU, DECLINED, 9990, T + MIN);
        assertEquals(CONFIRMED, samsung.state);
    }

    @Test
    public void theBankWinsOverADeclinedFromSamsung() {
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 9990, T);
        NotifyPairing.Detection declined = arrive(SAMSUNG, DECLINED, 9990, T + 10_000);

        assertEquals(REFUSED, declined.state);
        assertEquals(SUGGESTED, bank.state);
    }

    @Test
    public void differentCardsNeverPair() {
        NotifyPairing.Detection samsung = detection(SAMSUNG, CREDIT_PURCHASE, 2500, T);
        samsung.cardLast4 = "1234";
        arrive(samsung);
        NotifyPairing.Detection bank = detection(ITAU, CREDIT_PURCHASE, 2500, T + MIN);
        bank.cardLast4 = "9876";
        arrive(bank);

        assertEquals(HELD, samsung.state);
        assertEquals(SUGGESTED, bank.state);
    }

    @Test
    public void aSamsungCardOfAnotherIssuerNeverPairs() {
        NotifyPairing.Detection samsung = detection(SAMSUNG, CREDIT_PURCHASE, 2500, T);
        samsung.issuer = "itau";
        arrive(samsung);
        NotifyPairing.Detection bank = arrive(BB, CREDIT_PURCHASE, 2500, T + MIN);

        assertEquals(HELD, samsung.state);
        assertEquals(SUGGESTED, bank.state);
    }

    @Test
    public void theSameCardNamedOnBothSidesPairs() {
        NotifyPairing.Detection samsung = detection(SAMSUNG, CREDIT_PURCHASE, 2500, T);
        samsung.cardLast4 = "1234";
        samsung.issuer = "itau";
        arrive(samsung);
        NotifyPairing.Detection bank = detection(ITAU, CREDIT_PURCHASE, 2500, T + MIN);
        bank.cardLast4 = "1234";
        arrive(bank);

        assertEquals(SUPERSEDED, samsung.state);
    }

    @Test
    public void aCardNamedOnOneSideOnlyDoesNotBlock() {
        NotifyPairing.Detection samsung = detection(SAMSUNG, CREDIT_PURCHASE, 2500, T);
        samsung.cardLast4 = "1234";
        arrive(samsung);
        arrive(ITAU, CREDIT_PURCHASE, 2500, T + MIN);

        assertEquals(SUPERSEDED, samsung.state);
    }

    @Test
    public void theWindowEdgeIsInclusive() {
        NotifyPairing.Detection atEdge = arrive(SAMSUNG, CREDIT_PURCHASE, 700, T);
        arrive(ITAU, CREDIT_PURCHASE, 700, T + W);
        assertEquals(SUPERSEDED, atEdge.state);

        NotifyPairing.Detection pastEdge = arrive(SAMSUNG, CREDIT_PURCHASE, 701, T);
        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 701, T + W + 1);
        assertEquals(HELD, pastEdge.state);
        assertEquals(SUGGESTED, bank.state);
    }

    @Test
    public void theWindowCountsBothWays() {
        // O Samsung postado depois do banco, mas lido antes dele.
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 700, T + 2 * MIN);
        arrive(ITAU, CREDIT_PURCHASE, 700, T);
        assertEquals(SUPERSEDED, samsung.state);
    }

    @Test
    public void amountsMustMatchToTheCent() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 4590, T);
        arrive(ITAU, CREDIT_PURCHASE, 4591, T + MIN);
        assertEquals(HELD, samsung.state);
    }

    @Test
    public void creditAndDebitPairButAPixDoesNotPairWithAPurchase() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 4590, T);
        arrive(ITAU, PIX_OUT, 4590, T + MIN);
        assertEquals(HELD, samsung.state);

        arrive(ITAU, DEBIT_PURCHASE, 4590, T + 2 * MIN);
        assertEquals(SUPERSEDED, samsung.state);
    }

    @Test
    public void aRefundPairsWithARefund() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, REFUND, 4590, T);
        NotifyPairing.Detection purchase = arrive(ITAU, CREDIT_PURCHASE, 4590, T + MIN);
        assertEquals(HELD, samsung.state);
        assertEquals(SUGGESTED, purchase.state);

        arrive(ITAU, REFUND, 4590, T + 2 * MIN);
        assertEquals(SUPERSEDED, samsung.state);
    }

    @Test
    public void onlyASuggestionCanBeConfirmedOrDiscarded() {
        NotifyPairing.Detection samsung = arrive(SAMSUNG, CREDIT_PURCHASE, 100, T);
        assertFalse(NotifyPairing.confirm(samsung));
        assertFalse(NotifyPairing.discard(samsung));
        assertEquals(HELD, samsung.state);

        NotifyPairing.Detection bank = arrive(ITAU, CREDIT_PURCHASE, 100, T + MIN);
        assertFalse(NotifyPairing.confirm(samsung));
        assertTrue(NotifyPairing.confirm(bank));
        assertFalse(NotifyPairing.discard(bank));
    }

    @Test
    public void theIssuerComesFromTheBankPackage() {
        assertEquals("itau", NotifyPairing.issuerOf("com.itau"));
        assertEquals("bb", NotifyPairing.issuerOf("br.com.bb.android"));
        assertEquals("btg", NotifyPairing.issuerOf("com.btg.pactual.banking"));
        assertEquals("flash", NotifyPairing.issuerOf("br.com.flashapp"));
        assertEquals(null, NotifyPairing.issuerOf(SAMSUNG));
        assertEquals(null, NotifyPairing.issuerOf("com.btg.pactual.digital.mobile"));
    }

    @Test(expected = IllegalArgumentException.class)
    public void aDetectionArrivesAlreadyStored() {
        NotifyPairing.Detection row = detection(ITAU, CREDIT_PURCHASE, 100, T);
        row.id = 0;
        NotifyPairing.arrive(row, stored, W);
    }

    @Test
    public void thePairingsSamsungPackageIsHeard() {
        assertTrue(NotifyRules.isAllowed(SAMSUNG, false));
    }
}
