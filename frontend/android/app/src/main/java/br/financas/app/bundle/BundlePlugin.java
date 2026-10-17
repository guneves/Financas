package br.financas.app.bundle;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import androidx.core.content.pm.PackageInfoCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import br.financas.app.BuildConfig;

/**
 * A tela se atualiza sozinha (lib/appBundle.js): o app pergunta ao servidor qual tela ele
 * serve (GET /api/app-bundle), baixa o zip, confere o SHA-256 e a deixa esperando; ela entra
 * na proxima abertura. As regras estao em BundleRules; aqui so a rede, os arquivos e a WebView.
 *
 * A troca e feita pelo proprio Capacitor: o Bridge le o caminho de CapWebViewSettings ao
 * montar a WebView. load() roda antes disso (os plugins sao registrados antes da WebView
 * carregar), entao decidir aqui vale ja para esta abertura.
 *
 * Volta para a tela do APK quando: a tela nova nao chama ready() em READY_TIMEOUT_MS, o app
 * e morto antes disso duas vezes, ou o dono pede (reset()). Abrir sem rede nunca depende do
 * servidor: a tela baixada mora no aparelho, e a do APK continua dentro dele.
 */
@CapacitorPlugin(name = "AppBundle")
public class BundlePlugin extends Plugin {

    private static final String TAG = "FinancasBundle";
    private static final long READY_TIMEOUT_MS = 30_000;
    private static final int CONNECT_TIMEOUT_MS = 10_000;
    private static final int READ_TIMEOUT_MS = 30_000;
    private static final long MAX_BUNDLE_BYTES = 50L * 1024 * 1024;
    private static final String MANIFEST_PATH = "/api/app-bundle";
    // Os assets do APK, onde o Capacitor procura a tela por padrao.
    private static final String BUILTIN_ASSET_PATH = "public";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final AtomicBoolean checking = new AtomicBoolean(false);
    private final Runnable readyTimeout = this::onReadyTimeout;

    @Override
    public void load() {
        Context context = getContext();
        synchronized (BundleStore.class) {
            BundleRules.State state = BundleStore.load(context);
            BundleRules.planLaunch(state, version -> BundleStore.isComplete(context, version));
            BundleStore.save(context, state);
            if (state.inTrial()) {
                Log.i(TAG, "Abrindo a tela " + state.current + " em teste (abertura " + state.attempts + ")");
                main.postDelayed(readyTimeout, READY_TIMEOUT_MS);
            }
        }
    }

    @Override
    protected void handleOnDestroy() {
        main.removeCallbacks(readyTimeout);
        executor.shutdown();
    }

    /** A tela desenhou: a que estava em teste passa. */
    @PluginMethod
    public void ready(PluginCall call) {
        Context context = getContext();
        main.removeCallbacks(readyTimeout);
        synchronized (BundleStore.class) {
            BundleRules.State state = BundleStore.load(context);
            if (state.inTrial()) {
                state.confirmed = true;
                state.attempts = 0;
                BundleStore.save(context, state);
                Log.i(TAG, "Tela " + state.current + " confirmada");
            }
            BundleRules.State snapshot = state;
            executor.execute(() -> BundleStore.prune(context, snapshot));
        }
        call.resolve(info(context));
    }

    @PluginMethod
    public void info(PluginCall call) {
        call.resolve(info(getContext()));
    }

    /** Pergunta ao servidor e, se a tela de la e outra, baixa e deixa esperando. */
    @PluginMethod
    public void check(PluginCall call) {
        String baseUrl = call.getString("baseUrl", "").replaceAll("/+$", "");
        if (!baseUrl.startsWith("https://")) {
            call.reject("Endereço do servidor inválido.");
            return;
        }
        if (!checking.compareAndSet(false, true)) {
            JSObject busy = new JSObject();
            busy.put("status", "busy");
            call.resolve(busy);
            return;
        }
        executor.execute(() -> {
            try {
                call.resolve(runCheck(getContext(), baseUrl));
            } catch (Exception error) {
                Log.w(TAG, "Nao foi possivel procurar uma tela nova", error);
                call.reject(error.getMessage() == null ? "Não foi possível procurar atualização." : error.getMessage());
            } finally {
                checking.set(false);
            }
        });
    }

    /** Troca agora pela tela que espera, recarregando a WebView. */
    @PluginMethod
    public void apply(PluginCall call) {
        Context context = getContext();
        BundleRules.State state;
        synchronized (BundleStore.class) {
            state = BundleStore.load(context);
            if (state.staged.isEmpty()) {
                JSObject result = new JSObject();
                result.put("applied", false);
                call.resolve(result);
                return;
            }
            BundleRules.planLaunch(state, version -> BundleStore.isComplete(context, version));
            BundleStore.save(context, state);
        }
        JSObject result = new JSObject();
        result.put("applied", true);
        call.resolve(result);
        switchTo(context, state);
    }

    /** Volta para a tela do APK; a baixada em uso nao volta mais. */
    @PluginMethod
    public void reset(PluginCall call) {
        Context context = getContext();
        BundleRules.State state;
        synchronized (BundleStore.class) {
            state = BundleStore.load(context);
            state.fail(state.current);
            state.current = "";
            state.confirmed = true;
            state.attempts = 0;
            BundleStore.save(context, state);
        }
        call.resolve();
        switchTo(context, state);
    }

    private void switchTo(Context context, BundleRules.State state) {
        main.post(() -> {
            main.removeCallbacks(readyTimeout);
            if (state.current.isEmpty()) {
                getBridge().setServerAssetPath(BUILTIN_ASSET_PATH);
            } else {
                if (state.inTrial()) main.postDelayed(readyTimeout, READY_TIMEOUT_MS);
                getBridge().setServerBasePath(BundleStore.dir(context, state.current).getAbsolutePath());
            }
        });
    }

    private void onReadyTimeout() {
        Context context = getContext();
        synchronized (BundleStore.class) {
            BundleRules.State state = BundleStore.load(context);
            if (!state.inTrial()) return;
            Log.w(TAG, "A tela " + state.current + " nao confirmou em " + READY_TIMEOUT_MS + " ms: volta a do APK");
            state.fail(state.current);
            state.current = "";
            state.confirmed = true;
            state.attempts = 0;
            BundleStore.save(context, state);
        }
        getBridge().setServerAssetPath(BUILTIN_ASSET_PATH);
    }

    private static JSObject info(Context context) {
        BundleRules.State state = BundleStore.load(context);
        String builtin = BundleStore.builtinVersion(context);
        JSObject result = new JSObject();
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            result.put("apkVersion", info.versionName);
            result.put("apkCode", PackageInfoCompat.getLongVersionCode(info));
        } catch (Exception ignored) {
            // Sem as informacoes do pacote a tela mostra so o resto.
        }
        result.put("nativeLevel", BuildConfig.NATIVE_LEVEL);
        result.put("builtin", builtin);
        result.put("current", state.current);
        result.put("staged", BundleRules.BUILTIN.equals(state.staged) ? "builtin" : state.staged);
        result.put("running", state.current.isEmpty() ? builtin : state.current);
        result.put("onBuiltin", state.current.isEmpty());
        result.put("inTrial", state.inTrial());
        return result;
    }

    private static JSObject runCheck(Context context, String baseUrl) throws Exception {
        JSObject result = new JSObject();
        JSONObject manifest = fetchManifest(baseUrl);
        if (manifest == null) {
            result.put("status", "none");
            return result;
        }
        String target = manifest.optString("version", "");
        if (!BundleRules.isValidVersion(target)) throw new IOException("Resposta do servidor sem versão da tela.");
        int targetLevel = manifest.optInt("native_level", -1);
        result.put("version", target);
        result.put("nativeLevel", targetLevel);

        String decision;
        synchronized (BundleStore.class) {
            BundleRules.State state = BundleStore.load(context);
            decision = BundleRules.decide(
                target, targetLevel, manifest.optString("api_base", ""),
                BuildConfig.NATIVE_LEVEL, baseUrl, BundleStore.builtinVersion(context), state
            );
            if (BundleRules.DROP_STAGED.equals(decision)) {
                state.staged = "";
                BundleStore.save(context, state);
                BundleStore.prune(context, state);
                decision = BundleRules.UP_TO_DATE;
            } else if (BundleRules.USE_BUILTIN.equals(decision)) {
                state.staged = BundleRules.BUILTIN;
                BundleStore.save(context, state);
                BundleStore.prune(context, state);
                decision = BundleRules.ALREADY_STAGED;
            }
        }
        if (BundleRules.DOWNLOAD.equals(decision)) {
            download(context, baseUrl, manifest, target);
            synchronized (BundleStore.class) {
                BundleRules.State state = BundleStore.load(context);
                state.staged = target;
                BundleStore.save(context, state);
                BundleStore.prune(context, state);
            }
            Log.i(TAG, "Tela " + target + " baixada; entra na proxima abertura");
            decision = BundleRules.ALREADY_STAGED;
        }
        result.put("status", decision);
        return result;
    }

    private static JSONObject fetchManifest(String baseUrl) throws Exception {
        HttpURLConnection connection = open(baseUrl + MANIFEST_PATH);
        try {
            int status = connection.getResponseCode();
            if (status == 404) return null;
            if (status != 200) throw new IOException("O servidor respondeu " + status + ".");
            try (InputStream in = connection.getInputStream()) {
                return new JSONObject(BundleStore.readUtf8(in));
            }
        } finally {
            connection.disconnect();
        }
    }

    private static void download(Context context, String baseUrl, JSONObject manifest, String target) throws Exception {
        String path = manifest.optString("url", "");
        if (!path.equals(MANIFEST_PATH + "/" + target + ".zip")) throw new IOException("Endereço da tela inesperado.");
        long size = manifest.optLong("size", -1);
        String sha256 = manifest.optString("sha256", "").toLowerCase(Locale.ROOT);
        if (size <= 0 || size > MAX_BUNDLE_BYTES || !sha256.matches("^[0-9a-f]{64}$")) {
            throw new IOException("Manifesto da tela inválido.");
        }

        File zip = new File(context.getCacheDir(), "bundle-" + target + ".zip");
        File part = new File(BundleStore.root(context), target + ".part");
        try {
            HttpURLConnection connection = open(baseUrl + path);
            try {
                int status = connection.getResponseCode();
                if (status != 200) throw new IOException("O servidor respondeu " + status + " ao baixar a tela.");
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long total = 0;
                try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(zip)) {
                    byte[] buffer = new byte[16384];
                    int count;
                    while ((count = in.read(buffer)) != -1) {
                        total += count;
                        if (total > size) throw new IOException("A tela baixada é maior que o anunciado.");
                        digest.update(buffer, 0, count);
                        out.write(buffer, 0, count);
                    }
                }
                if (total != size || !hex(digest.digest()).equals(sha256)) {
                    throw new IOException("A tela baixada não confere com o servidor.");
                }
            } finally {
                connection.disconnect();
            }

            BundleStore.deleteRecursively(part);
            unzip(zip, part);
            if (!new File(part, "index.html").isFile()) throw new IOException("A tela baixada não tem index.html.");
            JSONObject inner = new JSONObject(BundleStore.readUtf8(new File(part, "bundle.json")));
            if (!target.equals(inner.optString("version")) || inner.optInt("native_level", Integer.MAX_VALUE) > BuildConfig.NATIVE_LEVEL) {
                throw new IOException("A tela baixada não é a anunciada.");
            }
            File done = BundleStore.dir(context, target);
            BundleStore.deleteRecursively(done);
            if (!part.renameTo(done)) throw new IOException("Não foi possível guardar a tela baixada.");
        } finally {
            //noinspection ResultOfMethodCallIgnored
            zip.delete();
            BundleStore.deleteRecursively(part);
        }
    }

    private static void unzip(File zip, File target) throws IOException {
        if (!target.mkdirs() && !target.isDirectory()) throw new IOException("Não foi possível criar a pasta da tela.");
        String root = target.getCanonicalPath() + File.separator;
        try (ZipInputStream in = new ZipInputStream(new FileInputStream(zip))) {
            ZipEntry entry;
            byte[] buffer = new byte[16384];
            while ((entry = in.getNextEntry()) != null) {
                String name = entry.getName();
                if (!BundleRules.isSafeEntryName(name)) throw new IOException("Arquivo inválido na tela: " + name);
                File out = new File(target, name);
                if (!out.getCanonicalPath().startsWith(root)) throw new IOException("Arquivo fora da pasta: " + name);
                if (entry.isDirectory()) {
                    //noinspection ResultOfMethodCallIgnored
                    out.mkdirs();
                    continue;
                }
                File parent = out.getParentFile();
                if (parent != null && !parent.isDirectory() && !parent.mkdirs()) throw new IOException("Não foi possível criar " + parent);
                try (OutputStream stream = new FileOutputStream(out)) {
                    int count;
                    while ((count = in.read(buffer)) != -1) stream.write(buffer, 0, count);
                }
            }
        }
    }

    private static HttpURLConnection open(String address) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(address).openConnection();
        connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        // Um portal de Wi-Fi responderia 3xx com uma pagina qualquer: nao segue.
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty("Accept", "application/json, application/zip");
        return connection;
    }

    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) out.append(String.format("%02x", value & 0xff));
        return out.toString();
    }
}
