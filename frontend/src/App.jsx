import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { getSession, onAuthStateChange } from './lib/auth'
import { legacyRedirects } from './lib/navigation'
import Auth from './pages/Auth'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Layout from './components/Layout'
import Investments from './pages/Investments'
import Proventos from './pages/Proventos'
import Orcamento from './pages/Orcamento'
import Recorrentes from './pages/Recorrentes'
import Ajustes from './pages/Ajustes'

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
            <Route path="/lancamentos/extrato" element={<Transactions tab="extrato" />} />
            <Route path="/lancamentos/cartoes" element={<Transactions tab="cartoes" />} />

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
