package br.financas.app.ui.inbox

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import br.financas.app.R
import br.financas.app.rules.InboxRules
import br.financas.app.ui.nav.NativeActivity
import br.financas.app.ui.nav.NativeRoutes
import org.json.JSONObject

/**
 * "Novo para aprovar": a notificacao local que o envio das deteccoes (notify/DetectionSender) poe
 * quando o servidor diz que uma virou item novo ou entrou num item (new / merged). O toque abre
 * Aprovar nativo direto no item, So os campos lidos vao ao servidor;
 * esta notificacao e local e nao mostra texto de banco nenhum.
 */
object InboxNotifier {

    private const val CHANNEL_ID = "financas_inbox"
    private const val NOTIFICATION_ID = 4020
    private const val REQUEST_CODE = 4020

    /** Aprovar esta na frente: nada de notificacao (a lista se rele sozinha em ate 20 s). */
    @Volatile
    @JvmField
    var screenVisible: Boolean = false

    /**
     * Os itens que chegaram para aprovar na resposta de POST /api/inbox/detections
     * ({results: [{status, item_id}]}): status "new" ou "merged", na ordem. Puro (testado).
     */
    @JvmStatic
    fun newItemIds(body: String?): List<String> {
        if (body.isNullOrBlank()) return emptyList()
        val results = try {
            JSONObject(body).optJSONArray("results")
        } catch (error: Exception) {
            null
        } ?: return emptyList()
        val ids = mutableListOf<String>()
        for (index in 0 until results.length()) {
            val result = results.optJSONObject(index) ?: continue
            val status = result.optString("status", "")
            val itemId = if (result.isNull("item_id")) "" else result.optString("item_id", "")
            if ((status == "new" || status == "merged") && itemId.isNotEmpty() && itemId !in ids) ids.add(itemId)
        }
        return ids
    }

    /** Mostra (ou troca) a notificacao para [itemIds]; o toque abre o ultimo. */
    @JvmStatic
    fun show(context: Context, itemIds: List<String>) {
        if (itemIds.isEmpty() || screenVisible) return
        val app = context.applicationContext
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(app, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(CHANNEL_ID, app.getString(R.string.inbox_notify_channel), NotificationManager.IMPORTANCE_DEFAULT)
            channel.description = app.getString(R.string.inbox_notify_channel_description)
            app.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
        val open = NativeActivity.intent(app, NativeRoutes.INBOX, itemIds.last())
        val tap = PendingIntent.getActivity(app, REQUEST_CODE, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val text = InboxRules.pendingNoticeText(itemIds.size)
        val builder = NotificationCompat.Builder(app, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_financas)
            .setContentTitle(app.getString(R.string.inbox_notify_title))
            .setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setContentIntent(tap)
            .setAutoCancel(true)
        try {
            NotificationManagerCompat.from(app).notify(NOTIFICATION_ID, builder.build())
        } catch (ignored: SecurityException) {
            // Permissao retirada entre a checagem e o aviso.
        }
    }

    /** Aprovar abriu: a notificacao ja nao tem o que dizer. */
    @JvmStatic
    fun cancel(context: Context) {
        NotificationManagerCompat.from(context.applicationContext).cancel(NOTIFICATION_ID)
    }
}
