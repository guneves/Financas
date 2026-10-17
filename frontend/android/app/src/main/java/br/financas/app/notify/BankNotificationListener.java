package br.financas.app.notify;

import android.app.Notification;
import android.content.ComponentName;
import android.os.Build;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

import br.financas.app.BuildConfig;

/**
 * O leitor de notificacoes dos bancos (mobile-docs/steps-to-production.md, Fase 6). O Android
 * o liga quando o dono permite o acesso as notificacoes e o mantem ligado com o app fechado.
 *
 * So apps da lista (NotifyRules.APPS) passam; o resto e descartado sem ler o texto. Hoje nao ha
 * parser: com a captura desligada o leitor nao guarda nada, e com ela ligada guarda cada
 * notificacao inteira na tabela do aparelho (NotifyStore), para escrever os parsers contra o
 * texto real. Nada sai do aparelho por aqui.
 *
 * Num build debug o shell do adb tambem passa: `adb shell cmd notification post -S bigtext -t
 * "<titulo>" <tag> "<texto>"` testa o caminho inteiro sem uma compra. Num build release, nao.
 */
public class BankNotificationListener extends NotificationListenerService {

    private static final String TAG = "FinancasNotify";

    @Override
    public void onListenerConnected() {
        long now = System.currentTimeMillis();
        NotifySettings.markConnected(this, now);
        NotifyEvents.changed();
        // O que chegou enquanto o leitor estava desligado (APK novo, processo morto) e ainda
        // esta na bandeja. A chave unica impede a segunda linha do que ja foi guardado.
        if (!NotifySettings.isCaptureOn(this)) return;
        long since = NotifySettings.captureSince(this);
        try {
            StatusBarNotification[] active = getActiveNotifications();
            if (active == null) return;
            for (StatusBarNotification sbn : active) {
                if (sbn.getPostTime() >= since) keep(sbn, NotifyRules.VIA_ACTIVE);
            }
        } catch (RuntimeException error) {
            Log.w(TAG, "Nao foi possivel ler a bandeja ao religar", error);
        }
    }

    @Override
    public void onListenerDisconnected() {
        NotifySettings.markDisconnected(this, System.currentTimeMillis());
        NotifyEvents.changed();
        // O acesso continua permitido; pede ao Android para ligar de novo.
        requestRebind(new ComponentName(this, BankNotificationListener.class));
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        keep(sbn, NotifyRules.VIA_POSTED);
    }

    private void keep(StatusBarNotification sbn, String via) {
        String packageName = sbn.getPackageName();
        if (!NotifyRules.isAllowed(packageName, BuildConfig.DEBUG)) {
            // Num build de teste, o nome do pacote (so ele) vai para o logcat: e assim que se
            // descobre de onde vem uma notificacao que nao apareceu na captura.
            if (BuildConfig.DEBUG) Log.d(TAG, "Fora da lista: " + packageName);
            return;
        }
        if (!NotifySettings.isCaptureOn(this)) return;
        try {
            if (NotifyStore.get(this).insert(read(sbn, via))) NotifyEvents.changed();
        } catch (RuntimeException error) {
            Log.w(TAG, "Nao foi possivel guardar a notificacao de " + packageName, error);
        }
    }

    /**
     * A notificacao como chegou: nada aparado, nada reescrito. Bundle.get(String) esta obsoleto,
     * mas e o unico jeito de ler cada extra sem saber o tipo de antemao.
     */
    @SuppressWarnings("deprecation")
    static NotifyRules.Captured read(StatusBarNotification sbn, String via) {
        Notification notification = sbn.getNotification();
        Bundle extras = notification.extras;
        NotifyRules.Captured row = new NotifyRules.Captured();
        row.packageName = sbn.getPackageName();
        row.key = sbn.getKey();
        row.postedAt = sbn.getPostTime();
        row.receivedAt = System.currentTimeMillis();
        row.when = notification.when;
        row.via = via;
        row.channelId = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O ? notification.getChannelId() : null;
        row.category = notification.category;
        row.groupSummary = (notification.flags & Notification.FLAG_GROUP_SUMMARY) != 0;
        row.ongoing = (notification.flags & Notification.FLAG_ONGOING_EVENT) != 0;
        if (extras == null) return row;
        try {
            row.title = text(extras.getCharSequence(Notification.EXTRA_TITLE));
            row.text = text(extras.getCharSequence(Notification.EXTRA_TEXT));
            row.bigText = text(extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
            for (String name : extras.keySet()) {
                Object value;
                try {
                    value = extras.get(name);
                } catch (RuntimeException unreadable) {
                    // Um extra que o app nao consegue abrir (classe de outro app) nao derruba os outros.
                    continue;
                }
                if (value instanceof CharSequence) {
                    row.extras.put(name, value.toString());
                } else if (value instanceof CharSequence[]) {
                    StringBuilder lines = new StringBuilder();
                    for (CharSequence line : (CharSequence[]) value) {
                        if (lines.length() > 0) lines.append('\n');
                        lines.append(line == null ? "" : line.toString());
                    }
                    row.extras.put(name, lines.toString());
                }
            }
        } catch (RuntimeException unreadable) {
            // Extras que nao abrem: a linha fica (pacote, hora, key), com o motivo, para a
            // captura mostrar que a notificacao chegou.
            row.extras.put("financas.unreadable", unreadable.getClass().getName());
        }
        return row;
    }

    private static String text(CharSequence value) {
        return value == null ? null : value.toString();
    }
}
