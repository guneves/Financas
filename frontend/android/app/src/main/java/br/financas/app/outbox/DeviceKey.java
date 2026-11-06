package br.financas.app.outbox;

import java.net.HttpURLConnection;

/**
 * A chave de acesso remoto: o segredo que o proxy na frente do app (Caddy, porta 8443 do
 * Funnel; README "Remote access") compara com PROXY_DEVICE_KEY antes de deixar o pedido passar.
 * Vai em todo pedido ao servidor, no cabecalho X-Device-Key, ao lado do Bearer do app (que
 * continua valendo atras do proxy). O proxy tira o cabecalho antes do app.
 *
 * Um 401 com "X-Proxy-Auth: required" e do proxy, nao do app: a chave falta ou esta errada.
 * Nunca apaga o login; a fila e as deteccoes esperam e tentam de novo, e as telas pedem a chave.
 *
 * Puro (sem Android): testado em DeviceKeyTest.
 */
public final class DeviceKey {

    public static final String HEADER = "X-Device-Key";
    public static final String PROXY_AUTH_HEADER = "X-Proxy-Auth";
    public static final String PROXY_AUTH_REQUIRED = "required";

    /** O texto das telas quando o proxy recusa. */
    public static final String MESSAGE = "Chave de acesso inválida ou ausente";

    private DeviceKey() {}

    /** A chave como foi colada: sem espacos nem quebras de linha (o proxy compara exato). */
    public static String normalize(String raw) {
        if (raw == null) return "";
        return raw.replaceAll("\\s+", "");
    }

    /** O 401 do proxy (chave ausente ou errada), diferente do 401 do app (login vencido). */
    public static boolean isProxyAuthRequired(int status, String proxyAuthHeader) {
        return status == 401 && proxyAuthHeader != null && PROXY_AUTH_REQUIRED.equalsIgnoreCase(proxyAuthHeader.trim());
    }

    /** O 401 do proxy, lido da resposta de uma conexao ja feita. */
    public static boolean isProxyAuthRequired(HttpURLConnection connection, int status) {
        return isProxyAuthRequired(status, connection.getHeaderField(PROXY_AUTH_HEADER));
    }

    /** Poe a chave no pedido (antes de conectar). Sem chave guardada, nada: o proxy recusa. */
    public static void apply(HttpURLConnection connection, String key) {
        String value = normalize(key);
        if (!value.isEmpty()) connection.setRequestProperty(HEADER, value);
    }
}
