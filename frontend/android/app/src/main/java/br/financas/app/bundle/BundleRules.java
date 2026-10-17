package br.financas.app.bundle;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.function.Predicate;
import java.util.regex.Pattern;

/**
 * As regras da tela baixada do servidor, sem Android: o que fazer com o manifesto que o
 * servidor mandou e qual tela abrir. Testadas na JVM (BundleRulesTest).
 *
 * Uma tela e identificada pela versao do bundle.json (hash do conteudo). Ha tres lugares:
 * - a tela do APK (builtin), sempre presente e sempre compativel;
 * - current: a baixada que esta em uso. Vazia = a do APK;
 * - staged: a baixada que entra na proxima abertura (ou BUILTIN, para voltar a do APK).
 *
 * Uma tela nova abre "em teste" (confirmed = false) e so passa quando a propria tela chama
 * ready() depois de desenhar. Se nao chamar, ela vai para failed e o app volta a tela do APK;
 * uma versao em failed nunca e baixada de novo.
 */
public final class BundleRules {

    public static final String BUILTIN = "@builtin";
    /** Aberturas em teste sem ready() (o app morto logo de cara) antes de desistir da tela. */
    public static final int MAX_TRIAL_LAUNCHES = 2;
    static final int MAX_FAILED = 20;

    public static final String UP_TO_DATE = "up-to-date";
    public static final String ALREADY_STAGED = "staged";
    public static final String DROP_STAGED = "drop-staged";
    public static final String USE_BUILTIN = "use-builtin";
    public static final String INCOMPATIBLE = "incompatible";
    public static final String OTHER_SERVER = "other-server";
    public static final String FAILED_BEFORE = "failed-before";
    public static final String DOWNLOAD = "download";

    private static final Pattern VERSION = Pattern.compile("^[0-9a-f]{16}$");

    private BundleRules() {}

    /** O estado guardado (BundleStore o le e grava). */
    public static final class State {
        public String current = "";
        public boolean confirmed = true;
        public int attempts = 0;
        public String staged = "";
        public final Set<String> failed = new LinkedHashSet<>();

        public void fail(String version) {
            if (version == null || version.isEmpty()) return;
            failed.remove(version);
            failed.add(version);
            while (failed.size() > MAX_FAILED) failed.remove(failed.iterator().next());
        }

        public boolean inTrial() {
            return !current.isEmpty() && !confirmed;
        }
    }

    public static boolean isValidVersion(String version) {
        return version != null && VERSION.matcher(version).matches();
    }

    /**
     * O que fazer com a versao que o servidor oferece. O servidor manda: nao ha "mais nova",
     * so "a de la". Se for a do APK, volta para ela.
     */
    public static String decide(
        String target, int targetLevel, String targetApiBase,
        int nativeLevel, String baseUrl, String builtin, State state
    ) {
        String running = state.current.isEmpty() ? nullToEmpty(builtin) : state.current;
        if (target.equals(state.staged)) return ALREADY_STAGED;
        if (BUILTIN.equals(state.staged) && target.equals(builtin)) return ALREADY_STAGED;
        if (target.equals(running)) return state.staged.isEmpty() ? UP_TO_DATE : DROP_STAGED;
        if (target.equals(builtin)) return USE_BUILTIN;
        // O nivel da tela e o minimo de Java que ela chama (plugin novo, metodo novo): num APK
        // mais velho ela quebraria. Um APK mais novo a abre (o Java so ganha metodos).
        if (targetLevel > nativeLevel) return INCOMPATIBLE;
        // A tela chama a API compilada nela: de outro servidor, falaria com outro lugar.
        if (!trimSlash(targetApiBase).equals(trimSlash(baseUrl))) return OTHER_SERVER;
        if (state.failed.contains(target)) return FAILED_BEFORE;
        return DOWNLOAD;
    }

    /**
     * Na abertura (e em apply()): desiste de uma tela em teste que nunca confirmou, promove a
     * que estava esperando e conta mais uma abertura em teste. Altera e devolve o estado.
     */
    public static State planLaunch(State state, Predicate<String> isComplete) {
        if (state.inTrial() && state.attempts >= MAX_TRIAL_LAUNCHES) {
            state.fail(state.current);
            state.current = "";
            state.confirmed = true;
            state.attempts = 0;
        }
        if (!state.staged.isEmpty()) {
            if (BUILTIN.equals(state.staged)) {
                state.current = "";
                state.confirmed = true;
                state.attempts = 0;
            } else if (isComplete.test(state.staged)) {
                state.current = state.staged;
                state.confirmed = false;
                state.attempts = 0;
            }
            state.staged = "";
        }
        if (!state.current.isEmpty() && !isComplete.test(state.current)) {
            state.current = "";
            state.confirmed = true;
            state.attempts = 0;
        }
        if (state.inTrial()) state.attempts++;
        return state;
    }

    /** Um nome de entrada do zip que fica dentro da pasta da tela. */
    public static boolean isSafeEntryName(String name) {
        if (name == null || name.isEmpty() || name.length() > 512) return false;
        if (name.startsWith("/") || name.startsWith("\\") || name.contains("\\") || name.contains(":")) return false;
        if (name.indexOf('\0') >= 0) return false;
        for (String part : name.split("/", -1)) {
            if (part.equals("..") || part.equals(".")) return false;
        }
        return true;
    }

    private static String trimSlash(String value) {
        return nullToEmpty(value).replaceAll("/+$", "");
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
