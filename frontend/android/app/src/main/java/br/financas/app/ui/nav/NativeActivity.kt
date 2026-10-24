package br.financas.app.ui.nav

import android.content.Context
import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
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
import br.financas.app.ui.cartoes.CartoesScreen
import br.financas.app.ui.cartoes.CartoesViewModel
import br.financas.app.ui.extrato.ExtratoScreen
import br.financas.app.ui.extrato.ExtratoViewModel
import br.financas.app.ui.lancamentos.LancamentosTab
import br.financas.app.ui.home.HomeScreen
import br.financas.app.ui.home.HomeViewModel
import br.financas.app.ui.newentry.NewEntryActivity
import br.financas.app.ui.inbox.InboxNotifier
import br.financas.app.ui.inbox.InboxScreen
import br.financas.app.ui.inbox.InboxViewModel
import br.financas.app.ui.theme.FinancasTheme
import br.financas.app.ui.theme.ShellPrefs

/** As rotas das paginas nativas (o NavHost de [NativeActivity]). */
object NativeRoutes {
    /** Lancamentos › Aprovar (ui/inbox/). */
    const val INBOX = "inbox"

    /** Inicio e o sino (ui/home/): a tela de partida; voltar nela minimiza o app. */
    const val HOME = "home"

    /** Lancamentos › Extrato, as duas vistas (ui/extrato/). */
    const val EXTRATO = "extrato"

    /** Lancamentos › Cartoes (ui/cartoes/). */
    const val CARTOES = "cartoes"

    val ALL: List<String> = listOf(INBOX, HOME, EXTRATO, CARTOES)

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

    /** Uma rota pedida com a Activity ja aberta (onNewIntent); null depois de usada. */
    private var routeRequest by mutableStateOf<String?>(null)

    /** A vista do Extrato pedida pela web (?ver=); null depois de usada. */
    private var viewRequest by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        val dark = ShellPrefs.dark(this)
            ?: ((resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES)
        val bars = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
        enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
        super.onCreate(savedInstanceState)
        val start = NativeRoutes.known(intent.getStringExtra(EXTRA_ROUTE))
        if (savedInstanceState == null) {
            focusItem = intent.getStringExtra(EXTRA_ITEM)?.takeIf { it.isNotEmpty() }
            viewRequest = intent.getStringExtra(EXTRA_VIEW)?.takeIf { it.isNotEmpty() }
        }
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
                    routeRequest = routeRequest,
                    onRouteConsumed = { routeRequest = null },
                    onLeave = ::leave,
                    onOpenWeb = ::leaveTo,
                    onNewEntry = ::openNewEntry,
                    onMinimize = { moveTaskToBack(true) },
                    onRouteShown = ::onRouteShown,
                    viewRequest = viewRequest,
                    onViewConsumed = { viewRequest = null },
                    onNewCardPurchase = ::openNewCardPurchase,
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.getStringExtra(EXTRA_ROUTE)?.takeIf { it in NativeRoutes.ALL }?.let { routeRequest = it }
        intent.getStringExtra(EXTRA_ITEM)?.takeIf { it.isNotEmpty() }?.let { focusItem = it }
        intent.getStringExtra(EXTRA_VIEW)?.takeIf { it.isNotEmpty() }?.let { viewRequest = it }
    }

    /** A pagina na frente (para o aviso de Aprovar); null antes da primeira. */
    private var visibleRoute: String? = null

    override fun onResume() {
        super.onResume()
        // Aprovar esta aberta: o "Novo para aprovar" ja foi visto.
        if (visibleRoute == null || visibleRoute == NativeRoutes.INBOX) InboxNotifier.cancel(this)
    }

    private fun onRouteShown(route: String?) {
        visibleRoute = route
        if (route == NativeRoutes.INBOX) InboxNotifier.cancel(this)
    }

    private fun leave() {
        if (isTaskRoot) {
            // Aberta pela notificacao com o app fechado: a WebView fica no lugar.
            startActivity(Intent(this, MainActivity::class.java))
        }
        finish()
    }

    /**
     * Um link para uma tela que ainda e React (architecture.md, "Going back to the WebView"): a
     * WebView abre [route] (evento "navigate") e esta Activity sai da frente. Sem WebView viva,
     * ela abre por baixo e le a rota guardada ao comecar.
     */
    private fun leaveTo(route: String) {
        val delivered = NativeScreensPlugin.emitNavigate(route)
        if (!delivered) {
            // Processo recriado: a WebView ainda nao existe. Ela le a rota ao abrir
            // (NativeScreens.takePendingRoute) em vez de voltar para o Inicio.
            NativeScreensPlugin.savePendingRoute(this, route)
        }
        if (!delivered || isTaskRoot) startActivity(Intent(this, MainActivity::class.java))
        finish()
        // Uma aba da barra (ou um link do Inicio): fade, nao o "voltar" que desliza para a direita.
        tabTransition()
    }

    /** O "+" da barra de baixo: o "+ Novo" nativo por cima (despesa, como na web). */
    private fun openNewEntry() {
        startActivity(NewEntryActivity.intent(this, type = "EXPENSE", clientId = null))
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    /** "Nova compra" de Cartoes: o "+ Novo" ja no cartao. */
    private fun openNewCardPurchase() {
        startActivity(NewEntryActivity.intent(this, type = "CARD", clientId = null))
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    companion object {
        const val EXTRA_ROUTE = "br.financas.app.nav.ROUTE"
        const val EXTRA_ITEM = "br.financas.app.nav.ITEM"
        const val EXTRA_VIEW = "br.financas.app.nav.VIEW"

        /**
         * [route]: uma de [NativeRoutes]; [itemId]: o item de Aprovar a mostrar (da notificacao);
         * [view]: a vista do Extrato (contas | investimentos).
         */
        @JvmStatic
        @JvmOverloads
        fun intent(context: Context, route: String, itemId: String? = null, view: String? = null): Intent =
            Intent(context, NativeActivity::class.java)
                .putExtra(EXTRA_ROUTE, route)
                .putExtra(EXTRA_ITEM, itemId.orEmpty())
                .putExtra(EXTRA_VIEW, view.orEmpty())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
    }
}

/** O NavHost das paginas nativas. Cada pagina nova entra aqui como uma rota de [NativeRoutes]. */
@Composable
private fun NativeNavHost(
    start: String,
    focusItem: String?,
    onFocusConsumed: () -> Unit,
    routeRequest: String?,
    onRouteConsumed: () -> Unit,
    onLeave: () -> Unit,
    onOpenWeb: (String) -> Unit,
    onNewEntry: () -> Unit,
    onMinimize: () -> Unit,
    onRouteShown: (String?) -> Unit,
    viewRequest: String?,
    onViewConsumed: () -> Unit,
    onNewCardPurchase: () -> Unit,
) {
    val nav = rememberNavController()
    // Um link de uma tela nativa: a pagina nativa, se este APK a tem (NativeLinks); senao a WebView.
    val openLink: (String) -> Unit = { route ->
        val target = NativeLinks.targetFor(route)
        if (target == null) {
            onOpenWeb(route)
        } else {
            if (target.view != null) ExtratoPendingView.value = target.view
            nav.navigate(target.route) { launchSingleTop = true }
        }
    }
    // As abas de Lancamentos: trocam de pagina sem empilhar (voltar sai de Lancamentos).
    val openTab: (LancamentosTab) -> Unit = { tab ->
        val route = when (tab) {
            LancamentosTab.EXTRATO -> NativeRoutes.EXTRATO
            LancamentosTab.CARTOES -> NativeRoutes.CARTOES
            LancamentosTab.APROVAR -> NativeRoutes.INBOX
        }
        val current = nav.currentDestination?.route
        nav.navigate(route) {
            launchSingleTop = true
            if (current != null && current != NativeRoutes.HOME) popUpTo(current) { inclusive = true }
        }
    }
    LaunchedEffect(nav) {
        nav.currentBackStackEntryFlow.collect { entry -> onRouteShown(entry.destination.route) }
    }
    val back: () -> Unit = {
        if (nav.previousBackStackEntry != null) nav.popBackStack() else onLeave()
    }
    // A notificacao de Aprovar (ou a WebView) pediu outra pagina com esta aberta: ela entra por cima.
    LaunchedEffect(routeRequest) {
        val route = routeRequest ?: return@LaunchedEffect
        if (nav.currentDestination?.route != route) nav.navigate(route) { launchSingleTop = true }
        onRouteConsumed()
    }
    NavHost(navController = nav, startDestination = start) {
        composable(NativeRoutes.HOME) {
            val home: HomeViewModel = viewModel()
            // Voltar no Inicio sai do app sem mata-lo, como a WebView na tela inicial.
            BackHandler(onBack = onMinimize)
            HomeScreen(
                viewModel = home,
                onOpenWeb = openLink,
                onOpenInbox = { nav.navigate(NativeRoutes.INBOX) { launchSingleTop = true } },
                onNewEntry = onNewEntry,
            )
        }
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
        composable(NativeRoutes.EXTRATO) {
            val extrato: ExtratoViewModel = viewModel()
            LaunchedEffect(viewRequest) {
                val requested = viewRequest ?: ExtratoPendingView.value
                if (requested != null) {
                    extrato.requestView(requested)
                    ExtratoPendingView.value = null
                    onViewConsumed()
                }
            }
            ExtratoScreen(viewModel = extrato, onBack = back, onTab = openTab, onOpenWeb = openLink, onNewEntry = onNewEntry)
        }
        composable(NativeRoutes.CARTOES) {
            val cartoes: CartoesViewModel = viewModel()
            CartoesScreen(viewModel = cartoes, onBack = back, onTab = openTab, onOpenWeb = openLink, onNewPurchase = onNewCardPurchase)
        }
    }
}

/** A vista do Extrato pedida por um link nativo ("/lancamentos/extrato?ver=..."), lida ao abrir. */
internal object ExtratoPendingView {
    var value: String? = null
}
