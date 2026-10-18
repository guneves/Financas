package br.financas.app.notify;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.BackoffPolicy;
import androidx.work.Constraints;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import java.util.concurrent.TimeUnit;

/**
 * Manda as deteccoes para o Aprovar com o app fechado, como OutboxWorker faz com a fila de
 * lancamentos: so com rede, espera exponencial quando o servidor nao responde, e sobrevive a
 * reinicio do aparelho.
 */
public final class DetectionWorker extends Worker {

    private static final String UNIQUE_NAME = "financas-notify-detections";

    public DetectionWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    /** Agenda uma rodada se houver deteccoes na fila. */
    public static void schedule(Context context) {
        if (DetectionQueue.get(context).count() == 0) return;
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(DetectionWorker.class)
            .setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build();
        // APPEND_OR_REPLACE: uma deteccao que chega durante a rodada ganha outra rodada depois.
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request);
    }

    @NonNull
    @Override
    public Result doWork() {
        String stopped = DetectionSender.run(getApplicationContext());
        if ("offline".equals(stopped)) return Result.retry();
        // "login": o proximo setSession agenda outra rodada.
        return Result.success();
    }
}
