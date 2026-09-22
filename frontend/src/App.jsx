import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { lazy, useEffect, useState } from 'react'
import { getSession, onAuthStateChange } from './lib/auth'
import { legacyRedirects } from './lib/navigation'
import Auth from './pages/Auth'
import Layout from './components/Layout'

// Cada tela e um chunk proprio (o bundle unico passava de 700 kB); o Layout
// mostra o carregamento dentro da area da pagina, com a navegacao ja montada.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Extrato = lazy(() => import('./pages/lancamentos/Extrato'))
const Cartoes = lazy(() => import('./pages/lancamentos/Cartoes'))
const Investments = lazy(() => import('./pages/Investments'))
const Proventos = lazy(() => import('./pages/Proventos'))
const Orcamento = lazy(() => import('./pages/Orcamento'))
const Recorrentes = lazy(() => import('./pages/Recorrentes'))
const Ajustes = lazy(() => import('./pages/Ajustes'))

export default function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setSession(getSession())
    setLoading(false)

    const unsubscribe = onAuthStateChange((session) => {
      setSession(session)
    })

    return unsubscribe
  }, [])

  if (loading) return <div className="flex h-screen items-center justify-center text-zinc-500">Carregando...</div>

  return (
    <Router>
      <Routes>
        <Route path="/" element={!session ? <Auth /> : <Navigate to="/inicio" replace />} />

        {session && (
          <Route element={<Layout />}>
            <Route path="/inicio" element={<Dashboard />} />

            <Route path="/lancamentos" element={<Navigate to="/lancamentos/extrato" replace />} />
            <Route path="/lancamentos/extrato" element={<Extrato />} />
            <Route path="/lancamentos/cartoes" element={<Cartoes />} />

            <Route path="/planejamento" element={<Navigate to="/planejamento/orcamento" replace />} />
            <Route path="/planejamento/orcamento" element={<Orcamento />} />
            <Route path="/planejamento/recorrentes" element={<Recorrentes />} />

            <Route path="/investimentos" element={<Navigate to="/investimentos/posicao" replace />} />
            <Route path="/investimentos/posicao" element={<Investments tab="posicao" />} />
            <Route path="/investimentos/operacoes" element={<Investments tab="operacoes" />} />
            <Route path="/investimentos/proventos" element={<Proventos />} />

            <Route path="/ajustes" element={<Ajustes />} />

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
