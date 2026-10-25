package br.financas.app.ui.nav

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import br.financas.app.R
import br.financas.app.data.AppGraph
import br.financas.app.outbox.Outbox
import br.financas.app.outbox.Session
import br.financas.app.ui.ajustes.AjustesScreen
import br.financas.app.ui.ajustes.AjustesViewModel
import br.financas.app.ui.areceber.AReceberScreen
import br.financas.app.ui.areceber.AReceberViewModel
import br.financas.app.ui.cartoes.CartoesScreen
import br.financas.app.ui.components.LocalShellChrome
import br.financas.app.ui.components.ShellChrome
import br.financas.app.ui.cartoes.CartoesViewModel
import br.financas.app.ui.extrato.ExtratoScreen
import br.financas.app.ui.extrato.ExtratoViewModel
import br.financas.app.ui.home.HomeScreen
import br.financas.app.ui.home.HomeViewModel
import br.financas.app.ui.inbox.InboxNotifier
import br.financas.app.ui.inbox.InboxScreen
import br.financas.app.ui.inbox.InboxViewModel
import br.financas.app.ui.investimentos.AlocacaoScreen
import br.financas.app.ui.investimentos.AlocacaoViewModel
import br.financas.app.ui.investimentos.CalculadoraScreen
import br.financas.app.ui.investimentos.CalculadoraViewModel
import br.financas.app.ui.investimentos.InvestimentosTab
import br.financas.app.ui.investimentos.IrScreen
import br.financas.app.ui.investimentos.IrViewModel
import br.financas.app.ui.investimentos.OperacoesScreen
import br.financas.app.ui.investimentos.OperacoesViewModel
import br.financas.app.ui.investimentos.PosicaoScreen
import br.financas.app.ui.investimentos.PosicaoViewModel
import br.financas.app.ui.investimentos.ProventosScreen
import br.financas.app.ui.investimentos.ProventosViewModel
import br.financas.app.ui.investimentos.RentabilidadeScreen
import br.financas.app.ui.investimentos.RentabilidadeViewModel
import br.financas.app.ui.lancamentos.LancamentosTab
import br.financas.app.ui.login.LoginScreen
import br.financas.app.ui.login.LoginViewModel
import br.financas.app.ui.metas.MetasScreen
import br.financas.app.ui.metas.MetasViewModel
import br.financas.app.ui.newentry.NewEntryActivity
import br.financas.app.ui.orcamento.OrcamentoScreen
import br.financas.app.ui.orcamento.OrcamentoViewModel
import br.financas.app.ui.planejar.PlanejarTab
import br.financas.app.ui.recorrentes.RecorrentesScreen
import br.financas.app.ui.recorrentes.RecorrentesViewModel
import br.financas.app.ui.theme.FinancasTheme
import br.financas.app.ui.theme.LocalPalette
import br.financas.app.ui.theme.ShellPrefs

/** As rotas do NavHost da casca. */
object NativeRoutes {
    /** Entrar (ui/login/): a primeira pagina sem sessao, e para onde um 401 leva. */
    const val LOGIN = "login"

    /** Lancamentos › Aprovar (ui/inbox/). */
    const val INBOX = "inbox"

    /** Inicio e o sino (ui/home/): a pagina de partida; voltar nela manda o app para o fundo. */
    const val HOME = "home"

    /** Lancamentos › Extrato, as duas vistas (ui/extrato/). */
    const val EXTRATO = "extrato"

    /** Lancamentos › Cartoes (ui/cartoes/). */
    const val CARTOES = "cartoes"

    /** Lancamentos › A receber (ui/areceber/). */
    const val A_RECEBER = "a-receber"

    /** Planejar › Orcamento, Recorrentes e Metas (ui/orcamento/, ui/recorrentes/, ui/metas/). */
    const val ORCAMENTO = "orcamento"
    const val RECORRENTES = "recorrentes"
    const val METAS = "metas"

    /** Ajustes (ui/ajustes/): a lista de secoes; a secao pedida abre por cima. */
    const val AJUSTES = "ajustes"

    /** Investimentos (ui/investimentos/): uma pagina por aba. */
    const val POSICAO = "posicao"
    const val OPERACOES = "operacoes"
    const val PROVENTOS = "proventos"
    const val RENTABILIDADE = "rentabilidade"
    const val ALOCACAO = "alocacao"
    const val IR = "ir"
    const val CALCULADORA = "calculadora"

    /** As sete abas de Investimentos, na ordem de lib/navigation.js. */
    val INVESTMENTS: List<String> = listOf(POSICAO, OPERACOES, PROVENTOS, RENTABILIDADE, ALOCACAO, IR, CALCULADORA)

    /** As paginas com sessao (o login fica de fora: nenhuma intent abre direto nele). */
    val ALL: List<String> = listOf(INBOX, HOME, EXTRATO, CARTOES, A_RECEBER, ORCAMENTO, RECORRENTES, METAS, AJUSTES) + INVESTMENTS
}

/**
 * O app (00-shell.md): a casca nativa. Sem sessao abre no login; com ela, no Inicio. Em volta de
 * todas as paginas: a barra de baixo (as quatro secoes e Ajustes), o "+" do "+ Novo", a folha
 * Pendentes e o aviso do APK novo. Um 401 apaga a sessao (AppGraph) e volta ao login. Aberta pelo
 * icone (o alias .MainActivity) e pelas notificacoes (Aprovar: a pagina e o item a mostrar).
 */
class NativeActivity : ComponentActivity() {

    /** O item que a notificacao pediu (Aprovar rola ate ele); null depois de usado. */
    private var focusItem by mutableStateOf<String?>(null)

    /** Uma pagina pedida por uma intent (a notificacao de Aprovar); null depois de usada. */
    private var routeRequest by mutableStateOf<String?>(null)

    /** A vista do Extrato (ou a secao de Ajustes) pedida junto; null depois de usada. */
    private var viewRequest by mutableStateOf<String?>(null)

    /** A pagina na frente (para o aviso de Aprovar); null antes da primeira. */
    private var visibleRoute: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        val systemDark = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        val dark = ShellPrefs.isDark(this, systemDark)
        val bars = if (dark) SystemBarStyle.dark(Color.TRANSPARENT) else SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT)
        enableEdgeToEdge(statusBarStyle = bars, navigationBarStyle = bars)
        super.onCreate(savedInstanceState)
        // Pendentes de uma sessao anterior (o app foi atualizado ou morto no meio).
        Outbox.resume(this)
        askNotificationPermission()
        val signedIn = Session.load(this) != null
        if (savedInstanceState == null) {
            routeRequest = intent.getStringExtra(EXTRA_ROUTE)?.takeIf { it in NativeRoutes.ALL && it != NativeRoutes.HOME }
            focusItem = intent.getStringExtra(EXTRA_ITEM)?.takeIf { it.isNotEmpty() }
            viewRequest = intent.getStringExtra(EXTRA_VIEW)?.takeIf { it.isNotEmpty() }
        }
        setContent {
            FinancasTheme(dark = dark) {
                AppShell(
                    start = if (signedIn) NativeRoutes.HOME else NativeRoutes.LOGIN,
                    focusItem = focusItem,
                    onFocusConsumed = { focusItem = null },
                    routeRequest = routeRequest,
                    onRouteConsumed = { routeRequest = null },
                    viewRequest = viewRequest,
                    onViewConsumed = { viewRequest = null },
                    onRouteShown = ::onRouteShown,
                    onMinimize = { moveTaskToBack(true) },
                    onNewEntry = ::openNewEntry,
                    onFixPending = ::openPendingFix,
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

    override fun onResume() {
        super.onResume()
        // Aprovar esta aberta: o "Novo para aprovar" ja foi visto.
        if (visibleRoute == NativeRoutes.INBOX) InboxNotifier.cancel(this)
    }

    private fun onRouteShown(route: String?) {
        visibleRoute = route
        if (route == NativeRoutes.INBOX) InboxNotifier.cancel(this)
    }

    // Android 13+: sem esta permissao os avisos (Aprovar, "Sessão expirada") nao aparecem. Pedida
    // uma vez; recusada, o app segue sem eles.
    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), NOTIFICATION_PERMISSION_REQUEST)
        }
    }

    /** O "+": o "+ Novo" nativo por cima ([type] CARD em Cartões; senao Despesa, como na web). */
    private fun openNewEntry(type: String) {
        startActivity(NewEntryActivity.intent(this, type = type, clientId = null))
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    /** Pendentes › Corrigir: o "+ Novo" com o item da fila. */
    private fun openPendingFix(clientId: String) {
        startActivity(NewEntryActivity.intent(this, type = null, clientId = clientId))
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    companion object {
        const val EXTRA_ROUTE = "br.financas.app.nav.ROUTE"
        const val EXTRA_ITEM = "br.financas.app.nav.ITEM"
        const val EXTRA_VIEW = "br.financas.app.nav.VIEW"
        private const val NOTIFICATION_PERMISSION_REQUEST = 1001

        /**
         * [route]: uma de [NativeRoutes]; [itemId]: o item de Aprovar a mostrar (da notificacao);
         * [view]: a vista do Extrato (contas | investimentos) ou a secao de Ajustes.
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

/**
 * Uma pagina do NavHost a partir da casca, sem empilhar (a atual sai da pilha; o Inicio fica). A
 * que sai guarda o estado (ViewModel, dados, rolagem) e a que volta o recupera: trocar de aba nao
 * recarrega a pagina nem a leva de volta ao topo.
 */
private fun NavHostController.openTab(route: String) {
    val current = currentDestination?.route
    navigate(route) {
        launchSingleTop = true
        restoreState = true
        if (current != null && current != NativeRoutes.HOME) {
            popUpTo(current) {
                inclusive = true
                saveState = true
            }
        }
    }
}

/**
 * A secao da barra de baixo: o Inicio fica embaixo de tudo, a secao entra por cima dele. Como nas
 * abas, a pagina que sai guarda o estado e a que volta o recupera.
 */
private fun NavHostController.openSection(section: ShellNav.Section) {
    if (section == ShellNav.Section.HOME) {
        // O Inicio que ja esta embaixo (sem refazer a pagina); sem ele na pilha, um novo.
        if (!popBackStack(NativeRoutes.HOME, inclusive = false, saveState = true)) navigate(NativeRoutes.HOME) { launchSingleTop = true }
        return
    }
    navigate(section.root) {
        launchSingleTop = true
        restoreState = true
        popUpTo(NativeRoutes.HOME) { saveState = true }
    }
}

private const val PAGE_FADE_MS = 120

/** Sem sessao: o login, e nada por baixo dele. */
private fun NavHostController.toLogin() {
    navigate(NativeRoutes.LOGIN) {
        launchSingleTop = true
        popUpTo(graph.id) { inclusive = true }
    }
}

@Composable
private fun AppShell(
    start: String,
    focusItem: String?,
    onFocusConsumed: () -> Unit,
    routeRequest: String?,
    onRouteConsumed: () -> Unit,
    viewRequest: String?,
    onViewConsumed: () -> Unit,
    onRouteShown: (String?) -> Unit,
    onMinimize: () -> Unit,
    onNewEntry: (String) -> Unit,
    onFixPending: (String) -> Unit,
) {
    val nav = rememberNavController()
    val shell: ShellViewModel = viewModel()
    val context = LocalContext.current
    val graph = AppGraph.from(context)
    val snackbar = remember { SnackbarHostState() }
    val lifecycleOwner = LocalLifecycleOwner.current
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    var expired by remember { mutableStateOf(false) }
    val desktopOnly = context.getString(R.string.shell_desktop_only)

    // Um link entre telas (um caminho da web): a pagina do NavHost, ou o aviso de que ela so
    // existe no computador (Importar, Regras de importação, Integrações).
    val openLink: (String) -> Unit = { link ->
        val target = NativeLinks.targetFor(link)
        if (target == null) {
            shell.notice(ShellNotice(desktopOnly, tone = "info", long = true))
        } else {
            if (target.view != null) {
                if (target.route == NativeRoutes.AJUSTES) AjustesPendingSection.value = target.view
                else ExtratoPendingView.value = target.view
            }
            if (target.route == NativeRoutes.HOME) nav.openSection(ShellNav.Section.HOME)
            else nav.navigate(target.route) { launchSingleTop = true }
        }
    }

    // As telas avisam a casca: gravou (rele a fila, mostra o aviso) ou pediu outra pagina.
    DisposableEffect(Unit) {
        val listener = object : ShellEvents.Listener {
            override fun dataChanged(notice: ShellEvents.Notice?) {
                shell.refresh()
                if (notice != null) shell.notice(ShellNotice(notice.message, notice.tone, notice.durationMs > 4000))
            }

            override fun navigate(route: String) = openLink(route)
        }
        ShellEvents.setListener(listener)
        onDispose { ShellEvents.clearListener(listener) }
    }

    // A fila, a rede e o APK novo de novo a cada volta para a frente.
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            shell.refresh()
            shell.checkApk()
        }
    }

    LaunchedEffect(Unit) {
        shell.notices.collect { notice ->
            snackbar.showSnackbar(notice.message, duration = if (notice.long) SnackbarDuration.Long else SnackbarDuration.Short)
        }
    }

    LaunchedEffect(nav) {
        nav.currentBackStackEntryFlow.collect { current -> onRouteShown(current.destination.route) }
    }

    // Um 401 (a sessao foi apagada pelo AppGraph): de volta ao login, com a fila guardada.
    val sessionExpired by graph.sessionExpired.collectAsState()
    LaunchedEffect(sessionExpired, route) {
        if (sessionExpired && route != null && route != NativeRoutes.LOGIN && graph.sessionUserId() == null) {
            expired = true
            nav.toLogin()
        }
    }

    // Uma intent pediu uma pagina (a notificacao de Aprovar): entra por cima do Inicio.
    LaunchedEffect(routeRequest, route) {
        val requested = routeRequest ?: return@LaunchedEffect
        if (route == null || route == NativeRoutes.LOGIN) return@LaunchedEffect
        if (route != requested) nav.navigate(requested) { launchSingleTop = true }
        onRouteConsumed()
    }

    // O voltar sem pagina por baixo: no Inicio (e no login) o app vai para o fundo; nas outras,
    // volta ao Inicio. O NavHost (com pagina por baixo) e os sheets vem antes.
    BackHandler(enabled = nav.previousBackStackEntry == null) {
        if (ShellNav.backGoesHome(route)) nav.openSection(ShellNav.Section.HOME) else onMinimize()
    }

    val back: () -> Unit = {
        if (nav.previousBackStackEntry != null) nav.popBackStack() else if (ShellNav.backGoesHome(route)) nav.openSection(ShellNav.Section.HOME)
    }
    val openTab: (LancamentosTab) -> Unit = { tab ->
        nav.openTab(
            when (tab) {
                LancamentosTab.EXTRATO -> NativeRoutes.EXTRATO
                LancamentosTab.CARTOES -> NativeRoutes.CARTOES
                LancamentosTab.APROVAR -> NativeRoutes.INBOX
                LancamentosTab.A_RECEBER -> NativeRoutes.A_RECEBER
            },
        )
    }
    val openPlanTab: (PlanejarTab) -> Unit = { tab ->
        nav.openTab(
            when (tab) {
                PlanejarTab.ORCAMENTO -> NativeRoutes.ORCAMENTO
                PlanejarTab.RECORRENTES -> NativeRoutes.RECORRENTES
                PlanejarTab.METAS -> NativeRoutes.METAS
            },
        )
    }
    val openInvestTab: (InvestimentosTab) -> Unit = { tab -> nav.openTab(InvestimentosRoutes.routeOf(tab)) }
    val signedIn: () -> Unit = {
        expired = false
        nav.navigate(NativeRoutes.HOME) {
            launchSingleTop = true
            popUpTo(NativeRoutes.LOGIN) { inclusive = true }
        }
        shell.refresh()
        shell.checkApk(force = true)
    }
    val signedOut: () -> Unit = {
        expired = false
        nav.toLogin()
        shell.refresh()
    }

    val chrome = ShellChrome(
        pendingCount = shell.rows.size,
        attention = shell.attention,
        offline = shell.offline,
        onOpenPending = shell::openPending,
    )
    val section = ShellNav.sectionOf(route)
    val palette = LocalPalette.current

    CompositionLocalProvider(LocalShellChrome provides chrome) {
        Column(Modifier.fillMaxSize()) {
            Box(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    // A barra de baixo ja cuida da barra do sistema: as paginas nao a somam de novo.
                    .then(if (section != null) Modifier.consumeWindowInsets(WindowInsets.navigationBars) else Modifier),
            ) {
                // Troca de pagina curta: o fade padrao (700 ms) fazia cada aba parecer recarregar.
                NavHost(
                    navController = nav,
                    startDestination = start,
                    enterTransition = { fadeIn(tween(PAGE_FADE_MS)) },
                    exitTransition = { fadeOut(tween(PAGE_FADE_MS)) },
                    popEnterTransition = { fadeIn(tween(PAGE_FADE_MS)) },
                    popExitTransition = { fadeOut(tween(PAGE_FADE_MS)) },
                ) {
                    composable(NativeRoutes.LOGIN) {
                        val login: LoginViewModel = viewModel()
                        LoginScreen(viewModel = login, expired = expired, onSignedIn = signedIn)
                    }
                    composable(NativeRoutes.HOME) {
                        val home: HomeViewModel = viewModel()
                        HomeScreen(
                            viewModel = home,
                            onOpenWeb = openLink,
                            onOpenInbox = { nav.openTab(NativeRoutes.INBOX) },
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
                        // Voltar (a seta e o do sistema) leva ao Extrato, nao ao que esta por baixo.
                        val toExtrato: () -> Unit = { nav.openTab(ShellNav.backTarget(NativeRoutes.INBOX) ?: NativeRoutes.EXTRATO) }
                        BackHandler(onBack = toExtrato)
                        InboxScreen(viewModel = inbox, onBack = toExtrato)
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
                        ExtratoScreen(viewModel = extrato, onBack = back, onTab = openTab, onOpenWeb = openLink, onNewEntry = { onNewEntry("EXPENSE") })
                    }
                    composable(NativeRoutes.CARTOES) {
                        val cartoes: CartoesViewModel = viewModel()
                        CartoesScreen(viewModel = cartoes, onBack = back, onTab = openTab, onOpenWeb = openLink, onNewPurchase = { onNewEntry("CARD") })
                    }
                    composable(NativeRoutes.A_RECEBER) {
                        val receivables: AReceberViewModel = viewModel()
                        AReceberScreen(viewModel = receivables, onBack = back, onTab = openTab)
                    }
                    composable(NativeRoutes.ORCAMENTO) {
                        val orcamento: OrcamentoViewModel = viewModel()
                        OrcamentoScreen(viewModel = orcamento, onBack = back, onTab = openPlanTab, onOpenLink = openLink)
                    }
                    composable(NativeRoutes.RECORRENTES) {
                        val recorrentes: RecorrentesViewModel = viewModel()
                        RecorrentesScreen(viewModel = recorrentes, onBack = back, onTab = openPlanTab)
                    }
                    composable(NativeRoutes.METAS) {
                        val metas: MetasViewModel = viewModel()
                        MetasScreen(viewModel = metas, onBack = back, onTab = openPlanTab)
                    }
                    composable(NativeRoutes.POSICAO) {
                        val posicao: PosicaoViewModel = viewModel()
                        PosicaoScreen(viewModel = posicao, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.OPERACOES) {
                        val operacoes: OperacoesViewModel = viewModel()
                        OperacoesScreen(viewModel = operacoes, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.PROVENTOS) {
                        val proventos: ProventosViewModel = viewModel()
                        ProventosScreen(viewModel = proventos, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.RENTABILIDADE) {
                        val rentabilidade: RentabilidadeViewModel = viewModel()
                        RentabilidadeScreen(viewModel = rentabilidade, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.ALOCACAO) {
                        val alocacao: AlocacaoViewModel = viewModel()
                        AlocacaoScreen(viewModel = alocacao, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.IR) {
                        val ir: IrViewModel = viewModel()
                        IrScreen(viewModel = ir, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.CALCULADORA) {
                        val calculadora: CalculadoraViewModel = viewModel()
                        CalculadoraScreen(viewModel = calculadora, onBack = back, onTab = openInvestTab)
                    }
                    composable(NativeRoutes.AJUSTES) {
                        val ajustes: AjustesViewModel = viewModel()
                        LaunchedEffect(viewRequest) {
                            val requested = viewRequest ?: AjustesPendingSection.value
                            if (requested != null) {
                                ajustes.openSection(requested)
                                AjustesPendingSection.value = null
                                onViewConsumed()
                            }
                        }
                        AjustesScreen(viewModel = ajustes, onBack = back, onOpenLink = openLink, onSignedOut = signedOut)
                    }
                }
                if (ShellNav.showsNewEntry(route)) {
                    NewEntryButton(
                        onClick = { onNewEntry(if (route == NativeRoutes.CARTOES) "CARD" else "EXPENSE") },
                        modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp),
                    )
                }
                SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 80.dp)) { data ->
                    Snackbar(containerColor = palette["zinc-900"], contentColor = palette["white"]) {
                        Text(data.visuals.message, color = palette["white"])
                    }
                }
            }
            if (section != null) {
                shell.apkPrompt?.let { prompt -> ApkBanner(prompt, shell.apkStatus, shell.apkBusy, shell::installApk) }
                ShellBottomBar(section) { selected ->
                    if (selected == section && selected.root == route) return@ShellBottomBar
                    nav.openSection(selected)
                }
            }
        }
        if (shell.pendingOpen) {
            PendingSheet(shell) { row ->
                shell.closePending()
                if (row.editable) onFixPending(row.clientId)
            }
        }
    }
}

/** A secao de Ajustes pedida por um link ("/ajustes#categorias"), lida ao abrir. */
internal object AjustesPendingSection {
    var value: String? = null
}

/** A vista do Extrato pedida por um link ("/lancamentos/extrato?ver=..."), lida ao abrir. */
internal object ExtratoPendingView {
    var value: String? = null
}
