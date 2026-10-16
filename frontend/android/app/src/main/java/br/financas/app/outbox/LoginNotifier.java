package br.financas.app.outbox;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

import br.financas.app.MainActivity;
import br.financas.app.R;

/** A notificacao "entre de novo": o envio parou num 401 ou sem login, com itens na fila. */
public final class LoginNotifier {

    private static final String CHANNEL_ID = "financas_outbox";
    private static final int NOTIFICATION_ID = 4010;

    private LoginNotifier() {}

    public static void show(Context context, int pending) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "Envio de lançamentos", NotificationManager.IMPORTANCE_DEFAULT);
            channel.setDescription("Avisa quando lançamentos guardados no aparelho não puderam ser enviados.");
            context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        Intent open = new Intent(context, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent tap = PendingIntent.getActivity(context, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        String text = pending == 1
            ? "1 lançamento aguarda envio. Entre novamente no app para enviá-lo."
            : pending + " lançamentos aguardam envio. Entre novamente no app para enviá-los.";
        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_financas)
            .setContentTitle("Sessão expirada")
            .setContentText(text)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(tap)
            .setAutoCancel(true);
        try {
            NotificationManagerCompat.from(context).notify(NOTIFICATION_ID, builder.build());
        } catch (SecurityException ignored) {
            // Permissao retirada entre a checagem e o aviso.
        }
    }

    public static void cancel(Context context) {
        NotificationManagerCompat.from(context).cancel(NOTIFICATION_ID);
    }
}
