package br.financas.app.notify;

import org.json.JSONException;
import org.json.JSONObject;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Os parsers das notificacoes dos bancos (mobile-docs/steps-to-production.md, Fase 6, passo 4),
 * sem Android. Testados na JVM (NotifyParsersTest) contra a captura do dono de 2026-10-17.
 *
 * Le uma notificacao guardada (NotifyRules.Captured) e devolve so os campos que o servidor
 * aceita em POST /api/inbox/detections (services/inbox.py, parse_detection): tipo, valor em
 * centavos, estabelecimento, cartao, parcelas e, num Pix ou transferencia, quem esta do outro
 * lado (nome, os digitos visiveis do CPF mascarado, a instituicao). O texto nunca sai daqui.
 *
 * Regras de todo parser (o plano da Fase 6):
 * - fragmentos (`R$ <valor>`, `em <local>`, `para <nome>`), nunca a frase inteira: uma
 *   preposicao trocada nao quebra a leitura;
 * - os tipos negativos primeiro (negada, estorno, cancelada), antes de "compra" ou "aprovada"
 *   marcarem o texto como compra;
 * - o valor e o da frase do movimento, nao o primeiro `R$`: o texto pode trazer saldo ou limite;
 * - valor sem estabelecimento ainda e deteccao, com o estabelecimento vazio.
 *
 * Onde o texto mora muda de banco para banco: o BB e o Itau usam bigText/text; o BTG deixa os
 * dois vazios e poe tudo em android.infoText (layout proprio). O texto lido junta titulo, texto,
 * texto longo, infoText e as linhas de uma notificacao em lista.
 *
 * O Samsung Wallet so trata pagamento com cartao (dono, 2026-10-17): dele saem compras e
 * negadas, nunca Pix, transferencia ou estorno. Quando o banco tambem notifica a compra, o
 * servidor fica com a do banco (o pareamento de services/inbox.py).
 */
public final class NotifyParsers {

    public static final String CREDIT_PURCHASE = "CREDIT_PURCHASE";
    public static final String DEBIT_PURCHASE = "DEBIT_PURCHASE";
    /** Compra que nao diz credito nem debito: o dono decide no Aprovar. */
    public static final String PURCHASE = "PURCHASE";
    public static final String PIX_OUT = "PIX_OUT";
    public static final String PIX_IN = "PIX_IN";
    public static final String TRANSFER_OUT = "TRANSFER_OUT";
    public static final String TRANSFER_IN = "TRANSFER_IN";
    public static final String REFUND = "REFUND";
    public static final String DECLINED = "DECLINED";

    /** O que o parser leu de uma notificacao. */
    public static final class Parsed {
        public String kind;
        public long amountCents;
        public String currency = "BRL";
        public String merchant;
        public String cardLast4;
        public int installments = 1;
        public String counterparty;
        public String counterpartyDoc;
        public String counterpartyBank;
    }

    private static final Pattern AMOUNT = Pattern.compile("R\\$\\s*(\\d{1,3}(?:\\.\\d{3})*|\\d+),(\\d{2})");
    private static final Pattern CARD_LAST4 = Pattern.compile("(?:final|terminado em|\\*{2,4})\\s*(\\d{4})\\b");
    private static final Pattern INSTALLMENTS = Pattern.compile("(?:em\\s+)?(\\d{1,2})\\s*(?:x\\b|parcelas)");
    /** CPF mascarado: ***.378.195-** ou XXX.378.195-XX. Os seis do meio sao o que se ve. */
    private static final Pattern MASKED_CPF = Pattern.compile("[\\dXx*•]{3}\\.(\\d{3})\\.(\\d{3})-[\\dXx*•]{2}");
    private static final Pattern INSTITUTION = Pattern.compile(
        "institui[cç][aã]o:?\\s+([^,\\n]+?)(?=,|\\s+[aà]s\\s+\\d|\\.?\\s*$|\\n)",
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

    // Palavras perto do valor que dizem que ele e o do movimento.
    private static final Pattern MOVEMENT_WORDS = Pattern.compile(
        "(compra|pix|valor|enviou|enviad|recebeu|recebid|transfer|ted|estorn|pagamento|debito|credito|de|no|em)\\s*$");
    // ... e as que dizem que nao e (saldo, limite).
    private static final Pattern BALANCE_WORDS = Pattern.compile("(saldo|limite|disponivel|fatura atual)[^.]{0,25}$");

    private NotifyParsers() {}

    /** A notificacao como deteccao, ou null quando ela nao fala de um movimento de dinheiro. */
    public static Parsed parse(NotifyRules.Captured row) {
        if (row == null || row.packageName == null) return null;
        String text = textOf(row);
        if (text.isEmpty()) return null;
        String folded = fold(text);

        String kind = kindOf(folded);
        if (kind == null) return null;
        boolean samsung = NotifyPairing.SAMSUNG_WALLET.equals(row.packageName);
        if (samsung && !isCardKind(kind)) return null;

        Long cents = amountOf(text, folded);
        if (cents == null || cents <= 0) return null;

        Parsed parsed = new Parsed();
        parsed.kind = kind;
        parsed.amountCents = cents;
        parsed.cardLast4 = group(CARD_LAST4, folded, 1);
        if (isCardKind(kind) || REFUND.equals(kind)) {
            parsed.merchant = merchantOf(text, folded);
            if (parsed.merchant == null && samsung) parsed.merchant = samsungMerchant(row);
            Matcher installments = INSTALLMENTS.matcher(folded);
            if (installments.find()) {
                int count = Integer.parseInt(installments.group(1));
                if (count >= 2 && count <= 72) parsed.installments = count;
            }
        } else {
            boolean out = PIX_OUT.equals(kind) || TRANSFER_OUT.equals(kind);
            parsed.counterparty = counterpartyOf(text, folded, out);
            Matcher cpf = MASKED_CPF.matcher(text);
            if (cpf.find()) parsed.counterpartyDoc = cpf.group(1) + cpf.group(2);
            Matcher institution = INSTITUTION.matcher(text);
            if (institution.find()) parsed.counterpartyBank = clean(institution.group(1));
        }
        return parsed;
    }

    /** O corpo de POST /api/inbox/detections para esta notificacao (um item da lista). */
    public static JSONObject toDetection(NotifyRules.Captured row, Parsed parsed, TimeZone zone) {
        try {
            JSONObject out = new JSONObject();
            out.put("key", row.dedupKey());
            out.put("app", row.packageName);
            out.put("kind", parsed.kind);
            out.put("amount_cents", parsed.amountCents);
            out.put("currency", parsed.currency);
            out.put("posted_ms", row.postedAt);
            if (row.when > 0) out.put("when_ms", row.when);
            out.put("utc_offset_minutes", zone.getOffset(row.postedAt) / 60000);
            putIf(out, "merchant", parsed.merchant);
            putIf(out, "card_last4", parsed.cardLast4);
            if (parsed.installments > 1) out.put("installments", parsed.installments);
            putIf(out, "counterparty", parsed.counterparty);
            putIf(out, "counterparty_doc", parsed.counterpartyDoc);
            putIf(out, "counterparty_bank", parsed.counterpartyBank);
            return out;
        } catch (JSONException error) {
            throw new IllegalStateException("Deteccao invalida", error);
        }
    }

    // -----------------------------------------------------------------------------------------

    /** Titulo, texto (o longo quando veio), infoText e linhas, sem repetir o mesmo trecho. */
    static String textOf(NotifyRules.Captured row) {
        Set<String> parts = new LinkedHashSet<>();
        add(parts, row.title);
        add(parts, NotifyRules.bestText(row.text, row.bigText));
        add(parts, row.extras.get("android.infoText"));
        add(parts, row.extras.get("android.textLines"));
        add(parts, row.extras.get("android.summaryText"));
        return String.join("\n", parts);
    }

    private static void add(Set<String> parts, String value) {
        if (value == null) return;
        String trimmed = value.trim();
        if (!trimmed.isEmpty()) parts.add(trimmed);
    }

    /** Minusculo e sem acento, letra por letra: o indice de cada letra e o mesmo do original. */
    static String fold(String text) {
        StringBuilder out = new StringBuilder(text.length());
        for (int index = 0; index < text.length(); index++) {
            char letter = text.charAt(index);
            if (letter < 128) {
                out.append(Character.toLowerCase(letter));
                continue;
            }
            String plain = Normalizer.normalize(String.valueOf(letter), Normalizer.Form.NFD);
            out.append(Character.toLowerCase(plain.charAt(0)));
        }
        return out.toString();
    }

    static String kindOf(String folded) {
        // Negativos primeiro: "compra negada" nao e compra; "estorno da compra" nao e compra.
        if (folded.matches("(?s).*\\b(negad[ao]|recusad[ao]|nao (foi )?(autorizad|aprovad)|nao concluid).*")) return DECLINED;
        if (folded.matches("(?s).*\\b(estorn|reembols|devolvid|devolucao).*")) return REFUND;
        if (folded.matches("(?s).*\\b(cancelad|agendad|agendamento|lembrete|vence (hoje|amanha)|fatura (fechou|fechada|disponivel)).*")) return null;

        boolean pix = folded.matches("(?s).*\\bpix\\b.*");
        boolean transfer = folded.matches("(?s).*\\b(transferencia|ted|doc)\\b.*");
        // "Sua transferência de R$ 5,08 foi confirmada." (BTG): quem confirma e quem mandou.
        boolean out = folded.matches("(?s).*\\b(enviad[ao]|enviou|voce fez|realizad[ao]|feito|efetuad[ao]|pagou|confirmad[ao])\\b.*");
        boolean in = folded.matches("(?s).*\\b(recebid[ao]|recebeu|recebemos|caiu|chegou|creditad[ao])\\b.*");
        if (pix || transfer) {
            if (in && !out) return pix ? PIX_IN : TRANSFER_IN;
            if (out && !in) return pix ? PIX_OUT : TRANSFER_OUT;
            // Os dois ("Pix recebido... enviado por"): o titulo decide pela primeira palavra.
            int inAt = firstIndex(folded, "receb");
            int outAt = firstIndex(folded, "envi");
            if (inAt >= 0 || outAt >= 0) {
                boolean firstIn = outAt < 0 || (inAt >= 0 && inAt < outAt);
                return firstIn ? (pix ? PIX_IN : TRANSFER_IN) : (pix ? PIX_OUT : TRANSFER_OUT);
            }
            return null;
        }
        if (folded.matches("(?s).*\\b(compra|pagamento aprovado|transacao aprovada|autorizad[ao]|aprovad[ao]).*")) {
            boolean credit = folded.matches("(?s).*\\bcredito\\b.*");
            boolean debit = folded.matches("(?s).*\\bdebito\\b.*");
            if (credit && !debit) return CREDIT_PURCHASE;
            if (debit && !credit) return DEBIT_PURCHASE;
            return PURCHASE;
        }
        return null;
    }

    private static boolean isCardKind(String kind) {
        return CREDIT_PURCHASE.equals(kind) || DEBIT_PURCHASE.equals(kind) || PURCHASE.equals(kind)
            || DECLINED.equals(kind);
    }

    private static int firstIndex(String folded, String word) {
        return folded.indexOf(word);
    }

    /**
     * O valor do movimento: o unico `R$` do texto, ou o primeiro que vem logo depois de uma
     * palavra do movimento e nao de "saldo"/"limite".
     */
    static Long amountOf(String text, String folded) {
        List<long[]> found = new ArrayList<>();
        Matcher matcher = AMOUNT.matcher(text);
        while (matcher.find()) {
            long reais = Long.parseLong(matcher.group(1).replace(".", ""));
            long cents = reais * 100 + Long.parseLong(matcher.group(2));
            found.add(new long[] { matcher.start(), cents });
        }
        if (found.isEmpty()) return null;
        if (found.size() == 1) return found.get(0)[1];
        Long fallback = null;
        for (long[] amount : found) {
            String before = folded.substring(Math.max(0, (int) amount[0] - 40), (int) amount[0]).trim();
            if (BALANCE_WORDS.matcher(before).find()) continue;
            if (MOVEMENT_WORDS.matcher(before).find()) return amount[1];
            if (fallback == null) fallback = amount[1];
        }
        return fallback;
    }

    /** "em <local> foi autorizada", "em <local> às 14:30", "Local: <local>", depois do valor. */
    static String merchantOf(String text, String folded) {
        Matcher local = Pattern.compile("(?:local|estabelecimento|loja):\\s*([^\\n.,;]+)").matcher(folded);
        if (local.find()) return clean(text.substring(local.start(1), local.end(1)));
        Matcher amount = AMOUNT.matcher(text);
        int from = amount.find() ? amount.end() : 0;
        Matcher at = Pattern.compile(
            "\\b(?:em|no|na)\\s+(?!\\d+\\s*(?:x|parcelas)\\b)(?!seu cart|sua conta|cartao|conta\\b)(.+?)"
                + "(?=\\s+foi\\b|\\s+(?:as|em)\\s+\\d|\\s+no\\s+(?:cartao|credito|debito)|\\s+com\\s+(?:o\\s+)?cartao"
                + "|,\\s|\\.\\s|\\.?\\s*$|\\n|\\s+-\\s)")
            .matcher(folded);
        if (at.find(from)) {
            String value = clean(text.substring(at.start(1), at.end(1)));
            if (value != null && !value.matches("(?i)(credito|debito|cr[ée]dito|d[ée]bito)")) return value;
        }
        return null;
    }

    /** O Samsung Wallet costuma por o lugar no titulo; "Samsung Wallet" nao e lugar. */
    private static String samsungMerchant(NotifyRules.Captured row) {
        String title = clean(row.title);
        if (title == null || fold(title).contains("samsung") || title.contains("R$")) return null;
        return title;
    }

    /**
     * Quem esta do outro lado: "para <nome>" numa saida; "de <nome>" numa entrada (o "de" que
     * nao e "de R$" nem "um Pix de" vazio). O nome para no CPF, na virgula ou no "no valor".
     */
    static String counterpartyOf(String text, String folded, boolean out) {
        String word = out ? "para" : "de";
        Matcher matcher = Pattern.compile(
            "\\b" + word + "\\s+(?!r\\$)(?!voce\\b)(?!sua conta\\b)(?!conta\\b)([^,\\n]+?)"
                + "(?=,|\\s+cpf|\\s+cnpj|\\s+[\\dx*•]{3}\\.|\\s+no valor|\\s+(?:as|em)\\s+\\d|\\s+institui|\\.\\s|\\.?\\s*$|\\n)")
            .matcher(folded);
        while (matcher.find()) {
            String value = clean(text.substring(matcher.start(1), matcher.end(1)));
            if (value == null) continue;
            String plain = fold(value);
            // "Pix de R$ 0,01 enviado da conta Corrente para..." tem um "de" antes do valor.
            if (plain.startsWith("r$") || plain.matches("^\\d.*")) continue;
            return value;
        }
        return null;
    }

    private static String group(Pattern pattern, String text, int index) {
        Matcher matcher = pattern.matcher(text);
        return matcher.find() ? matcher.group(index) : null;
    }

    private static String clean(String value) {
        if (value == null) return null;
        String out = value.replaceAll("\\s+", " ").trim().replaceAll("[\\s.,;:-]+$", "").trim();
        return out.isEmpty() ? null : out;
    }

    private static void putIf(JSONObject out, String key, String value) throws JSONException {
        if (value != null && !value.isEmpty()) out.put(key, value);
    }
}
