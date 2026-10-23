package br.financas.app.ui.nav

import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import br.financas.app.MainActivity
import br.financas.app.ui.inbox.InboxNotifier
import br.financas.app.ui.inbox.InboxScreen
import br.financas.app.ui.inbox.InboxViewModel
import br.financas.app.ui.theme.FinancasTheme
import br.financas.app.ui.theme.ShellPrefs

/** As rotas das paginas nativas (o NavHost de [NativeActivity]). */
object NativeRoutes {
    /** Lancamentos › Aprovar (ui/inbox/). */
    const val INBOX = "inbox"

    val ALL: List<String> = listOf(INBOX)

    /** A rota pedida, se este APK a tem; senao a primeira. */
    fun known(route: String?): String = if (route != null && route in ALL) route else INBOX
}

/**
 * As paginas nativas (architecture.md, "Native and WebView side by side"): uma Activity com um
 * NavHost do Compose, para que andar entre paginas nativas nao passe pela WebView. Aberta pela
 * WebView (NativeScreens.open) ou pela notificacao "Novo para aprovar" (ui/inbox/InboxNotifier),
 * que leva o item a mostrar. Voltar da primeira pagina volta para a WebView; aberta pela
 * notificacao sem o app aberto, abre a WebView por baixo antes de sair.
 */
class NativeActivity : ComponentActivity() {

    /** O item que a notificacao pediu (Aprovar rola ate ele); null depois de usado. */
    private var focusItem by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        val dark = ShellPrefs.dark(this)
            ?: ((resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES)
        val bars = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
        enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
        super.onCreate(savedInstanceState)
        val start = NativeRoutes.known(intent.getStringExtra(EXTRA_ROUTE))
        if (savedInstanceState == null) focusItem = intent.getStringExtra(EXTRA_ITEM)?.takeIf { it.isNotEmpty() }
        // Registrado antes do NavHost: o voltar do NavHost (com pagina anterior) vem primeiro.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = leave()
        })
        setContent {
            FinancasTheme {
                NativeNavHost(
                    start = start,
                    focusItem = focusItem,
                    onFocusConsumed = { focusItem = null },
                    onLeave = ::leave,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.getStringExtra(EXTRA_ITEM)?.takeIf { it.isNotEmpty() }?.let { focusItem = it }
    }

    override fun onResume() {
        super.onResume()
        // Aprovar esta aberta: o "Novo para aprovar" ja foi visto.
        InboxNotifier.cancel(this)
    }

    private fun leave() {
        if (isTaskRoot) {
            // Aberta pela notificacao com o app fechado: a WebView fica no lugar.
            startActivity(Intent(this, MainActivity::class.java))
        }
        finish()
    }

    companion object {
        const val EXTRA_ROUTE = "br.financas.app.nav.ROUTE"
        const val EXTRA_ITEM = "br.financas.app.nav.ITEM"

        /** [route]: uma de [NativeRoutes]; [itemId]: o item de Aprovar a mostrar (da notificacao). */
        @JvmStatic
        @JvmOverloads
        fun intent(context: Context, route: String, itemId: String? = null): Intent =
            Intent(context, NativeActivity::class.java)
                .putExtra(EXTRA_ROUTE, route)
                .putExtra(EXTRA_ITEM, itemId.orEmpty())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
    }
}

/** O NavHost das paginas nativas. Cada pagina nova entra aqui como uma rota de [NativeRoutes]. */
@Composable
private fun NativeNavHost(
    start: String,
    focusItem: String?,
    onFocusConsumed: () -> Unit,
    onLeave: () -> Unit,
) {
    val nav = rememberNavController()
    val back: () -> Unit = {
        if (nav.previousBackStackEntry != null) nav.popBackStack() else onLeave()
    }
    NavHost(navController = nav, startDestination = start) {
        composable(NativeRoutes.INBOX) {
            val inbox: InboxViewModel = viewModel()
            LaunchedEffect(focusItem) {
                if (focusItem != null) {
                    inbox.focus(focusItem)
                    onFocusConsumed()
                }
            }
            InboxScreen(viewModel = inbox, onBack = back)
        }
    }
}
