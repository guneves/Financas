package br.financas.app.bundle;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;

import androidx.core.content.pm.PackageInfoCompat;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/**
 * Onde as telas baixadas moram (files/bundles/<versao>/) e o estado das regras
 * (BundleRules.State), em SharedPreferences.
 *
 * Um APK novo apaga tudo: a tela dele e a mais nova, e uma baixada para o APK antigo pode
 * depender do Java antigo. O Capacitor faz o mesmo com o caminho que ele guarda
 * (Bridge.isNewBinary), e aqui se usa a mesma identidade: versionCode e versionName.
 */
final class BundleStore {

    private static final String PREFS = "financas_bundle";
    // As preferencias do proprio Capacitor (plugin/WebView.java): o Bridge le este caminho ao
    // montar a WebView e serve a tela dali em vez dos assets do APK.
    private static final String CAP_PREFS = "CapWebViewSettings";
    private static final String CAP_SERVER_PATH = "serverBasePath";

    private BundleStore() {}

    static File root(Context context) {
        return new File(context.getFilesDir(), "bundles");
    }

    static File dir(Context context, String version) {
        return new File(root(context), version);
    }

    static boolean isComplete(Context context, String version) {
        return BundleRules.isValidVersion(version) && new File(dir(context, version), "index.html").isFile();
    }

    static String apkIdentity(Context context) {
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            return PackageInfoCompat.getLongVersionCode(info) + ":" + (info.versionName == null ? "" : info.versionName);
        } catch (Exception error) {
            return "";
        }
    }

    static synchronized BundleRules.State load(Context context) {
        SharedPreferences prefs = prefs(context);
        String apk = apkIdentity(context);
        BundleRules.State state = new BundleRules.State();
        if (!apk.equals(prefs.getString("apk", null))) {
            deleteRecursively(root(context));
            prefs.edit().clear().putString("apk", apk).apply();
            return state;
        }
        state.current = prefs.getString("current", "");
        state.confirmed = prefs.getBoolean("confirmed", true);
        state.attempts = prefs.getInt("attempts", 0);
        state.staged = prefs.getString("staged", "");
        String failed = prefs.getString("failed", "");
        if (!failed.isEmpty()) state.failed.addAll(Arrays.asList(failed.split(",")));
        return state;
    }

    static synchronized void save(Context context, BundleRules.State state) {
        prefs(context).edit()
            .putString("current", state.current)
            .putBoolean("confirmed", state.confirmed)
            .putInt("attempts", state.attempts)
            .putString("staged", state.staged)
            .putString("failed", String.join(",", state.failed))
            .commit();
        // O caminho que o Capacitor abre na proxima montagem da WebView.
        String path = state.current.isEmpty() ? "" : dir(context, state.current).getAbsolutePath();
        context.getSharedPreferences(CAP_PREFS, Context.MODE_PRIVATE).edit()
            .putString(CAP_SERVER_PATH, path)
            .commit();
    }

    /** Apaga as pastas que nao sao nem a tela em uso nem a que espera. */
    static synchronized void prune(Context context, BundleRules.State state) {
        File[] children = root(context).listFiles();
        if (children == null) return;
        for (File child : children) {
            String name = child.getName();
            if (name.equals(state.current) || name.equals(state.staged)) continue;
            deleteRecursively(child);
        }
    }

    /** A versao da tela que veio no APK (assets/public/bundle.json), ou "" num build sem ela. */
    static String builtinVersion(Context context) {
        try (InputStream in = context.getAssets().open("public/bundle.json")) {
            return new JSONObject(readUtf8(in)).optString("version", "");
        } catch (Exception error) {
            return "";
        }
    }

    static String readUtf8(File file) throws IOException {
        try (InputStream in = new FileInputStream(file)) {
            return readUtf8(in);
        }
    }

    static String readUtf8(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
        return out.toString(StandardCharsets.UTF_8.name());
    }

    static void deleteRecursively(File file) {
        if (file == null || !file.exists()) return;
        File[] children = file.listFiles();
        if (children != null) for (File child : children) deleteRecursively(child);
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
