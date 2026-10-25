package br.financas.app.notify;

import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.InstallSourceInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;

import br.financas.app.BuildConfig;
import br.financas.app.JsonOut;

/**
 * Ajustes › Notificações dos bancos (ui/ajustes/): se o acesso as notificacoes esta permitido,
 * o que a captura guardou, exportar (folha de compartilhar do Android, JSON ou texto) e apagar.
 * Os textos nunca vao ao servidor.
 */
public final class NotifyAccess {

    private NotifyAccess() {}

    /** As ultimas capturadas, mais recentes primeiro (tambem o Ajustes nativo, ui/ajustes/). */
    public static JSONArray latestItems(Context context, int limit) {
        JSONArray items = new JSONArray();
        for (NotifyRules.Captured row : NotifyStore.get(context).latest(limit)) {
            JSONObject item = new JSONObject();
            JsonOut.put(item, "dedupKey", row.dedupKey());
            JsonOut.put(item, "package", row.packageName);
            JsonOut.put(item, "app", NotifyRules.labelFor(row.packageName));
            JsonOut.put(item, "postedAt", row.postedAt);
            JsonOut.put(item, "title", row.title);
            JsonOut.put(item, "text", NotifyRules.bestText(row.text, row.bigText));
            JsonOut.put(item, "via", row.via);
            JsonOut.put(item, "groupSummary", row.groupSummary);
            items.put(item);
        }
        return items;
    }

    /** Uma exportacao que nao deu: a mensagem e o que a tela mostra. */
    public static final class ExportException extends Exception {
        ExportException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    /** Grava o arquivo e abre a folha de compartilhar: { count, file } (tambem o Ajustes nativo). */
    public static JSONObject export(Context context, boolean json) throws ExportException {
        List<NotifyRules.Captured> rows = NotifyStore.get(context).all();
        if (rows.isEmpty()) throw new ExportException("Nenhuma notificação capturada ainda.", null);
        long now = System.currentTimeMillis();
        TimeZone zone = TimeZone.getDefault();
        String content = json ? NotifyRules.toJson(rows, now, zone) : NotifyRules.toText(rows, now, zone);
        SimpleDateFormat stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT);
        String name = "notificacoes-" + stamp.format(new Date(now)) + (json ? ".json" : ".txt");
        File file;
        try {
            file = writeExport(context, name, content);
        } catch (IOException error) {
            throw new ExportException("Não foi possível gravar a exportação.", error);
        }
        Uri uri = FileProvider.getUriForFile(context, context.getPackageName() + ".fileprovider", file);
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType(json ? "application/json" : "text/plain");
        send.putExtra(Intent.EXTRA_STREAM, uri);
        send.putExtra(Intent.EXTRA_SUBJECT, "Notificações capturadas (" + rows.size() + ")");
        send.setClipData(ClipData.newRawUri(name, uri));
        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        Intent chooser = Intent.createChooser(send, "Exportar notificações");
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(chooser);
        } catch (ActivityNotFoundException error) {
            throw new ExportException("Nenhum app para receber o arquivo.", null);
        }
        JSONObject result = new JSONObject();
        JsonOut.put(result, "count", rows.size());
        JsonOut.put(result, "file", name);
        return result;
    }

    /** Apaga as capturas e a ultima exportacao; devolve o estado novo. */
    public static JSONObject clear(Context context) {
        NotifyStore.get(context).clear();
        clearExports(context);
        return status(context);
    }
    public static void openAccessSettings(Context context) {
        Intent intent;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            intent = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS);
            intent.putExtra(Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME,
                new ComponentName(context, BankNotificationListener.class).flattenToString());
        } else {
            intent = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
        }
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            context.startActivity(intent);
        } catch (ActivityNotFoundException error) {
            // Algumas versoes nao tem a pagina do app: a lista de apps com acesso.
            context.startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        }
    }
    public static void openAppDetails(Context context) {
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + context.getPackageName()));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
    }

    /** O estado que a web le em status(): tambem o Ajustes nativo (ui/ajustes/). */
    public static JSONObject status(Context context) {
        JSONObject result = new JSONObject();
        JsonOut.put(result, "granted", NotificationManagerCompat.getEnabledListenerPackages(context).contains(context.getPackageName()));
        JsonOut.put(result, "captureOn", NotifySettings.isCaptureOn(context));
        JsonOut.put(result, "captureSince", NotifySettings.captureSince(context));
        JsonOut.put(result, "connectedAt", NotifySettings.connectedAt(context));
        JsonOut.put(result, "disconnectedAt", NotifySettings.disconnectedAt(context));
        JsonOut.put(result, "acceptsShell", BuildConfig.DEBUG);
        JsonOut.put(result, "sdk", Build.VERSION.SDK_INT);
        JsonOut.put(result, "installer", installer(context));

        NotifyStore store = NotifyStore.get(context);
        Map<String, long[]> counts = store.countsByPackage();
        PackageManager manager = context.getPackageManager();
        JSONArray apps = new JSONArray();
        for (NotifyRules.App app : NotifyRules.APPS) {
            apps.put(appEntry(app.packageName, app.label, isInstalled(manager, app.packageName), counts.remove(app.packageName)));
        }
        // O que sobrou na tabela e de fora da lista de hoje (o shell do adb, num build debug).
        for (Map.Entry<String, long[]> other : counts.entrySet()) {
            apps.put(appEntry(other.getKey(), NotifyRules.labelFor(other.getKey()), true, other.getValue()));
        }
        JsonOut.put(result, "apps", apps);
        JsonOut.put(result, "total", store.total());
        return result;
    }

    private static JSONObject appEntry(String packageName, String label, boolean installed, long[] count) {
        JSONObject entry = new JSONObject();
        JsonOut.put(entry, "package", packageName);
        JsonOut.put(entry, "label", label);
        JsonOut.put(entry, "installed", installed);
        JsonOut.put(entry, "count", count == null ? 0 : count[0]);
        JsonOut.put(entry, "lastPostedAt", count == null ? 0 : count[1]);
        return entry;
    }

    /** Precisa do <queries> do manifesto (Android 11+): sem ele todo app parece ausente. */
    private static boolean isInstalled(PackageManager manager, String packageName) {
        try {
            manager.getPackageInfo(packageName, 0);
            return true;
        } catch (PackageManager.NameNotFoundException error) {
            return false;
        }
    }

    /** Quem instalou este APK: e o que decide se o Android 13+ trava o acesso. */
    @SuppressWarnings("deprecation")
    private static String installer(Context context) {
        PackageManager manager = context.getPackageManager();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                InstallSourceInfo info = manager.getInstallSourceInfo(context.getPackageName());
                String initiating = info.getInitiatingPackageName();
                return initiating != null ? initiating : info.getInstallingPackageName();
            }
            return manager.getInstallerPackageName(context.getPackageName());
        } catch (PackageManager.NameNotFoundException | RuntimeException error) {
            return null;
        }
    }

    private static File writeExport(Context context, String name, String content) throws IOException {
        File dir = exportDir(context);
        if (!dir.isDirectory() && !dir.mkdirs()) throw new IOException("Não foi possível criar a pasta da exportação.");
        clearExports(context);
        File file = new File(dir, name);
        try (OutputStream out = new FileOutputStream(file)) {
            out.write(content.getBytes(StandardCharsets.UTF_8));
        }
        return file;
    }

    /** Uma exportacao por vez no cache: a anterior sai quando outra e gravada ou ao apagar. */
    private static void clearExports(Context context) {
        File[] files = exportDir(context).listFiles();
        if (files != null) for (File file : files) file.delete();
    }

    private static File exportDir(Context context) {
        return new File(context.getCacheDir(), "notify");
    }
}
