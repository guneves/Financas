package br.financas.app;

import android.graphics.Color;
import android.view.Window;

import androidx.core.view.WindowInsetsControllerCompat;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import br.financas.app.ui.theme.ShellPrefs;

/**
 * O tema do app (lib/theme.js) nas barras do Android: a faixa atras da barra de status e
 * da barra de gestos ganha o fundo da tela, e os icones ficam claros no tema escuro.
 * O botao de tema do app pode divergir do sistema, entao o tema do Android nao basta.
 * A escolha fica gravada (ShellPrefs) para as telas nativas abrirem no mesmo tema.
 */
@CapacitorPlugin(name = "Shell")
public class ShellPlugin extends Plugin {

    @PluginMethod
    public void setTheme(PluginCall call) {
        boolean dark = Boolean.TRUE.equals(call.getBoolean("dark", false));
        String background = call.getString("background", dark ? "#0B1210" : "#EFF2ED");
        int parsed;
        try {
            parsed = Color.parseColor(background);
        } catch (IllegalArgumentException error) {
            call.reject("Cor inválida: " + background);
            return;
        }
        final int color = parsed;
        // As telas nativas abrem no mesmo tema (ui/theme/Theme.kt).
        ShellPrefs.saveDark(getContext(), dark);
        getActivity().runOnUiThread(() -> {
            Window window = getActivity().getWindow();
            window.getDecorView().setBackgroundColor(color);
            WindowInsetsControllerCompat controller = new WindowInsetsControllerCompat(window, window.getDecorView());
            controller.setAppearanceLightStatusBars(!dark);
            controller.setAppearanceLightNavigationBars(!dark);
            call.resolve();
        });
    }
}
