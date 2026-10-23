package br.financas.app.ui.newentry

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.LaunchedEffect
import androidx.lifecycle.ViewModelProvider
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.theme.FinancasTheme

/**
 * O "+ Novo" nativo (mobile-docs/native/screens/01-novo.md): uma janela transparente por cima da
 * WebView, com o sheet do Compose. Aberta por NativeScreens.open({ screen: "new-entry" }).
 *
 * Ao gravar (ou guardar na fila) avisa a WebView (NativeScreens "dataChanged"), que relê a fila,
 * atualiza os dados e mostra o toast; sem WebView para ouvir, o aviso e um Toast do Android.
 */
class NewEntryActivity : ComponentActivity() {

    private lateinit var viewModel: NewEntryViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        viewModel = ViewModelProvider(this)[NewEntryViewModel::class.java]
        viewModel.start(intent.getStringExtra(EXTRA_TYPE), intent.getStringExtra(EXTRA_CLIENT_ID))
        setContent {
            FinancasTheme {
                val notice = viewModel.finished
                LaunchedEffect(notice) {
                    if (notice != null) finishWith(notice)
                }
                LaunchedEffect(viewModel.sessionExpired) {
                    // 401: a WebView relê os dados, recebe o 401 e mostra o login.
                    if (viewModel.sessionExpired) NativeScreensPlugin.emitDataChanged()
                }
                NewEntryScreen(
                    viewModel = viewModel,
                    onClose = { finish() },
                    onNavigate = { route ->
                        NativeScreensPlugin.emitNavigate(route)
                        finish()
                    },
                )
            }
        }
    }

    private fun finishWith(notice: EntryNotice) {
        val delivered = NativeScreensPlugin.emitDataChanged(notice.message, notice.tone, notice.durationMs)
        if (!delivered) {
            val length = if (notice.durationMs > EntryNotice.DEFAULT_DURATION_MS) Toast.LENGTH_LONG else Toast.LENGTH_SHORT
            Toast.makeText(applicationContext, notice.message, length).show()
        }
        finish()
    }

    override fun finish() {
        super.finish()
        // O sheet ja animou a saida; sem a transicao da janela.
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    companion object {
        const val EXTRA_TYPE = "br.financas.app.newentry.TYPE"
        const val EXTRA_CLIENT_ID = "br.financas.app.newentry.CLIENT_ID"

        /** [type]: EXPENSE | INCOME | TRANSFER | CARD (vazio = Despesa); [clientId]: item da fila a corrigir. */
        fun intent(context: Context, type: String?, clientId: String?): Intent =
            Intent(context, NewEntryActivity::class.java)
                .putExtra(EXTRA_TYPE, type.orEmpty())
                .putExtra(EXTRA_CLIENT_ID, clientId.orEmpty())
    }
}
