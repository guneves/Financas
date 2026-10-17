package br.financas.app.update;

import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import androidx.core.content.FileProvider;
import androidx.core.content.pm.PackageInfoCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import br.financas.app.BuildConfig;

/**
 * O APK novo, quando a tela sozinha nao basta (lib/appUpdate.js): o CI publica o APK
 * assinado e /apk/version.json no servidor, so na tailnet (tailscale serve, DEPLOY.md).
 * Aqui: perguntar qual e o mais novo, baixar, conferir e abrir o instalador do Android.
 *
 * O instalador e o do sistema; ele confere a assinatura e so instala por cima um APK da
 * mesma chave, mantendo os dados (a fila, o login, o cache). A permissao "instalar apps
 * desconhecidos" e pedida uma vez, abrindo a tela dela nos Ajustes do Android.
 */
@CapacitorPlugin(name = "AppUpdate")
public class ApkUpdatePlugin extends Plugin {

    private static final String TAG = "FinancasUpdate";
    private static final int CONNECT_TIMEOUT_MS = 10_000;
    private static final int READ_TIMEOUT_MS = 30_000;
    private static final String APK_MIME = "application/vnd.android.package-archive";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean installing = new AtomicBoolean(false);

    @Override
    protected void handleOnDestroy() {
        executor.shutdown();
    }

    /** O APK instalado e o que o servidor publica (latest = null quando nao publica nenhum). */
    @PluginMethod
    public void latest(PluginCall call) {
        String baseUrl = baseUrl(call);
        if (baseUrl == null) return;
        executor.execute(() -> {
            try {
                Context context = getContext();
                JSObject result = installed(context);
                ApkUpdateRules.Latest latest = fetchLatest(baseUrl);
                if (latest != null) {
                    JSObject out = new JSObject();
                    out.put("versionCode", latest.versionCode);
                    out.put("versionName", latest.versionName);
                    out.put("nativeLevel", latest.nativeLevel);
                    out.put("size", latest.size);
                    result.put("latest", out);
                    result.put("newer", ApkUpdateRules.isNewer(latest, installedCode(context)));
                } else {
                    result.put("newer", false);
                }
                result.put("canInstall", canInstall(context));
                call.resolve(result);
            } catch (Exception error) {
                Log.w(TAG, "Nao foi possivel ler o APK publicado", error);
                call.reject(message(error, "Não foi possível procurar um APK novo."));
            }
        });
    }

    /**
     * Baixa o APK mais novo, confere e abre o instalador. Sem a permissao de instalar, abre a
     * tela dela e responde "needs-permission"; a tela chama de novo quando o app volta.
     */
    @PluginMethod
    public void install(PluginCall call) {
        String baseUrl = baseUrl(call);
        if (baseUrl == null) return;
        Context context = getContext();
        if (!canInstall(context)) {
            openInstallPermission(context);
            JSObject result = new JSObject();
            result.put("status", "needs-permission");
            call.resolve(result);
            return;
        }
        if (!installing.compareAndSet(false, true)) {
            JSObject busy = new JSObject();
            busy.put("status", "busy");
            call.resolve(busy);
            return;
        }
        executor.execute(() -> {
            try {
                ApkUpdateRules.Latest latest = fetchLatest(baseUrl);
                JSObject result = new JSObject();
                if (!ApkUpdateRules.isNewer(latest, installedCode(context))) {
                    result.put("status", "up-to-date");
                    call.resolve(result);
                    return;
                }
                File apk = download(context, baseUrl, latest);
                openInstaller(context, apk);
                result.put("status", "installing");
                call.resolve(result);
            } catch (Exception error) {
                Log.w(TAG, "Nao foi possivel instalar o APK novo", error);
                call.reject(message(error, "Não foi possível baixar o APK novo."));
            } finally {
                installing.set(false);
            }
        });
    }

    private static boolean canInstall(Context context) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || context.getPackageManager().canRequestPackageInstalls();
    }

    private void openInstallPermission(Context context) {
        Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + context.getPackageName()));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(intent);
        } catch (ActivityNotFoundException error) {
            context.startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }

    private static void openInstaller(Context context, File apk) {
        Uri uri = FileProvider.getUriForFile(context, context.getPackageName() + ".fileprovider", apk);
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, APK_MIME);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
    }

    private static JSObject installed(Context context) {
        JSObject result = new JSObject();
        result.put("installedCode", installedCode(context));
        result.put("nativeLevel", BuildConfig.NATIVE_LEVEL);
        return result;
    }

    private static long installedCode(Context context) {
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            return PackageInfoCompat.getLongVersionCode(info);
        } catch (PackageManager.NameNotFoundException error) {
            return Long.MAX_VALUE;
        }
    }

    private static ApkUpdateRules.Latest fetchLatest(String baseUrl) throws Exception {
        HttpURLConnection connection = open(baseUrl + ApkUpdateRules.MANIFEST_PATH);
        try {
            int status = connection.getResponseCode();
            if (status == 404) return null;
            if (status != 200) throw new IOException("O servidor respondeu " + status + ".");
            try (InputStream in = connection.getInputStream()) {
                return ApkUpdateRules.parse(new JSONObject(readUtf8(in)));
            } catch (IllegalArgumentException error) {
                throw new IOException(error.getMessage());
            }
        } finally {
            connection.disconnect();
        }
    }

    /** O APK em cache/apk/, conferido (tamanho, SHA-256, pacote, versionCode). */
    private static File download(Context context, String baseUrl, ApkUpdateRules.Latest latest) throws Exception {
        File dir = new File(context.getCacheDir(), "apk");
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Não foi possível criar a pasta do APK.");
        File apk = new File(dir, latest.file);
        File[] old = dir.listFiles();
        if (old != null) for (File file : old) if (!file.getName().equals(latest.file)) file.delete();

        // Ja baixado numa tentativa anterior (o dono cancelou o instalador): reaproveita.
        if (!(apk.length() == latest.size && sha256(apk).equals(latest.sha256))) {
            File part = new File(dir, latest.file + ".part");
            HttpURLConnection connection = open(baseUrl + latest.path());
            try {
                int status = connection.getResponseCode();
                if (status != 200) throw new IOException("O servidor respondeu " + status + " ao baixar o APK.");
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long total = 0;
                try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(part)) {
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = in.read(buffer)) != -1) {
                        total += count;
                        if (total > latest.size) throw new IOException("O APK baixado é maior que o anunciado.");
                        digest.update(buffer, 0, count);
                        out.write(buffer, 0, count);
                    }
                }
                if (total != latest.size || !hex(digest.digest()).equals(latest.sha256)) {
                    throw new IOException("O APK baixado não confere com o servidor.");
                }
                if (!part.renameTo(apk)) throw new IOException("Não foi possível guardar o APK.");
            } finally {
                connection.disconnect();
                part.delete();
            }
        }

        PackageInfo archive = context.getPackageManager().getPackageArchiveInfo(apk.getAbsolutePath(), 0);
        String archivePackage = archive == null ? null : archive.packageName;
        long archiveCode = archive == null ? -1 : PackageInfoCompat.getLongVersionCode(archive);
        if (!ApkUpdateRules.matchesArchive(latest, context.getPackageName(), archivePackage, archiveCode)) {
            apk.delete();
            throw new IOException("O APK baixado não é o anunciado.");
        }
        Log.i(TAG, "APK " + latest.versionCode + " baixado; abrindo o instalador");
        return apk;
    }

    private static String baseUrl(PluginCall call) {
        String baseUrl = call.getString("baseUrl", "").replaceAll("/+$", "");
        if (!baseUrl.startsWith("https://")) {
            call.reject("Endereço do servidor inválido.");
            return null;
        }
        return baseUrl;
    }

    private static HttpURLConnection open(String address) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        // Um portal de Wi-Fi responderia 3xx com uma pagina qualquer: nao segue.
        connection.setInstanceFollowRedirects(false);
        // Sem cache: o manifesto muda a cada APK publicado.
        connection.setUseCaches(false);
        return connection;
    }

    private static String sha256(File file) throws Exception {
        if (!file.isFile()) return "";
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = in.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        return hex(digest.digest());
    }

    private static String readUtf8(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
        return out.toString(StandardCharsets.UTF_8.name());
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) out.append(String.format("%02x", value & 0xff));
        return out.toString();
    }

    private static String message(Exception error, String fallback) {
        return error.getMessage() == null ? fallback : error.getMessage();
    }
}
