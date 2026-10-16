package br.financas.app.outbox;

import org.json.JSONArray;
import org.json.JSONObject;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * As regras da fila, as mesmas de frontend/src/lib/outboxRules.js (que tem os testes
 * do lado web). Mudou uma, muda a outra. Funcoes puras: os testes de JVM
 * (OutboxRulesTest) rodam no PC, sem aparelho.
 */
public final class OutboxRules {

    public enum Outcome { DONE, RETRY, STOP, ATTENTION }

    public static final String ALREADY_DELIVERED_MESSAGE =
        "Este lançamento já tinha chegado ao servidor antes da correção, com os valores antigos. "
            + "Corrija-o na tela de lançamentos e descarte este pendente.";

    public static final String REFUSED_MESSAGE = "O servidor recusou este lançamento.";

    public static final String UNEXPECTED_RESPONSE_MESSAGE =
        "O servidor respondeu algo que não é o lançamento (uma rede Wi-Fi com página de login?). "
            + "Confira no extrato se ele chegou antes de tentar de novo.";

    private OutboxRules() {}

    /** A rota de cada um dos quatro formularios do "+ Novo"; null para um tipo desconhecido. */
    public static String endpointFor(String kind) {
        if (kind == null) return null;
        switch (kind) {
            case "EXPENSE":
            case "INCOME":
                return "/api/transactions";
            case "TRANSFER":
                return "/api/transfers";
            case "CARD":
                return "/api/cc-expenses/purchases";
            default:
                return null;
        }
    }

    /**
     * O que uma tentativa faz com o item. {@code status} e o HTTP da resposta; {@code network}
     * diz que o pedido nao chegou ao servidor.
     *   DONE      — 2xx: gravou (201) ou ja tinha gravado (200).
     *   RETRY     — nao chegou, 5xx, 408, 429: fica pendente, a rodada para.
     *   STOP      — 401: tudo fica como esta ate o dono entrar de novo.
     *   ATTENTION — 400, 409...: precisa do dono; os proximos seguem.
     */
    public static Outcome outcomeOf(boolean network, int status) {
        if (network) return Outcome.RETRY;
        if (status >= 200 && status < 300) return Outcome.DONE;
        if (status == 401) return Outcome.STOP;
        if (status >= 500 || status == 408 || status == 429 || status == 0) return Outcome.RETRY;
        return Outcome.ATTENTION;
    }

    /**
     * Uma criacao bem-sucedida devolve o lancamento (objeto) ou, na compra no cartao, as
     * parcelas (lista). Outra coisa com 2xx nao prova que o item chegou.
     */
    public static boolean isCreationResponse(String kind, Object data) {
        if ("CARD".equals(kind)) return data instanceof JSONArray;
        return data instanceof JSONObject;
    }

    /**
     * Um item corrigido na fila guarda o mesmo client_id. Se a primeira tentativa tinha
     * chegado, o servidor devolve o lancamento antigo e ignora a correcao: compara o que
     * voltou com o que o item pede. {@code data} e um JSONObject (lancamento) ou JSONArray
     * (parcelas da compra no cartao).
     */
    public static boolean deliveredDiffers(JSONObject item, Object data) {
        if (data == null) return false;
        String kind = item.optString("kind");
        JSONObject payload = item.optJSONObject("payload");
        if (payload == null) return false;
        if ("CARD".equals(kind)) {
            if (!(data instanceof JSONArray)) return false;
            JSONArray rows = (JSONArray) data;
            if (rows.length() == 0) return false;
            long total = 0;
            for (int index = 0; index < rows.length(); index++) {
                JSONObject row = rows.optJSONObject(index);
                total += row == null ? 0 : cents(row.opt("amount"));
            }
            JSONObject first = rows.optJSONObject(0);
            if (first == null) return false;
            return total != cents(payload.opt("total_amount"))
                || rows.length() != toInt(payload.opt("installments"))
                || !same(first.opt("purchase_date"), payload.opt("purchase_date"))
                || !same(first.opt("card_id"), payload.opt("card_id"));
        }
        if (!(data instanceof JSONObject)) return false;
        JSONObject row = (JSONObject) data;
        if (cents(row.opt("amount")) != cents(payload.opt("amount")) || !same(row.opt("date"), payload.opt("date"))) {
            return true;
        }
        if ("TRANSFER".equals(kind)) {
            return !same(row.opt("account_id"), payload.opt("account_id"))
                || !same(row.opt("transfer_account_id"), payload.opt("transfer_account_id"));
        }
        String accountId = payload.optString("account_id", "");
        return !same(row.opt("type"), kind) || (!accountId.isEmpty() && !same(row.opt("account_id"), accountId));
    }

    /**
     * Centavos inteiros, metade para cima, em decimal exato. Difere do toCents do JS
     * (Math.round sobre ponto flutuante) so com 3+ casas: 1.005 da 101 aqui e 100 la. Aqui
     * bate com o rounded_money() do servidor, que e o que deliveredDiffers compara.
     */
    static long cents(Object value) {
        if (value == null || value == JSONObject.NULL) return 0;
        try {
            return new BigDecimal(String.valueOf(value)).movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        } catch (RuntimeException error) {
            return 0;
        }
    }

    private static int toInt(Object value) {
        if (value == null || value == JSONObject.NULL) return 0;
        try {
            return new BigDecimal(String.valueOf(value)).intValue();
        } catch (RuntimeException error) {
            return 0;
        }
    }

    // Ids e datas vem como texto ou numero dependendo da rota: compara pelo texto.
    private static boolean same(Object left, Object right) {
        String a = left == null || left == JSONObject.NULL ? "" : String.valueOf(left);
        String b = right == null || right == JSONObject.NULL ? "" : String.valueOf(right);
        return a.equals(b);
    }
}
