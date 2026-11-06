package br.financas.app.outbox;

/**
 * O endereco do servidor guardado no login. Ate 2026-11 o APK falava com a porta 443 do
 * Tailscale (so na VPN); agora fala com a 8443, a do proxy de autenticacao, que funciona com e
 * sem a VPN. Um login guardado com o endereco antigo passa para o novo padrao ao abrir o app,
 * sem pedir login de novo. Puro: testado em ServerAddressTest.
 */
public final class ServerAddress {

    /** O endereco antigo (443, sem porta), so na tailnet. */
    public static final String OLD_BASE = "https://guilhermeserver.tail5084ff.ts.net";

    private ServerAddress() {}

    /**
     * O endereco a usar: o padrao do build no lugar do antigo; qualquer outro fica como esta.
     * Nada muda quando o proprio padrao e o antigo (um build feito com -PfinancasApiBase antigo).
     */
    public static String migrate(String stored, String defaultBase) {
        if (stored == null || stored.isEmpty()) return stored;
        if (defaultBase == null || defaultBase.isEmpty()) return stored;
        if (isOld(defaultBase) || !isOld(stored)) return stored;
        return defaultBase;
    }

    private static boolean isOld(String address) {
        String trimmed = address.trim().replaceAll("/+$", "");
        return trimmed.equalsIgnoreCase(OLD_BASE) || trimmed.equalsIgnoreCase(OLD_BASE + ":443");
    }
}
