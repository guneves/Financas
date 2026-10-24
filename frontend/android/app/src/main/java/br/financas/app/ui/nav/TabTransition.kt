package br.financas.app.ui.nav

import android.app.Activity
import br.financas.app.R

/**
 * A troca de aba da barra de baixo entre o Inicio nativo (NativeActivity) e as telas da WebView.
 * Para o Android isso e abrir ou fechar uma Activity, e a animacao padrao e a de empilhar (entra
 * pela direita) ou voltar (sai para a direita) — o contrario do lado da aba: ir do Inicio para
 * Lancamentos parecia "voltar", e da WebView para o Inicio parecia "avancar". Aba nao e pilha,
 * entao as duas trocam por um fade curto, sem direcao, que tambem cobre a WebView redesenhando a
 * rota nova por baixo. Chamar logo depois do startActivity() ou do finish().
 */
@Suppress("DEPRECATION")
fun Activity.tabTransition() {
    overridePendingTransition(R.anim.tab_fade_in, R.anim.tab_fade_out)
}
