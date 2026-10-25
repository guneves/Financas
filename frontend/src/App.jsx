import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, useEffect, useState } from 'react'
import { getSession, onAuthStateChange } from './lib/auth'
import { clearServerData } from './lib/queries'
import { clearPersistedQueryCache } from './lib/queryPersist'
import { legacyRedirects } from './lib/navigation'
import Auth from './pages/Auth'
import Layout from './components/Layout'
import NativePage from './components/NativePage'
import {
  AJUSTES_SCREEN,
  ALOCACAO_SCREEN,
  A_RECEBER_SCREEN,
  CALCULADORA_SCREEN,
  CARTOES_SCREEN,
  EXTRATO_SCREEN,
  HOME_SCREEN,
  INBOX_SCREEN,
  IR_SCREEN,
  METAS_SCREEN,
  OPERACOES_SCREEN,
  ORCAMENTO_SCREEN,
  POSICAO_SCREEN,
  PROVENTOS_SCREEN,
  RECORRENTES_SCREEN,
  RENTABILIDADE_SCREEN,
} from './lib/nativeScreensRules'

// Cada tela e um chunk proprio (o bundle unico passava de 700 kB); o Layout
// mostra o carregamento dentro da area da pagina, com a navegacao ja montada.
const PAGE_LOADERS = {
  Dashboard: () => import('./pages/Dashboard'),
  Extrato: () => import('./pages/lancamentos/Extrato'),
  Aprovar: () => import('./pages/lancamentos/Aprovar'),
  Cartoes: () => import('./pages/lancamentos/Cartoes'),
  AReceber: () => import('./pages/lancamentos/AReceber'),
  Importar: () => import('./pages/lancamentos/Importar'),
  Investments: () => import('./pages/Investments'),
  Proventos: () => import('./pages/Proventos'),
  ImpostoRenda: () => import('./pages/investimentos/ImpostoRenda'),
  Orcamento: () => import('./pages/Orcamento'),
  Recorrentes: () => import('./pages/Recorrentes'),
  Metas: () => import('./pages/Metas'),
  Alocacao: () => import('./pages/investimentos/Alocacao'),
  Rentabilidade: () => import('./pages/investimentos/Rentabilidade'),
  Calculadora: () => import('./pages/investimentos/Calculadora'),
  Ajustes: () => import('./pages/Ajustes'),
}

const Dashboard = lazy(PAGE_LOADERS.Dashboard)
const Extrato = lazy(PAGE_LOADERS.Extrato)
const Aprovar = lazy(PAGE_LOADERS.Aprovar)
const Cartoes = lazy(PAGE_LOADERS.Cartoes)
const AReceber = lazy(PAGE_LOADERS.AReceber)
const Importar = lazy(PAGE_LOADERS.Importar)
const Investments = lazy(PAGE_LOADERS.Investments)
const Proventos = lazy(PAGE_LOADERS.Proventos)
const ImpostoRenda = lazy(PAGE_LOADERS.ImpostoRenda)
const Orcamento = lazy(PAGE_LOADERS.Orcamento)
const Recorrentes = lazy(PAGE_LOADERS.Recorrentes)
const Metas = lazy(PAGE_LOADERS.Metas)
const Alocacao = lazy(PAGE_LOADERS.Alocacao)
const Rentabilidade = lazy(PAGE_LOADERS.Rentabilidade)
const Calculadora = lazy(PAGE_LOADERS.Calculadora)
const Ajustes = lazy(PAGE_LOADERS.Ajustes)

// Depois que a primeira tela abriu, baixa o codigo das outras em segundo plano:
// a primeira visita a uma tela deixa de esperar pelo chunk. No APK os chunks
// sao arquivos locais, entao isto custa so o parse. Um que falhe e baixado de
// novo pelo lazy() quando a tela abrir.
const PRELOAD_DELAY_MS = 1500
function preloadPages() {
  Object.values(PAGE_LOADERS).forEach((load) => load().catch(() => {}))
}

// Navegar dentro de uma transicao do React: enquanto o codigo da proxima tela
// carrega, a tela atual continua na frente em vez de virar esqueleto.
const ROUTER_FUTURE = { v7_startTransition: true }

export default function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!session) return undefined
    const timer = setTimeout(preloadPages, PRELOAD_DELAY_MS)
    return () => clearTimeout(timer)
  }, [session])

  useEffect(() => {
    setSession(getSession())
    setLoading(false)

    // Outra sessao (ou nenhuma): o cache do usuario anterior nao pode aparecer.
    const unsubscribe = onAuthStateChange((session) => {
      clearServerData()
      clearPersistedQueryCache()
      setSession(session)
    })

    return unsubscribe
  }, [])

  if (loading) return <div className="flex h-screen items-center justify-center text-zinc-500">Carregando...</div>

  return (
    <Router future={ROUTER_FUTURE}>
      <Routes>
        <Route path="/" element={!session ? <Auth /> : <Navigate to="/inicio" replace />} />

        {session && (
          <Route element={<Layout />}>
            {/* No APK com o Inicio nativo (native-level 5), a rota abre a tela em
                Kotlin e a WebView espera parada aqui; /inicio?web=1 e a React. */}
            <Route path="/inicio" element={<NativePage screen={HOME_SCREEN} stay><Dashboard /></NativePage>} />

            <Route path="/lancamentos" element={<Navigate to="/lancamentos/extrato" replace />} />
            {/* No APK com Extrato e Cartoes nativos (native-level 6), as rotas abrem as
                telas em Kotlin; ?web=1 fica na React. */}
            <Route path="/lancamentos/extrato" element={<NativePage screen={EXTRATO_SCREEN}><Extrato /></NativePage>} />
            {/* No APK com Aprovar nativo (native-level 4), a rota abre a tela em Kotlin. */}
            <Route path="/lancamentos/aprovar" element={<NativePage screen={INBOX_SCREEN}><Aprovar /></NativePage>} />
            <Route path="/lancamentos/cartoes" element={<NativePage screen={CARTOES_SCREEN}><Cartoes /></NativePage>} />
            <Route path="/lancamentos/a-receber" element={<NativePage screen={A_RECEBER_SCREEN}><AReceber /></NativePage>} />
            <Route path="/lancamentos/importar" element={<Importar />} />

            <Route path="/planejamento" element={<Navigate to="/planejamento/orcamento" replace />} />
            <Route path="/planejamento/orcamento" element={<NativePage screen={ORCAMENTO_SCREEN}><Orcamento /></NativePage>} />
            <Route path="/planejamento/recorrentes" element={<NativePage screen={RECORRENTES_SCREEN}><Recorrentes /></NativePage>} />
            <Route path="/planejamento/metas" element={<NativePage screen={METAS_SCREEN}><Metas /></NativePage>} />

            <Route path="/investimentos" element={<Navigate to="/investimentos/posicao" replace />} />
            {/* No APK com Investimentos nativo (native-level 8), cada aba que ele
                lista abre a tela em Kotlin; as outras (e ?web=1) ficam na React. */}
            <Route path="/investimentos/posicao" element={<NativePage screen={POSICAO_SCREEN}><Investments tab="posicao" /></NativePage>} />
            <Route path="/investimentos/rentabilidade" element={<NativePage screen={RENTABILIDADE_SCREEN}><Rentabilidade /></NativePage>} />
            <Route path="/investimentos/operacoes" element={<NativePage screen={OPERACOES_SCREEN}><Investments tab="operacoes" /></NativePage>} />
            <Route path="/investimentos/alocacao" element={<NativePage screen={ALOCACAO_SCREEN}><Alocacao /></NativePage>} />
            <Route path="/investimentos/proventos" element={<NativePage screen={PROVENTOS_SCREEN}><Proventos /></NativePage>} />
            <Route path="/investimentos/ir" element={<NativePage screen={IR_SCREEN}><ImpostoRenda /></NativePage>} />
            <Route path="/investimentos/calculadora" element={<NativePage screen={CALCULADORA_SCREEN}><Calculadora /></NativePage>} />

            <Route path="/ajustes" element={<NativePage screen={AJUSTES_SCREEN}><Ajustes /></NativePage>} />

            {Object.entries(legacyRedirects).map(([from, to]) => (
              <Route key={from} path={from} element={<Navigate to={to} replace />} />
            ))}
          </Route>
        )}

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  )
}
