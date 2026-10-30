package br.financas.app.notify;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;

import java.util.TimeZone;

import org.json.JSONObject;
import org.junit.Test;

/**
 * Os parsers (NotifyParsers) contra a captura do dono de 2026-10-17: os textos sao os que os
 * bancos mandaram, com o nome e os digitos do CPF trocados. Os casos sem captura ainda (credito
 * com final, negada, estorno, saldo no texto) seguem as variacoes que o plano da Fase 6 lista.
 */
public class NotifyParsersTest {

    private static final String BB = "br.com.bb.android";
    private static final String ITAU = "com.itau";
    private static final String BTG = "com.btg.pactual.banking";
    private static final String SAMSUNG = "com.samsung.android.spay";

    private static NotifyRules.Captured row(String pkg, String title, String text) {
        NotifyRules.Captured row = new NotifyRules.Captured();
        row.packageName = pkg;
        row.key = "0|" + pkg + "|1|null|10000";
        row.postedAt = 1_792_221_114_222L;
        row.when = 1_792_221_114_217L;
        row.title = title;
        row.text = text;
        row.bigText = text;
        return row;
    }

    /** O BTG deixa text e bigText vazios e poe a mensagem em android.infoText. */
    private static NotifyRules.Captured btg(String title, String info) {
        NotifyRules.Captured row = row(BTG, title, null);
        row.extras.put("android.infoText", info);
        row.extras.put("android.subText", "");
        return row;
    }

    // --- A captura ------------------------------------------------------------------------

    @Test
    public void bancoDoBrasilPixSent() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(BB, "Pix Enviado",
            "Pix de R$  0,01 enviado da conta Corrente para Fulano R Silva, Instituição BANCO BTG PACTUAL S., às 04:11."));
        assertEquals(NotifyParsers.PIX_OUT, parsed.kind);
        assertEquals(1, parsed.amountCents);
        assertEquals("Fulano R Silva", parsed.counterparty);
        assertEquals("BANCO BTG PACTUAL S", parsed.counterpartyBank);
        assertNull(parsed.counterpartyDoc);
        assertNull(parsed.merchant);
    }

    @Test
    public void bancoDoBrasilPixSentToItau() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(BB, "Pix Enviado",
            "Pix de R$  1.250,00 enviado da conta Corrente para Fulano R Silva, Instituição ITAÚ UNIBANCO S.A., às 04:28."));
        assertEquals(125_000, parsed.amountCents);
        assertEquals("ITAÚ UNIBANCO S.A", parsed.counterpartyBank);
    }

    @Test
    public void btgPixReceivedLivesInInfoText() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Pix Recebido",
            "Você recebeu um Pix de Fulano N Souza Silva ***.123.456-** no valor de R$ 0,01."));
        assertEquals(NotifyParsers.PIX_IN, parsed.kind);
        assertEquals(1, parsed.amountCents);
        assertEquals("Fulano N Souza Silva", parsed.counterparty);
        assertEquals("123456", parsed.counterpartyDoc);
    }

    @Test
    public void itauPixReceived() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Pix recebido",
            "Você recebeu R$ 0,01 de FULANO, CPF XXX.123.456-XX."));
        assertEquals(NotifyParsers.PIX_IN, parsed.kind);
        assertEquals("FULANO", parsed.counterparty);
        assertEquals("123456", parsed.counterpartyDoc);
    }

    @Test
    public void itauPixSent() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Feito. Pix enviado",
            "Você enviou R$ 0,01 para FULANO, CPF XXX.123.456-XX."));
        assertEquals(NotifyParsers.PIX_OUT, parsed.kind);
        assertEquals("FULANO", parsed.counterparty);
        assertEquals("123456", parsed.counterpartyDoc);
    }

    @Test
    public void btgPurchaseWithoutCreditOrDebit() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Compra autorizada",
            "Sua compra de R$ 19,58 em Drogaria São Paulo foi autorizada."));
        assertEquals(NotifyParsers.PURCHASE, parsed.kind);
        assertEquals(1958, parsed.amountCents);
        assertEquals("Drogaria São Paulo", parsed.merchant);
        assertNull(parsed.counterparty);
    }

    /** BTG Banking -> BTG Investimentos (captura de 2026-10-17, 23:25): as duas pontas. */
    @Test
    public void btgTransferConfirmedIsOutgoing() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Transferência confirmada",
            "Sua transferência de R$ 5,08 foi confirmada."));
        assertEquals(NotifyParsers.TRANSFER_OUT, parsed.kind);
        assertEquals(508, parsed.amountCents);
        assertNull(parsed.counterparty);
    }

    @Test
    public void btgInvestimentosTransferReceived() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row("com.btg.pactual.digital.mobile", "Transferência recebida",
            "Recebemos sua transferência no valor de R$ 5,08 e o seu saldo já está disponível."));
        assertEquals(NotifyParsers.TRANSFER_IN, parsed.kind);
        assertEquals(508, parsed.amountCents);
        assertNull(parsed.counterparty);
    }

    @Test
    public void samsungInstallingIsNothing() {
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Samsung Wallet", "Instalando…")));
        NotifyRules.Captured summary = row(SAMSUNG, null, null);
        summary.bigText = null;
        summary.groupSummary = true;
        assertNull(NotifyParsers.parse(summary));
    }

    // --- A captura de 2026-10-22 -----------------------------------------------------------

    /** O Samsung de 2026-10: titulo = cartao, texto = lugar + valor, U+00A0 depois do R$. */
    @Test
    public void samsungLineWithTheCardInTheTitle() throws Exception {
        NotifyRules.Captured captured = row(SAMSUNG, "Card used for Meal and Voucher", "CANTINA DO VALE R$\u00A014,20");
        captured.extras.put("android.title.big", "Card used for Meal and Voucher");
        NotifyParsers.Parsed parsed = NotifyParsers.parse(captured);
        assertEquals(NotifyParsers.PURCHASE, parsed.kind);
        assertEquals(1420, parsed.amountCents);
        assertEquals("CANTINA DO VALE", parsed.merchant);
        assertEquals("Card used for Meal and Voucher", parsed.cardName);
        JSONObject body = NotifyParsers.toDetection(captured, parsed, TimeZone.getTimeZone("America/Bahia"));
        assertEquals("Card used for Meal and Voucher", body.getString("card_name"));
    }

    /** A compra com o Flash pelo Samsung Wallet (2026-10-21, 20:28). */
    @Test
    public void samsungMealAndVoucherIsTheBenefitsCard() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(SAMSUNG, "Card used for Meal and Voucher",
            "DOCEPAOPITUBA R$\u00A046,81"));
        assertEquals(NotifyParsers.PURCHASE, parsed.kind);
        assertEquals(4681, parsed.amountCents);
        assertEquals("DOCEPAOPITUBA", parsed.merchant);
        assertEquals("Card used for Meal and Voucher", parsed.cardName);
    }

    @Test
    public void samsungKeepsTheStoreNumberOfTheMerchant() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(SAMSUNG, "Card used for Meal and Voucher", "DROGASIL 1439 R$\u00A017,11"));
        assertEquals(1711, parsed.amountCents);
        assertEquals("DROGASIL 1439", parsed.merchant);
    }

    /** Dono, 2026-10-30: o Samsung Wallet de qualquer outro cartao e descartado. */
    @Test
    public void samsungOtherCardsAreDropped() {
        assertNull(NotifyParsers.parse(row(SAMSUNG, "BTG Pactual Banking", "CANTINA DO VALE R$\u00A014,20")));
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Itaú Visa", "DROGASIL 1439 R$\u00A017,11")));
    }

    @Test
    public void samsungRewardsAreNothing() {
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Samsung Wallet",
            "Você ganhou 10 pontos. Toque aqui para verificar seus pontos do Samsung Rewards.")));
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Samsung Wallet",
            "Você alcançou o nível Ouro. Toque aqui para verificar seus pontos do Samsung Rewards.")));
    }

    /** O BB nao diz "de <nome>" num Pix recebido: o nome vem antes do CPF. */
    @Test
    public void bancoDoBrasilPixReceivedNamesTheSender() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(BB, "Pix Recebido",
            "Que ótimo! Fulano R Silva, CPF/CNPJ ***.123.456-** , enviou um Pix de R$  12,77, da Instituição BANCO BTG PACTUAL S., para sua conta Corrente às 13:38."));
        assertEquals(NotifyParsers.PIX_IN, parsed.kind);
        assertEquals(1277, parsed.amountCents);
        assertEquals("Fulano R Silva", parsed.counterparty);
        assertEquals("123456", parsed.counterpartyDoc);
        assertEquals("BANCO BTG PACTUAL S", parsed.counterpartyBank);
        parsed = NotifyParsers.parse(row(BB, "Pix Recebido",
            "Que ótimo! Beltrano R Souza, CPF/CNPJ ***.654.321-** , enviou um Pix de R$  2.400,00, da Instituição BCO DO BRASIL S.A., para sua conta Corrente às 14:12."));
        assertEquals(240_000, parsed.amountCents);
        assertEquals("Beltrano R Souza", parsed.counterparty);
    }

    @Test
    public void btgPixConfirmationsAreOutgoing() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Transação Pix Confirmada",
            "A transferência Pix de R$ 12,77 foi confirmada."));
        assertEquals(NotifyParsers.PIX_OUT, parsed.kind);
        assertEquals(1277, parsed.amountCents);
        parsed = NotifyParsers.parse(btg("Pagamento Pix Confirmado", "O Pagamento Pix de R$ 5,00 foi confirmado."));
        assertEquals(NotifyParsers.PIX_OUT, parsed.kind);
        assertEquals(500, parsed.amountCents);
    }

    @Test
    public void btgTransferReceivedNamesTheSender() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Transferência recebida",
            "Você recebeu uma transferência de Fulano Neves Silva no valor de R$ 2.400,00."));
        assertEquals(NotifyParsers.TRANSFER_IN, parsed.kind);
        assertEquals(240_000, parsed.amountCents);
        assertEquals("Fulano Neves Silva", parsed.counterparty);
    }

    @Test
    public void btgInvestimentosPixReceived() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row("com.btg.pactual.digital.mobile", "Transferência recebida",
            "Recebemos seu PIX no valor de R$ 2.400,00 e o seu saldo já está disponível."));
        assertEquals(NotifyParsers.PIX_IN, parsed.kind);
        assertEquals(240_000, parsed.amountCents);
    }

    @Test
    public void marketingAndAccessAreNothing() {
        assertNull(NotifyParsers.parse(row(BB, "Seu cashback pode chegar a 30% ",
            "Ainda dá pra subir de nível: somente hoje, 21/10, compre gift card de PlayStation no Shopping BB e aproveite até 30% de cashback com Cartão BB.")));
        assertNull(NotifyParsers.parse(row("com.btg.pactual.digital.mobile", "Acesso Portal de Clientes",
            "Precisamos confirmar a sua autenticação no BTG Pactual Portal de Clientes. Deseja prosseguir com o acesso?")));
        assertNull(NotifyParsers.parse(row("com.btg.pactual.digital.mobile", "Recebimento de BITCOIN confirmado!",
            "O recebimento de 0.00459551 BITCOIN foi confirmado com sucesso")));
        assertNull(NotifyParsers.parse(row("com.btg.pactual.digital.mobile", "Depósito pendente",
            "Você tem um depósito pendente de criptoativos. Complete as informações para concluir. Conferir")));
    }

    // --- O que o plano manda esperar -------------------------------------------------------

    @Test
    public void creditPurchaseWithCardAndInstallments() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra aprovada no cartão Itaú Click final 1234 de R$ 300,00 em 3x em LOJA EXEMPLO às 16h30."));
        assertEquals(NotifyParsers.PURCHASE, parsed.kind);
        assertEquals("1234", parsed.cardLast4);
        assertEquals(3, parsed.installments);
        assertEquals(30_000, parsed.amountCents);
        assertEquals("LOJA EXEMPLO", parsed.merchant);
    }

    // "3x de R$ 50,00" e o valor da parcela. Sem captura real nesse formato ainda (2026-10-18):
    // os textos abaixo sao variacoes escritas a mao; troque por uma captura quando aparecer.

    @Test
    public void perInstallmentAmountAloneBecomesTheTotal() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra aprovada no cartão final 1234 em 3x de R$ 50,00 em LOJA EXEMPLO."));
        assertEquals(3, parsed.installments);
        assertEquals(15_000, parsed.amountCents);
    }

    @Test
    public void totalWinsOverThePerInstallmentAmount() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra aprovada em 3x de R$ 50,00, total de R$ 150,00, cartão final 1234."));
        assertEquals(3, parsed.installments);
        assertEquals(15_000, parsed.amountCents);
        parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra de R$ 149,99 aprovada em 3x de R$ 50,00 no cartão final 1234."));
        assertEquals(14_999, parsed.amountCents);
    }

    @Test
    public void limitIsNotTakenForTheTotal() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra aprovada em 3x de R$ 50,00 no cartão final 1234. Limite disponível R$ 2.000,00."));
        assertEquals(15_000, parsed.amountCents);
    }

    @Test
    public void creditAndDebitAreRead() {
        assertEquals(NotifyParsers.CREDIT_PURCHASE, NotifyParsers.parse(row(BB, "Compra no crédito",
            "Compra de R$ 45,90 aprovada em PADARIA BOM PAO, cartão final 9876.")).kind);
        assertEquals(NotifyParsers.DEBIT_PURCHASE, NotifyParsers.parse(row(BB, "Compra no débito",
            "Compra de R$ 45,90 aprovada em PADARIA BOM PAO.")).kind);
    }

    @Test
    public void declinedComesBeforePurchase() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Compra não autorizada",
            "Sua compra de R$ 19,58 em Drogaria São Paulo não foi autorizada."));
        assertEquals(NotifyParsers.DECLINED, parsed.kind);
    }

    @Test
    public void refundComesBeforePurchase() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(btg("Estorno",
            "O estorno da compra de R$ 19,58 em Drogaria São Paulo foi feito."));
        assertEquals(NotifyParsers.REFUND, parsed.kind);
        assertEquals("Drogaria São Paulo", parsed.merchant);
    }

    @Test
    public void theAmountIsNotTheBalance() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Compra de R$ 25,00 em MERCADO. Limite disponível R$ 1.975,00."));
        assertEquals(2500, parsed.amountCents);
        parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada",
            "Seu saldo é R$ 900,00. Compra de R$ 25,00 em MERCADO."));
        assertEquals(2500, parsed.amountCents);
    }

    @Test
    public void anAmountWithoutMerchantIsStillADetection() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(ITAU, "Compra aprovada", "Compra aprovada de R$ 12,00."));
        assertEquals(1200, parsed.amountCents);
        assertNull(parsed.merchant);
    }

    @Test
    public void samsungIsCardOnly() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(SAMSUNG, "Card used for Meal and Voucher", "MERCADO BOM PRECO R$ 25,90"));
        assertEquals(NotifyParsers.PURCHASE, parsed.kind);
        assertEquals("MERCADO BOM PRECO", parsed.merchant);
        // Pix nao e com o Samsung Wallet, nem estorno.
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Card used for Meal and Voucher", "Pix: Você enviou R$ 10,00 para FULANO.")));
        assertNull(NotifyParsers.parse(row(SAMSUNG, "Card used for Meal and Voucher", "Estorno de R$ 10,00.")));
    }

    @Test
    public void nonMoneyNotificationsAreIgnored() {
        assertNull(NotifyParsers.parse(row(ITAU, "Sua fatura fechou", "A fatura de R$ 1.200,00 está disponível.")));
        assertNull(NotifyParsers.parse(row(BB, "Novidade", "Conheça o novo app.")));
        assertNull(NotifyParsers.parse(row(BTG, "Pix agendado", "Seu Pix de R$ 10,00 para FULANO está agendado.")));
    }

    @Test
    public void transfersWithoutPix() {
        NotifyParsers.Parsed parsed = NotifyParsers.parse(row(BB, "TED recebida",
            "Você recebeu uma transferência de R$ 500,00 de EMPRESA LTDA."));
        assertEquals(NotifyParsers.TRANSFER_IN, parsed.kind);
        assertEquals("EMPRESA LTDA", parsed.counterparty);
    }

    // --- O que vai para o servidor ----------------------------------------------------------

    @Test
    public void theDetectionCarriesOnlyReadFields() throws Exception {
        NotifyRules.Captured captured = row(ITAU, "Feito. Pix enviado",
            "Você enviou R$ 0,01 para FULANO, CPF XXX.123.456-XX.");
        JSONObject body = NotifyParsers.toDetection(captured, NotifyParsers.parse(captured),
            TimeZone.getTimeZone("America/Bahia"));
        assertEquals(captured.dedupKey(), body.getString("key"));
        assertEquals(ITAU, body.getString("app"));
        assertEquals("PIX_OUT", body.getString("kind"));
        assertEquals(1, body.getLong("amount_cents"));
        assertEquals(captured.when, body.getLong("when_ms"));
        assertEquals(-180, body.getInt("utc_offset_minutes"));
        assertEquals("123456", body.getString("counterparty_doc"));
        assertFalse(body.has("merchant"));
        // O texto nunca vai.
        assertFalse(body.toString().contains("enviou"));
        assertNotNull(body.optString("counterparty", null));
    }
}
