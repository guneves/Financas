package br.financas.app.outbox;

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
 * Envia a fila com o app fechado. So roda com rede (o Android segura o job ate ela
 * voltar); se o servidor nao responde (PC desligado, Tailscale fora), tenta de novo com
 * espera exponencial — 30 s, 1 min, 2 min... ate o teto de 5 h do WorkManager — para nao
 * manter o radio acordado. Sobrevive a reinicio do aparelho (o WorkManager persiste o job).
 */
public final class OutboxWorker extends Worker {

    private static final String UNIQUE_NAME = "financas-outbox-send";

    public OutboxWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    /** Agenda uma rodada se houver pendentes. Um job ja agendado ou rodando basta. */
    public static void schedule(Context context) {
        if (OutboxStore.get(context).countPending() == 0) return;
        OneTimeWorkRequest request = new OneTimeWorkRequest.Builder(OutboxWorker.class)
            .setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build();
        // KEEP: a rodada em curso tambem pega o que entrar na fila enquanto ela roda
        // (OutboxSender repete ate nao sobrar item novo).
        WorkManager.getInstance(context).enqueueUniqueWork(UNIQUE_NAME, ExistingWorkPolicy.KEEP, request);
    }

    @NonNull
    @Override
    public Result doWork() {
        OutboxSender.Summary summary = OutboxSender.run(getApplicationContext(), false);
        if ("offline".equals(summary.stopped)) return Result.retry();
        if ("login".equals(summary.stopped) && summary.kept > 0) {
            // Sem login nao adianta tentar de novo: o proximo setSession agenda outra rodada.
            LoginNotifier.show(getApplicationContext(), summary.kept);
        }
        return Result.success();
    }
}
