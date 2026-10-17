package br.financas.app.notify;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.TreeMap;

/**
 * As regras do leitor de notificacoes dos bancos, sem Android (mobile-docs/steps-to-production.md,
 * Fase 6). Testadas na JVM (NotifyRulesTest).
 *
 * - quais apps sao ouvidos: a lista fechada de APPS. O shell do adb so num build debug, para
 *   testar o caminho com `adb shell cmd notification post` sem uma compra de verdade;
 * - a chave de uma notificacao (pacote + key do Android + hora em que foi postada), para que a
 *   mesma postagem lida duas vezes (na chegada e de novo ao religar o leitor) seja uma linha so;
 * - o texto que vale: o bigText quando veio (costuma trazer o nome inteiro do lugar), senao o text;
 * - a exportacao da captura, em JSON ou texto. E o unico caminho por onde um texto sai do aparelho.
 *
 * O Samsung Wallet voltou (dono, 2026-10-17): vale quando o banco nao notifica a compra no
 * cartao; quando os dois notificam, a do banco e a que fica (Fase 6, passo 4). Itaú Cartões e
 * Ourocard seguem de fora: repetiriam as compras que o app do banco ja notifica.
 */
public final class NotifyRules {

    public static final String SHELL_PACKAGE = "com.android.shell";
    public static final String SHELL_LABEL = "Teste (adb)";

    /** Chegou pelo onNotificationPosted, ou estava na bandeja quando o Android religou o leitor. */
    public static final String VIA_POSTED = "posted";
    public static final String VIA_ACTIVE = "active";

    /** Um app ouvido. Cada pacote conferido na Play Store (a tabela da Fase 6). */
    public static final class App {
        public final String packageName;
        public final String label;

        App(String packageName, String label) {
            this.packageName = packageName;
            this.label = label;
        }
    }

    /** Na ordem da tela. O BTG de investimentos entra para as operacoes da corretora (Fase 6). */
    public static final List<App> APPS = Collections.unmodifiableList(Arrays.asList(
        new App("com.samsung.android.spay", "Samsung Wallet"),
        new App("com.itau", "Itaú"),
        new App("br.com.bb.android", "Banco do Brasil"),
        new App("com.btg.pactual.banking", "BTG Pactual"),
        new App("com.btg.pactual.digital.mobile", "BTG Investimentos")
    ));

    /** Os extras que o texto da exportacao ja mostra pelo nome (titulo, texto, texto longo). */
    static final List<String> SHOWN_EXTRAS = Collections.unmodifiableList(Arrays.asList(
        "android.title", "android.text", "android.bigText"
    ));

    private NotifyRules() {}

    /** Ouve este pacote? O shell so quando {@code acceptShell} (BuildConfig.DEBUG). */
    public static boolean isAllowed(String packageName, boolean acceptShell) {
        if (packageName == null || packageName.isEmpty()) return false;
        if (SHELL_PACKAGE.equals(packageName)) return acceptShell;
        for (App app : APPS) {
            if (app.packageName.equals(packageName)) return true;
        }
        return false;
    }

    public static String labelFor(String packageName) {
        if (SHELL_PACKAGE.equals(packageName)) return SHELL_LABEL;
        for (App app : APPS) {
            if (app.packageName.equals(packageName)) return app.label;
        }
        return packageName == null ? "" : packageName;
    }

    /**
     * A chave de uma postagem: SHA-256 em hexa de pacote, key e hora postada. A mesma postagem
     * da sempre a mesma chave; uma notificacao que o banco atualiza e postada de novo, com outra
     * hora, e vira outra chave (a captura mostra se os bancos fazem isso). 64 caracteres
     * [0-9a-f]: cabe no formato do client_id do servidor (validators.CLIENT_ID_PATTERN).
     */
    public static String dedupKey(String packageName, String key, long postedAt) {
        String source = nullToEmpty(packageName) + "\n" + nullToEmpty(key) + "\n" + postedAt;
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return hex(digest.digest(source.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 indisponivel", error);
        }
    }

    /** O bigText quando tem algo alem de espacos; senao o text (que pode ser null). */
    public static String bestText(String text, String bigText) {
        if (bigText != null && !bigText.trim().isEmpty()) return bigText;
        return text;
    }

    /** Uma notificacao guardada, palavra por palavra (nenhum campo e aparado ou reescrito). */
    public static final class Captured {
        public String packageName;
        public String key;
        public long postedAt;
        public long receivedAt;
        /** Notification.when: a hora que o proprio app pos na notificacao (0 quando nao pos). */
        public long when;
        /** android.title, android.text e android.bigText, os tres que os parsers vao ler. */
        public String title;
        public String text;
        public String bigText;
        /**
         * Todo extra de texto da notificacao, pelo nome do Android (android.subText,
         * android.textLines com uma linha por item, android.title.big, android.template...),
         * os tres acima inclusive. Para o parser nao depender de um campo que a captura deixou de fora.
         */
        public final Map<String, String> extras = new TreeMap<>();
        public String channelId;
        public String category;
        public boolean groupSummary;
        public boolean ongoing;
        public String via = VIA_POSTED;

        public String dedupKey() {
            return NotifyRules.dedupKey(packageName, key, postedAt);
        }
    }

    /** O arquivo JSON da exportacao: as capturas em ordem de chegada, com hora local legivel. */
    public static String toJson(List<Captured> rows, long exportedAt, TimeZone zone) {
        try {
            JSONArray list = new JSONArray();
            for (Captured row : chronological(rows)) {
                JSONObject item = new JSONObject();
                item.put("package", row.packageName);
                item.put("app", labelFor(row.packageName));
                item.put("posted_at", row.postedAt);
                item.put("posted_at_local", isoTime(row.postedAt, zone));
                item.put("received_at", row.receivedAt);
                item.put("when", row.when);
                item.put("key", row.key);
                item.put("dedup_key", row.dedupKey());
                item.put("title", nullable(row.title));
                item.put("text", nullable(row.text));
                item.put("big_text", nullable(row.bigText));
                item.put("extras", new JSONObject(row.extras));
                item.put("channel_id", nullable(row.channelId));
                item.put("category", nullable(row.category));
                item.put("group_summary", row.groupSummary);
                item.put("ongoing", row.ongoing);
                item.put("via", row.via);
                list.put(item);
            }
            JSONObject out = new JSONObject();
            out.put("exported_at", isoTime(exportedAt, zone));
            out.put("time_zone", zone.getID());
            out.put("count", list.length());
            out.put("notifications", list);
            return out.toString(2);
        } catch (JSONException error) {
            throw new IllegalStateException("Exportacao invalida", error);
        }
    }

    /** O arquivo de texto da exportacao: para ler e colar, um bloco por notificacao. */
    public static String toText(List<Captured> rows, long exportedAt, TimeZone zone) {
        List<Captured> ordered = chronological(rows);
        StringBuilder out = new StringBuilder();
        out.append("Finanças: notificações capturadas (").append(ordered.size()).append(")\n");
        out.append("Exportado em ").append(isoTime(exportedAt, zone)).append(" (").append(zone.getID()).append(")\n");
        for (Captured row : ordered) {
            out.append("\n----------------------------------------\n");
            out.append(isoTime(row.postedAt, zone)).append("  ").append(labelFor(row.packageName))
                .append(" (").append(row.packageName).append(")\n");
            field(out, "título", row.title);
            field(out, "texto", row.text);
            field(out, "texto longo", row.bigText);
            for (Map.Entry<String, String> extra : row.extras.entrySet()) {
                if (SHOWN_EXTRAS.contains(extra.getKey())) continue;
                field(out, extra.getKey(), extra.getValue());
            }
            out.append("key: ").append(row.key).append('\n');
            out.append("postada: ").append(row.postedAt).append(" · when: ").append(row.when)
                .append(" · via: ").append(row.via).append('\n');
            out.append("canal: ").append(nullable(row.channelId, "-"))
                .append(" · categoria: ").append(nullable(row.category, "-"));
            if (row.groupSummary) out.append(" · resumo de grupo");
            if (row.ongoing) out.append(" · fixa");
            out.append('\n');
        }
        return out.toString();
    }

    /** Hora local com milissegundos e fuso, para comparar notificacoes proximas. */
    public static String isoTime(long millis, TimeZone zone) {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.ROOT);
        format.setTimeZone(zone);
        return format.format(new Date(millis));
    }

    private static List<Captured> chronological(List<Captured> rows) {
        List<Captured> ordered = new ArrayList<>(rows);
        Collections.sort(ordered, (a, b) -> Long.compare(a.postedAt, b.postedAt));
        return ordered;
    }

    private static void field(StringBuilder out, String label, String value) {
        if (value == null) return;
        out.append(label).append(": ").append(value).append('\n');
    }

    private static Object nullable(String value) {
        return value == null ? JSONObject.NULL : value;
    }

    private static String nullable(String value, String fallback) {
        return value == null ? fallback : value;
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) out.append(String.format("%02x", value & 0xff));
        return out.toString();
    }
}
