package br.financas.app;

import android.graphics.Color;
import android.view.Window;

import androidx.core.view.WindowInsetsControllerCompat;

import com.getcapacitor.JSObject;
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
 *
 * O modo privado (o olho, lib/privacy.js) tambem: setValuesHidden({ hidden }) grava cada troca
 * da web, getValuesHidden() devolve { hidden } (ou {} sem escolha guardada) — o Inicio nativo
 * tem o olho e a web le o que ele deixou ao voltar (lib/nativeApp.js; frontend/native-level.txt
 * 5 em diante). Nunca tire um metodo que a web de um nivel abaixo ainda chama.
 *
 * Ajustes nativo (native-level 7): a Aparência e o "Sair" nativos deixam o pedido aqui, e a web o
 * le ao abrir e ao voltar para a frente (takeThemePreference, takeSignOut).
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
        // As telas nativas abrem no mesmo tema (ui/theme/Theme.kt), e a Aparência nativa mostra a
        // escolha da web (native-level 7; uma web antes dele nao manda `preference`).
        ShellPrefs.saveDark(getContext(), dark);
        String preference = call.getString("preference", null);
        if (preference != null) ShellPrefs.saveThemePreference(getContext(), preference);
        getActivity().runOnUiThread(() -> {
            Window window = getActivity().getWindow();
            window.getDecorView().setBackgroundColor(color);
            WindowInsetsControllerCompat controller = new WindowInsetsControllerCompat(window, window.getDecorView());
            controller.setAppearanceLightStatusBars(!dark);
            controller.setAppearanceLightNavigationBars(!dark);
            call.resolve();
        });
    }

    @PluginMethod
    public void setValuesHidden(PluginCall call) {
        Boolean hidden = call.getBoolean("hidden");
        if (hidden == null) {
            call.reject("Informe hidden.");
            return;
        }
        ShellPrefs.saveValuesHidden(getContext(), hidden);
        call.resolve();
    }

    @PluginMethod
    public void getValuesHidden(PluginCall call) {
        JSObject result = new JSObject();
        Boolean hidden = ShellPrefs.valuesHidden(getContext());
        if (hidden != null) result.put("hidden", hidden.booleanValue());
        call.resolve(result);
    }

    /**
     * A escolha de Aparência feita numa tela nativa que a web ainda nao aplicou: { preference }
     * ("system" | "light" | "dark") ou {} sem nenhuma. Lida e apagada; a web a aplica e manda
     * o setTheme de volta (native-level 7).
     */
    @PluginMethod
    public void takeThemePreference(PluginCall call) {
        JSObject result = new JSObject();
        String pending = ShellPrefs.takePendingTheme(getContext());
        if (pending != null) result.put("preference", pending);
        call.resolve(result);
    }

    /**
     * O "Sair" de Ajustes nativo: { signOut: true } uma vez, e a web apaga o login dela (o APK ja
     * apagou o dele). Lido antes de a web mandar a sessao ao APK (native-level 7).
     */
    @PluginMethod
    public void takeSignOut(PluginCall call) {
        JSObject result = new JSObject();
        result.put("signOut", ShellPrefs.takeSignOut(getContext()));
        call.resolve(result);
    }
}
