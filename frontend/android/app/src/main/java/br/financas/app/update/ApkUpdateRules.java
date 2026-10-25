package br.financas.app.update;

import org.json.JSONObject;

import java.util.regex.Pattern;

/**
 * As regras do APK novo, sem Android: o que o servidor publica em /apk/version.json (o job
 * "apk" de .github/workflows/deploy.yml grava) e quando ele vale para este aparelho.
 * Testadas na JVM (ApkUpdateRulesTest).
 *
 * O manifesto so e aceito inteiro: nome de arquivo do formato que o CI grava, SHA-256 e
 * tamanho plausiveis. O "native_level" que o CI ainda grava e so para os APKs da WebView
 * (que o exigem); este nao o le. Um APK so e oferecido quando o versionCode dele e maior que o
 * instalado; o Android recusaria um menor de qualquer jeito.
 */
public final class ApkUpdateRules {

    public static final String MANIFEST_PATH = "/apk/version.json";
    public static final long MAX_APK_BYTES = 200L * 1024 * 1024;

    private static final Pattern FILE = Pattern.compile("^financas-[0-9]{1,9}\\.apk$");
    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");

    private ApkUpdateRules() {}

    /** O APK que o servidor publica. */
    public static final class Latest {
        public final long versionCode;
        public final String versionName;
        public final String sha256;
        public final long size;
        public final String file;

        Latest(long versionCode, String versionName, String sha256, long size, String file) {
            this.versionCode = versionCode;
            this.versionName = versionName;
            this.sha256 = sha256;
            this.size = size;
            this.file = file;
        }

        /** Caminho do APK no servidor, ao lado do manifesto. */
        public String path() {
            return "/apk/" + file;
        }
    }

    /** O manifesto lido, ou IllegalArgumentException se faltar ou sobrar algo. */
    public static Latest parse(JSONObject json) {
        long versionCode = json.optLong("version_code", -1);
        String sha256 = json.optString("sha256", "");
        long size = json.optLong("size", -1);
        String file = json.optString("file", "");
        if (versionCode < 1) throw new IllegalArgumentException("Manifesto do APK sem versionCode.");
        if (!SHA256.matcher(sha256).matches()) throw new IllegalArgumentException("Manifesto do APK sem SHA-256.");
        if (size <= 0 || size > MAX_APK_BYTES) throw new IllegalArgumentException("Tamanho do APK inválido.");
        if (!FILE.matcher(file).matches()) throw new IllegalArgumentException("Nome do APK inválido.");
        return new Latest(versionCode, json.optString("version_name", ""), sha256, size, file);
    }

    public static boolean isNewer(Latest latest, long installedCode) {
        return latest != null && latest.versionCode > installedCode;
    }

    /**
     * O APK baixado e o anunciado e serve para este app: mesmo pacote, mesmo versionCode.
     * A assinatura quem confere e o instalador do Android (recusa outra chave).
     */
    public static boolean matchesArchive(Latest latest, String packageName, String archivePackage, long archiveCode) {
        return latest != null && packageName != null && packageName.equals(archivePackage) && archiveCode == latest.versionCode;
    }
}
