import { useState } from 'react'
import { ArrowRight, LockKeyhole, Mail, ShieldCheck, UserPlus, Wallet } from 'lucide-react'
import { signIn, signUp } from '../lib/auth'
import { Button, SegmentedControl } from '../components/ui'

export default function Auth() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [isLogin, setIsLogin] = useState(true)
  const [error, setError] = useState('')

  const handleAuth = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')

    try {
      if (isLogin) {
        await signIn(email, password)
      } else {
        await signUp(email, password)
      }
    } catch (authError) {
      setError(authError.message || 'Não foi possível autenticar agora.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 px-4 py-8 text-zinc-950">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl items-center justify-center">
        <div className="grid w-full overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm lg:grid-cols-[0.95fr_1.05fr]">
          <div className="hidden border-r border-zinc-200 bg-zinc-950 p-8 text-white lg:flex lg:flex-col lg:justify-between">
            <div>
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-zinc-950">
                <Wallet className="h-6 w-6" />
              </div>
              <h1 className="mt-6 text-3xl font-bold">FinanceMVP</h1>
              <p className="mt-3 max-w-sm text-sm leading-6 text-zinc-300">
                Controle operacional para contas, cartões, carteira e investimentos.
              </p>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/5 p-3">
                <ShieldCheck className="h-5 w-5 text-emerald-300" />
                <span className="text-sm text-zinc-200">Acesso protegido por sessão local e token da API.</span>
              </div>
              <p className="text-xs text-zinc-500">Conectado ao backend configurado no ambiente do frontend.</p>
            </div>
          </div>

          <div className="p-6 sm:p-8 lg:p-10">
            <div className="mb-8 flex items-center gap-3 lg:hidden">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-zinc-950 text-white">
                <Wallet className="h-5 w-5" />
              </div>
              <div>
                <p className="font-bold text-zinc-950">FinanceMVP</p>
                <p className="text-xs text-zinc-500">Painel financeiro</p>
              </div>
            </div>

            <SegmentedControl
              value={isLogin ? 'login' : 'signup'}
              onChange={(value) => {
                setIsLogin(value === 'login')
                setError('')
              }}
              items={[
                { value: 'login', label: 'Entrar', icon: ArrowRight },
                { value: 'signup', label: 'Cadastrar', icon: UserPlus },
              ]}
            />

            <div className="mt-8">
              <h2 className="text-2xl font-bold text-zinc-950">
                {isLogin ? 'Acesse sua conta' : 'Crie seu acesso'}
              </h2>
              <p className="mt-2 text-sm text-zinc-500">
                {isLogin ? 'Informe suas credenciais para continuar.' : 'Use um e-mail válido e uma senha com pelo menos 6 caracteres.'}
              </p>
            </div>

            {error ? (
              <div className="mt-5 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {error}
              </div>
            ) : null}

            <form onSubmit={handleAuth} className="mt-6 space-y-4">
              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-zinc-700">E-mail</span>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <input
                    type="email"
                    placeholder="voce@email.com"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    className="app-input pl-10"
                    required
                  />
                </div>
              </label>

              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-zinc-700">Senha</span>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                  <input
                    type="password"
                    placeholder="Mínimo de 6 caracteres"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="app-input pl-10"
                    required
                    minLength={6}
                  />
                </div>
              </label>

              <Button
                type="submit"
                className="w-full"
                icon={isLogin ? ArrowRight : UserPlus}
                loading={loading}
              >
                {isLogin ? 'Entrar' : 'Cadastrar'}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
