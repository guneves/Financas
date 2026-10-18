package br.financas.app.notify;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Uma compra, um lancamento: o pareamento entre a notificacao do app do banco e a do Samsung
 * Wallet (mobile-docs/steps-to-production.md, Fase 6, "One purchase, one entry"). Sem Android;
 * testado na JVM (NotifyPairingTest).
 *
 * Regra do dono (2026-10-17): o Samsung Wallet vale quando o banco nao notifica a compra no
 * cartao. Entao:
 * - uma deteccao do banco vira sugestao na hora;
 * - uma do Samsung fica retida (HELD) pela janela. Se a do banco da mesma compra chega, a do
 *   Samsung e superada (SUPERSEDED) e nunca aparece; se nao chega, ela e promovida a sugestao
 *   ("via Samsung Wallet") quando a janela fecha (promoteDue);
 * - a do banco que e lida depois da promocao (o leitor religado le a bandeja com atraso) toma o
 *   lugar da sugestao do Samsung ainda nao confirmada. Se o dono ja confirmou, a do banco fica
 *   MATCHED e nao vira um segundo lancamento; se ja descartou, fica descartada tambem;
 * - uma compra NEGADA pelo banco cancela a do Samsung ainda nao confirmada. A negada do Samsung
 *   nao cancela a do banco: o banco ganha, e uma sugestao a mais custa um toque em Descartar,
 *   enquanto uma compra real sumida nao voltaria.
 *
 * Pareia so banco com Samsung, um com um: duas deteccoes do mesmo lado nunca sao a mesma
 * compra, e duas compras de mesmo valor dentro da janela ficam duas (o par e a mais proxima no
 * tempo; a outra segue o proprio caminho).
 *
 * Todas as deteccoes de uma compra levam o mesmo groupClientId, o dedupKey da primeira que
 * chegou. Ele e o client_id do lancamento (migration 024): confirmar por qualquer uma delas, da
 * lista ou do botao da notificacao, grava uma vez so.
 *
 * Os campos de cada deteccao (tipo, valor, cartao) vem dos parsers (Fase 6, passo 4), escritos
 * contra a captura do dono. A janela comeca em 10 min e e ajustada pelo atraso que a captura
 * mostrar entre as duas notificacoes da mesma compra.
 */
public final class NotifyPairing {

    public static final String SAMSUNG_WALLET = "com.samsung.android.spay";
    public static final long DEFAULT_WINDOW_MS = 10L * 60L * 1000L;

    // O que o parser leu.
    public static final String CREDIT_PURCHASE = "CREDIT_PURCHASE";
    public static final String DEBIT_PURCHASE = "DEBIT_PURCHASE";
    public static final String PIX_OUT = "PIX_OUT";
    public static final String PIX_IN = "PIX_IN";
    public static final String REFUND = "REFUND";
    public static final String DECLINED = "DECLINED";

    // Onde a deteccao esta.
    /** Do Samsung, esperando a janela fechar. Nao aparece e nao notifica. */
    public static final String HELD = "HELD";
    /** Na lista "Compras detectadas", esperando Confirmar ou Descartar. */
    public static final String SUGGESTED = "SUGGESTED";
    public static final String CONFIRMED = "CONFIRMED";
    public static final String DISCARDED = "DISCARDED";
    /** A outra deteccao da mesma compra ficou no lugar desta (pairedWith). */
    public static final String SUPERSEDED = "SUPERSEDED";
    /** Do banco, de uma compra que o dono ja confirmou pelo Samsung (pairedWith). */
    public static final String MATCHED = "MATCHED";
    /** Do Samsung, de uma compra que o banco negou (pairedWith = a negada). */
    public static final String CANCELLED = "CANCELLED";
    /** Uma compra negada: nunca vira lancamento. */
    public static final String REFUSED = "REFUSED";

    private static final Set<String> PURCHASES =
        Collections.unmodifiableSet(new HashSet<>(Arrays.asList(CREDIT_PURCHASE, DEBIT_PURCHASE)));
    /** Estados de quem ainda pode ganhar um par. */
    private static final Set<String> PAIRABLE =
        Collections.unmodifiableSet(new HashSet<>(Arrays.asList(HELD, SUGGESTED, CONFIRMED, DISCARDED)));

    private NotifyPairing() {}

    /** Uma notificacao lida por um parser. */
    public static final class Detection {
        /** O id da linha no aparelho (positivo). 0 = nenhum, em pairedWith. */
        public long id;
        public String sourcePackage;
        /** NotifyRules.dedupKey da notificacao que gerou esta deteccao. */
        public String dedupKey;
        public String kind;
        /** Em centavos: o valor compara exato, sem ponto flutuante. */
        public long amountCents;
        public String currency = "BRL";
        public String merchant;
        /** Os 4 ultimos digitos do cartao, quando o texto traz. */
        public String cardLast4;
        /**
         * O emissor do cartao ("itau", "bb", "btg"). O do banco sai do pacote (issuerOf); o do
         * Samsung, do nome do cartao no texto ou do mapeamento dos digitos (Fase 6, passo 5).
         */
        public String issuer;
        public long postedAt;
        public String state;
        public String groupClientId;
        /** A outra deteccao da mesma compra, que decidiu o estado desta. 0 = nenhuma. */
        public long pairedWith;

        public boolean fromSamsung() {
            return SAMSUNG_WALLET.equals(sourcePackage);
        }
    }

    /** O emissor de um app de banco ouvido; null para o Samsung e o resto. */
    public static String issuerOf(String packageName) {
        if ("com.itau".equals(packageName)) return "itau";
        if ("br.com.bb.android".equals(packageName)) return "bb";
        if ("com.btg.pactual.banking".equals(packageName)) return "btg";
        return null;
    }

    /**
     * Chegou uma deteccao. {@code stored} sao as ja guardadas (basta a janela ao redor dela).
     * Muda {@code incoming} e as guardadas que ela decide, e devolve todas as que mudaram (a que
     * chegou sempre primeiro), para quem guarda gravar e atualizar as notificacoes do app.
     * {@code incoming} ja tem id: quem guarda insere a linha e chama isto na mesma transacao.
     */
    public static List<Detection> arrive(Detection incoming, List<Detection> stored, long windowMs) {
        if (incoming.id <= 0) throw new IllegalArgumentException("Deteccao sem id");
        List<Detection> changed = new ArrayList<>();
        changed.add(incoming);
        incoming.pairedWith = 0;
        incoming.groupClientId = incoming.dedupKey;
        if (incoming.issuer == null) incoming.issuer = issuerOf(incoming.sourcePackage);

        if (incoming.fromSamsung()) {
            if (DECLINED.equals(incoming.kind)) {
                incoming.state = REFUSED;
                return changed;
            }
            Detection bank = closest(incoming, stored, windowMs, false, PAIRABLE_PARTNER);
            if (bank != null) {
                // O banco chegou antes: ele e a compra, ganhe o estado que tiver.
                pair(incoming, bank, SUPERSEDED);
                return changed;
            }
            Detection refusal = closest(incoming, stored, windowMs, false, REFUSALS);
            if (refusal != null) {
                pair(incoming, refusal, CANCELLED);
                return changed;
            }
            incoming.state = HELD;
            return changed;
        }

        if (DECLINED.equals(incoming.kind)) {
            incoming.state = REFUSED;
            Detection samsung = closest(incoming, stored, windowMs, true, CANCELLABLE_SAMSUNG);
            if (samsung != null) {
                samsung.state = CANCELLED;
                samsung.pairedWith = incoming.id;
                incoming.groupClientId = samsung.groupClientId;
                changed.add(samsung);
            }
            return changed;
        }

        Detection samsung = closest(incoming, stored, windowMs, true, PAIRABLE_PARTNER);
        if (samsung == null) {
            incoming.state = SUGGESTED;
            return changed;
        }
        if (CONFIRMED.equals(samsung.state)) {
            pair(incoming, samsung, MATCHED);
        } else if (DISCARDED.equals(samsung.state)) {
            pair(incoming, samsung, DISCARDED);
        } else {
            // Retida ou sugerida e ainda nao confirmada: a do banco fica no lugar dela, com o
            // mesmo client_id.
            incoming.state = SUGGESTED;
            incoming.groupClientId = samsung.groupClientId;
            samsung.state = SUPERSEDED;
            samsung.pairedWith = incoming.id;
            changed.add(samsung);
        }
        return changed;
    }

    /**
     * Promove a sugestao cada deteccao retida cuja janela ja fechou: nenhuma do banco chegou.
     * Idempotente; roda no trabalho agendado para promoteAt() e sempre que o app abre.
     */
    public static List<Detection> promoteDue(List<Detection> stored, long now, long windowMs) {
        List<Detection> changed = new ArrayList<>();
        for (Detection held : stored) {
            if (HELD.equals(held.state) && now >= promoteAt(held, windowMs)) {
                held.state = SUGGESTED;
                changed.add(held);
            }
        }
        return changed;
    }

    /**
     * Quando a retida pode virar sugestao: logo depois do fim da janela. Um banco postado
     * exatamente no limite ainda pareia, entao a promocao espera 1 ms alem dele.
     */
    public static long promoteAt(Detection held, long windowMs) {
        return held.postedAt + windowMs + 1;
    }

    /** Confirmar so vale para uma sugestao; o client_id do lancamento e o groupClientId. */
    public static boolean confirm(Detection detection) {
        if (!SUGGESTED.equals(detection.state)) return false;
        detection.state = CONFIRMED;
        return true;
    }

    public static boolean discard(Detection detection) {
        if (!SUGGESTED.equals(detection.state)) return false;
        detection.state = DISCARDED;
        return true;
    }

    /** As duas deteccoes podem ser a mesma compra (tipo, valor, cartao, janela)? */
    static boolean samePurchase(Detection a, Detection b, long windowMs) {
        if (Math.abs(a.postedAt - b.postedAt) > windowMs) return false;
        if (a.amountCents != b.amountCents) return false;
        if (!sameText(a.currency, b.currency)) return false;
        if (!kindsMatch(a.kind, b.kind)) return false;
        // Um cartao que as duas nomeiam tem de ser o mesmo; o que so uma nomeia nao impede.
        if (a.cardLast4 != null && b.cardLast4 != null && !a.cardLast4.equals(b.cardLast4)) return false;
        if (a.issuer != null && b.issuer != null && !a.issuer.equals(b.issuer)) return false;
        return true;
    }

    /** Credito e debito pareiam entre si (o Samsung pode nao saber qual foi); a negada, com compra. */
    private static boolean kindsMatch(String a, String b) {
        if (a == null || b == null) return false;
        boolean purchaseA = PURCHASES.contains(a) || DECLINED.equals(a);
        boolean purchaseB = PURCHASES.contains(b) || DECLINED.equals(b);
        if (purchaseA && purchaseB) return !(DECLINED.equals(a) && DECLINED.equals(b));
        return a.equals(b);
    }

    private interface Filter {
        boolean accepts(Detection candidate);
    }

    private static final Filter PAIRABLE_PARTNER = candidate ->
        !DECLINED.equals(candidate.kind) && PAIRABLE.contains(candidate.state);
    private static final Filter REFUSALS = candidate -> REFUSED.equals(candidate.state);
    private static final Filter CANCELLABLE_SAMSUNG = candidate ->
        PURCHASES.contains(candidate.kind)
            && (HELD.equals(candidate.state) || SUGGESTED.equals(candidate.state));

    /**
     * A deteccao do outro lado mais proxima no tempo que ainda nao tem par. Empate: a mais
     * antiga, depois o menor id, para o resultado nao depender da ordem da lista.
     */
    private static Detection closest(Detection incoming, List<Detection> stored, long windowMs,
                                     boolean wantSamsung, Filter filter) {
        Set<Long> partnered = new HashSet<>();
        for (Detection row : stored) {
            if (row.pairedWith != 0) {
                partnered.add(row.id);
                partnered.add(row.pairedWith);
            }
        }
        Detection best = null;
        for (Detection candidate : stored) {
            if (candidate == incoming || candidate.id == incoming.id) continue;
            if (candidate.fromSamsung() != wantSamsung) continue;
            if (partnered.contains(candidate.id)) continue;
            if (!filter.accepts(candidate)) continue;
            if (!samePurchase(incoming, candidate, windowMs)) continue;
            if (best == null || closer(incoming, candidate, best)) best = candidate;
        }
        return best;
    }

    private static boolean closer(Detection incoming, Detection candidate, Detection best) {
        long gap = Math.abs(candidate.postedAt - incoming.postedAt);
        long bestGap = Math.abs(best.postedAt - incoming.postedAt);
        if (gap != bestGap) return gap < bestGap;
        if (candidate.postedAt != best.postedAt) return candidate.postedAt < best.postedAt;
        return candidate.id < best.id;
    }

    /** {@code loser} fica no estado dado, ligado a {@code winner} e com o client_id dele. */
    private static void pair(Detection loser, Detection winner, String state) {
        loser.state = state;
        loser.pairedWith = winner.id;
        loser.groupClientId = winner.groupClientId;
    }

    private static boolean sameText(String a, String b) {
        return a == null ? b == null : a.equals(b);
    }
}
