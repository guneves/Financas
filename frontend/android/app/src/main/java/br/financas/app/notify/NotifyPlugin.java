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

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

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

/**
 * Ajustes › Notificações dos bancos (lib/notifyCapture.js): se o acesso as notificacoes esta
 * permitido, ligar e desligar a captura, ver o que ela guardou, exportar (folha de
 * compartilhar do Android, JSON ou texto) e apagar. Os textos nunca vao ao servidor.
 */
@CapacitorPlugin(name = "Notify")
public class NotifyPlugin extends Plugin {

    private static final int LATEST_DEFAULT = 20;
    private static final int LATEST_MAX = 200;

    @Override
    public void load() {
        NotifyEvents.setListener(() -> notifyListeners("changed", new JSObject()));
    }

    @Override
    protected void handleOnDestroy() {
        NotifyEvents.setListener(null);
    }

    @PluginMethod
    public void status(PluginCall call) {
        call.resolve(status(getContext()));
    }

    @PluginMethod
    public void setCapture(PluginCall call) {
        Boolean on = call.getBoolean("on");
        if (on == null) {
            call.reject("Informe on.");
            return;
        }
        NotifySettings.setCapture(getContext(), on, System.currentTimeMillis());
        call.resolve(status(getContext()));
    }

    /** As ultimas capturadas, mais recentes primeiro, para conferir na tela. */
    @PluginMethod
    public void latest(PluginCall call) {
        int limit = Math.max(1, Math.min(LATEST_MAX, call.getInt("limit", LATEST_DEFAULT)));
        JSArray items = new JSArray();
        for (NotifyRules.Captured row : NotifyStore.get(getContext()).latest(limit)) {
            JSObject item = new JSObject();
            item.put("dedupKey", row.dedupKey());
            item.put("package", row.packageName);
            item.put("app", NotifyRules.labelFor(row.packageName));
            item.put("postedAt", row.postedAt);
            item.put("title", row.title);
            item.put("text", NotifyRules.bestText(row.text, row.bigText));
            item.put("via", row.via);
            item.put("groupSummary", row.groupSummary);
            items.put(item);
        }
        JSObject result = new JSObject();
        result.put("items", items);
        call.resolve(result);
    }

    /** Grava o arquivo no cache do app e abre a folha de compartilhar. */
    @PluginMethod
    public void export(PluginCall call) {
        boolean json = !"text".equals(call.getString("format", "json"));
        Context context = getContext();
        List<NotifyRules.Captured> rows = NotifyStore.get(context).all();
        if (rows.isEmpty()) {
            call.reject("Nenhuma notificação capturada ainda.");
            return;
        }
        long now = System.currentTimeMillis();
        TimeZone zone = TimeZone.getDefault();
        String content = json ? NotifyRules.toJson(rows, now, zone) : NotifyRules.toText(rows, now, zone);
        SimpleDateFormat stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.ROOT);
        String name = "notificacoes-" + stamp.format(new Date(now)) + (json ? ".json" : ".txt");
        File file;
        try {
            file = writeExport(context, name, content);
        } catch (IOException error) {
            call.reject("Não foi possível gravar a exportação.", error);
            return;
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
            call.reject("Nenhum app para receber o arquivo.");
            return;
        }
        JSObject result = new JSObject();
        result.put("count", rows.size());
        result.put("file", name);
        call.resolve(result);
    }

    @PluginMethod
    public void clear(PluginCall call) {
        NotifyStore.get(getContext()).clear();
        clearExports(getContext());
        call.resolve(status(getContext()));
    }

    /** A pagina do Android que liga o acesso as notificacoes, direto no app quando da. */
    @PluginMethod
    public void openAccessSettings(PluginCall call) {
        Context context = getContext();
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
        call.resolve();
    }

    /** Informações do app: o menu ⋮ dela tem "Permitir configurações restritas". */
    @PluginMethod
    public void openAppDetails(PluginCall call) {
        Context context = getContext();
        Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + context.getPackageName()));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(intent);
        call.resolve();
    }

    static JSObject status(Context context) {
        JSObject result = new JSObject();
        result.put("granted", NotificationManagerCompat.getEnabledListenerPackages(context).contains(context.getPackageName()));
        result.put("captureOn", NotifySettings.isCaptureOn(context));
        result.put("captureSince", NotifySettings.captureSince(context));
        result.put("connectedAt", NotifySettings.connectedAt(context));
        result.put("disconnectedAt", NotifySettings.disconnectedAt(context));
        result.put("acceptsShell", BuildConfig.DEBUG);
        result.put("sdk", Build.VERSION.SDK_INT);
        result.put("installer", installer(context));

        NotifyStore store = NotifyStore.get(context);
        Map<String, long[]> counts = store.countsByPackage();
        PackageManager manager = context.getPackageManager();
        JSArray apps = new JSArray();
        for (NotifyRules.App app : NotifyRules.APPS) {
            apps.put(appEntry(app.packageName, app.label, isInstalled(manager, app.packageName), counts.remove(app.packageName)));
        }
        // O que sobrou na tabela e de fora da lista de hoje (o shell do adb, num build debug).
        for (Map.Entry<String, long[]> other : counts.entrySet()) {
            apps.put(appEntry(other.getKey(), NotifyRules.labelFor(other.getKey()), true, other.getValue()));
        }
        result.put("apps", apps);
        result.put("total", store.total());
        return result;
    }

    private static JSObject appEntry(String packageName, String label, boolean installed, long[] count) {
        JSObject entry = new JSObject();
        entry.put("package", packageName);
        entry.put("label", label);
        entry.put("installed", installed);
        entry.put("count", count == null ? 0 : count[0]);
        entry.put("lastPostedAt", count == null ? 0 : count[1]);
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
