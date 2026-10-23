package br.financas.app;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;

import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;

import br.financas.app.bundle.BundlePlugin;
import br.financas.app.notify.NotifyPlugin;
import br.financas.app.outbox.OutboxPlugin;
import br.financas.app.ui.nav.NativeScreensPlugin;
import br.financas.app.update.ApkUpdatePlugin;

public class MainActivity extends BridgeActivity {

    private static final int NOTIFICATION_PERMISSION_REQUEST = 1001;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Plugins do proprio app: registrados antes do super, que monta a ponte.
        registerPlugin(OutboxPlugin.class);
        registerPlugin(ShellPlugin.class);
        // Antes da WebView carregar: decide qual tela abrir (a do APK ou a baixada).
        registerPlugin(BundlePlugin.class);
        // O APK novo publicado pelo CI (instalador do Android).
        registerPlugin(ApkUpdatePlugin.class);
        // O leitor de notificacoes dos bancos: acesso, captura, exportacao (Ajustes).
        registerPlugin(NotifyPlugin.class);
        // A ponte para as telas nativas (ui/nav/): rotas nativas, abrir, dataChanged/navigate.
        registerPlugin(NativeScreensPlugin.class);
        super.onCreate(savedInstanceState);

        // Android 13+: sem esta permissao o aviso de "entre de novo" do envio em segundo
        // plano nao aparece. Pedida uma vez; recusada, o app segue sem o aviso.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[] { Manifest.permission.POST_NOTIFICATIONS }, NOTIFICATION_PERMISSION_REQUEST);
        }
    }
}
