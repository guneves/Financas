import { useState } from 'react'
import { supabase } from '../lib/supabaseClient'

export default function Auth() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [isLogin, setIsLogin] = useState(true) // Estado para alternar entre Login e Cadastro

  const handleAuth = async (e) => {
    e.preventDefault()
    setLoading(true)

    if (isLogin) {
      // Lógica de Login
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) alert("Erro ao entrar: " + error.message)
    } else {
      // Lógica de Cadastro
      const { error } = await supabase.auth.signUp({ email, password })
      if (error) {
        alert("Erro ao cadastrar: " + error.message)
      } else {
        // Como desativamos a confirmação de email no Supabase
        // o signUp já faz o login automático e o App.jsx vai te redirecionar pro Dashboard
        console.log("Cadastro realizado com sucesso!")
      }
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50">
      <div className="p-8 bg-white rounded-xl shadow-md w-96 border border-slate-200">
        <h2 className="text-2xl font-bold mb-6 text-center text-slate-800">
          {isLogin ? 'Acesso ao Sistema' : 'Criar Conta'}
        </h2>
        
        <form onSubmit={handleAuth} className="space-y-4">
          <input
            type="email"
            placeholder="Seu email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
          <input
            type="password"
            placeholder="Sua senha (mín. 6 caracteres)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            minLength={6}
          />
          <button 
            type="submit" 
            disabled={loading}
            className="w-full bg-blue-600 text-white font-medium py-2 rounded-md hover:bg-blue-700 transition"
          >
            {loading ? 'Carregando...' : (isLogin ? 'Entrar' : 'Cadastrar')}
          </button>
        </form>

        <div className="mt-6 text-center">
          <button 
            type="button"
            onClick={() => setIsLogin(!isLogin)} 
            className="text-sm text-slate-600 hover:text-blue-600 hover:underline transition"
          >
            {isLogin ? 'Não tem uma conta? Cadastre-se' : 'Já tem uma conta? Entre aqui'}
          </button>
        </div>

      </div>
    </div>
  )
}