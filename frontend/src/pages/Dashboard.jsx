import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabaseClient'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { TrendingUp, Landmark, Wallet, PiggyBank } from 'lucide-react'

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [bankBalance, setBankBalance] = useState(0)
  
  useEffect(() => {
    fetchAllData()
  }, [])

  const fetchAllData = async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return

    // 1. Busca os Investimentos do Flask
    try {
      const response = await fetch('http://localhost:5000/api/investments/portfolio', {
        headers: { 'Authorization': `Bearer ${session.access_token}` }
      })
      const data = await response.json()
      setPortfolio(data)
    } catch (error) {
      console.error("Erro ao buscar portfólio:", error)
    }

    // 2. Busca as transações diretamente do Supabase para calcular o saldo em conta
    const { data: transData } = await supabase.from('transactions').select('amount, type')
    if (transData) {
      const calcBalance = transData.reduce((acc, curr) => {
        return curr.type === 'INCOME' ? acc + parseFloat(curr.amount) : acc - parseFloat(curr.amount)
      }, 0)
      setBankBalance(calcBalance)
    }
  }

  if (!portfolio) return <div className="text-slate-500 animate-pulse p-8">Calculando patrimônio...</div>

  const totalWealth = bankBalance + portfolio.current_balance;

  const chartData = Object.keys(portfolio.distribution || {}).map(key => ({
    name: key,
    value: portfolio.distribution[key]
  }))
  const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div>
        <h1 className="text-3xl font-bold text-slate-800">Visão Geral</h1>
        <p className="text-slate-500 mt-1">Seu patrimônio consolidado e distribuição de ativos.</p>
      </div>
      
      {/* Cards de Patrimônio Consolidado */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        
        {/* Novo Card: Patrimônio Total (Conta + Investimentos) */}
        <div className="bg-slate-900 p-6 rounded-2xl shadow-lg border border-slate-800 flex items-center gap-4 md:col-span-2">
          <div className="bg-blue-500 p-4 rounded-xl text-white"><Landmark size={28} /></div>
          <div>
            <h3 className="text-sm font-medium text-slate-300">Patrimônio Total</h3>
            <p className="text-3xl font-bold text-white">R$ {totalWealth.toFixed(2)}</p>
          </div>
        </div>

        {/* Card: Saldo em Conta Corrente */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-slate-100 p-4 rounded-xl text-slate-600"><Wallet /></div>
          <div>
            <h3 className="text-sm font-medium text-slate-500">Saldo em Conta</h3>
            <p className={`text-2xl font-bold ${bankBalance >= 0 ? 'text-slate-900' : 'text-red-500'}`}>
              R$ {bankBalance.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Card: Total Investido (Cotação Atual) */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 flex items-center gap-4">
          <div className="bg-blue-50 p-4 rounded-xl text-blue-600"><PiggyBank /></div>
          <div>
            <h3 className="text-sm font-medium text-slate-500">Investimentos</h3>
            <p className="text-2xl font-bold text-blue-600">R$ {portfolio.current_balance}</p>
          </div>
        </div>

      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-lg font-bold text-slate-800">Distribuição da Carteira</h2>
            <span className={`px-3 py-1 rounded-full text-sm font-bold ${portfolio.portfolio_profitability >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
              Rentabilidade: {portfolio.portfolio_profitability > 0 ? '+' : ''}{portfolio.portfolio_profitability}%
            </span>
          </div>
          
          {chartData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={chartData} innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => `${value}%`} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
             <div className="h-64 flex items-center justify-center text-slate-400">Nenhum ativo cadastrado.</div>
          )}
        </div>
      </div>
    </div>
  )
}